"""Dependency-free SVG charts, light/dark pairs.

Colours are the first three slots of a documented, pre-validated categorical
palette plus its blue sequential ramp -- nothing here is eyeballed.  Three
categorical series is the cap that palette validates for charts where any two
marks can sit adjacent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    primary: str
    secondary: str
    muted: str
    grid: str
    axis: str
    series: tuple[str, ...]


LIGHT = Theme("light", "#fcfcfb", "#0b0b0b", "#52514e", "#898781",
              "#e1e0d9", "#c3c2b7", ("#2a78d6", "#eb6834", "#1baf7a"))
DARK = Theme("dark", "#1a1a19", "#ffffff", "#c3c2b7", "#898781",
             "#2c2c2a", "#383835", ("#3987e5", "#d95926", "#199e70"))
THEMES = (LIGHT, DARK)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Canvas:
    def __init__(self, w: float, h: float, t: Theme, title: str):
        self.w, self.h, self.t, self.title = w, h, t, title
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, fill, **kw):
        extra = "".join(f' {k.replace("_","-")}="{v}"' for k, v in kw.items())
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(0.0,w):.2f}" '
                 f'height="{max(0.0,h):.2f}" fill="{fill}"{extra}/>')

    def line(self, x1, y1, x2, y2, stroke, width=1.0, **kw):
        extra = "".join(f' {k.replace("_","-")}="{v}"' for k, v in kw.items())
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" '
                 f'y2="{y2:.2f}" stroke="{stroke}" stroke-width="{width}"{extra}/>')

    def path(self, pts, stroke, width=2.0):
        if not pts:
            return
        d = " ".join(("M" if i == 0 else "L") + f"{x:.2f},{y:.2f}"
                     for i, (x, y) in enumerate(pts))
        self.add(f'<path d="{d}" fill="none" stroke="{stroke}" '
                 f'stroke-width="{width}" stroke-linejoin="round" '
                 f'stroke-linecap="round"/>')

    def dot(self, x, y, fill, r=4.5):
        self.add(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r+2:.1f}" '
                 f'fill="{self.t.surface}"/>')
        self.add(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.1f}" fill="{fill}"/>')

    def text(self, x, y, s, fill=None, size=12, weight=400, anchor="start",
             tabular=False):
        num = ' font-variant-numeric="tabular-nums"' if tabular else ""
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" fill="{fill or self.t.primary}" '
                 f'font-size="{size}" font-weight="{weight}" '
                 f'text-anchor="{anchor}" font-family=\'{FONT}\'{num}>'
                 f'{esc(s)}</text>')

    def render(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" '
                f'height="{self.h:.0f}" viewBox="0 0 {self.w:.0f} {self.h:.0f}" '
                f'role="img" aria-label="{esc(self.title)}">'
                f'<title>{esc(self.title)}</title>'
                f'<rect width="{self.w:.0f}" height="{self.h:.0f}" '
                f'fill="{self.t.surface}"/>' + "".join(self.parts) + "</svg>")


def legend(c: Canvas, x: float, y: float, items: Sequence[tuple[str, str]],
           gap: float = 210.0) -> None:
    for i, (col, label) in enumerate(items):
        cx = x + i * gap
        c.rect(cx, y - 9, 11, 11, col, rx=2)
        c.text(cx + 17, y, label, c.t.secondary, 12)


def line_chart(t: Theme, title: str, subtitle: str, xs: Sequence[float],
               series: Sequence[tuple[str, Sequence[float]]],
               x_title: str, y_title: str, log_x: bool = True,
               y_zero: bool = True, fmt: str = "{:.0f}",
               width: float = 780, height: float = 470) -> Canvas:
    import math
    c = Canvas(width, height, t, title or y_title)
    # a figure destined for a paper carries its title in the LaTeX caption, so
    # drawing one here would duplicate it; drop the header band instead
    bare = not title
    L, R, T, B = 78, 34, (30 if bare else 96), 86
    pw, ph = width - L - R, height - T - B

    if not bare:
        c.text(40, 44, title, t.primary, 19, weight=600)
        if subtitle:
            c.text(40, 68, subtitle, t.secondary, 12.5)

    fx = [math.log10(x) if log_x else x for x in xs]
    x0, x1 = min(fx), max(fx)
    span = (x1 - x0) or 1.0
    allv = [v for _, ys in series for v in ys]
    lo = 0.0 if y_zero else min(allv) * 0.95
    hi = max(allv) * 1.12 or 1.0

    def px(v):
        return L + (((math.log10(v) if log_x else v) - x0) / span) * pw

    def py(v):
        return T + ph - ((v - lo) / (hi - lo)) * ph

    ticks = 5
    for i in range(ticks + 1):
        v = lo + (hi - lo) * i / ticks
        y = py(v)
        c.line(L, y, L + pw, y, t.grid, 1)
        c.text(L - 10, y + 4, fmt.format(v), t.muted, 10.5, anchor="end",
               tabular=True)
    c.line(L, T + ph, L + pw, T + ph, t.axis, 1)
    c.line(L, T, L, T + ph, t.axis, 1)

    # thin the tick labels rather than let them collide; endpoints always shown
    last_x = -1e9
    min_sep = 62.0
    for i, x in enumerate(xs):
        at = px(x)
        is_end = i in (0, len(xs) - 1)
        if not is_end and at - last_x < min_sep:
            c.line(at, T + ph, at, T + ph + 4, t.axis, 1)
            continue
        if is_end and i == len(xs) - 1 and at - last_x < min_sep:
            pass  # the final label wins the collision; the previous was drawn
        c.text(at, T + ph + 18, f"{x:,.0f}", t.muted, 10.5, anchor="middle",
               tabular=True)
        last_x = at

    for i, (label, ys) in enumerate(series):
        col = t.series[i % len(t.series)]
        pts = [(px(x), py(y)) for x, y in zip(xs, ys)]
        c.path(pts, col, 2)
        for x, y in pts:
            c.dot(x, y, col)
        c.text(pts[-1][0] - 6, pts[-1][1] - 14, label, col, 12, weight=600,
               anchor="end")

    c.text(L + pw / 2, height - 34, x_title, t.secondary, 12, anchor="middle")
    c.add(f'<g transform="translate({L-52:.1f},{T+ph/2:.1f}) rotate(-90)">'
          f'<text x="0" y="0" fill="{t.secondary}" font-size="12" '
          f'text-anchor="middle" font-family=\'{FONT}\'>{esc(y_title)}</text></g>')
    legend(c, L, height - 10,
           [(t.series[i % 3], lbl) for i, (lbl, _) in enumerate(series)])
    return c


def grouped_bars(t: Theme, title: str, subtitle: str,
                 categories: Sequence[str],
                 series: Sequence[tuple[str, Sequence[float]]],
                 y_title: str, fmt: str = "{:.2f}",
                 width: float = 780, height: float = 470) -> Canvas:
    c = Canvas(width, height, t, title or y_title)
    bare = not title
    L, R, T, B = 78, 34, (30 if bare else 96), 92
    pw, ph = width - L - R, height - T - B

    if not bare:
        c.text(40, 44, title, t.primary, 19, weight=600)
        if subtitle:
            c.text(40, 68, subtitle, t.secondary, 12.5)

    hi = max(v for _, ys in series for v in ys) * 1.18 or 1.0
    ticks = 5
    for i in range(ticks + 1):
        v = hi * i / ticks
        y = T + ph - (v / hi) * ph
        c.line(L, y, L + pw, y, t.grid, 1)
        c.text(L - 10, y + 4, fmt.format(v), t.muted, 10.5, anchor="end",
               tabular=True)
    c.line(L, T + ph, L + pw, T + ph, t.axis, 1)

    ncat, nser = len(categories), len(series)
    slot = pw / ncat
    bw = (slot * 0.68) / nser
    for ci, cat in enumerate(categories):
        base = L + ci * slot + slot * 0.16
        for si, (label, ys) in enumerate(series):
            v = ys[ci]
            h = (v / hi) * ph
            x = base + si * bw
            col = t.series[si % len(t.series)]
            # 2px surface gap between adjacent fills
            c.rect(x, T + ph - h, bw - 2, h, col, rx=3)
            c.text(x + (bw - 2) / 2, T + ph - h - 7, fmt.format(v), t.secondary,
                   10.5, anchor="middle", tabular=True)
        c.text(L + ci * slot + slot / 2, T + ph + 20, cat, t.secondary, 11.5,
               anchor="middle")

    c.add(f'<g transform="translate({L-52:.1f},{T+ph/2:.1f}) rotate(-90)">'
          f'<text x="0" y="0" fill="{t.secondary}" font-size="12" '
          f'text-anchor="middle" font-family=\'{FONT}\'>{esc(y_title)}</text></g>')
    legend(c, L, height - 12,
           [(t.series[i % 3], lbl) for i, (lbl, _) in enumerate(series)])
    return c


def write_pair(stem: str, build: Callable[[Theme], Canvas]) -> list[str]:
    out = []
    for theme in THEMES:
        path = f"{stem}_{theme.name}.svg"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build(theme).render())
        out.append(path)
    return out
