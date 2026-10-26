"""Fixed synthetic indicator arithmetic with explicit as-of window validation.

This is a standalone synthetic interface, not a licensed-data/policy adapter.
No ticker lookup, provider fallback, window repair or shortened lookback exists.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from .common import fixed_decimal


@dataclass(frozen=True)
class SyntheticPoint:
    asset_id: int
    session: date
    previous_session: date | None
    total_return: Decimal | None
    total_return_index: Decimal | None
    segment: int | None
    source_reference: str
    eligible: bool | None = True
    price_flag: str = 'TR'
    duration_flag: str = 'D2'
    trading_status_flag: str = 'A'


@dataclass(frozen=True)
class IndicatorValue:
    valid: bool
    reason: str | None
    value: Decimal | None
    state: str | None = None
    difference: Decimal | None = None


def _window(points, sessions, asset_id, as_of, count):
    def bad(reason):
        return None, reason
    if (type(points) is not tuple or any(type(p) is not SyntheticPoint for p in points)
            or type(sessions) is not tuple or type(as_of) is not date
            or type(asset_id) is not int or asset_id <= 0
            or any(type(d) is not date for d in sessions)
            or sessions != tuple(sorted(set(sessions)))):
        return bad('INVALID_WINDOW_INPUT')
    past_sessions = tuple(d for d in sessions if d <= as_of)
    if not past_sessions or past_sessions[-1] != as_of:
        return bad('INVALID_AS_OF_SESSION')
    if len(past_sessions) < count:
        return bad('INSUFFICIENT_HISTORY')
    expected = past_sessions[-count:]
    rows = tuple(p for p in points if p.asset_id == asset_id and expected[0] <= p.session <= as_of)
    if tuple(p.session for p in rows) != expected:
        return bad('MISSING_DUPLICATE_OR_UNORDERED_SESSION')
    if len({p.source_reference for p in rows}) != 1 or any(type(p.source_reference) is not str
            or not p.source_reference.startswith('SYNTHETIC_') for p in rows):
        return bad('UNAUTHORIZED_SOURCE')
    if any(type(p.eligible) is not bool for p in rows):
        return bad('UNKNOWN_ELIGIBILITY')
    if not all(p.eligible for p in rows):
        return bad('INELIGIBLE_WINDOW')
    if any(p.price_flag not in ('BA','TR') or p.duration_flag != 'D2'
           or p.trading_status_flag != 'A' for p in rows):
        return bad('UNSUPPORTED_SOURCE_FLAGS')
    if any(type(p.segment) is not int or p.segment < 1 for p in rows) or len({p.segment for p in rows}) != 1:
        return bad('SEGMENT_BOUNDARY_OR_UNDEFINED')
    first_position = past_sessions.index(expected[0])
    previous = past_sessions[first_position-1] if first_position else None
    if rows[0].previous_session != previous:
        return bad('NONCONSECUTIVE_INTERVAL')
    for p in rows:
        if p.total_return is None or p.total_return_index is None:
            return bad('MISSING_RETURN_OR_INDEX')
        if (type(p.total_return) is not Decimal or not p.total_return.is_finite() or p.total_return < -1
                or type(p.total_return_index) is not Decimal or not p.total_return_index.is_finite()
                or p.total_return_index < 0):
            return bad('INVALID_RETURN_OR_INDEX')
    for a, b in zip(rows, rows[1:]):
        if b.previous_session != a.session:
            return bad('NONCONSECUTIVE_INTERVAL')
        if b.total_return_index != a.total_return_index*(1+b.total_return):
            return bad('INDEX_RETURN_INCONSISTENCY')
    return rows, None


@fixed_decimal
def _evaluate(feature, points, sessions, asset_id, as_of):
    required = {'trend_200':200, 'relative_strength_63':64, 'realized_volatility_20':21}[feature]
    rows, reason = _window(points, sessions, asset_id, as_of, required)
    if reason:
        return IndicatorValue(False, reason, None)
    if feature == 'trend_200':
        value = sum((p.total_return_index for p in rows), Decimal(0))/Decimal(200)
        difference = rows[-1].total_return_index-value
        return IndicatorValue(True, None, value, 'ABOVE' if difference > 0 else 'BELOW' if difference < 0 else 'EQUAL', difference)
    if feature == 'relative_strength_63':
        if rows[0].total_return_index == 0:
            return IndicatorValue(False, 'ZERO_RELATIVE_STRENGTH_BASE', None)
        product = Decimal(1)
        for p in rows[1:]:
            product *= 1+p.total_return
        return IndicatorValue(True, None, product-1)
    returns = tuple(p.total_return for p in rows[1:])
    centered = tuple(v-returns[0] for v in returns)
    mean = sum(centered, Decimal(0))/Decimal(20)
    variance = sum(((v-mean)**2 for v in centered), Decimal(0))/Decimal(19)
    return IndicatorValue(True, None, variance.sqrt()*Decimal(252).sqrt())


def trend_200(points, sessions, asset_id, as_of):
    """Exactly 200 contiguous index endpoints; explicit ABOVE/BELOW/EQUAL."""
    return _evaluate('trend_200', points, sessions, asset_id, as_of)


def relative_strength_63(points, sessions, asset_id, as_of):
    """Exactly 63 returns and 64 contiguous index endpoints; no ranking."""
    return _evaluate('relative_strength_63', points, sessions, asset_id, as_of)


def realized_volatility_20(points, sessions, asset_id, as_of):
    """20 returns, sample divisor 19, Decimal sqrt(252); constant input -> 0."""
    return _evaluate('realized_volatility_20', points, sessions, asset_id, as_of)
