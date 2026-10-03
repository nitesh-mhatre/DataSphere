"""NSE market time awareness: session phase, holidays, next trading day.

Pure logic (no I/O): answers "is the market open right now?", which phase of
the session we are in, why it is closed, and when it opens next. Useful for
gating any live data fetch or trade signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from dataspear.utils.time import IST

PRE_OPEN_START = time(9, 0)
PRE_OPEN_END = time(9, 15)
NORMAL_START = time(9, 15)
NORMAL_END = time(15, 30)
CLOSING_START = time(15, 30)
CLOSING_END = time(16, 0)

# NSE holidays 2025-2026 (official list; keep in sync yearly).
NSE_HOLIDAYS: Dict[date, str] = {
    # 2025
    date(2025, 1, 26): "Republic Day",
    date(2025, 2, 26): "Mahashivratri",
    date(2025, 3, 14): "Holi",
    date(2025, 3, 31): "Id-Ul-Fitr (Ramadan Eid)",
    date(2025, 4, 10): "Shri Ram Navami",
    date(2025, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 1): "Maharashtra Day",
    date(2025, 8, 15): "Independence Day",
    date(2025, 8, 27): "Ganesh Chaturthi",
    date(2025, 10, 2): "Mahatma Gandhi Jayanti",
    date(2025, 10, 20): "Diwali Laxmi Puja (Muhurat Trading)",
    date(2025, 10, 21): "Diwali Balipratipada",
    date(2025, 11, 5): "Prakash Gurpurb Sri Guru Nanak Dev Ji",
    date(2025, 12, 25): "Christmas",
    # 2026
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 20): "Holi",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 4, 15): "Ram Navami",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 8, 15): "Independence Day",
    date(2026, 8, 25): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 29): "Diwali Laxmi Puja",
    date(2026, 11, 11): "Gurunanak Jayanti",
    date(2026, 12, 25): "Christmas",
}


def is_trading_day(day: date) -> bool:
    """True if ``day`` is a weekday that is not an NSE holiday."""
    return day.weekday() < 5 and day not in NSE_HOLIDAYS


def next_trading_day(from_date: date) -> date:
    """First tradable day on or after ``from_date``."""
    d = from_date
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


@dataclass
class MarketStatus:
    """A snapshot of the current NSE session state."""

    now_ist: datetime
    is_open: bool
    phase: str  # PRE_OPEN | NORMAL | CLOSING | CLOSED
    close_reason: str  # "" | NIGHT | WEEKEND | HOLIDAY | PRE_OPEN | CLOSING_SESSION
    holiday_name: str
    next_trading_day: date
    next_open_ist: datetime
    minutes_to_open: int
    minutes_to_close: int
    trade_rules: List[str] = field(default_factory=list)

    @property
    def weekday_name(self) -> str:
        return self.now_ist.strftime("%A")

    def context_block(self) -> str:
        """Compact multi-line summary suitable for prompts/logs."""
        lines = [
            "=== MARKET TIME CONTEXT ===",
            f"Current IST   : {self.now_ist.strftime('%A %d-%b-%Y %H:%M:%S IST')}",
            f"Market status : {'OPEN' if self.is_open else 'CLOSED'} - {self.phase}",
        ]
        if not self.is_open:
            reason = self.close_reason
            if self.holiday_name:
                reason += f" ({self.holiday_name})"
            lines.append(f"Closed because: {reason}")
            lines.append(
                f"Next trading  : {self.next_trading_day.strftime('%A %d-%b-%Y')}"
                + (
                    f" (opens in {self.minutes_to_open} min)"
                    if self.minutes_to_open > 0
                    else ""
                )
            )
        for rule in self.trade_rules:
            lines.append(f"  - {rule}")
        lines.append("===========================")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "now_ist": self.now_ist.isoformat(),
            "is_open": self.is_open,
            "phase": self.phase,
            "close_reason": self.close_reason,
            "holiday_name": self.holiday_name,
            "next_trading_day": self.next_trading_day.isoformat(),
            "next_open_ist": self.next_open_ist.isoformat(),
            "minutes_to_open": self.minutes_to_open,
            "minutes_to_close": self.minutes_to_close,
            "trade_rules": self.trade_rules,
        }


def _build_trade_rules(is_open: bool, phase: str, now_time: time) -> List[str]:
    rules: List[str] = []
    if not is_open:
        rules.append(
            "Market is CLOSED - any LTP is the last traded price from the "
            "previous session, not a live price."
        )
        if phase == "PRE_OPEN":
            rules.append(
                "PRE-OPEN session (09:00-09:15). No execution yet; prices are "
                "discovered via auction."
            )
        return rules

    if time(9, 15) <= now_time <= time(9, 30):
        rules.append(
            "OPENING WINDOW (09:15-09:30): highest-velocity window; hard exit "
            "by 09:30 and max 1 lot."
        )
    elif time(9, 30) <= now_time <= time(9, 45):
        rules.append("POST-OPENING (09:30-09:45): wait for 09:45 before analysis.")
    elif time(9, 45) <= now_time <= time(11, 30):
        rules.append(
            "MORNING SESSION (09:45-11:30): prime window; OI buildup most reliable."
        )
    elif time(11, 30) <= now_time <= time(14, 0):
        rules.append(
            "MID-SESSION (11:30-14:00): often range-bound; favour premium selling."
        )
    elif time(14, 0) <= now_time <= time(14, 30):
        rules.append("PRE-EXPIRY CAUTION (14:00-14:30): tighten stop-losses.")
    elif time(14, 30) <= now_time <= time(15, 0):
        rules.append("CLOSING APPROACH (14:30-15:00): avoid new entries.")
    elif now_time >= time(15, 0):
        rules.append(
            "LAST 30 MIN (15:00-15:30): close intraday positions; no new trades."
        )
    return rules


def get_market_status(now: Optional[datetime] = None) -> MarketStatus:
    """Return a fully populated :class:`MarketStatus` for ``now`` (default now)."""
    now = now.astimezone(IST) if now else datetime.now(IST)
    today = now.date()
    now_time = now.time()
    holiday_name = NSE_HOLIDAYS.get(today, "")
    is_weekend = today.weekday() >= 5

    if is_weekend or holiday_name:
        phase = "CLOSED"
        is_open = False
        close_reason = "WEEKEND" if is_weekend else "HOLIDAY"
    elif now_time < PRE_OPEN_START:
        phase, is_open, close_reason = "CLOSED", False, "NIGHT"
    elif now_time < PRE_OPEN_END:
        phase, is_open, close_reason = "PRE_OPEN", False, "PRE_OPEN"
    elif now_time <= NORMAL_END:
        phase, is_open, close_reason = "NORMAL", True, ""
    elif now_time <= CLOSING_END:
        phase, is_open, close_reason = "CLOSING", False, "CLOSING_SESSION"
    else:
        phase, is_open, close_reason = "CLOSED", False, "NIGHT"

    if is_open:
        nxt = today
    else:
        anchor = today if now_time < NORMAL_END else today + timedelta(days=1)
        nxt = next_trading_day(anchor)
    next_open = datetime.combine(nxt, NORMAL_START, tzinfo=IST)

    minutes_to_open = -1 if is_open else max(
        0, int((next_open - now).total_seconds() / 60)
    )
    next_close = datetime.combine(today, NORMAL_END, tzinfo=IST)
    minutes_to_close = (
        max(0, int((next_close - now).total_seconds() / 60)) if is_open else -1
    )

    return MarketStatus(
        now_ist=now,
        is_open=is_open,
        phase=phase,
        close_reason=close_reason,
        holiday_name=holiday_name,
        next_trading_day=nxt,
        next_open_ist=next_open,
        minutes_to_open=minutes_to_open,
        minutes_to_close=minutes_to_close,
        trade_rules=_build_trade_rules(is_open, phase, now_time),
    )


def is_market_open(now: Optional[datetime] = None) -> bool:
    """Convenience wrapper around :func:`get_market_status`."""
    return get_market_status(now).is_open
