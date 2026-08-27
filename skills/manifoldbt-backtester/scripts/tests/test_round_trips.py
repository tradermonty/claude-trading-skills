"""Tests for the fill-to-round-trip pairing.

Every case here is one the naive "zip consecutive rows" approach gets wrong.
That is the point of the module, so it is the point of the tests.
"""

import pytest
from round_trips import SIDE_BUY, SIDE_SELL, pair_round_trips, summarize_round_trips

# ---------------------------------------------------------------- the simple case


def test_long_round_trip_returns_price_move(fill):
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_SELL, 110.0, 10),
        ]
    )
    assert len(trips) == 1
    assert trips[0]["direction"] == "long"
    assert trips[0]["return_pct"] == 10.0
    assert trips[0]["entry_price"] == 100.0
    assert trips[0]["exit_price"] == 110.0


def test_open_position_at_end_is_dropped(fill):
    """An entry with no exit has no return, and must not inflate the count."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_SELL, 110.0, 10),
            fill(SIDE_BUY, 105.0, 10),
        ]
    )
    assert len(trips) == 1


# --------------------------------------------------------- what naive zipping breaks


def test_short_round_trip_is_signed_by_direction(fill):
    """A sell that OPENS is a short: a price fall is a gain, not a loss.

    Zipping rows in pairs and computing (exit - entry) / entry would report
    -10% here, sign-flipping the entire short side of a strategy.
    """
    trips = pair_round_trips(
        [
            fill(SIDE_SELL, 100.0, 10),
            fill(SIDE_BUY, 90.0, 10),
        ]
    )
    assert len(trips) == 1
    assert trips[0]["direction"] == "short"
    assert trips[0]["return_pct"] == 10.0


def test_scaling_in_uses_weighted_average_entry(fill):
    """Two entries then one exit is ONE round trip, not two.

    Naive pairing reads (buy, buy) as a trip and leaves the exit dangling.
    """
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_BUY, 200.0, 10),
            fill(SIDE_SELL, 180.0, 20),
        ]
    )
    assert len(trips) == 1
    assert trips[0]["entry_price"] == 150.0  # weighted, not last, not first
    assert trips[0]["return_pct"] == 20.0
    assert trips[0]["quantity"] == 20


def test_scaling_out_closes_once_flat(fill):
    """One entry answered by two exits is still one round trip."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 20),
            fill(SIDE_SELL, 110.0, 10),
            fill(SIDE_SELL, 130.0, 10),
        ]
    )
    assert len(trips) == 1
    assert trips[0]["exit_price"] == 120.0  # weighted across both exits
    assert trips[0]["return_pct"] == 20.0


def test_scaling_out_then_back_in_uses_whole_lifecycle_cash_flows(fill):
    """A re-add must not mix the remaining-position entry with all exits."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_SELL, 110.0, 4),
            fill(SIDE_BUY, 120.0, 5),
            fill(SIDE_SELL, 130.0, 11),
        ]
    )

    assert len(trips) == 1
    trip = trips[0]
    assert trip["entry_qty"] == pytest.approx(15.0)
    assert trip["exit_qty"] == pytest.approx(15.0)
    assert trip["entry_value"] == pytest.approx(1_600.0)
    assert trip["exit_value"] == pytest.approx(1_870.0)
    assert trip["entry_price"] == pytest.approx(1_600.0 / 15.0)
    assert trip["exit_price"] == pytest.approx(1_870.0 / 15.0)
    assert trip["gross_pnl"] == pytest.approx(270.0)
    assert trip["net_pnl"] == pytest.approx(270.0)
    assert trip["gross_return_pct"] == pytest.approx(16.875)
    assert trip["return_pct"] == pytest.approx(16.875)


def test_scaling_out_then_back_in_cannot_flip_a_loser_to_a_win(fill):
    """Regression for the silent sign flip reported in PR #325 review."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_SELL, 50.0, 9),
            fill(SIDE_BUY, 50.0, 100),
            fill(SIDE_SELL, 51.0, 101),
        ]
    )

    assert len(trips) == 1
    trip = trips[0]
    assert trip["entry_value"] == pytest.approx(6_000.0)
    assert trip["exit_value"] == pytest.approx(5_601.0)
    assert trip["gross_pnl"] == pytest.approx(-399.0)
    assert trip["return_pct"] == pytest.approx(-6.65)

    summary = summarize_round_trips(trips)
    assert summary["wins"] == 0
    assert summary["losses"] == 1


def test_short_scaling_out_then_back_in_uses_whole_lifecycle_cash_flows(fill):
    trips = pair_round_trips(
        [
            fill(SIDE_SELL, 100.0, 10),
            fill(SIDE_BUY, 90.0, 4),
            fill(SIDE_SELL, 80.0, 5),
            fill(SIDE_BUY, 70.0, 11),
        ]
    )

    assert len(trips) == 1
    trip = trips[0]
    assert trip["entry_qty"] == pytest.approx(15.0)
    assert trip["exit_qty"] == pytest.approx(15.0)
    assert trip["entry_value"] == pytest.approx(1_400.0)
    assert trip["exit_value"] == pytest.approx(1_130.0)
    assert trip["gross_pnl"] == pytest.approx(270.0)
    assert trip["gross_return_pct"] == pytest.approx(100.0 * 270.0 / 1_400.0)


def test_reversal_splits_into_close_then_open(fill):
    """A fill that crosses through flat closes one trip and opens the next.

    Booking it as a single event would invent an entry price that never traded.
    """
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10),
            fill(SIDE_SELL, 110.0, 20),  # closes the long, opens a short of 10
            fill(SIDE_BUY, 99.0, 10),  # closes the short
        ]
    )
    assert len(trips) == 2
    assert trips[0]["direction"] == "long"
    assert trips[0]["return_pct"] == 10.0
    assert trips[1]["direction"] == "short"
    assert trips[1]["entry_price"] == 110.0
    assert round(trips[1]["return_pct"], 6) == 10.0


def test_symbols_do_not_contaminate_each_other(fill):
    """Interleaved fills across a universe must pair per symbol."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 1, symbol_id=1),
            fill(SIDE_BUY, 50.0, 1, symbol_id=2),
            fill(SIDE_SELL, 110.0, 1, symbol_id=1),
            fill(SIDE_SELL, 45.0, 1, symbol_id=2),
        ]
    )
    assert len(trips) == 2
    par_sym = {t["symbol_id"]: t["return_pct"] for t in trips}
    assert par_sym[1] == 10.0
    assert par_sym[2] == -10.0


def test_float_dust_on_close_reads_as_flat(fill):
    """Fraction-of-equity sizing leaves dust; dust must not read as still open."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10.0),
            fill(SIDE_SELL, 110.0, 10.0 - 1e-12),
        ]
    )
    assert len(trips) == 1


# ------------------------------------------------------------------ net of fees


def test_return_is_net_of_fees_and_gross_is_kept_alongside(fill):
    """10% on price, 1% of notional in fees, is a 9% trade."""
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10, fees=5.0),
            fill(SIDE_SELL, 110.0, 10, fees=5.0),
        ]
    )
    assert trips[0]["gross_return_pct"] == 10.0
    assert round(trips[0]["return_pct"], 6) == 9.0
    assert trips[0]["fees"] == 10.0


def test_a_gross_winner_eaten_by_fees_counts_as_a_loser(fill):
    """The case that makes gross the wrong basis.

    Price moved in the strategy's favour, the trade still lost money. Counting
    it as a win inflates the win rate and, with it, the expectancy the quality
    framework computes.
    """
    trips = pair_round_trips(
        [
            fill(SIDE_BUY, 100.0, 10, fees=5.0),
            fill(SIDE_SELL, 100.1, 10, fees=5.0),
        ]
    )
    assert trips[0]["gross_return_pct"] > 0
    assert trips[0]["return_pct"] < 0
    s = summarize_round_trips(trips)
    assert s["wins"] == 0
    assert s["losses"] == 1


def test_short_return_is_also_net(fill):
    trips = pair_round_trips(
        [
            fill(SIDE_SELL, 100.0, 10, fees=5.0),
            fill(SIDE_BUY, 90.0, 10, fees=5.0),
        ]
    )
    assert trips[0]["gross_return_pct"] == 10.0
    assert round(trips[0]["return_pct"], 6) == 9.0


# ------------------------------------------------------------------- the aggregate


def test_summary_reports_loss_magnitude_positive(fill):
    """The quality framework asks for the magnitude of the average loser."""
    s = summarize_round_trips(
        pair_round_trips(
            [
                fill(SIDE_BUY, 100.0, 1),
                fill(SIDE_SELL, 90.0, 1),
            ]
        )
    )
    assert s["avg_loss_pct"] == 10.0
    assert s["losses"] == 1
    assert s["avg_win_pct"] == 0.0


def test_scratch_trades_remain_in_win_rate_denominator(fill):
    """A flat trade is neither a win nor a loss.

    It is still a completed trade that did not win, so omitting it from the
    denominator would overstate the observed win rate.
    """
    s = summarize_round_trips(
        pair_round_trips(
            [
                fill(SIDE_BUY, 100.0, 1),
                fill(SIDE_SELL, 110.0, 1),  # win
                fill(SIDE_BUY, 100.0, 1),
                fill(SIDE_SELL, 100.0, 1),  # scratch
            ]
        )
    )
    assert s["total_trades"] == 2
    assert s["scratches"] == 1
    assert s["win_rate_pct"] == 50.0


def test_empty_log_summarizes_without_dividing_by_zero():
    s = summarize_round_trips(pair_round_trips([]))
    assert s["total_trades"] == 0
    assert s["win_rate_pct"] == 0.0
    assert s["avg_win_pct"] == 0.0
    assert s["avg_loss_pct"] == 0.0
