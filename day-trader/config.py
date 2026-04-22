"""Risk mode configurations for the day trading agent.

Three risk modes with distinct parameters:
  - LOW:    Conservative. Mean reversion only. No shorts, no margin. 2% position size.
  - MEDIUM: Balanced. Multiple strategies. Light shorts, 1.5x leverage. 5% position size.
  - HIGH:   Aggressive. All strategies including gap-and-go and short-the-rip.
            Heavy shorts, 4x day-trading margin. 25% position size. Margin calls enabled.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskMode:
    name: str
    description: str

    # Position sizing
    max_position_pct: float          # Max % of equity per position
    max_concurrent_positions: int     # Max simultaneous open positions
    min_trade_dollars: float          # Skip trades smaller than this ($)

    # Risk controls
    stop_loss_pct: float              # Stop loss as % of entry
    take_profit_pct: float            # Take profit as % of entry
    max_daily_loss_pct: float         # Halt trading if daily loss exceeds this

    # Advanced exits
    trailing_activation_pct: float    # Min unrealized gain before trailing stop arms
    trailing_retrace_pct: float       # Retrace from HWM that triggers exit
    stagnation_minutes: int           # Close position after this many min of sideways action
    eod_flatten_minutes: int          # Flatten all N minutes before market close

    # Leverage & shorting
    allow_shorts: bool
    max_short_positions: int
    max_leverage: float               # 1.0 = no margin, 4.0 = pattern day trader max
    margin_call_threshold: float      # Equity/position ratio that triggers margin call

    # Strategy selection
    allowed_strategies: List[str]

    # Universe of tradable symbols
    universe: List[str]

    # Scan/entry cadence (seconds between strategy scans)
    scan_interval_sec: int = 60


# Liquid large-cap universe (safest)
LARGE_CAP_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "JPM", "V", "MA", "UNH", "JNJ", "WMT", "PG", "KO",
]

# Mid/large cap with more movement
MID_LARGE_UNIVERSE = LARGE_CAP_UNIVERSE + [
    "AMD", "INTC", "CRM", "ADBE", "NFLX", "DIS", "BA", "CAT",
    "XOM", "CVX", "GS", "MS", "BAC", "WFC", "C",
    "COIN", "SQ", "PYPL", "SHOP", "UBER", "LYFT",
    "F", "GM", "RIVN", "LCID",
]

# High volatility universe — small caps, meme stocks, leveraged ETFs
HIGH_VOL_UNIVERSE = MID_LARGE_UNIVERSE + [
    "TQQQ", "SQQQ", "SOXL", "SOXS", "TNA", "TZA", "UVXY", "SVXY",
    "GME", "AMC", "PLTR", "MARA", "RIOT", "HOOD",
    "SMCI", "ARKK", "ARKG", "XBI",
    "NIO", "XPEV", "LI", "PDD", "BABA",
]


RISK_MODES = {
    "low": RiskMode(
        name="low",
        description="Conservative — mean reversion only, large caps, no shorts, no margin.",
        max_position_pct=0.02,              # 2% per position
        max_concurrent_positions=12,
        min_trade_dollars=2000.0,
        stop_loss_pct=0.01,                 # 1% stop
        take_profit_pct=0.02,               # 2% target (1:2 R:R)
        max_daily_loss_pct=0.02,            # halt at -2% daily
        trailing_activation_pct=0.01,       # arm after +1%
        trailing_retrace_pct=0.005,         # exit on 0.5% retrace from HWM
        stagnation_minutes=45,
        eod_flatten_minutes=5,
        allow_shorts=False,
        max_short_positions=0,
        max_leverage=1.0,                    # cash only
        margin_call_threshold=0.0,           # N/A
        allowed_strategies=["mean_reversion"],
        universe=LARGE_CAP_UNIVERSE,
        scan_interval_sec=120,
    ),

    "medium": RiskMode(
        name="medium",
        description="Balanced — multiple strategies, mid/large caps, light shorts, 1.5x margin.",
        max_position_pct=0.05,              # 5% per position
        max_concurrent_positions=16,
        min_trade_dollars=2000.0,
        stop_loss_pct=0.02,                 # 2% stop
        take_profit_pct=0.04,               # 4% target (1:2 R:R)
        max_daily_loss_pct=0.05,            # halt at -5% daily
        trailing_activation_pct=0.02,       # arm after +2%
        trailing_retrace_pct=0.01,          # exit on 1% retrace from HWM
        stagnation_minutes=45,
        eod_flatten_minutes=5,
        allow_shorts=True,
        max_short_positions=4,
        max_leverage=1.5,
        margin_call_threshold=0.30,          # 30% maintenance margin
        allowed_strategies=[
            "mean_reversion", "momentum", "ma_crossover", "vwap_bounce",
        ],
        universe=MID_LARGE_UNIVERSE,
        scan_interval_sec=60,
    ),

    "high": RiskMode(
        name="high",
        description="Aggressive — all strategies, high-vol names, heavy shorts, 4x margin, margin calls ENABLED.",
        max_position_pct=0.15,              # 15% per position (hard-capped)
        max_concurrent_positions=12,
        min_trade_dollars=2000.0,
        stop_loss_pct=0.05,                 # 5% stop (wide — lets positions breathe)
        take_profit_pct=0.15,               # 15% target (home-run hunting)
        max_daily_loss_pct=0.25,            # halt at -25% daily (near blow-up)
        trailing_activation_pct=0.05,       # arm after +5%
        trailing_retrace_pct=0.03,          # exit on 3% retrace from HWM
        stagnation_minutes=20,              # HIGH mode moves fast — exit dead trades quicker
        eod_flatten_minutes=5,
        allow_shorts=True,
        max_short_positions=6,
        max_leverage=4.0,                    # pattern day trader max
        margin_call_threshold=0.25,          # 25% maintenance — aggressive liquidation
        allowed_strategies=[
            "mean_reversion", "momentum", "ma_crossover", "vwap_bounce",
            "gap_and_go", "short_the_rip", "breakout",
        ],
        universe=HIGH_VOL_UNIVERSE,
        scan_interval_sec=30,                # scan every 30s — fast moves
    ),
}


def get_risk_mode(name: str) -> RiskMode:
    name = (name or "medium").lower()
    if name not in RISK_MODES:
        raise ValueError(f"Unknown risk mode '{name}'. Valid: {list(RISK_MODES.keys())}")
    return RISK_MODES[name]
