"""Reproduce every number and figure.

    python3 run_experiments.py            # full run
    python3 run_experiments.py --quick    # smaller sweep, for iteration

Stdlib only.  Writes results/ and figures/.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from svgplot import Theme, grouped_bars, line_chart, write_pair
from topology.graphs import (GROUP_CHIPS, GROUP_OPTICAL_PORTS, POD_CHIPS,
                             POD_GROUPS, boardfly_group_level,
                             boardfly_pod_chip_level, chip_hops, imase_itoh,
                             kautz, kautz_capacity, log_diameter,
                             min_diameter_for, moore_bound,
                             shiftfly_group_level, torus)
from topology.metrics import (bfs, bfs_tree, distance_stats, merge_step,
                              multicast, shift_path, spectral_gap)
from topology.workload import (SharingModel, cluster_placement_labelling,
                               draw_requests, locality_labelling,
                               random_labelling)

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "figures"
RES = ROOT / "results"
QUICK = "--quick" in sys.argv

PORTS = GROUP_OPTICAL_PORTS          # 40 optical ports per group
D_OUT = PORTS // 2                   # Kautz out-degree at equal port cost


def md_table(header, rows) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# 1. the Moore audit
# --------------------------------------------------------------------------

#: (label, chips, degree, diameter, source of the diameter)
TPU_GENERATIONS = [
    ("v2 (2D torus 16x16)", 256, 4, 16, "analytic"),
    ("v3 (2D torus 32x32)", 1024, 4, 32, "analytic"),
    ("v4 (3D torus 16^3)", 4096, 6, 24, "analytic"),
    ("v5e (2D torus 16x16)", 256, 4, 16, "analytic"),
    ("v5p (3D torus 16x20x28)", 8960, 6, 32, "analytic, shape inferred"),
    ("v6e (2D torus 16x16)", 256, 4, 16, "analytic"),
    ("v7 Ironwood (3D torus)", 9216, 6, 32, "analytic, shape inferred"),
    ("v8t (3D torus)", 9600, 6, 33, "analytic, shape inferred"),
    ("v8i Boardfly", 1152, 7, 7, "published; reproduced here"),
]


def experiment_moore() -> str:
    rows = []
    for label, n, delta, diam, note in TPU_GENERATIONS:
        bound = moore_bound(delta, diam)
        best = min_diameter_for(delta, n)
        rows.append([label, f"{n:,}", delta, diam, f"{bound:,}",
                     f"{bound / n:,.0f}x", best, note])
    body = ["## 1. Moore-bound audit\n",
            "How far each shipped topology sits from the largest graph its own "
            "degree and diameter would permit. The bound is a ceiling that only "
            "a handful of graphs attain, so no design reaches it -- but the "
            "*ratio* says how much structure is being left unused.\n\n"]
    body.append(md_table(
        ["Generation", "Chips", "Degree", "Diameter", "Moore bound",
         "Bound / actual", "Min feasible D", "Diameter source"], rows))

    bf = boardfly_pod_chip_level()
    st = distance_stats(bf, max_exact=2000)
    body.append(
        f"\nThe chip-level Boardfly model built here has n={bf.n:,}, "
        f"max degree {bf.max_degree}, mean degree {bf.mean_degree:.2f}, and "
        f"**measured diameter {st.diameter}** against Google's published 7 -- "
        f"which is the check that the port-assignment model is faithful. "
        f"Mean distance is {st.mean:.3f}.\n")
    return "".join(body)


# --------------------------------------------------------------------------
# 2. equal-cost scaling
# --------------------------------------------------------------------------

def experiment_scale() -> tuple[str, dict]:
    sizes = ([POD_GROUPS, 144, 576, 2304] if QUICK
             else [POD_GROUPS, 144, 576, 2304, 8400, 12500, 36000])
    rows, data = [], {"sizes": sizes, "bf": [], "sf": [], "bfm": [], "sfm": [],
                      "bfg": [], "sfg": []}
    for n in sizes:
        bf = boardfly_group_level(n)
        sf = shiftfly_group_level(n, PORTS)
        sbf = distance_stats(bf, max_exact=3000, samples=120)
        ssf = distance_stats(sf, max_exact=3000, samples=120)
        gap_iters = 60 if n > 10000 else 120
        gbf = spectral_gap(bf, iters=gap_iters)
        gsf = spectral_gap(sf, iters=gap_iters)
        data["bf"].append(sbf.diameter); data["sf"].append(ssf.diameter)
        data["bfm"].append(chip_hops(sbf.mean)); data["sfm"].append(chip_hops(ssf.mean))
        data["bfg"].append(gbf); data["sfg"].append(gsf)
        rows.append([f"{n:,}", f"{n*GROUP_CHIPS:,}",
                     sbf.diameter, ssf.diameter,
                     f"{chip_hops(sbf.diameter)}", f"{chip_hops(ssf.diameter)}",
                     f"{chip_hops(sbf.mean):.2f}", f"{chip_hops(ssf.mean):.2f}",
                     f"{gbf:.3f}", f"{gsf:.3f}"])

    body = ["\n## 2. Equal-cost comparison\n",
            f"Both designs get **{PORTS} optical ports per group** and the same "
            f"32-chip group internals. Shiftfly therefore runs at Kautz "
            f"out-degree {D_OUT}, not {PORTS}: in- and out-neighbourhoods are "
            f"disjoint, so out-degree d costs 2d bidirectional ports. Getting "
            f"that wrong hands Shiftfly twice the hardware.\n\n",
            "Chip-level distance is `3(g+1) + g` for g group hops -- the same "
            "arithmetic that makes Boardfly's published intra-pod diameter "
            "7 = 3 + 1 + 3.\n\n"]
    body.append(md_table(
        ["Groups", "Chips", "BF group D", "SF group D", "BF chip D",
         "SF chip D", "BF chip mean", "SF chip mean", "BF gap", "SF gap"], rows))
    return "".join(body), data


# --------------------------------------------------------------------------
# 3. sharing / redundancy -- the part that can fail
# --------------------------------------------------------------------------

def _evaluate(g, lab, reqs, n_logical, use_shift):
    uni = tre = 0
    merges, mn = 0.0, 0
    trees: dict[int, tuple[list[int], list[int]]] = {}
    for item, logical in reqs:
        home = lab(item * 2654435761 % n_logical)
        req = [lab(x) for x in logical]
        r = multicast(g, home, req)
        uni += r.unicast_cost
        tre += r.tree_cost
        if len(req) >= 2:
            a, b = req[0], req[1]
            if use_shift and g.labels is not None:
                pa, pb = shift_path(g, a, home), shift_path(g, b, home)
            else:
                if home not in trees:
                    trees[home] = bfs_tree(g.adj, home)
                _, parent = trees[home]

                def up(x: int) -> list[int]:
                    o = [x]
                    while o[-1] != home and parent[o[-1]] >= 0:
                        o.append(parent[o[-1]])
                    return o
                pa, pb = up(a), up(b)
            k = merge_step(pa, pb)
            if k >= 0:
                merges += k
                mn += 1
    nreq = sum(len(r) for _, r in reqs) or 1
    return {"uni": uni / nreq, "tree": tre / nreq,
            "eff": uni / tre if tre else 1.0,
            "merge": merges / mn if mn else 0.0}


def experiment_sharing() -> tuple[str, dict]:
    n_logical = 8400
    model = SharingModel(clusters=64, agents=32, locality=0.85, zipf=1.0)
    reqs = draw_requests(model, n_logical, trials=80 if QUICK else 250)

    sf = kautz(D_OUT, 3, name=f"Shiftfly K({D_OUT},3)")   # exactly 8,400
    bf = boardfly_group_level(n_logical)

    runs = [
        ("Boardfly", "random", bf, random_labelling(bf, n_logical), False),
        ("Boardfly", "locality", bf,
         cluster_placement_labelling(bf, n_logical, model.clusters), False),
        ("Shiftfly", "random", sf, random_labelling(sf, n_logical), True),
        ("Shiftfly", "locality", sf,
         locality_labelling(sf, n_logical, model.clusters), True),
    ]
    rows, res = [], {}
    for topo, lab_kind, g, lab, shift in runs:
        r = _evaluate(g, lab, reqs, n_logical, shift)
        res[(topo, lab_kind)] = r
        rows.append([topo, lab.name, f"{r['uni']:.3f}", f"{r['tree']:.3f}",
                     f"{r['eff']:.3f}", f"{r['merge']:.3f}"])

    body = ["\n## 3. Redundancy and sharing\n",
            f"Workload: {model.agents} agents per query, {model.clusters} "
            f"affinity clusters, scheduler locality {model.locality:.0%}, Zipf "
            f"exponent {model.zipf}. Both topologies carry {n_logical:,} groups "
            f"at {PORTS} ports.\n\n",
            "`unicast/req` is hops charged if every agent fetches "
            "independently; `tree/req` is what a fabric with in-network "
            "replication pays. **`tree/req` is the number that matters** -- the "
            "efficiency *ratio* rewards a topology for being far apart, so it "
            "flatters the worse network and should not be read alone.\n\n"]
    body.append(md_table(
        ["Topology", "Labelling", "unicast/req", "tree/req", "ratio",
         "merge depth"], rows))

    b_r, b_l = res[("Boardfly", "random")], res[("Boardfly", "locality")]
    s_r, s_l = res[("Shiftfly", "random")], res[("Shiftfly", "locality")]
    body.append(
        f"\n**Reading it honestly.** Locality-aware placement cuts tree cost by "
        f"{1 - b_l['tree']/b_r['tree']:.0%} on Boardfly and "
        f"{1 - s_l['tree']/s_r['tree']:.0%} on Shiftfly -- so most of the "
        f"redundancy win is *placement*, which any topology can do, not "
        f"algebra. Shiftfly's own contribution is the residual: "
        f"{1 - s_l['tree']/b_l['tree']:.1%} lower tree cost than Boardfly at "
        f"matched placement, and merge depth {s_l['merge']:.2f} against "
        f"{b_l['merge']:.2f}. Note also that the efficiency *ratio* ranks "
        f"Boardfly higher ({b_l['eff']:.3f} vs {s_l['eff']:.3f}) while absolute "
        f"cost ranks it lower -- which is exactly the trap that metric sets.\n")
    return "".join(body), res


# --------------------------------------------------------------------------
# 3b. deployment and operations
# --------------------------------------------------------------------------

def experiment_operations() -> str:
    from topology.operations import (boardfly_slice_diameter, slice_quality,
                                     swap_cost, wiring_state_bits)
    n_groups = 12500
    bf = boardfly_group_level(n_groups)
    sf = shiftfly_group_level(n_groups, PORTS)

    body = ["\n## 3b. Deployment and operations\n",
            "A topology that is better on paper and worse to run is not "
            "better. Four operational questions, measured on a 12,500-group "
            "(400,000-chip) machine.\n",
            "\n### Replacing a failed group\n\n"]
    from topology.operations import mean_swap_cost
    rows = []
    for g in (bf, sf):
        s = swap_cost(g, 17)
        rows.append([g.meta["family"], s.circuits,
                     f"{mean_swap_cost(g):.1f}", s.peers, s.recompute])
    body.append(md_table(
        ["Design", "Circuits (typical)", "Circuits (mean)", "Peers disturbed",
         "Control-plane work"], rows))
    body.append(
        "\n**The same.** In both designs the replacement inherits the identity "
        "of the unit it replaces and the OCS re-points that identity's fibres, "
        "so the cost is simply the degree, and the same 40-port budget binds "
        "both. Neither is exactly regular -- Shiftfly loses a port on the thin "
        "set of vertices carrying a bidirectional pair, Boardfly wherever an "
        "inter-pod stub failed to pair -- but the means agree to within a few "
        "percent. The difference is that Shiftfly need not *look anything up*: "
        "the neighbour set of a label is a shift of it.\n")

    body.append("\n### Control-plane state for the global wiring\n\n")
    rows = [[g.meta["family"], f"{wiring_state_bits(g, n_groups):,} bits"]
            for g in (bf, sf)]
    body.append(md_table(["Design", "State"], rows))
    body.append(
        "\nBoardfly's intra-pod tier is derivable (a complete graph needs only "
        "pod membership), but its inter-pod tier has no closed form and must be "
        "tabulated. Shiftfly's entire global tier follows from two integers. "
        "Boardfly could of course adopt a *structured* inter-pod tier instead "
        "-- which is essentially the proposal of this paper.\n")

    body.append(
        "\n### Slice allocation\n\n"
        "Group-level diameter of a slice, by size. `SF naive` takes an "
        "arbitrary subset of the deployed fabric and uses whichever links fall "
        "inside it; `SF re-instantiated` installs a correctly sized shift "
        "permutation over exactly those groups, which is available because the "
        "global tier is a permutation on an OCS and Imase--Itoh exists at "
        "every order.\n\n")
    rows = []
    for m in (16, 36, 128, 512, 2048):
        q = slice_quality(n_groups, m, PORTS)
        naive = "disconnected" if not q.naive_connected else str(q.naive_diameter)
        rows.append([f"{m:,}", f"{m*GROUP_CHIPS:,}",
                     boardfly_slice_diameter(m), naive,
                     q.reinstantiated_diameter, q.guaranteed])
    body.append(md_table(
        ["Slice (groups)", "Chips", "Boardfly", "SF naive",
         "SF re-instantiated", "SF guarantee"], rows))
    body.append(
        "\n**This is the one place Shiftfly is operationally worse, and the "
        "table says so.** An arbitrary induced subset of a shift graph is "
        "disconnected at every size tested -- slices cannot simply be carved "
        "out. They must be *instantiated*, which costs one OCS reconfiguration "
        "per allocation. Within a single pod Boardfly needs none, because any "
        "subset of a complete tier is already complete. Beyond one pod both "
        "designs must establish circuits anyway.\n\n"
        "The trade is acceptable only because it matches how the machine is "
        "already operated: OCS reconfiguration takes milliseconds to seconds "
        "and happens at job-scheduling time, against job lifetimes of "
        "30 minutes to days. Given that, Shiftfly slices are *better* from 128 "
        "groups upward, and every slice is a correctly sized fabric in its own "
        "right rather than a fragment of a larger one.\n")
    return "".join(body)


# --------------------------------------------------------------------------
# 4. fault tolerance
# --------------------------------------------------------------------------

def experiment_faults() -> tuple[str, dict]:
    n = 2304
    rates = [0.0, 0.02, 0.05, 0.10, 0.20]
    rows = []
    data = {"rates": rates, "bf": [], "sf": []}
    for name, g in (("Boardfly", boardfly_group_level(n)),
                    ("Shiftfly", shiftfly_group_level(n, PORTS))):
        col = []
        for rate in rates:
            rng = random.Random(101)
            adj = [[v for v in nbrs if rng.random() >= rate]
                   for nbrs in g.adj]
            # keep the graph symmetric after independent link drops
            keep = {(min(u, v), max(u, v))
                    for u, nb in enumerate(adj) for v in nb}
            adj = [[] for _ in range(g.n)]
            for a, b in keep:
                adj[a].append(b)
                adj[b].append(a)
            reach, tot, worst = 0, 0, 0
            for s in [rng.randrange(g.n) for _ in range(60)]:
                dist = bfs(adj, s)
                for d in dist:
                    if d >= 0:
                        reach += 1
                        tot += d
                        worst = max(worst, d)
            frac = reach / (60 * g.n)
            col.append((frac, tot / max(1, reach), worst))
        data[name.lower()[:2] if name == "Boardfly" else "sf"] = col
        for rate, (frac, mean, worst) in zip(rates, col):
            rows.append([name, f"{rate:.0%}", f"{frac:.4f}", f"{mean:.3f}", worst])
    data["bf"] = data.get("bo", data.get("bf", []))

    body = ["\n## 4. Link failures\n",
            f"Independent link drops on a {n:,}-group instance; reachability "
            f"and distance measured from 60 random sources.\n\n"]
    body.append(md_table(
        ["Topology", "Link failure rate", "Reachable fraction",
         "Mean distance", "Eccentricity"], rows))
    body.append(
        "\nKautz digraphs have vertex connectivity exactly `d`, which is the "
        "maximum possible for their degree, so the thin global tier degrades "
        "gracefully. Boardfly's intra-pod cliques are highly redundant but its "
        "inter-pod links are few, so damage concentrates at pod boundaries.\n")
    return "".join(body), data


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------

def figures(scale: dict, sharing: dict) -> None:
    FIG.mkdir(exist_ok=True)
    chips = [s * GROUP_CHIPS for s in scale["sizes"]]

    write_pair(str(FIG / "diameter_vs_scale"), lambda t: line_chart(
        t, "Chip-level diameter at equal optical cost",
        f"Both designs: {PORTS} optical ports per group, 32-chip groups. "
        f"Lower is better.",
        chips,
        [("Boardfly-of-pods", [chip_hops(d) for d in scale["bf"]]),
         ("Shiftfly", [chip_hops(d) for d in scale["sf"]])],
        "chips in the system (log scale)", "worst-case chip hops", fmt="{:.0f}"))

    write_pair(str(FIG / "mean_distance"), lambda t: line_chart(
        t, "Mean chip-level distance",
        "Average hops between a random pair of chips. Lower is better.",
        chips,
        [("Boardfly-of-pods", scale["bfm"]), ("Shiftfly", scale["sfm"])],
        "chips in the system (log scale)", "mean chip hops", fmt="{:.1f}"))

    write_pair(str(FIG / "spectral_gap"), lambda t: line_chart(
        t, "Expansion: spectral gap of the group graph",
        "Higher is better. A hierarchy of near-cliques expands poorly; a "
        "flat shift graph does not.",
        chips,
        [("Boardfly-of-pods", scale["bfg"]), ("Shiftfly", scale["sfg"])],
        "chips in the system (log scale)", "1 - lambda_2", fmt="{:.2f}"))

    # bare variants for the paper, whose LaTeX captions carry the titles
    write_pair(str(FIG / "paper_diameter"), lambda t: line_chart(
        t, "", "", chips,
        [("Boardfly-of-pods", [chip_hops(d) for d in scale["bf"]]),
         ("Shiftfly", [chip_hops(d) for d in scale["sf"]])],
        "chips in the system (log scale)", "worst-case chip hops",
        fmt="{:.0f}", height=390))

    write_pair(str(FIG / "paper_gap"), lambda t: line_chart(
        t, "", "", chips,
        [("Boardfly-of-pods", scale["bfg"]), ("Shiftfly", scale["sfg"])],
        "chips in the system (log scale)", "spectral gap  1 - lambda_2",
        fmt="{:.2f}", height=390))

    cats = ["random placement", "locality placement"]
    write_pair(str(FIG / "sharing_cost"), lambda t: grouped_bars(
        t, "Cost of serving one shared item to 32 agents",
        "Hops per requester with in-network replication. Lower is better. "
        "Placement does most of the work -- on both topologies.",
        cats,
        [("Boardfly-of-pods", [sharing[("Boardfly", "random")]["tree"],
                               sharing[("Boardfly", "locality")]["tree"]]),
         ("Shiftfly", [sharing[("Shiftfly", "random")]["tree"],
                       sharing[("Shiftfly", "locality")]["tree"]])],
        "tree hops per requester", fmt="{:.3f}"))

    write_pair(str(FIG / "paper_sharing"), lambda t: grouped_bars(
        t, "", "", cats,
        [("Boardfly-of-pods", [sharing[("Boardfly", "random")]["tree"],
                               sharing[("Boardfly", "locality")]["tree"]]),
         ("Shiftfly", [sharing[("Shiftfly", "random")]["tree"],
                       sharing[("Shiftfly", "locality")]["tree"]])],
        "tree hops per requester", fmt="{:.3f}", height=390))


def main() -> None:
    t0 = time.time()
    RES.mkdir(exist_ok=True)
    parts = ["# Results\n\nRegenerate with `python3 run_experiments.py`. "
             "Every figure and table below comes out of this one script.\n\n"]
    parts.append(experiment_moore())
    scale_md, scale = experiment_scale()
    parts.append(scale_md)
    share_md, sharing = experiment_sharing()
    parts.append(share_md)
    parts.append(experiment_operations())
    fault_md, _ = experiment_faults()
    parts.append(fault_md)
    (RES / "results.md").write_text("".join(parts), encoding="utf-8")
    figures(scale, sharing)

    print(f"results/ and figures/ written in {time.time()-t0:.1f}s\n")
    for n, dbf, dsf in zip(scale["sizes"], scale["bf"], scale["sf"]):
        print(f"  {n*GROUP_CHIPS:>9,} chips: Boardfly chip-D {chip_hops(dbf):>3}"
              f"   Shiftfly chip-D {chip_hops(dsf):>3}")
    print()
    for k, v in sharing.items():
        print(f"  {k[0]:9s} {k[1]:9s} tree/req={v['tree']:.3f} "
              f"merge={v['merge']:.3f}")


if __name__ == "__main__":
    main()
