from decimal import Decimal as D

import pytest
from app.journal import robinhood

# Shape of Robinhood's account activity report: newest first, disclaimer at the end.
# Every value below is made up.
SAMPLE = """"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"
"11/14/2026","11/14/2026","11/17/2026","AAA","Option Expiration for AAA 11/14/2026 Call $20.00","OEXP","1S","",""
"11/12/2026","11/12/2026","11/13/2026","AAA","AAA 11/14/2026 Call $20.00","STO","1","$0.80","$79.95"
"11/10/2026","11/10/2026","11/12/2026","BBB","Example Corp","Sell","5","$12.00","$59.99"
"11/05/2026","11/05/2026","11/06/2026","BBB","Example Corp","Buy","10","$10.00","($100.00)"
"11/04/2026","11/04/2026","11/04/2026","","ACH Deposit","ACH","","","$500.00"
"11/03/2026","11/03/2026","11/03/2026","BBB","Cash Div: R/D 2026-10-30","CDIV","","","$0.25"
""
"","","","","","","","","The data provided is for informational purposes only."
"""


def test_parse_sample():
    res = robinhood.parse(SAMPLE.encode())
    assert [f.side for f in res.fills] == ["buy", "sell", "sell", "close"]
    buy, sell, sto, oexp = res.fills
    assert buy.symbol == "BBB" and buy.quantity == D("10") and buy.fee == D("0.00")
    assert sell.fee == D("0.01")
    assert sto.asset_class == "option" and sto.multiplier == D("100")
    assert sto.symbol == "AAA 2026-11-14 20.00 C"
    assert sto.strike == D("20.00") and sto.right == "call" and sto.expiry == "2026-11-14"
    assert sto.fee == D("0.05")
    assert oexp.note == "expired" and oexp.quantity == D("1")
    assert res.skipped == {"ACH": 1, "CDIV": 1}
    assert res.errors == []


def test_source_keys_stable_and_distinct_for_twin_rows():
    twin = SAMPLE.replace(
        '"11/05/2026",',
        '"11/05/2026","11/05/2026","11/06/2026","BBB","Example Corp","Buy","10","$10.00","($100.00)"\n"11/05/2026",',
        1,
    )
    a = robinhood.parse(twin)
    b = robinhood.parse(twin)
    keys = [f.source_key for f in a.fills]
    assert keys == [f.source_key for f in b.fills]
    assert len(set(keys)) == len(keys) == 5


def test_rejects_other_csv():
    with pytest.raises(robinhood.NotRobinhoodCSV):
        robinhood.parse(b"date,symbol,qty\n2026-11-01,AAA,1\n")
