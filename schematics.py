"""Structural diagrams: what Shiftfly changes, and how shift routing works.

Generated rather than drawn, so they cannot drift out of step with the code.
"""

from __future__ import annotations

import math
from pathlib import Path

from svgplot import Canvas, Theme, write_pair
from topology.graphs import kautz

FIG = Path(__file__).resolve().parent / "figures"


def _ring(cx: float, cy: float, r: float, n: int, phase: float = -math.pi / 2):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n),
             cy + r * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]


def _complete(c: Canvas, pts, stroke, width=1.0, op=1.0):
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            c.line(*pts[i], *pts[j], stroke, width, opacity=op)


def hierarchy(t: Theme) -> Canvas:
    c = Canvas(820, 500, t, "What Shiftfly changes")
    c.text(38, 42, "Shiftfly changes one tier", t.primary, 19, weight=600)
    c.text(38, 66, "The building block and the group are Boardfly's, unchanged. "
                   "Only the global tier is replaced.", t.secondary, 12.5)

    # ---- shared local tiers -------------------------------------------------
    c.text(38, 108, "SHARED — unchanged from Boardfly", t.muted, 11, weight=600)

    bb = _ring(110, 186, 34, 4)
    _complete(c, bb, t.series[2], 1.6)
    for p in bb:
        c.dot(*p, t.series[2], 7)
    c.text(110, 248, "building block", t.secondary, 11.5, anchor="middle")
    c.text(110, 264, "4 chips, complete", t.muted, 10.5, anchor="middle")

    grp = _ring(300, 186, 52, 8)
    _complete(c, grp, t.series[2], 0.9, 0.55)
    for p in grp:
        c.dot(*p, t.series[2], 6)
    c.text(300, 248, "group", t.secondary, 11.5, anchor="middle")
    c.text(300, 264, "8 blocks = 32 chips, copper", t.muted, 10.5, anchor="middle")

    c.line(430, 186, 466, 186, t.axis, 1.5)
    c.add(f'<path d="M466,180 L478,186 L466,192 Z" fill="{t.axis}"/>')

    # ---- the tier that differs ---------------------------------------------
    c.text(508, 108, "GLOBAL TIER — the difference", t.muted, 11, weight=600)

    a = _ring(590, 186, 52, 8)
    _complete(c, a, t.series[0], 0.9)
    for p in a:
        c.dot(*p, t.series[0], 6)
    c.text(590, 248, "Boardfly: complete", t.series[0], 11.5, anchor="middle",
           weight=600)
    c.text(590, 264, "G−1 ports to reach G groups", t.muted, 10.5, anchor="middle")

    b = _ring(748, 186, 52, 8)
    for i, p in enumerate(b):
        for step in (2, 3):
            q = b[(i + step) % 8]
            c.line(*p, *q, t.series[1], 0.9, opacity=0.8)
    for p in b:
        c.dot(*p, t.series[1], 6)
    c.text(748, 248, "Shiftfly: shift graph", t.series[1], 11.5, anchor="middle",
           weight=600)
    c.text(748, 264, "2d ports, diameter ⌈log_d G⌉", t.muted, 10.5,
           anchor="middle")

    # ---- the consequence ----------------------------------------------------
    y = 322
    c.line(38, y - 18, 782, y - 18, t.grid, 1)
    c.text(38, y + 4, "Consequence at 400,000 chips (12,500 groups, 40 optical "
                      "ports per group)", t.secondary, 12, weight=600)
    rows = [
        ("Boardfly", "complete tier needs 12,499 ports — infeasible, so a pod "
                     "tier is stacked and diameters add", "23 chip hops",
         t.series[0]),
        ("Shiftfly", "one flat graph, no pod boundary, no added tier",
         "19 chip hops", t.series[1]),
    ]
    for k, (name, why, res, col) in enumerate(rows):
        yy = y + 34 + k * 34
        c.rect(38, yy - 11, 10, 10, col, rx=2)
        c.text(56, yy - 2, name, t.primary, 12, weight=600)
        c.text(132, yy - 2, why, t.secondary, 11.5)
        c.text(782, yy - 2, res, col, 12, weight=600, anchor="end",
               tabular=True)

    c.text(38, y + 118, "Both tiers ride the optical circuit switch that already "
                        "exists; the wiring is a permutation, not new cable.",
           t.muted, 11.5)
    return c


def routing(t: Theme) -> Canvas:
    """Shift routing on K(2,2), with a worked two-hop route."""
    c = Canvas(820, 430, t, "Shift routing")
    c.text(38, 42, "Routing is a shift register, not a table", t.primary, 19,
           weight=600)
    c.text(38, 66, "The Kautz graph K(2,2). To reach v, shift its symbols in "
                   "from the right; the destination label is the route.",
           t.secondary, 12.5)

    g = kautz(2, 2)
    labels = ["".join(str(s) for s in w) for w in g.labels]
    pts = _ring(250, 250, 116, g.n)

    def arrow(p, q, col, w, op=1.0):
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        p2 = (p[0] + ux * 20, p[1] + uy * 20)
        q2 = (q[0] - ux * 22, q[1] - uy * 22)
        c.line(*p2, *q2, col, w, opacity=op)
        ax, ay = q2
        c.add(f'<path d="M{ax:.1f},{ay:.1f} '
              f'L{ax-ux*9-uy*4.5:.1f},{ay-uy*9+ux*4.5:.1f} '
              f'L{ax-ux*9+uy*4.5:.1f},{ay-uy*9-ux*4.5:.1f} Z" '
              f'fill="{col}" opacity="{op}"/>')

    idx = {lab: i for i, lab in enumerate(labels)}
    route = ["01", "12", "20"]
    hot = {(idx[route[i]], idx[route[i + 1]]) for i in range(len(route) - 1)}

    for u, outs in enumerate(g.arcs):
        for v in outs:
            if (u, v) in hot:
                continue
            arrow(pts[u], pts[v], t.muted, 1.1, 0.45)
    for u, v in hot:
        arrow(pts[u], pts[v], t.series[1], 2.6)

    for i, (p, lab) in enumerate(zip(pts, labels)):
        on = lab in route
        col = t.series[1] if on else t.surface
        c.add(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="19" fill="{col}" '
              f'stroke="{t.series[1] if on else t.axis}" stroke-width="2"/>')
        c.text(p[0], p[1] + 4.5, lab, t.surface if on else t.secondary, 12.5,
               weight=600, anchor="middle")

    x = 452
    c.text(x, 132, "Worked example:  01 → 20", t.primary, 13, weight=600)
    lines = [
        ("Longest suffix of u that is a", ""),
        ("prefix of v:  ℓ = 0, so k = D − ℓ = 2 hops.", ""),
        ("", ""),
        ("step 1:   u[1:] + v[0:1]  =  1 + 2  =  12", ""),
        ("step 2:   u[2:] + v[0:2]  =  ε + 20  =  20", ""),
        ("", ""),
        ("No table is consulted. No protocol", ""),
        ("converges. The label is the route.", ""),
    ]
    for k, (s, _) in enumerate(lines):
        c.text(x, 164 + k * 21, s, t.secondary if k < 5 else t.muted, 12)

    c.text(x, 366, "Merge criterion", t.primary, 12.5, weight=600)
    c.text(x, 388, "Two sources routing to the same v meet at step k", t.muted, 11.5)
    c.text(x, 406, "iff their last D − k symbols agree.", t.muted, 11.5)
    return c


def main() -> None:
    FIG.mkdir(exist_ok=True)
    write_pair(str(FIG / "hierarchy"), hierarchy)
    write_pair(str(FIG / "routing"), routing)
    print("schematics written")


if __name__ == "__main__":
    main()
