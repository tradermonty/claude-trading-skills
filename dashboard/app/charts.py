"""Small server-side SVG line charts, so the page needs no JavaScript or CDN."""

from __future__ import annotations

from markupsafe import Markup, escape


def line_chart(
    points: list[tuple[str, float]],
    y_min: float = 0,
    y_max: float = 100,
    suffix: str = "",
    width: int = 640,
    height: int = 180,
    step: bool = False,
    label: str = "",
) -> Markup:
    if not points:
        return Markup('<p class="muted">No history yet.</p>')
    pad_l, pad_r, pad_t, pad_b = 36, 12, 10, 24
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b
    span = (y_max - y_min) or 1

    def x(i: int) -> float:
        return pad_l + (inner_w * i / (len(points) - 1) if len(points) > 1 else inner_w / 2)

    def y(v: float) -> float:
        v = min(max(v, y_min), y_max)
        return pad_t + inner_h * (1 - (v - y_min) / span)

    coords: list[str] = []
    for i, (_, v) in enumerate(points):
        if step and coords:
            coords.append(f"{x(i):.1f},{y(points[i - 1][1]):.1f}")
        coords.append(f"{x(i):.1f},{y(v):.1f}")

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img"'
        f' aria-label="{escape(label)}">'
    ]
    for frac in (0, 0.5, 1):
        gv = y_min + span * frac
        gy = y(gv)
        parts.append(
            f'<line class="grid" x1="{pad_l}" x2="{width - pad_r}" y1="{gy:.1f}" y2="{gy:.1f}"/>'
            f'<text class="axis" x="{pad_l - 6}" y="{gy + 4:.1f}" text-anchor="end">'
            f"{gv:g}{escape(suffix)}</text>"
        )
    parts.append(f'<polyline class="line" points="{" ".join(coords)}"/>')
    for i, (day, v) in enumerate(points):
        parts.append(
            f'<circle class="dot" cx="{x(i):.1f}" cy="{y(v):.1f}" r="3">'
            f"<title>{escape(day)}: {v:g}{escape(suffix)}</title></circle>"
        )
    first, last = points[0][0], points[-1][0]
    parts.append(f'<text class="axis" x="{pad_l}" y="{height - 6}">{escape(first)}</text>')
    if last != first:
        parts.append(
            f'<text class="axis" x="{width - pad_r}" y="{height - 6}" text-anchor="end">'
            f"{escape(last)}</text>"
        )
    parts.append("</svg>")
    return Markup("".join(parts))
