"""NSE India data access (async).

Example:
    from dataspear.nse import get_nifty_option_chain, oi_analysis

    chain = await get_nifty_option_chain(atm_range=10)
    summary = oi_analysis(chain)
"""

from dataspear.nse.analysis import (
    iv_skew,
    max_pain,
    oi_analysis,
    oi_buildup_unwinding,
    pcr_sentiment,
    support_resistance,
    top_oi_strikes,
)
from dataspear.nse.context import MarketContext, build_market_context
from dataspear.nse.levels import (
    LevelAnalysis,
    detect_levels,
    distribution_accumulation_zones,
    merge_with_oi_walls,
    swing_highs,
    swing_lows,
    wick_levels,
)
from dataspear.nse.market_extra import (
    get_fii_dii_data,
    get_global_indices,
    get_nifty_technicals,
    get_premarket_data,
)
from dataspear.nse.market_time import (
    NSE_HOLIDAYS,
    MarketStatus,
    get_market_status,
    is_market_open,
    is_trading_day,
    next_trading_day,
)
from dataspear.nse.models import OptionChain, OptionQuote, OptionStrike
from dataspear.nse.option_chain import (
    fetch_option_chain,
    get_expiry_dates,
    get_nifty_option_chain,
    parse_option_chain,
)
from dataspear.nse.option_chart import (
    ChartPoint,
    OptionChart,
    build_identifier,
    fetch_option_chart,
    get_both_charts,
    get_option_chart,
    parse_chart_data,
)
from dataspear.nse.regime import MarketRegime, classify_pcr, detect_regime
from dataspear.nse.scanner import (
    MarketBrief,
    StrikeBrief,
    build_market_brief,
    select_target_strikes,
)
from dataspear.nse.session import (
    NseSession,
    aclose,
    force_refresh,
    nse_get,
    nse_get_json,
)
from dataspear.nse.vix import (
    get_india_vix,
    get_india_vix_history,
    get_spot_and_vix,
    vix_regime,
)

__all__ = [
    # session
    "NseSession",
    "nse_get",
    "nse_get_json",
    "force_refresh",
    "aclose",
    # models / option chain
    "OptionChain",
    "OptionQuote",
    "OptionStrike",
    "parse_option_chain",
    "fetch_option_chain",
    "get_expiry_dates",
    "get_nifty_option_chain",
    # OI analysis
    "pcr_sentiment",
    "max_pain",
    "top_oi_strikes",
    "support_resistance",
    "oi_buildup_unwinding",
    "iv_skew",
    "oi_analysis",
    # VIX
    "get_india_vix",
    "get_india_vix_history",
    "get_spot_and_vix",
    "vix_regime",
    # levels
    "LevelAnalysis",
    "detect_levels",
    "swing_highs",
    "swing_lows",
    "wick_levels",
    "distribution_accumulation_zones",
    "merge_with_oi_walls",
    # option chart
    "OptionChart",
    "ChartPoint",
    "build_identifier",
    "fetch_option_chart",
    "get_option_chart",
    "get_both_charts",
    "parse_chart_data",
    # market extras
    "get_fii_dii_data",
    "get_global_indices",
    "get_nifty_technicals",
    "get_premarket_data",
    # market time
    "MarketStatus",
    "get_market_status",
    "is_market_open",
    "is_trading_day",
    "next_trading_day",
    "NSE_HOLIDAYS",
    # regime
    "MarketRegime",
    "detect_regime",
    "classify_pcr",
    # scanner
    "MarketBrief",
    "StrikeBrief",
    "build_market_brief",
    "select_target_strikes",
    # full context
    "MarketContext",
    "build_market_context",
]
