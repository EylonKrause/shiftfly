"""The sharing workload, and the label assignment that exploits it.

The claim under test is not that Shiftfly is a good graph -- Kautz digraphs
have been known to be near-optimal for the directed degree-diameter problem
since 1968.  The claim is that its *labelling* can be chosen so that requests
for the same content merge early, and that this is worth something.  Both
halves are measurable, and the second one is where the idea can fail.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .graphs import Graph


# --------------------------------------------------------------------------
# workload
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SharingModel:
    """Agentic serving as an access pattern over groups.

    A query fans out into `agents` concurrent rollouts.  Those rollouts share
    a prompt prefix, tool definitions and retrieved context, so they request
    the *same* content items.  Scheduling is imperfect but not adversarial:
    with probability `locality` an agent lands in the query's affinity cluster,
    otherwise anywhere.

    `zipf` shapes item popularity; 0 is uniform, ~1 is the usual heavy-tailed
    regime for shared prefixes and system prompts.
    """

    clusters: int = 64
    agents: int = 32
    locality: float = 0.85
    zipf: float = 1.0
    items: int = 4096

    def item_weights(self) -> list[float]:
        w = [1.0 / (i + 1) ** self.zipf for i in range(self.items)]
        total = sum(w)
        return [x / total for x in w]


def cluster_of(logical: int, n_logical: int, clusters: int) -> int:
    per = max(1, n_logical // clusters)
    return min(clusters - 1, logical // per)


def draw_requests(model: SharingModel, n_logical: int, trials: int,
                  seed: int = 23) -> list[tuple[int, list[int]]]:
    """Draw `(item, requesting logical groups)` pairs."""
    rng = random.Random(seed)
    weights = model.item_weights()
    cum: list[float] = []
    acc = 0.0
    for w in weights:
        acc += w
        cum.append(acc)

    def pick_item() -> int:
        x = rng.random()
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo

    per = max(1, n_logical // model.clusters)
    out: list[tuple[int, list[int]]] = []
    for _ in range(trials):
        item = pick_item()
        c = item % model.clusters
        lo = c * per
        hi = min(n_logical, lo + per)
        req = []
        for _ in range(model.agents):
            if hi > lo and rng.random() < model.locality:
                req.append(rng.randrange(lo, hi))
            else:
                req.append(rng.randrange(n_logical))
        out.append((item, sorted(set(req))))
    return out


# --------------------------------------------------------------------------
# labelling
# --------------------------------------------------------------------------

def suffix_classes(g: Graph, length: int) -> dict[tuple[int, ...], list[int]]:
    """Partition vertices by their last `length` symbols.

    In a shift-routed graph these classes are exactly the sets that merge
    early: two routes to a common destination coincide as soon as the symbols
    still to be shifted out agree.
    """
    if g.labels is None:
        raise ValueError("graph has no labels")
    out: dict[tuple[int, ...], list[int]] = {}
    for i, w in enumerate(g.labels):
        out.setdefault(w[-length:] if length else (), []).append(i)
    return out


def suffix_length_for(g: Graph, clusters: int) -> int:
    """Shortest suffix whose classes are at least as numerous as `clusters`."""
    if g.labels is None:
        raise ValueError("graph has no labels")
    D = len(g.labels[0])
    for j in range(1, D + 1):
        if len(suffix_classes(g, j)) >= clusters:
            return j
    return D


@dataclass
class Labelling:
    """A map from logical group id to physical vertex."""

    name: str
    to_vertex: list[int]

    def __call__(self, logical: int) -> int:
        return self.to_vertex[logical % len(self.to_vertex)]


def random_labelling(g: Graph, n_logical: int, seed: int = 29) -> Labelling:
    rng = random.Random(seed)
    verts = list(range(g.n))
    rng.shuffle(verts)
    return Labelling("random", verts[:n_logical])


def locality_labelling(g: Graph, n_logical: int, clusters: int,
                       seed: int = 31) -> Labelling:
    """Place each affinity cluster inside one suffix class.

    This is the co-design step.  It is deliberately simple: the point is to
    measure whether suffix-locality buys anything at all, not to find the
    optimal embedding.
    """
    rng = random.Random(seed)
    j = suffix_length_for(g, clusters)
    classes = suffix_classes(g, j)
    buckets = [sorted(v) for _, v in sorted(classes.items())]
    rng.shuffle(buckets)

    per = max(1, n_logical // clusters)
    to_vertex = [0] * n_logical
    cursor = [0] * len(buckets)
    for logical in range(n_logical):
        c = min(clusters - 1, logical // per)
        b = c % len(buckets)
        # walk forward if this bucket is exhausted
        for step in range(len(buckets)):
            idx = (b + step) % len(buckets)
            if cursor[idx] < len(buckets[idx]):
                to_vertex[logical] = buckets[idx][cursor[idx]]
                cursor[idx] += 1
                break
    return Labelling(f"suffix-locality(j={j})", to_vertex)


def cluster_placement_labelling(g: Graph, n_logical: int, clusters: int,
                                seed: int = 37) -> Labelling:
    """Baseline for non-shift graphs: put each cluster in one BFS ball.

    Boardfly has no shift algebra, but it does have locality, and a fair
    comparison must give it the same scheduling advantage Shiftfly gets.
    """
    from .metrics import bfs

    rng = random.Random(seed)
    unused = set(range(g.n))
    per = max(1, n_logical // clusters)
    to_vertex = [0] * n_logical
    logical = 0
    while logical < n_logical and unused:
        seed_v = rng.choice(sorted(unused))
        dist = bfs(g.adj, seed_v)
        ball = sorted((d, v) for v, d in enumerate(dist) if v in unused and d >= 0)
        take = ball[:per]
        for _, v in take:
            if logical >= n_logical:
                break
            to_vertex[logical] = v
            unused.discard(v)
            logical += 1
    return Labelling("cluster-placement", to_vertex)
