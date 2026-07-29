"""Deployment and operations: can this actually be run?

A topology that is better on paper and worse to operate is not better. The
operational questions a fabric has to answer are concrete: what does it cost to
replace a failed group, how much state does the control plane hold, can a job be
given an isolated slice, and can the machine be grown. This module measures
each, for both designs, so the claim "at least as convenient as Boardfly" is
checked rather than asserted.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .graphs import (GROUP_OPTICAL_PORTS, POD_GROUPS, Graph,
                     boardfly_group_level, imase_itoh, log_diameter,
                     shiftfly_group_level)
from .metrics import bfs, distance_stats


# --------------------------------------------------------------------------
# field replacement
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SwapCost:
    circuits: int      # optical circuits the OCS must re-establish
    peers: int         # other groups whose port assignment is disturbed
    recompute: str     # what the control plane must work out


def swap_cost(g: Graph, v: int) -> SwapCost:
    """Cost of physically replacing group `v`.

    In both designs the replacement inherits the identity of the unit it
    replaces, and the optical circuit switch re-points that identity's fibres at
    the new hardware.  The count of circuits is therefore just the degree, and
    the designs differ only in what has to be *known* to do it.
    """
    deg = len(g.adj[v])
    family = g.meta.get("family")
    if family == "shiftfly":
        how = "none: the label determines the neighbour set arithmetically"
    else:
        how = "look up the group's recorded peer list"
    return SwapCost(circuits=deg, peers=deg, recompute=how)


def mean_swap_cost(g: Graph, samples: int = 64, seed: int = 41) -> float:
    rng = random.Random(seed)
    return sum(swap_cost(g, rng.randrange(g.n)).circuits
               for _ in range(samples)) / samples


# --------------------------------------------------------------------------
# control-plane state
# --------------------------------------------------------------------------

def wiring_state_bits(g: Graph, n_groups: int,
                      pod_groups: int = POD_GROUPS) -> int:
    """Bits the control plane must hold to derive the global wiring.

    Shiftfly's entire global tier follows from two integers, because the
    neighbour set of a label is a shift.  Boardfly's intra-pod tier is likewise
    derivable -- it is a complete graph, so pod membership suffices -- but the
    inter-pod tier has no closed form and must be tabulated.

    Boardfly could of course adopt a *structured* inter-pod tier instead. That
    is essentially the proposal of this paper.
    """
    family = g.meta.get("family")
    idx = max(1, math.ceil(math.log2(max(2, n_groups))))
    if family == "shiftfly":
        # n and d, and nothing else
        return 2 * idx
    pods = max(1, math.ceil(n_groups / pod_groups))
    membership = n_groups * max(1, math.ceil(math.log2(max(2, pods))))
    spare_ports = GROUP_OPTICAL_PORTS - (pod_groups - 1)
    inter_pod = n_groups * spare_ports * idx // 2      # each link counted once
    return membership + inter_pod


# --------------------------------------------------------------------------
# slice allocation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SliceQuality:
    groups: int
    naive_diameter: int         # induced subgraph of an arbitrary subset
    naive_connected: bool
    reinstantiated_diameter: int  # a correctly sized fabric over those groups
    guaranteed: int


def slice_quality(n_groups: int, slice_groups: int,
                  ports: int = GROUP_OPTICAL_PORTS,
                  seed: int = 43) -> SliceQuality:
    """How good a slice of `slice_groups` is, two ways.

    *Naive*: take an arbitrary subset of the deployed fabric and use the links
    that happen to fall inside it.  This is the honest worst case for a
    shift-routed graph, and it is bad -- an arbitrary induced subgraph of a
    Kautz digraph is sparse.

    *Re-instantiated*: install a correctly sized shift permutation over exactly
    those groups.  This is available because the global tier is a permutation on
    an optical circuit switch and the Imase--Itoh construction exists at every
    order, so a slice is a fabric in its own right rather than a fragment of one.
    """
    rng = random.Random(seed)
    full = shiftfly_group_level(n_groups, ports)
    chosen = rng.sample(range(full.n), min(slice_groups, full.n))
    keep = set(chosen)
    remap = {v: i for i, v in enumerate(chosen)}
    sub = [[] for _ in chosen]
    for v in chosen:
        for w in full.adj[v]:
            if w in keep:
                sub[remap[v]].append(remap[w])
    induced = Graph(f"induced-{slice_groups}", sub)
    dist = bfs(induced.adj, 0)
    connected = all(d >= 0 for d in dist)
    naive_d = max(dist) if connected else -1

    d_out = max(2, ports // 2)
    fresh = imase_itoh(max(2, slice_groups), d_out)
    fresh_d = distance_stats(fresh, max_exact=4000, samples=80).diameter

    return SliceQuality(slice_groups, naive_d, connected, fresh_d,
                        log_diameter(max(2, slice_groups), d_out))


def boardfly_slice_diameter(slice_groups: int,
                            pod_groups: int = POD_GROUPS) -> int:
    """Group-level diameter of a Boardfly slice of `slice_groups` groups."""
    if slice_groups <= pod_groups:
        return 1                     # any subset of a complete tier is complete
    g = boardfly_group_level(slice_groups)
    return distance_stats(g, max_exact=4000, samples=80).diameter


# --------------------------------------------------------------------------
# growth
# --------------------------------------------------------------------------

def growth_step(n_groups: int, ports: int = GROUP_OPTICAL_PORTS,
                pod_groups: int = POD_GROUPS) -> dict:
    """What changes when the machine grows by one group.

    Shiftfly is defined at every order, so growth re-installs a permutation and
    the diameter moves only when ``ceil(log_d n)`` does.  Boardfly is defined at
    multiples of a pod, and crossing a pod boundary introduces a hierarchy level
    rather than widening an existing one.
    """
    d_out = max(2, ports // 2)
    before, after = log_diameter(n_groups, d_out), log_diameter(n_groups + 1, d_out)
    return {
        "shiftfly_diameter_changes": before != after,
        "boardfly_crosses_pod": (n_groups % pod_groups) == 0 and n_groups > 0,
        "shiftfly_defined_at_this_order": True,
        "boardfly_natural_order": n_groups % pod_groups == 0,
    }
