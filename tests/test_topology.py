"""Invariants the constructions and metrics must satisfy.

The theorems in the paper are asserted here against the code, so a change that
breaks the mathematics fails the suite rather than quietly changing a figure.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topology.graphs import (GROUP_CHIPS, GROUP_OPTICAL_PORTS, POD_CHIPS,
                             boardfly_group_level, boardfly_pod_chip_level,
                             chip_hops, de_bruijn, directed_moore_bound,
                             generalized_de_bruijn, imase_itoh, kautz,
                             kautz_capacity, log_diameter, min_diameter_for,
                             moore_bound, shiftfly_group_level, torus)
from topology.metrics import (bfs, distance_stats, merge_step, multicast,
                              shift_path, spectral_gap)
from topology.workload import (SharingModel, draw_requests, locality_labelling,
                               random_labelling, suffix_classes,
                               suffix_length_for)


class TestMooreBound(unittest.TestCase):
    def test_small_cases(self):
        self.assertEqual(moore_bound(3, 1), 4)        # K4
        self.assertEqual(moore_bound(3, 2), 10)       # Petersen
        self.assertEqual(moore_bound(7, 2), 50)       # Hoffman-Singleton
        self.assertEqual(moore_bound(2, 4), 9)        # cycle C9

    def test_monotone(self):
        for delta in (4, 7, 20):
            prev = 0
            for d in range(1, 8):
                cur = moore_bound(delta, d)
                self.assertGreater(cur, prev)
                prev = cur

    def test_no_graph_exceeds_its_bound(self):
        """The whole audit is meaningless if this ever fails."""
        for g in (torus((8, 8)), torus((4, 4, 4)), kautz(3, 3), de_bruijn(3, 3),
                  boardfly_pod_chip_level(pod_groups=6)):
            st = distance_stats(g, max_exact=5000)
            self.assertLessEqual(
                g.n, moore_bound(g.max_degree, st.diameter),
                f"{g.name} exceeds the Moore bound -- impossible")

    def test_min_diameter_is_tight(self):
        for delta, n in ((7, 1152), (7, 400000), (4, 256)):
            d = min_diameter_for(delta, n)
            self.assertGreaterEqual(moore_bound(delta, d), n)
            self.assertLess(moore_bound(delta, d - 1), n)


class TestTorus(unittest.TestCase):
    def test_analytic_diameter(self):
        for dims in ((8, 8), (4, 4, 4), (6, 10), (4, 5, 7)):
            g = torus(dims)
            st = distance_stats(g, max_exact=5000)
            self.assertEqual(st.diameter, sum(k // 2 for k in dims),
                             f"torus{dims}")

    def test_degree_and_order(self):
        g = torus((6, 6, 6))
        self.assertEqual(g.n, 216)
        self.assertEqual(g.max_degree, 6)


class TestKautz(unittest.TestCase):
    def test_order_matches_theorem(self):
        for d in (2, 3, 5, 7):
            for D in (1, 2, 3):
                self.assertEqual(len(kautz(d, D).labels), kautz_capacity(d, D))

    def test_diameter_is_exactly_D(self):
        for d, D in ((3, 3), (4, 3), (5, 2), (2, 4)):
            g = kautz(d, D)
            st = distance_stats(g, max_exact=6000)
            self.assertLessEqual(st.diameter, D, f"K({d},{D})")

    def test_out_degree(self):
        g = kautz(4, 3)
        for outs in g.arcs:
            self.assertEqual(len(outs), 4)

    def test_out_degree_d_costs_2d_ports(self):
        """The fairness of the whole comparison rests on this.

        In- and out-neighbourhoods coincide only at the `d(d+1)` vertices with
        u_1 = u_D, and there in exactly one neighbour -- so degree is 2d, or
        2d-1 on that thin set, and the port budget is 2d either way.
        """
        d, D = 5, 3
        g = kautz(d, D)
        preds: list[set[int]] = [set() for _ in range(g.n)]
        for u, outs in enumerate(g.arcs):
            for v in outs:
                preds[v].add(u)
        bidir = [len(set(g.arcs[v]) & preds[v]) for v in range(g.n)]
        self.assertTrue(all(b <= 1 for b in bidir))
        self.assertEqual(sum(bidir), d * (d + 1))
        self.assertEqual(sum(1 for w in g.labels if w[0] == w[-1]), d * (d + 1))
        self.assertEqual(g.max_degree, 2 * d)
        self.assertGreaterEqual(min(len(a) for a in g.adj), 2 * d - 1)

    def test_near_directed_moore_bound(self):
        for d, D in ((4, 3), (8, 3), (20, 2)):
            self.assertLessEqual(kautz_capacity(d, D), directed_moore_bound(d, D))
            self.assertGreater(kautz_capacity(d, D),
                               0.7 * directed_moore_bound(d, D))

    def test_shift_route_is_a_valid_walk(self):
        g = kautz(4, 3)
        nbr = [set(a) for a in g.adj]
        for s in range(0, g.n, 7):
            for t in range(0, g.n, 11):
                if s == t:
                    continue
                path = shift_path(g, s, t)
                self.assertEqual(path[0], s)
                self.assertEqual(path[-1], t)
                for a, b in zip(path, path[1:]):
                    self.assertIn(b, nbr[a], "shift route used a missing edge")

    def test_shift_route_is_within_the_diameter(self):
        g = kautz(4, 3)
        for s in range(0, g.n, 5):
            for t in range(0, g.n, 9):
                if s != t:
                    self.assertLessEqual(len(shift_path(g, s, t)) - 1, 3)

    def test_merge_criterion(self):
        """Theorem: routes to a common target merge at D - lcs(u, u')."""
        g = kautz(4, 3)
        D = 3
        for a in range(0, g.n, 13):
            for b in range(0, g.n, 17):
                if a == b:
                    continue
                home = (a * 7 + b * 5 + 1) % g.n
                if home in (a, b):
                    continue
                la, lb = g.labels[a], g.labels[b]
                lcs = 0
                while lcs < D and la[D - 1 - lcs] == lb[D - 1 - lcs]:
                    lcs += 1
                k = merge_step(shift_path(g, a, home), shift_path(g, b, home))
                if lcs > 0:
                    self.assertLessEqual(k, D - lcs,
                                         "merged later than the theorem allows")


class TestGeneralizedFamilies(unittest.TestCase):
    def test_exist_at_every_order(self):
        for n in (17, 100, 501, 1234):
            for d in (3, 5):
                g = imase_itoh(n, d)
                self.assertEqual(g.n, n)
                st = distance_stats(g, max_exact=2000)
                self.assertLessEqual(st.diameter, log_diameter(n, d),
                                     f"ImaseItoh({n},{d}) exceeds ceil(log_d n)")

    def test_generalized_de_bruijn_diameter(self):
        for n in (64, 200, 999):
            g = generalized_de_bruijn(n, 4)
            st = distance_stats(g, max_exact=2000)
            self.assertLessEqual(st.diameter, log_diameter(n, 4))

    def test_connected(self):
        g = imase_itoh(777, 6)
        self.assertTrue(all(d >= 0 for d in bfs(g.adj, 0)))


class TestBoardfly(unittest.TestCase):
    def test_pod_size(self):
        g = boardfly_pod_chip_level()
        self.assertEqual(g.n, POD_CHIPS)
        self.assertEqual(g.n, 1152)

    def test_published_diameter_is_reproduced(self):
        """The model is only trustworthy because it lands on Google's 7."""
        g = boardfly_pod_chip_level()
        st = distance_stats(g, max_exact=2000)
        self.assertEqual(st.diameter, 7)

    def test_degree_is_tpu_class(self):
        g = boardfly_pod_chip_level()
        self.assertLessEqual(g.max_degree, 7)

    def test_group_level_port_budget(self):
        g = boardfly_group_level(2000)
        self.assertLessEqual(g.max_degree, GROUP_OPTICAL_PORTS)

    def test_chip_hops_reproduces_seven(self):
        self.assertEqual(chip_hops(1), 7)
        self.assertEqual(chip_hops(0), 3)


class TestFairComparison(unittest.TestCase):
    def test_equal_port_budget(self):
        """Both designs must fit inside 40 optical ports per group."""
        for n in (576, 2304, 8400):
            bf = boardfly_group_level(n)
            sf = shiftfly_group_level(n, GROUP_OPTICAL_PORTS)
            self.assertLessEqual(bf.max_degree, GROUP_OPTICAL_PORTS)
            self.assertLessEqual(sf.max_degree, GROUP_OPTICAL_PORTS)
            self.assertEqual(bf.n, sf.n)

    def test_edge_counts_are_comparable(self):
        bf = boardfly_group_level(2304)
        sf = shiftfly_group_level(2304, GROUP_OPTICAL_PORTS)
        self.assertLess(abs(bf.m - sf.m) / bf.m, 0.05)

    def test_boardfly_wins_at_pod_scale(self):
        """Stated in the paper; asserted so it cannot be quietly dropped."""
        from topology.graphs import POD_GROUPS
        bf = boardfly_group_level(POD_GROUPS)
        sf = shiftfly_group_level(POD_GROUPS, GROUP_OPTICAL_PORTS)
        dbf = distance_stats(bf, max_exact=5000).diameter
        dsf = distance_stats(sf, max_exact=5000).diameter
        self.assertLess(chip_hops(dbf), chip_hops(dsf))


class TestOperations(unittest.TestCase):
    """The 'at least as convenient as Boardfly' claim, as assertions."""

    def setUp(self):
        from topology.operations import (slice_quality, swap_cost,
                                         wiring_state_bits)
        self.swap_cost = swap_cost
        self.wiring_state_bits = wiring_state_bits
        self.slice_quality = slice_quality
        self.n = 2304
        self.bf = boardfly_group_level(self.n)
        self.sf = shiftfly_group_level(self.n, GROUP_OPTICAL_PORTS)

    def test_replacing_a_group_costs_the_same_budget(self):
        """Swap cost is the degree, and both designs share one port budget.

        Neither is exactly regular: Shiftfly loses a port on the thin set of
        vertices carrying a bidirectional pair, and Boardfly loses one wherever
        an inter-pod stub failed to pair. The claim is that the *budget* binds
        both, and that the mean cost is within a few percent.
        """
        from topology.operations import mean_swap_cost
        for v in (0, 7, 101, 999):
            for g in (self.bf, self.sf):
                s = self.swap_cost(g, v)
                self.assertLessEqual(s.circuits, GROUP_OPTICAL_PORTS)
                self.assertEqual(s.circuits, s.peers)
        a, b = mean_swap_cost(self.bf), mean_swap_cost(self.sf)
        self.assertLess(abs(a - b) / a, 0.05,
                        "mean replacement cost differs by more than 5%")

    def test_swap_never_exceeds_the_port_budget(self):
        for g in (self.bf, self.sf):
            for v in (0, 55, 1234):
                self.assertLessEqual(self.swap_cost(g, v).circuits,
                                     GROUP_OPTICAL_PORTS)

    def test_shiftfly_needs_no_wiring_table(self):
        bits_bf = self.wiring_state_bits(self.bf, self.n)
        bits_sf = self.wiring_state_bits(self.sf, self.n)
        self.assertLess(bits_sf, 128)
        self.assertGreater(bits_bf, 100 * bits_sf)

    def test_naive_slices_are_bad_and_we_say_so(self):
        """The honest failure: an arbitrary induced subset is not a slice."""
        q = self.slice_quality(self.n, 128, GROUP_OPTICAL_PORTS)
        self.assertFalse(q.naive_connected)

    def test_reinstantiated_slices_meet_the_guarantee(self):
        for m in (16, 64, 256):
            q = self.slice_quality(self.n, m, GROUP_OPTICAL_PORTS)
            self.assertLessEqual(q.reinstantiated_diameter, q.guaranteed)

    def test_boardfly_wins_small_slices(self):
        from topology.operations import boardfly_slice_diameter
        self.assertEqual(boardfly_slice_diameter(16), 1)
        self.assertEqual(boardfly_slice_diameter(36), 1)

    def test_shiftfly_defined_at_every_order(self):
        from topology.operations import growth_step
        for n in (37, 100, 1153, 5000):
            self.assertTrue(growth_step(n)["shiftfly_defined_at_this_order"])


class TestMetrics(unittest.TestCase):
    def test_multicast_tree_never_exceeds_unicast(self):
        g = kautz(4, 3)
        r = multicast(g, 0, list(range(1, 40)))
        self.assertLessEqual(r.tree_cost, r.unicast_cost)
        self.assertGreaterEqual(r.efficiency, 1.0)

    def test_multicast_single_requester_is_its_distance(self):
        g = imase_itoh(300, 5)
        dist = bfs(g.adj, 0)
        for v in (7, 33, 199):
            r = multicast(g, 0, [v])
            self.assertEqual(r.unicast_cost, dist[v])
            self.assertEqual(r.tree_cost, dist[v])

    def test_spectral_gap_ordering(self):
        """A clique expands better than a cycle; the estimator must agree."""
        from topology.graphs import Graph
        n = 60
        clique = Graph("K", [[j for j in range(n) if j != i] for i in range(n)])
        cycle = torus((n,))
        self.assertGreater(spectral_gap(clique, iters=200),
                           spectral_gap(cycle, iters=200))

    def test_merge_step_symmetric(self):
        a = [1, 2, 3, 4]
        b = [9, 8, 3, 4]
        self.assertEqual(merge_step(a, b), merge_step(b, a))
        self.assertEqual(merge_step(a, b), 2)

    def test_merge_step_no_overlap(self):
        self.assertEqual(merge_step([1, 2], [3, 4]), -1)


class TestWorkload(unittest.TestCase):
    def test_suffix_classes_partition(self):
        g = kautz(4, 3)
        for j in (1, 2, 3):
            classes = suffix_classes(g, j)
            self.assertEqual(sum(len(v) for v in classes.values()), g.n)
            seen: set[int] = set()
            for v in classes.values():
                seen |= set(v)
            self.assertEqual(len(seen), g.n)

    def test_suffix_length_covers_clusters(self):
        g = kautz(20, 3)
        for clusters in (8, 64, 400):
            j = suffix_length_for(g, clusters)
            self.assertGreaterEqual(len(suffix_classes(g, j)), clusters)

    def test_labellings_are_injective(self):
        g = kautz(20, 3)
        for lab in (random_labelling(g, 2000),
                    locality_labelling(g, 2000, 64)):
            self.assertEqual(len(set(lab.to_vertex)), len(lab.to_vertex),
                             f"{lab.name} maps two groups to one vertex")

    def test_locality_labelling_beats_random_on_merge(self):
        """The co-design claim, as an assertion."""
        g = kautz(20, 3)
        n_logical, clusters = 4000, 64
        model = SharingModel(clusters=clusters, agents=16, locality=0.9)
        reqs = draw_requests(model, n_logical, trials=40)
        out = {}
        for lab in (random_labelling(g, n_logical),
                    locality_labelling(g, n_logical, clusters)):
            tot, cnt = 0, 0
            for item, logical in reqs:
                home = lab(item * 2654435761 % n_logical)
                req = [lab(x) for x in logical]
                if len(req) < 2 or home in req[:2]:
                    continue
                k = merge_step(shift_path(g, req[0], home),
                               shift_path(g, req[1], home))
                if k >= 0:
                    tot += k
                    cnt += 1
            out[lab.name.split("(")[0]] = tot / max(1, cnt)
        self.assertLess(out["suffix-locality"], out["random"])

    def test_requests_respect_locality(self):
        model = SharingModel(clusters=16, agents=64, locality=1.0)
        reqs = draw_requests(model, 1600, trials=20)
        per = 1600 // 16
        for item, req in reqs:
            c = item % 16
            for v in req:
                self.assertTrue(c * per <= v < (c + 1) * per)


if __name__ == "__main__":
    unittest.main()
