"""Tests for reusable theme match scoring."""

from leadership import ScanHit
from theme_matcher import calculate_theme_match, load_narrative_scores


def _theme(name, static_stocks, proxy_etfs):
    industries = [
        {"name": "Software - Application", "weighted_return": 15.0},
        {"name": "Software - Infrastructure", "weighted_return": 14.0},
    ]
    return {
        "theme_name": name,
        "matching_industries": industries,
        "matching_keyword_count": 2,
        "static_stocks": static_stocks,
        "proxy_etfs": proxy_etfs,
    }


def test_overlapping_themes_rank_by_basket_and_etf_confirmation():
    themes = [
        _theme("AI & Semiconductors", ["NVDA", "AVGO"], ["SMH"]),
        _theme("Cybersecurity", ["CRWD", "PANW"], ["CIBR"]),
        _theme("Cloud Computing & SaaS", ["CRM", "NOW"], ["SKYY"]),
    ]
    scan_hits = [
        ScanHit(date="2026-07-04", symbol="CRWD", scan_type="ep9m"),
        ScanHit(date="2026-07-04", symbol="PANW", scan_type="range_expansion"),
    ]
    etf_volume = {
        "SMH": {"vol_ratio": 1.0},
        "CIBR": {"vol_ratio": 1.8},
        "SKYY": {"vol_ratio": 0.9},
    }

    scored = [
        calculate_theme_match(theme, scan_hits, etf_volume, scan_hits_available=True)
        for theme in themes
    ]
    ranked_names = [
        name
        for name, detail in sorted(
            zip([theme["theme_name"] for theme in themes], scored),
            key=lambda item: item[1]["theme_match_score"],
            reverse=True,
        )
    ]

    assert ranked_names[0] == "Cybersecurity"
    assert scored[1]["theme_match_components"]["static_stock_hit_score"] == 80.0
    assert scored[1]["proxy_etf_confirmation"]["confirmed"] is True


def test_stock_basket_hits_exclude_industry_only_evidence():
    theme = _theme("Cybersecurity", ["CRWD", "PANW"], ["CIBR"])
    scan_hits = [
        ScanHit(
            date="2026-07-04",
            symbol="DDOG",
            scan_type="ep9m",
            industry="Software - Infrastructure",
        )
    ]

    detail = calculate_theme_match(theme, scan_hits, {}, scan_hits_available=True)

    assert detail["theme_match_components"]["static_stock_hit_score"] == 0.0
    assert detail["static_stock_confirmation"]["hit_symbols"] == []


def test_missing_scan_hits_and_narrative_are_optional():
    theme = _theme("AI & Semiconductors", ["NVDA"], ["SMH"])

    detail = calculate_theme_match(theme, [], {}, scan_hits_available=False)

    assert detail["theme_match_score"] is not None
    assert detail["theme_match_components"]["static_stock_hit_score"] is None
    assert detail["theme_match_components"]["narrative_keyword_score"] is None
    assert "static_stock_hit_score" in detail["theme_match_missing_components"]
    assert "narrative_keyword_score" in detail["theme_match_missing_components"]


def test_narrative_scores_accept_wrapped_shape(tmp_path):
    path = tmp_path / "narrative.json"
    path.write_text(
        '{"themes": {"Cybersecurity": {"narrative_keyword_score": 82}}}', encoding="utf-8"
    )

    scores = load_narrative_scores(str(path))
    theme = _theme("Cybersecurity", ["CRWD"], ["CIBR"])
    detail = calculate_theme_match(theme, [], {}, False, narrative_scores=scores)

    assert scores == {"Cybersecurity": 82.0}
    assert detail["theme_match_components"]["narrative_keyword_score"] == 82.0
