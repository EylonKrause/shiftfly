# Results

Regenerate with `python3 run_experiments.py`. Every figure and table below comes out of this one script.

## 1. Moore-bound audit
How far each shipped topology sits from the largest graph its own degree and diameter would permit. The bound is a ceiling that only a handful of graphs attain, so no design reaches it -- but the *ratio* says how much structure is being left unused.

| Generation | Chips | Degree | Diameter | Moore bound | Bound / actual | Min feasible D | Diameter source |
|---|---|---|---|---|---|---|---|
| v2 (2D torus 16x16) | 256 | 4 | 16 | 86,093,441 | 336,303x | 5 | analytic |
| v3 (2D torus 32x32) | 1,024 | 4 | 32 | 3,706,040,377,703,681 | 3,619,180,056,351x | 6 | analytic |
| v4 (3D torus 16^3) | 4,096 | 6 | 24 | 89,406,967,163,085,937 | 21,827,872,842,550x | 5 | analytic |
| v5e (2D torus 16x16) | 256 | 4 | 16 | 86,093,441 | 336,303x | 5 | analytic |
| v5p (3D torus 16x20x28) | 8,960 | 6 | 32 | 34,924,596,548,080,444,335,937 | 3,897,834,436,169,692,672x | 6 | analytic, shape inferred |
| v6e (2D torus 16x16) | 256 | 4 | 16 | 86,093,441 | 336,303x | 5 | analytic |
| v7 Ironwood (3D torus) | 9,216 | 6 | 32 | 34,924,596,548,080,444,335,937 | 3,789,561,257,387,201,024x | 6 | analytic, shape inferred |
| v8t (3D torus) | 9,600 | 6 | 33 | 174,622,982,740,402,221,679,687 | 18,189,894,035,458,564,096x | 6 | analytic, shape inferred |
| v8i Boardfly | 1,152 | 7 | 7 | 391,910 | 340x | 4 | published; reproduced here |

The chip-level Boardfly model built here has n=1,152, max degree 7, mean degree 5.84, and **measured diameter 7** against Google's published 7 -- which is the check that the port-assignment model is faithful. Mean distance is 5.211.

## 2. Equal-cost comparison
Both designs get **40 optical ports per group** and the same 32-chip group internals. Shiftfly therefore runs at Kautz out-degree 20, not 40: in- and out-neighbourhoods are disjoint, so out-degree d costs 2d bidirectional ports. Getting that wrong hands Shiftfly twice the hardware.

Chip-level distance is `3(g+1) + g` for g group hops -- the same arithmetic that makes Boardfly's published intra-pod diameter 7 = 3 + 1 + 3.

| Groups | Chips | BF group D | SF group D | BF chip D | SF chip D | BF chip mean | SF chip mean | BF gap | SF gap |
|---|---|---|---|---|---|---|---|---|---|
| 36 | 1,152 | 1 | 2 | 7 | 11 | 7.00 | 7.76 | 1.029 | 0.843 |
| 144 | 4,608 | 3 | 2 | 15 | 11 | 10.10 | 9.96 | 0.113 | 0.553 |
| 576 | 18,432 | 3 | 3 | 15 | 15 | 12.63 | 11.03 | 0.119 | 0.486 |
| 2,304 | 73,728 | 4 | 3 | 19 | 15 | 14.35 | 13.53 | 0.110 | 0.311 |
| 8,400 | 268,800 | 5 | 3 | 23 | 15 | 16.17 | 14.57 | 0.111 | 0.306 |
| 12,500 | 400,000 | 5 | 4 | 23 | 19 | 16.81 | 15.14 | 0.117 | 0.270 |
| 36,000 | 1,152,000 | 5 | 4 | 23 | 19 | 18.28 | 17.17 | 0.117 | 0.202 |

## 3. Redundancy and sharing
Workload: 32 agents per query, 64 affinity clusters, scheduler locality 85%, Zipf exponent 1.0. Both topologies carry 8,400 groups at 40 ports.

`unicast/req` is hops charged if every agent fetches independently; `tree/req` is what a fabric with in-network replication pays. **`tree/req` is the number that matters** -- the efficiency *ratio* rewards a topology for being far apart, so it flatters the worse network and should not be read alone.

| Topology | Labelling | unicast/req | tree/req | ratio | merge depth |
|---|---|---|---|---|---|
| Boardfly | random | 3.297 | 2.768 | 1.191 | 2.868 |
| Boardfly | cluster-placement | 3.111 | 2.174 | 1.431 | 2.336 |
| Shiftfly | random | 2.896 | 2.470 | 1.172 | 2.772 |
| Shiftfly | suffix-locality(j=2) | 2.881 | 2.112 | 1.364 | 2.152 |

**Reading it honestly.** Locality-aware placement cuts tree cost by 21% on Boardfly and 14% on Shiftfly -- so most of the redundancy win is *placement*, which any topology can do, not algebra. Shiftfly's own contribution is the residual: 2.8% lower tree cost than Boardfly at matched placement, and merge depth 2.15 against 2.34. Note also that the efficiency *ratio* ranks Boardfly higher (1.431 vs 1.364) while absolute cost ranks it lower -- which is exactly the trap that metric sets.

## 4. Link failures
Independent link drops on a 2,304-group instance; reachability and distance measured from 60 random sources.

| Topology | Link failure rate | Reachable fraction | Mean distance | Eccentricity |
|---|---|---|---|---|
| Boardfly | 0% | 1.0000 | 2.840 | 4 |
| Boardfly | 2% | 1.0000 | 2.840 | 4 |
| Boardfly | 5% | 1.0000 | 2.841 | 4 |
| Boardfly | 10% | 1.0000 | 2.847 | 4 |
| Boardfly | 20% | 1.0000 | 2.863 | 4 |
| Shiftfly | 0% | 1.0000 | 2.631 | 3 |
| Shiftfly | 2% | 1.0000 | 2.631 | 3 |
| Shiftfly | 5% | 1.0000 | 2.633 | 3 |
| Shiftfly | 10% | 1.0000 | 2.636 | 3 |
| Shiftfly | 20% | 1.0000 | 2.654 | 3 |

Kautz digraphs have vertex connectivity exactly `d`, which is the maximum possible for their degree, so the thin global tier degrades gracefully. Boardfly's intra-pod cliques are highly redundant but its inter-pod links are few, so damage concentrates at pod boundaries.
