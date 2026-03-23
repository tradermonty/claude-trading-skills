"""
Fixed list of large-cap US stock candidates for institutional flow screening.
Replaces the FMP stock screener endpoint.
This covers the S&P 100 (top 100 by market cap in the S&P 500).
Update quarterly or when major index changes occur.
"""

SP100_CANDIDATES = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B",
    "LLY", "UNH", "JPM", "V", "XOM", "MA", "JNJ", "HD", "AVGO", "PG", "MRK",
    "COST", "ABBV", "CVX", "KO", "WMT", "AMD", "BAC", "NFLX", "CRM", "PEP",
    "TMO", "LIN", "ORCL", "ACN", "ADBE", "MCD", "ABT", "CSCO", "PM", "GE",
    "DHR", "TXN", "IBM", "INTU", "CAT", "AMGN", "MS", "GS", "RTX", "SPGI",
    "NEE", "ISRG", "BLK", "AXP", "SYK", "BKNG", "T", "ETN", "AMAT", "GILD",
    "VRTX", "PLD", "MDLZ", "ADI", "DE", "MMC", "CI", "REGN", "MU", "BSX",
    "HCA", "SO", "LRCX", "NOW", "ZTS", "SHW", "CB", "PANW", "MCO", "CME",
    "TJX", "ITW", "CL", "PGR", "FI", "DUK", "AON", "UBER", "EQIX", "APH",
    "KLAC", "WM", "NOC", "USB", "TGT", "ICE", "PH", "EMR", "SNPS", "CDNS",
]
