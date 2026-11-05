#!/usr/bin/env python3
"""
Market Breadth Analyzer - HTML Report

Renders the same analysis as the Markdown report as a self-contained HTML page.
Every value is shown next to what it measures and a plain-language reading of
today's value, so a beginner can read the report without the methodology
reference.
"""

import html
import sys

COMPONENT_ORDER = [
    "breadth_level_trend",
    "ma_crossover",
    "cycle_position",
    "bearish_signal",
    "historical_percentile",
    "divergence",
]

COMPONENT_MEANING = {
    "breadth_level_trend": (
        "How many S&P 500 stocks are in long-term uptrends right now, and whether "
        "the long-term breadth trend is rising or falling."
    ),
    "ma_crossover": (
        "Whether short-term breadth (8-day average) is above or below long-term "
        "breadth (200-day average), i.e. is participation improving or fading."
    ),
    "cycle_position": (
        "Breadth moves in waves. This places today in the wave: shortly after a "
        "high (risky) or after a low (often the best time to buy)."
    ),
    "bearish_signal": (
        "A backtested warning flag from the dataset, plus the 'pink zone' "
        "(long-term breadth falling and short-term below it)."
    ),
    "historical_percentile": "How today's breadth compares with every day since 2016.",
    "divergence": (
        "Whether the S&P 500 index and the number of participating stocks move "
        "together. Index up while fewer stocks take part is a classic warning."
    ),
}

ZONES = [
    ("80-100", "Strong", "90-100%", "Full position, growth/momentum favored"),
    ("60-79", "Healthy", "75-90%", "Normal operations"),
    ("40-59", "Neutral", "60-75%", "Selective positioning, tighten stops"),
    ("20-39", "Weakening", "40-60%", "Profit-taking, raise cash"),
    ("0-19", "Critical", "25-40%", "Capital preservation, watch for a bottom"),
]

LEVEL_BANDS = [
    (0.70, "Very strong: a broad rally, most stocks take part."),
    (0.60, "Healthy: above-average participation."),
    (0.50, "Neutral: about half of the stocks take part."),
    (0.40, "Weakening: below-average participation, a selective market."),
    (0.20, "Extreme weakness: few stocks in uptrends; bottoms often form here."),
]


# --- Plain-language readings ---------------------------------------------


def _pct_of(value) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def explain_8ma_level(value) -> str:
    """Interpret a breadth value (0-1) against the methodology thresholds."""
    if value is None:
        return "No data."
    prefix = f"About {value * 100:.0f}% of S&P 500 stocks are above their 200-day average. "
    for threshold, text in LEVEL_BANDS:
        if value > threshold:
            return prefix + text
    return prefix + "Crisis level: rare, historically near major market bottoms."


def explain_gap(gap, direction) -> str:
    """Interpret the 8MA - 200MA gap together with the 8MA direction."""
    if gap is None:
        return "No data."
    rising = str(direction).lower() == "rising"
    pts = f"{abs(gap) * 100:.1f} points"
    if gap >= 0:
        text = f"Short-term breadth is {pts} above the long-term average"
        if rising:
            return text + " and rising: participation is improving."
        return text + " but falling: early deterioration, it may cross below soon."
    text = f"Short-term breadth is {pts} below the long-term average"
    if rising:
        return text + " but rising: early recovery, not yet confirmed."
    return text + " and falling: participation keeps shrinking."


def explain_cycle(marker, days, ma8_trend) -> str:
    """Interpret the latest breadth peak/trough marker."""
    if not marker:
        return "No peak or trough found yet."
    rising = str(ma8_trend).lower() == "rising"
    if str(marker).upper() == "PEAK":
        text = f"The last turning point was a breadth peak {days} trading days ago. "
        if days is not None and days <= 20:
            text += "Right after a peak is historically the riskiest phase."
        elif days is not None and days <= 60:
            text += "Breadth has been declining since; a deeper pullback phase."
        else:
            text += "A long decline; bottoms often form in this phase."
        if rising:
            text += " Short-term breadth is now rising again (recovery attempt)."
        return text
    text = f"The last turning point was a breadth trough (low) {days} trading days ago. "
    if days is not None and days <= 20:
        text += "Early recovery: historically the best upside potential."
    elif days is not None and days <= 60:
        text += "A confirmed recovery that is still running."
    else:
        text += "A mature recovery; watch for the next peak."
    if not rising:
        text += " Short-term breadth is currently falling, though."
    return text


def explain_bearish(signal_active, trend, in_pink_zone) -> str:
    """Interpret the bearish flag, long-term trend and pink zone together."""
    trend_up = trend == 1
    if signal_active:
        if trend_up:
            return "Bearish signal active, but the long-term trend is still up: a warning, not a breakdown."
        return "Bearish signal active and the long-term trend is down: full bearish alignment."
    if in_pink_zone:
        return (
            "No warning flag, but the market is in the pink zone: long-term breadth "
            "is falling and short-term breadth is below it. Structurally weak."
        )
    if trend_up:
        return "No warning flag and the long-term trend is up: all clear."
    return "No warning flag, but the long-term breadth trend is down: a cautious backdrop."


def explain_percentile(percentile) -> str:
    """Interpret the historical percentile rank."""
    if percentile is None:
        return "No data."
    p = f"{percentile:.0f}"
    if percentile >= 80:
        return f"Breadth is higher than on {p}% of past days: historically strong."
    if percentile >= 60:
        return f"Higher than on {p}% of past days: above average."
    if percentile >= 40:
        return f"Higher than on {p}% of past days: an ordinary reading."
    if percentile >= 20:
        return f"Higher than on only {p}% of past days: below average."
    return f"Higher than on only {p}% of past days: historically weak."


def explain_divergence_window(sp_pct, breadth_change) -> str:
    """Interpret one divergence window from index % change and breadth change."""
    if sp_pct is None or breadth_change is None:
        return "No data."
    if abs(sp_pct) < 0.5 and abs(breadth_change) < 0.01:
        return "Both are roughly flat: no meaningful signal."
    if sp_pct >= 0 and breadth_change >= 0:
        return "Index and breadth both rising: a healthy rally that many stocks support."
    if sp_pct >= 0 > breadth_change:
        return (
            "Index rising while fewer stocks take part: a narrow market. "
            "This pattern preceded major tops (2000, 2007, 2021)."
        )
    if sp_pct < 0 <= breadth_change:
        return (
            "Index falling while more stocks improve: a positive divergence that "
            "often appears near a bottom."
        )
    return "Index and breadth both falling: a consistent decline, no hidden strength."


def explain_composite(score, zone, exposure) -> str:
    return (
        f"{score}/100 puts breadth in the {zone} zone. From breadth alone, "
        f"{exposure} of your capital in stocks would be appropriate."
    )


# --- HTML helpers ---------------------------------------------------------


def _e(value) -> str:
    return html.escape("N/A" if value is None else str(value))


def _tone(score) -> str:
    if score is None:
        return "na"
    if score >= 60:
        return "good"
    if score >= 40:
        return "mid"
    return "bad"


def _score_bar(score) -> str:
    width = max(0, min(100, score or 0))
    return (
        f'<div class="bar"><span class="fill {_tone(score)}" style="width:{width}%"></span></div>'
    )


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _explained_table(rows) -> str:
    """rows: (metric, value, what it measures, today) with plain-text cells."""
    cells = [
        (f"<strong>{_e(m)}</strong>", f'<span class="val">{_e(v)}</span>', _e(w), _e(t))
        for m, v, w, t in rows
    ]
    return _table(["Metric", "Value", "What it measures", "Today"], cells)


def _section(title, intro, body) -> str:
    intro_html = f'<p class="intro">{_e(intro)}</p>' if intro else ""
    return f"<section><h2>{_e(title)}</h2>{intro_html}{body}</section>"


def _level_scale(ma8, ma200) -> str:
    """Horizontal 0-100% scale with threshold bands and today's markers."""

    def pos(v):
        return max(0.0, min(100.0, v * 100))

    bands = [
        (0.0, 0.2, "crit", "Crisis"),
        (0.2, 0.4, "weak", "Extreme"),
        (0.4, 0.6, "nm", "Selective"),
        (0.6, 1.0, "ok", "Healthy"),
    ]
    band_html = "".join(
        f'<span class="band {cls}" style="width:{(hi - lo) * 100:.0f}%">{label}</span>'
        for lo, hi, cls, label in bands
    )
    markers = ""
    if ma200 is not None:
        markers += (
            f'<span class="tick" style="left:{pos(ma200):.1f}%">'
            f"<em>200-day avg {_pct_of(ma200)}</em></span>"
        )
    if ma8 is not None:
        markers += (
            f'<span class="marker" style="left:{pos(ma8):.1f}%">'
            f"<b>today (8-day avg) {_pct_of(ma8)}</b></span>"
        )
    return (
        f'<div class="scale">{band_html}{markers}</div>'
        '<div class="scale-axis"><span>0%</span><span>20%</span><span>40%</span>'
        "<span>60%</span><span>100%</span></div>"
    )


# --- Sections -------------------------------------------------------------


def _how_to_read(components) -> str:
    c1 = components.get("breadth_level_trend", {}) or {}
    zones = _table(
        ["Score", "Zone", "Equity exposure", "Typical action"],
        [(_e(r), _e(z), _e(x), _e(a)) for r, z, x, a in ZONES],
    )
    return _section(
        "How to read this report",
        None,
        "<p><strong>Market breadth</strong> asks: how many stocks take part in the market's "
        "move? A rally carried by many stocks is healthy; a rally carried by a few big names "
        "is fragile.</p>"
        "<p>Everything here is built on one number, the <strong>breadth index</strong>: the "
        "share of S&amp;P 500 stocks trading above their own 200-day moving average (their "
        "long-term trend line). 0.64 means 64% of the stocks are above it.</p>"
        "<p>The index is smoothed two ways: the <strong>8-day average</strong> (short-term, "
        "reacts fast) and the <strong>200-day average</strong> (long-term trend, slow). "
        "Comparing them shows whether participation is improving or fading.</p>"
        + _level_scale(c1.get("current_8ma"), c1.get("current_200ma"))
        + "<p>Six components turn this into a <strong>composite score from 0 to 100</strong> "
        "(higher = healthier). The score maps to a zone:</p>"
        + zones
        + '<p class="note">The exposure range is this indicator\'s view alone. The daily '
        "exposure decision (exposure-coach) also weighs uptrend participation and top risk, "
        "so it can be stricter.</p>",
    )


def _freshness(metadata) -> str:
    warning = (metadata.get("data_freshness", {}) or {}).get("warning")
    if not warning:
        return ""
    return f'<div class="card warn"><strong>Data warning:</strong> {_e(warning)}</div>'


def _overall(composite, components) -> str:
    score = composite.get("composite_score")
    zone = composite.get("zone", "Unknown")
    exposure = composite.get("exposure_guidance", "N/A")
    strongest = composite.get("strongest_health", {}) or {}
    weakest = composite.get("weakest_health", {}) or {}
    dq = composite.get("data_quality", {}) or {}

    rows = [
        (
            "Composite score",
            f"{score}/100",
            "Overall breadth health, 0-100. Higher is healthier.",
            explain_composite(score, zone, exposure),
        ),
        (
            "Health zone",
            zone,
            "The band the score falls in (see the zone table above).",
            composite.get("guidance", ""),
        ),
        (
            "Equity exposure",
            exposure,
            "Suggested share of your capital in stocks, from breadth alone.",
            "Treat as an upper bound; the exposure-coach decision is the one to act on.",
        ),
        (
            "Strongest component",
            f"{strongest.get('label', 'N/A')} ({strongest.get('score', 0)}/100)",
            "The part of the score holding it up most.",
            "Where breadth looks best right now.",
        ),
        (
            "Weakest component",
            f"{weakest.get('label', 'N/A')} ({weakest.get('score', 0)}/100)",
            "The part of the score dragging it down most.",
            "Where breadth looks worst right now.",
        ),
    ]
    if dq:
        rows.append(
            (
                "Data quality",
                dq.get("label", "N/A"),
                "How many of the 6 components had enough data.",
                "Complete data." if "Complete" in str(dq.get("label")) else "Some data missing.",
            )
        )
    c1_mod = (components.get("breadth_level_trend", {}) or {}).get("direction_modifier", 0) or 0
    c2_mod = (components.get("ma_crossover", {}) or {}).get("direction_modifier", 0) or 0
    caution = ""
    if c1_mod < 0 or c2_mod < 0:
        caution = (
            '<div class="card warn"><strong>Caution:</strong> the short-term (8-day) breadth '
            "average is falling. Watch for further deterioration.</div>"
        )

    verdict = (
        f'<div class="verdict {_tone(score)}"><div class="big">{_e(score)}<small>/100</small></div>'
        f'<div><div class="zone">{_e(zone)}</div><div>Equity exposure {_e(exposure)}</div>'
        f'<div class="muted">{_e(composite.get("guidance"))}</div></div></div>'
    )
    return _section("Overall Assessment", None, verdict + caution + _explained_table(rows))


def _component_scores(composite, components) -> str:
    rows = []
    for i, key in enumerate(COMPONENT_ORDER, 1):
        comp = composite.get("component_scores", {}).get(key, {}) or {}
        score = round(comp.get("score", 0) or 0)
        label = comp.get("label", key)
        if not comp.get("data_available", True):
            label += " (excluded: not enough data)"
        weight = comp.get("weight", 0) or 0
        eff = comp.get("effective_weight", weight) or 0
        weight_txt = f"{weight * 100:.0f}%"
        if abs(eff - weight) > 1e-9:
            weight_txt += f" (now {eff * 100:.0f}%)"
        rows.append(
            (
                _e(i),
                f"<strong>{_e(label)}</strong>",
                _e(weight_txt),
                f'{_score_bar(score)}<span class="val">{_e(score)}</span>',
                _e(f"{comp.get('weighted_contribution', 0) or 0:.1f}"),
                _e(COMPONENT_MEANING.get(key, "")),
                _e((components.get(key, {}) or {}).get("signal", "N/A")),
            )
        )
    table = _table(
        ["#", "Component", "Weight", "Score", "Contribution", "What it measures", "Today"],
        rows,
    )
    note = ""
    excluded = composite.get("excluded_components", []) or []
    if excluded:
        note = (
            f'<p class="note">{len(excluded)} component(s) had too little data and were left '
            "out; their weight was shared among the others.</p>"
        )
    return _section(
        "Component Scores",
        "Each component scores 0-100. Contribution = score x weight; the contributions "
        "add up to the composite score.",
        table + note,
    )


def _trend_word(trend) -> str:
    if trend == 1:
        return "Rising (uptrend)"
    if trend == -1:
        return "Falling (downtrend)"
    return "N/A"


def _component_details(components) -> str:
    parts = []

    c1 = components.get("breadth_level_trend", {}) or {}
    if c1:
        ma8 = c1.get("current_8ma")
        rows = [
            (
                "8-day average (8MA)",
                _pct_of(ma8),
                "Short-term breadth: share of stocks above their 200-day line, averaged over ~8 days.",
                explain_8ma_level(ma8),
            ),
            (
                "200-day average (200MA)",
                _pct_of(c1.get("current_200ma")),
                "Long-term breadth: the same share averaged over ~200 days. The 'normal' level.",
                "Short-term breadth is above its long-term norm."
                if ma8 is not None
                and c1.get("current_200ma") is not None
                and ma8 >= c1["current_200ma"]
                else "Short-term breadth is below its long-term norm.",
            ),
            (
                "Long-term trend",
                _trend_word(c1.get("trend")),
                "Direction of the 200-day average: the big-picture breadth trend.",
                "Long-term participation is growing."
                if c1.get("trend") == 1
                else "Long-term participation is shrinking, so strength may not last.",
            ),
            (
                "Level score / trend score",
                f"{c1.get('level_score', 'N/A')} / {c1.get('trend_score', 'N/A')}",
                "Sub-scores (0-100) for today's level and for the long-term direction.",
                "A good level held back by a weak long-term trend."
                if (c1.get("level_score") or 0) > (c1.get("trend_score") or 0)
                else "The level is no better than the long-term trend.",
            ),
        ]
        if c1.get("ma8_direction"):
            rows.append(
                (
                    "8MA direction (5 days)",
                    c1.get("ma8_direction"),
                    "Whether short-term breadth went up or down over the last 5 days.",
                    "Improving this week."
                    if str(c1.get("ma8_direction")).lower() == "rising"
                    else "Getting worse this week.",
                )
            )
        parts.append("<h3>1. Current breadth level &amp; trend</h3>" + _explained_table(rows))

    c2 = components.get("ma_crossover", {}) or {}
    if c2:
        gap = c2.get("gap")
        mod = c2.get("direction_modifier", 0) or 0
        rows = [
            (
                "Gap (8MA - 200MA)",
                "N/A" if gap is None else f"{gap * 100:+.1f} pts",
                "Short-term minus long-term breadth. Positive = participation above normal.",
                explain_gap(gap, c2.get("ma8_direction")),
            ),
            (
                "Gap score",
                c2.get("gap_score"),
                "Score for the size of the gap (bigger positive gap = higher).",
                "Near the crossover line: small gap, no strong momentum either way."
                if gap is not None and abs(gap) < 0.05
                else "A clear gap: momentum has a direction.",
            ),
            (
                "Direction modifier",
                f"{mod:+d}",
                "Bonus/penalty when the 8MA moves toward a crossover.",
                "No adjustment."
                if mod == 0
                else ("+ early recovery bonus." if mod > 0 else "- early deterioration penalty."),
            ),
        ]
        parts.append("<h3>2. Short-term vs long-term (crossover)</h3>" + _explained_table(rows))

    c3 = components.get("cycle_position", {}) or {}
    if c3:
        rows = [
            (
                "Latest turning point",
                c3.get("latest_marker_type") or "None",
                "The most recent breadth peak (high) or trough (low) in the long-term average.",
                explain_cycle(
                    c3.get("latest_marker_type"),
                    c3.get("days_since_marker"),
                    c3.get("ma8_trend"),
                ),
            ),
            (
                "Days since",
                c3.get("days_since_marker"),
                "Trading days since that turning point.",
                "0-20 days = early phase, 21-60 = middle, 60+ = late phase.",
            ),
        ]
        if c3.get("extreme_trough"):
            rows.append(
                (
                    "Extreme trough",
                    "Yes",
                    "The low happened with fewer than 40% of stocks above their 200-day line.",
                    "Historically these deep lows were good long-term entry points (+10 bonus).",
                )
            )
        parts.append("<h3>3. Position in the breadth cycle</h3>" + _explained_table(rows))

    c4 = components.get("bearish_signal", {}) or {}
    if c4:
        active = bool(c4.get("signal_active"))
        pink = bool(c4.get("in_pink_zone"))
        rows = [
            (
                "Bearish signal",
                "ACTIVE" if active else "Off",
                "A backtested warning flag supplied with the dataset.",
                explain_bearish(active, c4.get("trend"), pink),
            ),
            (
                "Pink zone",
                f"Yes ({c4.get('pink_zone_days', 0)} days)" if pink else "No",
                "Long-term breadth falling AND short-term breadth below it.",
                "Structural weakness; can last weeks or months."
                if pink
                else "Not in the bearish region.",
            ),
        ]
        parts.append("<h3>4. Bearish warning flags</h3>" + _explained_table(rows))

    c5 = components.get("historical_percentile", {}) or {}
    if c5:
        pr = c5.get("percentile_rank")
        rows = [
            (
                "Percentile rank",
                "N/A" if pr is None else f"{pr:.0f}th",
                "Share of all past days (since 2016) with lower breadth than today.",
                explain_percentile(pr),
            ),
            (
                "Average peak",
                _pct_of(c5.get("avg_peak")),
                "Typical breadth level at past cycle highs.",
                "Approaching this level means breadth may be near a high.",
            ),
            (
                "Average trough",
                _pct_of(c5.get("avg_trough")),
                "Typical breadth level at past extreme lows.",
                "Reaching this level has historically been a contrarian buy zone.",
            ),
        ]
        adj = c5.get("adjustment", 0) or 0
        if adj:
            rows.append(
                (
                    "Adjustment",
                    f"{adj:+d}",
                    "Penalty near the average peak, bonus near the average trough.",
                    "Overheated: near past highs." if adj < 0 else "Near past lows: oversold.",
                )
            )
        parts.append("<h3>5. Compared with history</h3>" + _explained_table(rows))

    c6 = components.get("divergence", {}) or {}
    if c6:
        rows = []
        windows = [("window_60d", "60-day window"), ("window_20d", "20-day window")]
        if c6.get("window_60d") or c6.get("window_20d"):
            for key, label in windows:
                w = c6.get(key) or {}
                if not w:
                    continue
                sp = w.get("sp500_pct_change")
                br = w.get("breadth_change")
                rows.append(
                    (
                        label,
                        f"S&P {sp:+.2f}% / breadth {br * 100:+.1f} pts"
                        if sp is not None and br is not None
                        else "N/A",
                        "Index change vs change in share of participating stocks over "
                        + label.split()[0]
                        + "."
                        + (" Weighted 60%." if key == "window_60d" else " Weighted 40%."),
                        explain_divergence_window(sp, br),
                    )
                )
        else:
            sp = c6.get("sp500_pct_change")
            br = c6.get("breadth_change")
            rows.append(
                (
                    "Index vs breadth",
                    f"S&P {sp:+.2f}% / breadth {br * 100:+.1f} pts"
                    if sp is not None and br is not None
                    else "N/A",
                    "Index change vs change in share of participating stocks.",
                    explain_divergence_window(sp, br),
                )
            )
        if c6.get("early_warning"):
            rows.append(
                (
                    "Early warning",
                    "Yes",
                    "Short-term (20d) divergence while the 60-day picture is still fine.",
                    "Breadth has started to weaken under the surface. Watch closely.",
                )
            )
        parts.append("<h3>6. S&amp;P 500 vs breadth (divergence)</h3>" + _explained_table(rows))

    if not parts:
        return _section("Component Details", None, "<p>No component data available.</p>")
    return _section(
        "Component Details",
        "The inputs behind each component, with what they mean today.",
        "".join(parts),
    )


def _score_trend(analysis) -> str:
    ts = analysis.get("trend_summary") or {}
    entries = ts.get("entries", []) or []
    if not entries:
        return ""
    if len(entries) == 1:
        intro = "Only one run recorded so far; a trend needs at least two."
    else:
        intro = (
            f"Direction: {str(ts.get('direction', '')).capitalize()} "
            f"({ts.get('delta', 0):+.1f} points over {len(entries)} runs). "
            "Rising scores mean breadth is getting healthier from day to day."
        )
    rows = [
        (
            _e(e.get("data_date")),
            f"{_score_bar(e.get('composite_score'))}"
            f'<span class="val">{_e(e.get("composite_score"))}</span>',
        )
        for e in entries
    ]
    return _section("Score Trend", intro, _table(["Data date", "Composite score"], rows))


def _key_levels(analysis) -> str:
    levels = analysis.get("key_levels", {}) or {}
    if not levels:
        return _section("Key Levels to Watch", None, "<p>No key levels computed.</p>")
    rows = []
    for name, info in levels.items():
        value = info.get("value")
        try:
            shown = f"{float(value) * 100:.1f}% ({value})"
        except (TypeError, ValueError):
            shown = value
        rows.append(
            (
                f"<strong>{_e(name)}</strong>",
                f'<span class="val">{_e(shown)}</span>',
                _e(info.get("significance", "")),
            )
        )
    return _section(
        "Key Levels to Watch",
        "Breadth levels where the picture changes. Compare them with today's 8-day average.",
        _table(["Level", "Value", "Why it matters"], rows),
    )


def _actions(composite, components) -> str:
    actions = list(composite.get("actions", []) or [])
    c1_mod = (components.get("breadth_level_trend", {}) or {}).get("direction_modifier", 0) or 0
    c2_mod = (components.get("ma_crossover", {}) or {}).get("direction_modifier", 0) or 0
    if c1_mod < 0 or c2_mod < 0:
        actions += [
            "Reduce new position sizes until the 8-day average stabilizes",
            "Tighten stop-loss levels on existing positions",
        ]
    items = "".join(f"<li>{_e(a)}</li>" for a in actions)
    return _section(
        "Recommended Actions",
        f"Standard actions for the {composite.get('zone', 'Unknown')} zone. "
        "This is a posture, not a buy or sell signal for any single stock.",
        f"<ul>{items}</ul>",
    )


CSS = """
:root{--bg:#f7f7f5;--surface:#fff;--text:#1d1d1b;--muted:#6b6b66;--border:#e3e2dd;
--good:#2f8f5b;--mid:#c9a227;--bad:#c4472f;--crit:#f3d9d2;--weak:#f6e6c4;--nm:#eef0e4;--ok:#e2efe6;--accent:#2b5cab}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--surface:#1f1f1d;
--text:#ecebe6;--muted:#a3a29b;--border:#34342f;--good:#4fb47c;--mid:#d9b440;--bad:#e06a52;
--crit:#4a2a24;--weak:#4a3b1c;--nm:#2e3124;--ok:#25311f;--accent:#7aa2e3}}
:root[data-theme="dark"]{--bg:#161615;--surface:#1f1f1d;--text:#ecebe6;--muted:#a3a29b;--border:#34342f;
--good:#4fb47c;--mid:#d9b440;--bad:#e06a52;--crit:#4a2a24;--weak:#4a3b1c;--nm:#2e3124;--ok:#25311f;--accent:#7aa2e3}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
header h1{margin:0 0 4px;font-size:26px}
.muted,header p{color:var(--muted)}
section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;margin:18px 0}
h2{margin:0 0 10px;font-size:19px}h3{margin:18px 0 8px;font-size:16px}
.intro,.note{color:var(--muted);margin-top:0}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;font-weight:600;color:var(--muted);border-bottom:2px solid var(--border);padding:8px 10px;white-space:nowrap}
td{border-bottom:1px solid var(--border);padding:8px 10px;vertical-align:top}
td:last-child{min-width:220px}
.val{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.bar{display:inline-block;width:80px;height:8px;background:var(--border);border-radius:4px;margin-right:8px;vertical-align:middle;overflow:hidden}
.fill{display:block;height:100%}
.fill.good{background:var(--good)}.fill.mid{background:var(--mid)}.fill.bad{background:var(--bad)}
.verdict{display:flex;gap:20px;align-items:center;padding:14px 16px;border-radius:8px;margin-bottom:14px;border-left:6px solid var(--mid);background:var(--bg)}
.verdict.good{border-color:var(--good)}.verdict.bad{border-color:var(--bad)}
.big{font-size:42px;font-weight:700;line-height:1}.big small{font-size:16px;color:var(--muted)}
.zone{font-size:18px;font-weight:600}
.card{border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin:10px 0}
.card.warn{border-left:5px solid var(--mid)}
.scale{position:relative;display:flex;height:30px;margin:34px 0 4px;border-radius:6px;overflow:visible;font-size:12px}
.band{display:flex;align-items:center;justify-content:center;color:var(--muted)}
.band.crit{background:var(--crit);border-radius:6px 0 0 6px}.band.weak{background:var(--weak)}
.band.nm{background:var(--nm)}.band.ok{background:var(--ok);border-radius:0 6px 6px 0}
.marker,.tick{position:absolute;top:-6px;bottom:-6px;width:3px;background:var(--accent)}
.tick{width:1px;background:var(--muted)}
.marker b,.tick em{position:absolute;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:12px}
.marker b{top:-20px;color:var(--accent)}.tick em{bottom:-20px;color:var(--muted)}
.scale-axis{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin:22px 0 14px}
footer{color:var(--muted);font-size:13px;margin-top:24px}
"""


def generate_html_report(analysis: dict, output_file: str):
    """Write a self-contained HTML report with explanations for every value."""
    composite = analysis.get("composite", {}) or {}
    components = analysis.get("components", {}) or {}
    metadata = analysis.get("metadata", {}) or {}
    freshness = metadata.get("data_freshness", {}) or {}
    data_date = freshness.get("latest_date", "")

    body = (
        _freshness(metadata)
        + _how_to_read(components)
        + _overall(composite, components)
        + _component_scores(composite, components)
        + _component_details(components)
        + _score_trend(analysis)
        + _key_levels(analysis)
        + _actions(composite, components)
    )
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Market Breadth {_e(data_date)}</title><style>{CSS}</style></head>"
        "<body><main><header><h1>Market Breadth Report</h1>"
        f"<p>Generated {_e(metadata.get('generated_at'))} · Data as of {_e(data_date)} "
        f"({_e(freshness.get('days_old', '?'))} day(s) old) · Source: TraderMonty market "
        "breadth CSV</p></header>"
        f"{body}<footer>For education and information only. Not investment advice. "
        "Past patterns may not predict future outcomes.</footer></main></body></html>\n"
    )

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(page)
    except OSError as e:
        print(f"ERROR: Failed to write HTML report to {output_file}: {e}", file=sys.stderr)
        raise

    print(f"  HTML report saved to: {output_file}")
