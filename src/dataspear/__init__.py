from dataspear.config import Config, config
from dataspear.core import DataConnection, IndexDataConnection
from dataspear.news import (
    NewsArticle,
    fetch_all_news,
    fetch_market_news,
    news_brief,
)
from dataspear.nse import (
    MarketBrief,
    MarketContext,
    MarketRegime,
    MarketStatus,
    OptionChain,
    OptionChart,
    OptionQuote,
    OptionStrike,
    build_market_brief,
    build_market_context,
    classify_pcr,
    detect_levels,
    detect_regime,
    get_expiry_dates,
    get_india_vix,
    get_india_vix_history,
    get_market_status,
    get_nifty_option_chain,
    get_nifty_technicals,
    is_market_open,
    oi_analysis,
    parse_option_chain,
    vix_regime,
)
from dataspear.utils.request_handler import RequestHandler
from dataspear.utils.url import URL
from dataspear.utils.validation import (
    ConnectionType,
    IndexRequestParameters,
)

__all__ = [
    # core
    "Config",
    "config",
    "DataConnection",
    "IndexDataConnection",
    "RequestHandler",
    "URL",
    "ConnectionType",
    "IndexRequestParameters",
    # option chain
    "OptionChain",
    "OptionQuote",
    "OptionStrike",
    "OptionChart",
    "get_expiry_dates",
    "get_nifty_option_chain",
    "parse_option_chain",
    "oi_analysis",
    # vix
    "get_india_vix",
    "get_india_vix_history",
    "vix_regime",
    # levels
    "detect_levels",
    # market time
    "MarketStatus",
    "get_market_status",
    "is_market_open",
    # technicals
    "get_nifty_technicals",
    # regime
    "MarketRegime",
    "detect_regime",
    "classify_pcr",
    # brief
    "MarketBrief",
    "build_market_brief",
    # full context
    "MarketContext",
    "build_market_context",
    # news
    "NewsArticle",
    "fetch_all_news",
    "fetch_market_news",
    "news_brief",
]
