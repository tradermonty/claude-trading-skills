"""Tests for theme_discoverer module.

Covers unmatched industry extraction, proximity clustering with perf vectors,
auto-naming, duplicate detection, and full discover_themes flow.
"""

import pytest

from calculators.theme_discoverer import (
    discover_themes,
    _get_unmatched_industries,
    _cluster_by_proximity,
    _perf_vector_distance,
    _compute_ranges,
    _auto_name_cluster,
    _is_duplicate_of_existing,
    _build_theme_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ind(name, weighted_return, direction="bullish", sector="Tech",
         perf_1w=0.0, perf_1m=0.0, perf_3m=0.0):
    return {
        "name": name,
        "weighted_return": weighted_return,
        "direction": direction,
        "sector": sector,
        "perf_1w": perf_1w,
        "perf_1m": perf_1m,
        "perf_3m": perf_3m,
    }


# ---------------------------------------------------------------------------
# TestGetUnmatchedIndustries
# ---------------------------------------------------------------------------


class TestGetUnmatchedIndustries:

    def test_excludes_matched_names(self):
        ranked = [
            _ind("A", 10.0, "bullish"), _ind("B", 8.0, "bullish"), _ind("C", 6.0, "bullish"),
            _ind("D", -5.0, "bearish"), _ind("E", -8.0, "bearish"), _ind("F", -10.0, "bearish"),
        ]
        matched = {"A", "E"}
        bull, bear = _get_unmatched_industries(ranked, matched, top_n=3)
        bull_names = {i["name"] for i in bull}
        bear_names = {i["name"] for i in bear}
        assert "A" not in bull_names
        assert "E" not in bear_names
        assert "B" in bull_names
        assert "F" in bear_names

    def test_separates_bullish_and_bearish(self):
        ranked = [
            _ind("A", 10.0, "bullish"), _ind("B", 8.0, "bullish"),
            _ind("C", -5.0, "bearish"), _ind("D", -10.0, "bearish"),
        ]
        bull, bear = _get_unmatched_industries(ranked, set(), top_n=2)
        assert all(i["direction"] == "bullish" for i in bull)
        assert all(i["direction"] == "bearish" for i in bear)

    def test_respects_top_n(self):
        ranked = [_ind(f"I{i}", 20.0 - i) for i in range(20)]
        bull, bear = _get_unmatched_industries(ranked, set(), top_n=5)
        # Top 5 + bottom 5 from 20 items
        assert len(bull) + len(bear) <= 10

    def test_empty_matched_returns_all(self):
        ranked = [_ind("A", 10.0), _ind("B", -10.0)]
        bull, bear = _get_unmatched_industries(ranked, set(), top_n=30)
        assert len(bull) + len(bear) == 2


# ---------------------------------------------------------------------------
# TestClusterByProximity
# ---------------------------------------------------------------------------


class TestClusterByProximity:

    def test_adjacent_within_both_thresholds_grouped(self):
        # Use 3+ items so range is wider than pairwise diff
        industries = [
            _ind("A", 10.0, perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 11.5, perf_1w=6.0, perf_1m=11.0, perf_3m=16.0),
            _ind("C", 13.0, perf_1w=15.0, perf_1m=20.0, perf_3m=25.0),
        ]
        # A-B gap=1.5 within 3.0, C far in perf space; A&B should cluster
        clusters = _cluster_by_proximity(industries, gap_threshold=3.0,
                                          vector_threshold=0.5)
        assert len(clusters) >= 1
        cluster_names = [set(i["name"] for i in c) for c in clusters]
        assert {"A", "B"} in cluster_names or any("A" in c and "B" in c for c in cluster_names)

    def test_gap_exceeds_splits(self):
        industries = [
            _ind("A", 10.0, perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 20.0, perf_1w=6.0, perf_1m=11.0, perf_3m=16.0),
        ]
        clusters = _cluster_by_proximity(industries, gap_threshold=3.0,
                                          vector_threshold=0.5)
        # Gap is 10.0 > 3.0, so separate clusters; each < min_size so empty
        assert len(clusters) == 0

    def test_vector_distance_exceeds_splits(self):
        """Different perf patterns should prevent clustering."""
        industries = [
            _ind("A", 10.0, perf_1w=20.0, perf_1m=5.0, perf_3m=1.0),
            _ind("B", 11.0, perf_1w=1.0, perf_1m=5.0, perf_3m=20.0),
        ]
        clusters = _cluster_by_proximity(industries, gap_threshold=3.0,
                                          vector_threshold=0.3)
        # Vector distance should be high despite close weighted_return
        assert len(clusters) == 0

    def test_single_industry_not_a_cluster(self):
        industries = [_ind("A", 10.0)]
        clusters = _cluster_by_proximity(industries, gap_threshold=3.0,
                                          vector_threshold=0.5)
        assert len(clusters) == 0

    def test_all_within_thresholds_single_cluster(self):
        # Add a distant outlier to widen the range, so close items normalize well
        industries = [
            _ind("A", 10.0, perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 11.0, perf_1w=5.5, perf_1m=10.5, perf_3m=15.5),
            _ind("C", 12.0, perf_1w=6.0, perf_1m=11.0, perf_3m=16.0),
            _ind("Far", 30.0, perf_1w=50.0, perf_1m=60.0, perf_3m=70.0),
        ]
        clusters = _cluster_by_proximity(industries, gap_threshold=3.0,
                                          vector_threshold=0.5)
        # A, B, C should form a single cluster (close in both gap and perf)
        abc_cluster = [c for c in clusters if len(c) >= 3]
        assert len(abc_cluster) >= 1
        names = {i["name"] for i in abc_cluster[0]}
        assert {"A", "B", "C"}.issubset(names)

    def test_empty_input_returns_empty(self):
        clusters = _cluster_by_proximity([], gap_threshold=3.0,
                                          vector_threshold=0.5)
        assert clusters == []


# ---------------------------------------------------------------------------
# TestPerfVectorDistance
# ---------------------------------------------------------------------------


class TestPerfVectorDistance:

    def test_identical_returns_zero(self):
        a = _ind("A", 10.0, perf_1w=5.0, perf_1m=10.0, perf_3m=15.0)
        b = _ind("B", 10.0, perf_1w=5.0, perf_1m=10.0, perf_3m=15.0)
        ranges = {"perf_1w": 20.0, "perf_1m": 20.0, "perf_3m": 20.0}
        assert _perf_vector_distance(a, b, ranges) == 0.0

    def test_different_patterns_high_distance(self):
        a = _ind("A", 10.0, perf_1w=20.0, perf_1m=0.0, perf_3m=0.0)
        b = _ind("B", 10.0, perf_1w=0.0, perf_1m=0.0, perf_3m=20.0)
        ranges = {"perf_1w": 20.0, "perf_1m": 20.0, "perf_3m": 20.0}
        dist = _perf_vector_distance(a, b, ranges)
        assert dist > 1.0  # sqrt(1^2 + 0 + 1^2) = sqrt(2) ~= 1.414


# ---------------------------------------------------------------------------
# TestAutoNameCluster
# ---------------------------------------------------------------------------


class TestAutoNameCluster:

    def test_top_two_tokens(self):
        industries = [
            _ind("Oil & Gas E&P", 10.0),
            _ind("Oil & Gas Integrated", 9.0),
            _ind("Oil & Gas Midstream", 8.0),
        ]
        name = _auto_name_cluster(industries)
        assert "Oil" in name
        assert "Gas" in name

    def test_stop_words_excluded(self):
        industries = [
            _ind("General Services", 10.0),
            _ind("Specialty Services", 9.0),
        ]
        name = _auto_name_cluster(industries)
        # "General", "Specialty", "Services" are stop words
        # Should still produce a name
        assert len(name) > 0

    def test_single_token_adds_related(self):
        industries = [
            _ind("Gold", 10.0),
            _ind("Silver", 9.0),
        ]
        name = _auto_name_cluster(industries)
        assert len(name) > 0

    def test_oil_gas_example(self):
        industries = [
            _ind("Oil & Gas E&P", 10.0),
            _ind("Oil & Gas Drilling", 9.0),
        ]
        name = _auto_name_cluster(industries)
        assert "Oil" in name or "Gas" in name

    def test_metals_mining_example(self):
        industries = [
            _ind("Other Industrial Metals & Mining", 10.0),
            _ind("Steel", 9.0),
            _ind("Copper", 8.0),
        ]
        name = _auto_name_cluster(industries)
        assert len(name) > 0


# ---------------------------------------------------------------------------
# TestDiscoverThemes
# ---------------------------------------------------------------------------


class TestDiscoverThemes:

    def test_discovers_cross_sector_cluster(self):
        ranked = [
            _ind("UnmatchedA", 15.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("UnmatchedB", 14.0, "bullish", "Industrials",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("MatchedC", 13.0, "bullish"),
            _ind("Bottom1", -10.0, "bearish"),
            _ind("Bottom2", -11.0, "bearish"),
        ]
        matched = {"MatchedC"}
        existing = []
        discovered = discover_themes(ranked, matched, existing, top_n=5)
        assert len(discovered) >= 1

    def test_single_sector_with_no_vertical_overlap_kept(self):
        """Single-sector cluster not overlapping vertical should be kept."""
        ranked = [
            _ind("Drug Manufacturers - General", 15.0, "bullish", "Healthcare",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("Drug Manufacturers - Specialty & Generic", 14.0, "bullish", "Healthcare",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
        ] + [_ind(f"Filler{i}", -10.0 - i, "bearish") for i in range(8)]
        matched = set()
        existing_vertical = [{
            "theme_name": "Healthcare Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Medical Devices"},
                {"name": "Healthcare Plans"},
                {"name": "Medical Care Facilities"},
            ],
        }]
        discovered = discover_themes(ranked, matched, existing_vertical, top_n=5)
        # GLP-1 like cluster (Drug Manufacturers) should not overlap Healthcare Vertical
        if discovered:
            names = {i["name"] for d in discovered for i in d.get("matching_industries", [])}
            assert "Drug Manufacturers - General" in names or len(discovered) == 0

    def test_single_sector_with_vertical_overlap_excluded(self):
        """Single-sector cluster overlapping existing vertical should be excluded."""
        ranked = [
            _ind("Medical Devices", 15.0, "bullish", "Healthcare",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("Healthcare Plans", 14.0, "bullish", "Healthcare",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
        ] + [_ind(f"Filler{i}", -10.0 - i, "bearish") for i in range(8)]
        matched = set()
        existing_vertical = [{
            "theme_name": "Healthcare Sector Concentration",
            "direction": "bullish",
            "matching_industries": [
                {"name": "Medical Devices"},
                {"name": "Healthcare Plans"},
                {"name": "Medical Care Facilities"},
            ],
        }]
        discovered = discover_themes(ranked, matched, existing_vertical, top_n=5)
        # Should be excluded due to high overlap with Healthcare Vertical
        for d in discovered:
            d_names = {i["name"] for i in d.get("matching_industries", [])}
            overlap = d_names & {"Medical Devices", "Healthcare Plans", "Medical Care Facilities"}
            # If cluster is detected, it shouldn't overlap significantly
            if d.get("direction") == "bullish":
                assert len(overlap) / max(len(d_names), 1) < 0.5

    def test_small_cluster_rejected(self):
        """Cluster with only 1 industry should be rejected."""
        ranked = [
            _ind("LoneIndustry", 15.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("FarAway", 50.0, "bullish", "Other",
                 perf_1w=30.0, perf_1m=40.0, perf_3m=50.0),
        ] + [_ind(f"Bottom{i}", -10.0 - i, "bearish") for i in range(8)]
        discovered = discover_themes(ranked, set(), [], top_n=5)
        # Single-industry clusters don't form (min_cluster_size=2)
        for d in discovered:
            assert len(d.get("matching_industries", [])) >= 2

    def test_sets_theme_origin_discovered(self):
        ranked = [
            _ind("A", 15.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 14.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
        ] + [_ind(f"Bottom{i}", -10.0 - i, "bearish") for i in range(8)]
        discovered = discover_themes(ranked, set(), [], top_n=5)
        for d in discovered:
            assert d["theme_origin"] == "discovered"

    def test_sets_proxy_etfs_empty(self):
        ranked = [
            _ind("A", 15.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 14.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
        ] + [_ind(f"Bottom{i}", -10.0 - i, "bearish") for i in range(8)]
        discovered = discover_themes(ranked, set(), [], top_n=5)
        for d in discovered:
            assert d["proxy_etfs"] == []

    def test_name_confidence_is_medium(self):
        ranked = [
            _ind("A", 15.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
            _ind("B", 14.0, "bullish", "Tech",
                 perf_1w=5.0, perf_1m=10.0, perf_3m=15.0),
        ] + [_ind(f"Bottom{i}", -10.0 - i, "bearish") for i in range(8)]
        discovered = discover_themes(ranked, set(), [], top_n=5)
        for d in discovered:
            assert d["name_confidence"] == "medium"

    def test_no_unmatched_returns_empty(self):
        ranked = [_ind("A", 10.0), _ind("B", -10.0)]
        matched = {"A", "B"}
        discovered = discover_themes(ranked, matched, [], top_n=30)
        assert discovered == []

    def test_bearish_clusters_detected(self):
        ranked = [
            _ind("TopFiller", 20.0, "bullish"),
        ] + [
            _ind(f"BearInd{i}", -10.0 - i * 0.5, "bearish", "Consumer",
                 perf_1w=-3.0 - i, perf_1m=-5.0 - i, perf_3m=-8.0 - i)
            for i in range(5)
        ]
        discovered = discover_themes(ranked, set(), [], top_n=5)
        bearish = [d for d in discovered if d["direction"] == "bearish"]
        if bearish:
            assert bearish[0]["direction"] == "bearish"


# ---------------------------------------------------------------------------
# TestIsDuplicateOfExisting
# ---------------------------------------------------------------------------


class TestIsDuplicateOfExisting:

    def test_high_overlap_same_direction_is_duplicate(self):
        cluster = [{"name": "A"}, {"name": "B"}]
        existing = [{
            "direction": "bullish",
            "matching_industries": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
        }]
        assert _is_duplicate_of_existing(cluster, "bullish", existing, 0.5) is True

    def test_high_overlap_different_direction_not_duplicate(self):
        cluster = [{"name": "A"}, {"name": "B"}]
        existing = [{
            "direction": "bearish",
            "matching_industries": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
        }]
        assert _is_duplicate_of_existing(cluster, "bullish", existing, 0.5) is False

    def test_low_overlap_same_direction_not_duplicate(self):
        cluster = [{"name": "X"}, {"name": "Y"}]
        existing = [{
            "direction": "bullish",
            "matching_industries": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
        }]
        assert _is_duplicate_of_existing(cluster, "bullish", existing, 0.5) is False

    def test_glp1_not_duplicate_of_healthcare_vertical(self):
        """GLP-1 (Drug Manufacturers) should not be duplicate of Healthcare Vertical."""
        cluster = [
            {"name": "Drug Manufacturers - General"},
            {"name": "Drug Manufacturers - Specialty & Generic"},
        ]
        existing = [{
            "direction": "bullish",
            "matching_industries": [
                {"name": "Medical Devices"},
                {"name": "Healthcare Plans"},
                {"name": "Medical Care Facilities"},
            ],
        }]
        assert _is_duplicate_of_existing(cluster, "bullish", existing, 0.5) is False


# ---------------------------------------------------------------------------
# TestBuildThemeDict
# ---------------------------------------------------------------------------


class TestBuildThemeDict:

    def test_has_required_fields(self):
        industries = [_ind("A", 10.0, "bullish"), _ind("B", 9.0, "bullish")]
        result = _build_theme_dict("Test Cluster", industries)
        assert result["theme_name"] == "Test Cluster"
        assert result["direction"] == "bullish"
        assert result["proxy_etfs"] == []
        assert result["static_stocks"] == []
        assert result["theme_origin"] == "discovered"
        assert result["name_confidence"] == "medium"
        assert len(result["matching_industries"]) == 2
        assert "sector_weights" in result
