"""Distance, expansion, multicast and path-merge measurements.

Exact where the graph is small enough, sampled where it is not -- and every
sampled figure is reported as such rather than quietly presented as exact.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from .graphs import Graph

INF = float("inf")


# --------------------------------------------------------------------------
# distances
# --------------------------------------------------------------------------

def bfs(adj: list[list[int]], source: int) -> list[int]:
    """Hop distances from `source`; unreachable vertices get -1."""
    dist = [-1] * len(adj)
    dist[source] = 0
    q = deque([source])
    while q:
        u = q.popleft()
        du = dist[u] + 1
        for v in adj[u]:
            if dist[v] < 0:
                dist[v] = du
                q.append(v)
    return dist


def bfs_tree(adj: list[list[int]], root: int) -> tuple[list[int], list[int]]:
    """Return (distance, parent) for a BFS tree rooted at `root`."""
    n = len(adj)
    dist = [-1] * n
    parent = [-1] * n
    dist[root] = 0
    q = deque([root])
    while q:
        u = q.popleft()
        du = dist[u] + 1
        for v in adj[u]:
            if dist[v] < 0:
                dist[v] = du
                parent[v] = u
                q.append(v)
    return dist, parent


@dataclass
class DistanceStats:
    n: int
    diameter: int
    mean: float
    exact: bool
    sources: int
    disconnected: bool = False

    def describe(self) -> str:
        kind = "exact" if self.exact else f"sampled ({self.sources} sources)"
        return (f"n={self.n} diameter={self.diameter} "
                f"mean={self.mean:.3f} [{kind}]")


def distance_stats(g: Graph, max_exact: int = 20_000, samples: int = 256,
                   seed: int = 11) -> DistanceStats:
    """Eccentricity/diameter and mean distance.

    Runs an all-pairs sweep when the graph is small, otherwise BFS from a
    random sample of sources.  A sampled diameter is a *lower bound* on the
    true diameter; the mean is an unbiased estimate.
    """
    n = g.n
    exact = n <= max_exact
    rng = random.Random(seed)
    sources = range(n) if exact else [rng.randrange(n) for _ in range(samples)]

    diameter = 0
    total = 0
    pairs = 0
    disconnected = False
    for s in sources:
        dist = bfs(g.adj, s)
        for d in dist:
            if d < 0:
                disconnected = True
                continue
            if d > diameter:
                diameter = d
            total += d
            pairs += 1
    pairs -= len(list(sources))  # drop the zero-distance self pairs
    mean = total / pairs if pairs else 0.0
    return DistanceStats(n, diameter, mean, exact,
                         n if exact else samples, disconnected)


# --------------------------------------------------------------------------
# expansion -- the honest proxy for bisection bandwidth
# --------------------------------------------------------------------------

def spectral_gap(g: Graph, iters: int = 400, seed: int = 3) -> float:
    """Estimate 1 - lambda_2 of the normalised adjacency operator.

    Power iteration on ``M = (P + I)/2`` with the uniform vector projected
    out, where ``P = D^-1 A``.  Larger gap means better expansion, and
    expansion is what bounds bisection from below.  This is an *estimate*:
    power iteration converges slowly when the gap is small, so treat small
    values as "small", not as exact.
    """
    n = g.n
    if n < 3:
        return 0.0
    rng = random.Random(seed)
    deg = [max(1, len(a)) for a in g.adj]
    x = [rng.uniform(-1.0, 1.0) for _ in range(n)]

    def project(v: list[float]) -> None:
        mean = sum(v) / n
        for i in range(n):
            v[i] -= mean

    def normalise(v: list[float]) -> float:
        nrm = sum(t * t for t in v) ** 0.5
        if nrm == 0:
            return 0.0
        for i in range(n):
            v[i] /= nrm
        return nrm

    project(x)
    normalise(x)
    mu = 0.0
    for _ in range(iters):
        y = [0.0] * n
        for u, nbrs in enumerate(g.adj):
            if not nbrs:
                continue
            acc = 0.0
            for v in nbrs:
                acc += x[v]
            y[u] = 0.5 * (acc / deg[u] + x[u])
        project(y)
        mu = sum(y[i] * x[i] for i in range(n))
        if normalise(y) == 0.0:
            break
        x = y
    lambda2 = 2.0 * mu - 1.0
    return max(0.0, 1.0 - lambda2)


def greedy_bisection(g: Graph, rounds: int = 6, seed: int = 5) -> int:
    """Upper bound on bisection width by local search from a random split.

    Exact bisection is NP-hard; this is a cheap upper bound, reported as such.
    """
    n = g.n
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    side = [0] * n
    for i in order[n // 2:]:
        side[i] = 1

    def cut() -> int:
        return sum(1 for u in range(n) for v in g.adj[u] if side[u] != side[v]) // 2

    for _ in range(rounds):
        improved = False
        for u in range(n):
            here = sum(1 for v in g.adj[u] if side[v] != side[u])
            there = len(g.adj[u]) - here
            if there < here:
                # only swap if it keeps the halves balanced
                cand = [v for v in range(n) if side[v] != side[u]]
                if not cand:
                    continue
                w = cand[rng.randrange(len(cand))]
                before = here + sum(1 for v in g.adj[w] if side[v] != side[w])
                side[u], side[w] = side[w], side[u]
                after = (sum(1 for v in g.adj[u] if side[v] != side[u])
                         + sum(1 for v in g.adj[w] if side[v] != side[w]))
                if after < before:
                    improved = True
                else:
                    side[u], side[w] = side[w], side[u]
        if not improved:
            break
    return cut()


# --------------------------------------------------------------------------
# the sharing objective
# --------------------------------------------------------------------------

@dataclass
class MulticastResult:
    unicast_cost: int
    tree_cost: int
    efficiency: float     # unicast / tree; 1.0 means no sharing is possible
    requesters: int


def multicast(g: Graph, home: int, requesters: list[int]) -> MulticastResult:
    """Cost of serving one content item to `requesters` from `home`.

    ``unicast_cost`` charges every requester its full distance.  ``tree_cost``
    charges each *edge* of the union of shortest paths once, which is what a
    fabric with in-network replication would actually pay.  The union of
    root-paths in a BFS tree is a Steiner tree of the requester set, so this is
    an upper bound on the optimum and a lower bound on what unicast costs.
    """
    dist, parent = bfs_tree(g.adj, home)
    unicast = 0
    edges: set[tuple[int, int]] = set()
    reached = 0
    for v in requesters:
        if dist[v] < 0:
            continue
        reached += 1
        unicast += dist[v]
        u = v
        while u != home and parent[u] >= 0:
            p = parent[u]
            edges.add((u, p) if u < p else (p, u))
            u = p
    tree = len(edges)
    eff = (unicast / tree) if tree else 1.0
    return MulticastResult(unicast, tree, eff, reached)


def mean_multicast_efficiency(g: Graph, trials: int = 200, fanout: int = 32,
                              seed: int = 13) -> tuple[float, float]:
    """Average multicast efficiency over random (home, requester-set) draws.

    Returns ``(efficiency, mean_unicast_distance)``.
    """
    rng = random.Random(seed)
    n = g.n
    effs, dists = [], []
    for _ in range(trials):
        home = rng.randrange(n)
        req = rng.sample(range(n), min(fanout, n))
        r = multicast(g, home, req)
        if r.requesters:
            effs.append(r.efficiency)
            dists.append(r.unicast_cost / r.requesters)
    if not effs:
        return 1.0, 0.0
    return sum(effs) / len(effs), sum(dists) / len(dists)


# --------------------------------------------------------------------------
# path merging -- where redundant requests collapse
# --------------------------------------------------------------------------

def shift_path(g: Graph, source: int, dest: int) -> list[int]:
    """Route by shifting the destination label into the source label.

    Defined for the de Bruijn / Kautz family only.  Returns the vertex
    sequence, source first.  This is table-free: every step is a shift.
    """
    if g.labels is None:
        raise ValueError(f"{g.name} has no labels; shift routing undefined")
    index = g.meta.setdefault("_index", {w: i for i, w in enumerate(g.labels)})
    u = g.labels[source]
    v = g.labels[dest]
    D = len(u)

    # Landing on v after k steps requires the last D-k symbols of u to equal
    # the first D-k of v, and appends the *last* k symbols of v -- not the
    # first.  The shortest route takes the largest such overlap.
    overlap = 0
    for ell in range(D, -1, -1):
        if (ell == 0) or (u[D - ell:] == v[:ell]):
            overlap = ell
            break
    k = D - overlap

    path = [source]
    for j in range(1, k + 1):
        word = u[j:] + v[overlap:overlap + j]
        nxt = index.get(word)
        if nxt is None:            # not a legal vertex: fall back, never lie
            return _bfs_path(g, source, dest)
        path.append(nxt)
    if path[-1] != dest:
        return _bfs_path(g, source, dest)
    return path


def _bfs_path(g: Graph, source: int, dest: int) -> list[int]:
    _, parent = bfs_tree(g.adj, dest)
    path, u = [source], source
    while u != dest and parent[u] >= 0:
        u = parent[u]
        path.append(u)
    return path


def merge_step(path_a: list[int], path_b: list[int]) -> int:
    """Hops from the sources until two routes first touch the same vertex.

    Returns the smaller of the two hop counts at the meeting point, or -1 if
    the routes never share a vertex before the destination.
    """
    pos_b = {v: i for i, v in enumerate(path_b)}
    best = -1
    for i, v in enumerate(path_a):
        if v in pos_b:
            k = min(i, pos_b[v])
            if best < 0 or k < best:
                best = k
    return best


def mean_merge_depth(g: Graph, trials: int = 400, seed: int = 17,
                     use_shift: bool = True) -> float:
    """Average hops before two independent requests for the same item merge.

    Small is good: it is the number of hops of *duplicated* traffic the fabric
    carries before in-network caching can collapse the second request.
    """
    rng = random.Random(seed)
    n = g.n
    total, count = 0, 0
    trees: dict[int, tuple[list[int], list[int]]] = {}
    for _ in range(trials):
        home = rng.randrange(n)
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b or a == home or b == home:
            continue
        if use_shift and g.labels is not None:
            pa, pb = shift_path(g, a, home), shift_path(g, b, home)
        else:
            if home not in trees:
                trees[home] = bfs_tree(g.adj, home)
            _, parent = trees[home]

            def up(x: int) -> list[int]:
                out = [x]
                while out[-1] != home and parent[out[-1]] >= 0:
                    out.append(parent[out[-1]])
                return out

            pa, pb = up(a), up(b)
        k = merge_step(pa, pb)
        if k >= 0:
            total += k
            count += 1
    return total / count if count else 0.0
