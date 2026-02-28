"""Tests for open_finviz_screener.py"""

from __future__ import annotations

import argparse
import subprocess
from unittest import mock

import pytest
from open_finviz_screener import (
    KNOWN_PREFIXES,
    VIEW_CODES,
    build_url,
    detect_elite,
    open_browser,
    validate_filters,
    validate_order,
)


# ---------------------------------------------------------------------------
# TestBuildUrl
# ---------------------------------------------------------------------------
class TestBuildUrl:
    """URL construction for various configurations."""

    def test_public_overview_default(self):
        url = build_url(["cap_small", "fa_div_o3"])
        assert url == "https://finviz.com/screener.ashx?v=111&f=cap_small,fa_div_o3"

    def test_elite_url(self):
        url = build_url(["cap_small", "fa_div_o3"], elite=True)
        assert url.startswith("https://elite.finviz.com/screener.ashx")
        assert "f=cap_small,fa_div_o3" in url

    def test_valuation_view(self):
        url = build_url(["fa_pe_u20"], view="valuation")
        assert "v=121" in url

    def test_financial_view(self):
        url = build_url(["fa_roe_o15"], view="financial")
        assert "v=161" in url

    def test_technical_view(self):
        url = build_url(["ta_rsi_os30"], view="technical")
        assert "v=171" in url

    def test_ownership_view(self):
        url = build_url(["fa_insttown_o50"], view="ownership")
        assert "v=131" in url

    def test_performance_view(self):
        url = build_url(["ta_perf_13wup"], view="performance")
        assert "v=141" in url

    def test_custom_view(self):
        url = build_url(["cap_large"], view="custom")
        assert "v=152" in url

    def test_order_parameter(self):
        url = build_url(["cap_small"], order="-marketcap")
        assert "&o=-marketcap" in url

    def test_no_order_parameter(self):
        url = build_url(["cap_small"])
        assert "&o=" not in url

    def test_unknown_view_falls_back_to_overview(self):
        url = build_url(["cap_small"], view="nonexistent")
        assert "v=111" in url

    def test_all_view_codes_covered(self):
        expected = {"111", "121", "131", "141", "152", "161", "171"}
        assert set(VIEW_CODES.values()) == expected


# ---------------------------------------------------------------------------
# TestValidateFilters
# ---------------------------------------------------------------------------
class TestValidateFilters:
    """Filter token validation."""

    # --- Valid tokens ---
    def test_single_filter(self):
        result = validate_filters("cap_small")
        assert result == ["cap_small"]

    def test_multiple_filters(self):
        result = validate_filters("cap_small,fa_div_o3,fa_pe_u20")
        assert result == ["cap_small", "fa_div_o3", "fa_pe_u20"]

    def test_whitespace_trimming(self):
        result = validate_filters("  cap_small , fa_div_o3  ")
        assert result == ["cap_small", "fa_div_o3"]

    def test_filter_with_dot(self):
        result = validate_filters("fa_ltdebteq_u0.5")
        assert result == ["fa_ltdebteq_u0.5"]

    def test_long_prefix_earningsdate(self):
        result = validate_filters("earningsdate_thisweek")
        assert result == ["earningsdate_thisweek"]

    def test_filter_with_hyphen(self):
        """Filters like fa_grossmargin_u-10 contain hyphens."""
        result = validate_filters("fa_grossmargin_u-10")
        assert result == ["fa_grossmargin_u-10"]

    def test_filter_with_hyphen_negative_value(self):
        result = validate_filters("fa_roa_u-50,sh_insidertrans_u-90")
        assert result == ["fa_roa_u-50", "sh_insidertrans_u-90"]

    def test_known_prefixes_accepted(self):
        # One filter from each known prefix category
        tokens = [
            "an_recom_strongbuy",
            "cap_large",
            "earningsdate_thisweek",
            "etf_return_1yo10",
            "exch_nasd",
            "fa_pe_u20",
            "geo_usa",
            "idx_sp500",
            "ind_semiconductors",
            "ipodate_prevweek",
            "news_date_today",
            "sec_technology",
            "sh_avgvol_o200",
            "subtheme_aiadssearch",
            "ta_rsi_os30",
            "targetprice_a20",
            "theme_artificialintelligence",
        ]
        result = validate_filters(",".join(tokens))
        assert len(result) == len(tokens)

    # --- Range pattern tokens ---
    def test_filter_with_range_pattern(self):
        """Range filter like fa_div_3to8 should pass validation."""
        result = validate_filters("fa_div_3to8")
        assert result == ["fa_div_3to8"]

    def test_filter_with_decimal_range(self):
        """Decimal range filter like ta_beta_0.5to1.5 should pass validation."""
        result = validate_filters("ta_beta_0.5to1.5")
        assert result == ["ta_beta_0.5to1.5"]

    def test_filter_with_custom_highlow_below_high(self):
        """Custom 52-week below-high range like ta_highlow52w_10to30-bhx should pass."""
        result = validate_filters("ta_highlow52w_10to30-bhx")
        assert result == ["ta_highlow52w_10to30-bhx"]

    def test_filter_with_custom_highlow_above_low(self):
        """Custom 52-week above-low range like ta_highlow52w_10to30-alx should pass."""
        result = validate_filters("ta_highlow52w_10to30-alx")
        assert result == ["ta_highlow52w_10to30-alx"]

    # --- Rejected tokens (URL injection) ---
    def test_reject_ampersand(self):
        with pytest.raises(SystemExit):
            validate_filters("cap_small&evil=1")

    def test_reject_equals(self):
        with pytest.raises(SystemExit):
            validate_filters("cap_small=bad")

    def test_reject_space_in_token(self):
        with pytest.raises(SystemExit):
            validate_filters("cap small")

    def test_reject_url_encoded(self):
        with pytest.raises(SystemExit):
            validate_filters("cap%20small")

    def test_reject_uppercase(self):
        with pytest.raises(SystemExit):
            validate_filters("Cap_Small")

    def test_reject_semicolon(self):
        with pytest.raises(SystemExit):
            validate_filters("cap_small;drop")

    def test_reject_slash(self):
        with pytest.raises(SystemExit):
            validate_filters("cap_small/evil")

    def test_reject_question_mark(self):
        with pytest.raises(SystemExit):
            validate_filters("cap_small?v=111")

    # --- Empty input ---
    def test_reject_empty_string(self):
        with pytest.raises(SystemExit):
            validate_filters("")

    def test_reject_only_commas(self):
        with pytest.raises(SystemExit):
            validate_filters(",,,")

    # --- Unknown prefix warning (stderr, no error) ---
    def test_unknown_prefix_warns(self, capsys):
        result = validate_filters("xyz_something")
        assert result == ["xyz_something"]
        captured = capsys.readouterr()
        assert "Warning: Unknown filter prefix" in captured.err

    def test_known_prefix_no_warning(self, capsys):
        validate_filters("fa_pe_u20")
        captured = capsys.readouterr()
        assert "Warning" not in captured.err

    def test_known_prefixes_count(self):
        """All 17 FinViz filter prefixes are registered."""
        assert len(KNOWN_PREFIXES) == 17


# ---------------------------------------------------------------------------
# TestValidateOrder
# ---------------------------------------------------------------------------
class TestValidateOrder:
    """Order parameter validation."""

    # --- Valid orders ---
    def test_simple_order(self):
        assert validate_order("marketcap") == "marketcap"

    def test_descending_order(self):
        assert validate_order("-marketcap") == "-marketcap"

    def test_order_with_underscore(self):
        assert validate_order("dividend_yield") == "dividend_yield"

    def test_order_with_digits(self):
        assert validate_order("sma200") == "sma200"

    # --- Rejected orders (URL injection) ---
    def test_reject_ampersand(self):
        with pytest.raises(SystemExit):
            validate_order("-marketcap&evil=1")

    def test_reject_equals(self):
        with pytest.raises(SystemExit):
            validate_order("order=bad")

    def test_reject_space(self):
        with pytest.raises(SystemExit):
            validate_order("market cap")

    def test_reject_url_encoded(self):
        with pytest.raises(SystemExit):
            validate_order("-market%20cap")

    def test_reject_semicolon(self):
        with pytest.raises(SystemExit):
            validate_order("-marketcap;drop")

    def test_reject_uppercase(self):
        with pytest.raises(SystemExit):
            validate_order("-MarketCap")

    def test_reject_dot(self):
        with pytest.raises(SystemExit):
            validate_order("market.cap")


# ---------------------------------------------------------------------------
# TestEliteDetection
# ---------------------------------------------------------------------------
class TestEliteDetection:
    """Elite vs Public detection logic."""

    def _make_args(self, elite: bool = False) -> argparse.Namespace:
        return argparse.Namespace(elite=elite)

    def test_elite_flag_explicit(self):
        args = self._make_args(elite=True)
        assert detect_elite(args) is True

    def test_env_var_present(self):
        args = self._make_args(elite=False)
        with mock.patch.dict(
            "os.environ",
            {"FINVIZ_API_KEY": "test_key_123"},  # pragma: allowlist secret
        ):
            assert detect_elite(args) is True

    def test_no_flag_no_env(self):
        args = self._make_args(elite=False)
        with mock.patch.dict("os.environ", {}, clear=True):
            assert detect_elite(args) is False

    def test_elite_flag_overrides_missing_env(self):
        args = self._make_args(elite=True)
        with mock.patch.dict("os.environ", {}, clear=True):
            assert detect_elite(args) is True

    def test_empty_env_var_not_detected(self):
        args = self._make_args(elite=False)
        with mock.patch.dict("os.environ", {"FINVIZ_API_KEY": ""}):
            assert detect_elite(args) is False


# ---------------------------------------------------------------------------
# TestOpenBrowser
# ---------------------------------------------------------------------------
class TestOpenBrowser:
    """Browser opening with OS-specific fallbacks."""

    @mock.patch("open_finviz_screener.sys")
    @mock.patch("open_finviz_screener.subprocess.run")
    def test_macos_chrome(self, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        mock_run.return_value = mock.MagicMock(returncode=0)
        open_browser("https://finviz.com/screener.ashx?v=111&f=cap_small")
        mock_run.assert_called_once_with(
            ["open", "-a", "Google Chrome", "https://finviz.com/screener.ashx?v=111&f=cap_small"],
            check=True,
            capture_output=True,
        )

    @mock.patch("open_finviz_screener.sys")
    @mock.patch("open_finviz_screener.subprocess.run")
    def test_macos_fallback_to_open(self, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        # First call (Chrome) fails, second call (open) succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "open"),
            mock.MagicMock(returncode=0),
        ]
        open_browser("https://finviz.com/screener.ashx?v=111&f=cap_small")
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == [
            "open",
            "https://finviz.com/screener.ashx?v=111&f=cap_small",
        ]

    @mock.patch("open_finviz_screener.sys")
    @mock.patch("open_finviz_screener.shutil.which")
    @mock.patch("open_finviz_screener.subprocess.run")
    def test_linux_chrome(self, mock_run, mock_which, mock_sys):
        mock_sys.platform = "linux"
        mock_which.return_value = "/usr/bin/google-chrome"
        mock_run.return_value = mock.MagicMock(returncode=0)
        open_browser("https://finviz.com/screener.ashx?v=111&f=cap_small")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "google-chrome"

    @mock.patch("open_finviz_screener.webbrowser.open")
    @mock.patch("open_finviz_screener.subprocess.run")
    def test_fallback_to_webbrowser(self, mock_run, mock_wb_open):
        # Both macOS calls fail → webbrowser fallback
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "open"),
            subprocess.CalledProcessError(1, "open"),
        ]
        url = "https://finviz.com/screener.ashx?v=111&f=cap_small"
        open_browser(url)
        mock_wb_open.assert_called_once_with(url)


# ---------------------------------------------------------------------------
# TestMainIntegration
# ---------------------------------------------------------------------------
class TestMainIntegration:
    """Integration tests via parse_args + main logic."""

    def test_url_only_prints_url(self, capsys):
        from open_finviz_screener import main

        with mock.patch.dict("os.environ", {}, clear=True):
            main(["--filters", "cap_small,fa_div_o3", "--url-only"])
        captured = capsys.readouterr()
        assert "https://finviz.com/screener.ashx" in captured.out
        assert "cap_small,fa_div_o3" in captured.out
        assert "[Public]" in captured.out

    def test_elite_flag_in_output(self, capsys):
        from open_finviz_screener import main

        with mock.patch.dict("os.environ", {}, clear=True):
            main(["--filters", "cap_small", "--elite", "--url-only"])
        captured = capsys.readouterr()
        assert "[Elite]" in captured.out
        assert "elite.finviz.com" in captured.out

    def test_view_selection(self, capsys):
        from open_finviz_screener import main

        with mock.patch.dict("os.environ", {}, clear=True):
            main(["--filters", "fa_pe_u20", "--view", "valuation", "--url-only"])
        captured = capsys.readouterr()
        assert "v=121" in captured.out

    def test_order_in_output(self, capsys):
        from open_finviz_screener import main

        with mock.patch.dict("os.environ", {}, clear=True):
            # Use = syntax because argparse treats -marketcap as a flag
            main(["--filters", "cap_small", "--order=-marketcap", "--url-only"])
        captured = capsys.readouterr()
        assert "o=-marketcap" in captured.out
