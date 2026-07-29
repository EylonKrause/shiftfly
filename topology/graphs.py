"""Graph constructions for every topology under study, plus the Moore bound.

Everything is an undirected adjacency list over vertices ``0..n-1``.  Directed
constructions (de Bruijn, Kautz) keep their arc structure separately, because
shift routing needs it even though the physical links are bidirectional.

Stdlib only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import product


# --------------------------------------------------------------------------
# the bound everything is measured against
# --------------------------------------------------------------------------

def moore_bound(delta: int, diameter: int) -> int:
    """Largest possible undirected graph of max degree `delta`, diameter `D`.

        N <= 1 + delta * sum_{i=0}^{D-1} (delta-1)^i

    Attained only by complete graphs, cycles, and the Moore graphs of diameter
    two (Petersen, Hoffman-Singleton, and a hypothetical 57-regular graph), so
    it is a ceiling rather than a target.
    """
    if delta < 1 or diameter < 1:
        raise ValueError("delta and diameter must be positive")
    if delta == 1:
        return 2 if diameter >= 1 else 1
    if delta == 2:
        return 2 * diameter + 1
    total, term = 1, 1
    for _ in range(diameter):
        total += delta * term
        term *= delta - 1
    return total


def directed_moore_bound(d: int, diameter: int) -> int:
    """Largest possible digraph of out-degree `d`, diameter `D`.

        N <= (d^(D+1) - 1) / (d - 1)

    Kautz digraphs sit within a hair of this, which is the whole reason they
    are interesting here.
    """
    if d < 1 or diameter < 1:
        raise ValueError("d and diameter must be positive")
    if d == 1:
        return diameter + 1
    return (d ** (diameter + 1) - 1) // (d - 1)


def min_diameter_for(delta: int, n: int) -> int:
    """Smallest diameter the Moore bound permits for `n` nodes at degree `delta`."""
    d = 1
    while moore_bound(delta, d) < n:
        d += 1
        if d > 10_000:
            raise ValueError("no feasible diameter")
    return d


# --------------------------------------------------------------------------
# graph container
# --------------------------------------------------------------------------

@dataclass
class Graph:
    name: str
    adj: list[list[int]]
    #: optional vertex labels (tuples of symbols) for the shift-routed families
    labels: list[tuple[int, ...]] | None = None
    #: optional directed arcs, arcs[u] = successors of u under the shift map
    arcs: list[list[int]] | None = None
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.adj)

    @property
    def m(self) -> int:
        return sum(len(a) for a in self.adj) // 2

    @property
    def max_degree(self) -> int:
        return max((len(a) for a in self.adj), default=0)

    @property
    def mean_degree(self) -> float:
        return 2.0 * self.m / self.n if self.n else 0.0


def _undirected(n: int, arcs: list[list[int]]) -> list[list[int]]:
    """Symmetrise an arc list, dropping self-loops and duplicates."""
    seen = [set() for _ in range(n)]
    for u, outs in enumerate(arcs):
        for v in outs:
            if u == v:
                continue
            seen[u].add(v)
            seen[v].add(u)
    return [sorted(s) for s in seen]


# --------------------------------------------------------------------------
# the shift-routed families
# --------------------------------------------------------------------------

def kautz_labels(d: int, diameter: int) -> list[tuple[int, ...]]:
    """Strings of length `diameter` over `d+1` symbols with no equal neighbours."""
    if d < 2 or diameter < 1:
        raise ValueError("need d >= 2 and diameter >= 1")
    out: list[tuple[int, ...]] = [(s,) for s in range(d + 1)]
    for _ in range(diameter - 1):
        out = [w + (s,) for w in out for s in range(d + 1) if s != w[-1]]
    return out


def kautz(d: int, diameter: int, name: str | None = None) -> Graph:
    """Kautz digraph K(d, D).

    ``N = (d+1) * d^(D-1)`` vertices, out-degree ``d``, diameter exactly ``D``,
    and vertex connectivity ``d`` -- maximally connected, which matters when the
    global tier is thin.
    """
    labels = kautz_labels(d, diameter)
    index = {w: i for i, w in enumerate(labels)}
    arcs = [
        [index[w[1:] + (s,)] for s in range(d + 1) if s != w[-1]]
        for w in labels
    ]
    g = Graph(name or f"Kautz({d},{diameter})", _undirected(len(labels), arcs),
              labels=labels, arcs=arcs)
    g.meta.update(family="kautz", d=d, D=diameter, alphabet=d + 1)
    return g


def de_bruijn(d: int, diameter: int, name: str | None = None) -> Graph:
    """de Bruijn digraph B(d, D): ``d^D`` vertices, out-degree ``d``."""
    if d < 2 or diameter < 1:
        raise ValueError("need d >= 2 and diameter >= 1")
    labels = [tuple(w) for w in product(range(d), repeat=diameter)]
    index = {w: i for i, w in enumerate(labels)}
    arcs = [[index[w[1:] + (s,)] for s in range(d)] for w in labels]
    g = Graph(name or f"deBruijn({d},{diameter})", _undirected(len(labels), arcs),
              labels=labels, arcs=arcs)
    g.meta.update(family="debruijn", d=d, D=diameter, alphabet=d)
    return g


def generalized_de_bruijn(n: int, d: int, name: str | None = None) -> Graph:
    """Generalized de Bruijn digraph GB(n, d) -- Reddy, Pradhan & Kuhl (1980).

    Vertices ``Z_n`` for *any* n, arcs ``i -> d*i + r (mod n)`` for
    ``r = 0..d-1``, diameter at most ``ceil(log_d n)``.  This is what makes the
    family deployable: the string constructions only exist at sizes
    ``d^D`` or ``(d+1)d^(D-1)``, and a real machine is whatever size it is.
    """
    if n < 2 or d < 2:
        raise ValueError("need n >= 2 and d >= 2")
    arcs = [[(d * i + r) % n for r in range(d)] for i in range(n)]
    g = Graph(name or f"GB({n},{d})", _undirected(n, arcs), arcs=arcs)
    g.meta.update(family="gen-debruijn", d=d, n=n)
    return g


def imase_itoh(n: int, d: int, name: str | None = None) -> Graph:
    """Generalized Kautz digraph (Imase & Itoh, 1981).

    Arcs ``i -> -d*i - r (mod n)`` for ``r = 1..d``; diameter at most
    ``ceil(log_d n)`` for any n, and it inherits Kautz's better connectivity.
    """
    if n < 2 or d < 2:
        raise ValueError("need n >= 2 and d >= 2")
    arcs = [[(-d * i - r) % n for r in range(1, d + 1)] for i in range(n)]
    g = Graph(name or f"ImaseItoh({n},{d})", _undirected(n, arcs), arcs=arcs)
    g.meta.update(family="imase-itoh", d=d, n=n)
    return g


def log_diameter(n: int, d: int) -> int:
    """ceil(log_d n) -- the diameter guarantee for the generalized families."""
    k, cap = 0, 1
    while cap < n:
        cap *= d
        k += 1
    return k


def kautz_capacity(d: int, diameter: int) -> int:
    return (d + 1) * d ** (diameter - 1)


def smallest_kautz_for(n: int, d: int, max_diameter: int = 12) -> int:
    """Least diameter D with K(d, D) >= n."""
    for diameter in range(1, max_diameter + 1):
        if kautz_capacity(d, diameter) >= n:
            return diameter
    raise ValueError(f"K({d},.) cannot reach {n} within {max_diameter}")


# --------------------------------------------------------------------------
# what Google actually ships
# --------------------------------------------------------------------------

def torus(dims: tuple[int, ...], name: str | None = None) -> Graph:
    """k-ary n-cube: Cayley graph of the product of cyclic groups.

    Diameter is exactly ``sum(k_i // 2)``; degree is ``2n`` (less if some
    ``k_i == 2``, where the two neighbours coincide).
    """
    sizes = list(dims)
    n = 1
    for k in sizes:
        n *= k
    strides, acc = [], 1
    for k in sizes:
        strides.append(acc)
        acc *= k

    def coords(i: int) -> list[int]:
        return [(i // s) % k for s, k in zip(strides, sizes)]

    def index(c: list[int]) -> int:
        return sum((ci % k) * s for ci, k, s in zip(c, sizes, strides))

    arcs: list[list[int]] = []
    for i in range(n):
        c = coords(i)
        outs = []
        for axis, k in enumerate(sizes):
            if k < 2:
                continue
            for step in (1, -1):
                cc = list(c)
                cc[axis] = (cc[axis] + step) % k
                outs.append(index(cc))
        arcs.append(outs)

    g = Graph(name or f"Torus{tuple(sizes)}", _undirected(n, arcs))
    g.meta.update(family="torus", dims=tuple(sizes),
                  analytic_diameter=sum(k // 2 for k in sizes))
    return g


#: Published Boardfly structure (TPU 8i).  Google's wording: "a building block
#: of four fully connected chips into a fully connected group of eight boards,
#: with 36 of such groups fully connected into a TPU 8i pod".
BB_CHIPS = 4
GROUP_BBS = 8
GROUP_CHIPS = BB_CHIPS * GROUP_BBS      # 32
POD_GROUPS = 36
POD_CHIPS = GROUP_CHIPS * POD_GROUPS    # 1152
BB_EXTERNAL_LINKS = 16
BB_INTRA_GROUP_LINKS = 11
BB_OPTICAL_LINKS = BB_EXTERNAL_LINKS - BB_INTRA_GROUP_LINKS   # 5
GROUP_OPTICAL_PORTS = GROUP_BBS * BB_OPTICAL_LINKS            # 40


def boardfly_pod_chip_level(pod_groups: int = POD_GROUPS) -> Graph:
    """Chip-level Boardfly pod.

    Ports are assigned as follows, since Google has not published the
    assignment: the copper link between building blocks ``i`` and ``j`` of a
    group is owned by chip ``j mod 4`` of ``i`` and chip ``i mod 4`` of ``j``;
    the optical link between groups ``p`` and ``q`` is owned by one specific
    (building block, chip) pair on each side.  This is *a* realisation
    consistent with the published counts, and it reproduces the published
    diameter of 7.
    """
    n = pod_groups * GROUP_CHIPS

    def chip(group: int, bb: int, c: int) -> int:
        return (group * GROUP_BBS + bb) * BB_CHIPS + c

    arcs: list[list[int]] = [[] for _ in range(n)]

    def link(a: int, b: int) -> None:
        arcs[a].append(b)
        arcs[b].append(a)

    for g in range(pod_groups):
        # building blocks: four fully connected chips
        for bb in range(GROUP_BBS):
            for a in range(BB_CHIPS):
                for b in range(a + 1, BB_CHIPS):
                    link(chip(g, bb, a), chip(g, bb, b))
        # group: eight building blocks fully connected in copper
        for i in range(GROUP_BBS):
            for j in range(i + 1, GROUP_BBS):
                link(chip(g, i, j % BB_CHIPS), chip(g, j, i % BB_CHIPS))

    # pod: groups fully connected through the optical circuit switch, each
    # link landing on one designated chip of one designated building block
    for p in range(pod_groups):
        for q in range(p + 1, pod_groups):
            link(chip(p, q % GROUP_BBS, (q // GROUP_BBS) % BB_CHIPS),
                 chip(q, p % GROUP_BBS, (p // GROUP_BBS) % BB_CHIPS))

    g = Graph(f"Boardfly pod ({n} chips)", _undirected(n, arcs))
    g.meta.update(family="boardfly", level="chip", groups=pod_groups)
    return g


def boardfly_group_level(n_groups: int, pod_groups: int = POD_GROUPS,
                         inter_pod_ports: int = GROUP_OPTICAL_PORTS - (POD_GROUPS - 1),
                         seed: int = 7) -> Graph:
    """Group-level Boardfly, extended past one pod.

    Within a pod the 36 groups are fully connected, consuming 35 of each
    group's 40 optical ports.  The remaining ``inter_pod_ports`` (5) per group
    are spent on links to other pods, wired here as a random graph over pods --
    which is generous to Boardfly, since a random high-degree graph over 347
    pods has diameter two.
    """
    rng = random.Random(seed)
    n_pods = (n_groups + pod_groups - 1) // pod_groups
    arcs: list[list[int]] = [[] for _ in range(n_groups)]

    def link(a: int, b: int) -> None:
        if a != b:
            arcs[a].append(b)
            arcs[b].append(a)

    for pod in range(n_pods):
        members = [g for g in range(pod * pod_groups,
                                    min((pod + 1) * pod_groups, n_groups))]
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                link(a, b)

    if n_pods > 1:
        # every group offers `inter_pod_ports` stubs; pair them at random
        # between distinct pods
        stubs: list[int] = []
        for g in range(n_groups):
            stubs.extend([g] * inter_pod_ports)
        rng.shuffle(stubs)
        for i in range(0, len(stubs) - 1, 2):
            a, b = stubs[i], stubs[i + 1]
            if a // pod_groups != b // pod_groups:
                link(a, b)

    g = Graph(f"Boardfly-of-pods ({n_groups} groups)", _undirected(n_groups, arcs))
    g.meta.update(family="boardfly", level="group", pods=n_pods,
                  pod_groups=pod_groups, inter_pod_ports=inter_pod_ports)
    return g


def shiftfly_group_level(n_groups: int, ports: int = GROUP_OPTICAL_PORTS,
                         exact_size: bool = True) -> Graph:
    """Group-level Shiftfly over `n_groups` groups within an optical port budget.

    A Kautz arc set of out-degree ``d`` costs ``2d`` bidirectional ports, since
    in- and out-neighbourhoods are disjoint.  Matching Boardfly's 40 optical
    ports per group therefore means ``d = 20``, not 40 -- getting this wrong
    hands Shiftfly twice the hardware and invalidates the comparison.

    `exact_size` uses the Imase-Itoh construction, which exists at every n.
    Setting it False falls back to the string Kautz graph, which only exists
    at ``(d+1)d^(D-1)`` and therefore strands capacity.
    """
    d = max(2, ports // 2)
    if exact_size:
        g = imase_itoh(n_groups, d, name=f"Shiftfly GK({n_groups},{d})")
        g.meta.update(guaranteed_diameter=log_diameter(n_groups, d))
    else:
        diameter = smallest_kautz_for(n_groups, d)
        g = kautz(d, diameter, name=f"Shiftfly K({d},{diameter})")
    g.meta.update(family="shiftfly", level="group", ports=ports,
                  capacity=g.n, requested=n_groups, out_degree=d)
    return g


#: chip hops charged for traversing one group: in through a port, across the
#: building blocks, out through another (the same 3 that make Boardfly's
#: published intra-pod diameter come to 7 = 3 + 1 + 3)
INTRA_GROUP_HOPS = 3


def chip_hops(group_hops: int, intra: int = INTRA_GROUP_HOPS) -> int:
    """Chip-level distance implied by a group-level distance.

    Traversing ``g`` group-hops passes through ``g+1`` groups, each costing
    ``intra`` chip hops internally, plus the ``g`` inter-group links::

        chips = intra * (g + 1) + g
    """
    return intra * (group_hops + 1) + group_hops
