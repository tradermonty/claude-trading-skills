from decimal import Decimal as D

from app.journal.pnl import Fill, compute, dec, r_multiple, summarize


def test_dec_parses_money_text():
    assert dec("$1,234.50") == D("1234.50")
    assert dec("($12.00)") == D("-12.00")
    assert dec("") == D("0")
    assert dec("abc", None) is None


def test_long_stock_round_trip_with_fees():
    r = compute([Fill("buy", D("10"), D("50"), D("1")), Fill("sell", D("10"), D("55"), D("1"))])
    assert r.realized_gross == D("50")
    assert r.net == D("48")
    assert r.status == "closed"


def test_partial_exit_fifo():
    r = compute(
        [
            Fill("buy", D("10"), D("10")),
            Fill("buy", D("10"), D("20")),
            Fill("sell", D("15"), D("30")),
        ]
    )
    # 10 @ 10 -> +200, 5 @ 20 -> +50
    assert r.realized_gross == D("250")
    assert r.status == "open"
    assert r.legs[0].open_qty == D("5")


def test_short_option_uses_multiplier():
    r = compute(
        [
            Fill("sell", D("1"), D("2.00"), multiplier=D("100")),
            Fill("buy", D("1"), D("0.50"), multiplier=D("100")),
        ]
    )
    assert r.realized_gross == D("150")
    assert r.first_side == "sell"


def test_vertical_spread_two_legs():
    r = compute(
        [
            Fill("buy", D("1"), D("3.00"), multiplier=D("100"), instrument="250C"),
            Fill("sell", D("1"), D("1.00"), multiplier=D("100"), instrument="260C"),
            Fill("sell", D("1"), D("5.00"), multiplier=D("100"), instrument="250C"),
            Fill("buy", D("1"), D("2.00"), multiplier=D("100"), instrument="260C"),
        ]
    )
    assert r.realized_gross == D("100")  # +200 long leg, -100 short leg
    assert r.status == "closed"


def test_crypto_fractional_and_coin_fee():
    r = compute(
        [
            Fill("buy", D("0.00123456"), D("50000"), D("0.00000100"), fee_in_quote=False),
            Fill("sell", D("0.00123456"), D("60000")),
        ]
    )
    assert r.realized_gross == D("12.34560000")
    assert r.fees == D("0.05000000")


def test_r_multiple_and_summary():
    assert r_multiple(D("100"), D("50"), D("45"), D("10"), D("1")) == D("2")
    assert r_multiple(D("100"), D("50"), None, D("10"), D("1")) is None
    s = summarize([{"net": D("100")}, {"net": D("-50")}, {"net": D("20")}])
    assert s["count"] == 3 and s["wins"] == 2
    assert s["profit_factor"] == D("120") / D("50")
    assert s["expectancy"] == D("70") / 3
