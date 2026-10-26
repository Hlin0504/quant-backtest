"""Pure fee equation for an explicitly selected gross risky-notional model."""

from decimal import Decimal
from .configuration import AccountingError, fixed_decimal


@fixed_decimal
def gross_notional_fee(values, desired, basis_points):
    """Solve f=k*sum_i|w_i*(V-f)-v_i|, excluding cash, at 34 digits.

    Nonnegative fully funded positions/weights give a unique root for 0<=k<1.
    Fixed 128-step bisection is deterministic; rounding may stop progress sooner.
    No spread calibration, order or fill inference is implied.
    """
    if not isinstance(basis_points, Decimal) or not basis_points.is_finite() or not 0 <= basis_points < 10000:
        raise AccountingError("invalid gross-notional cost rate")
    for mapping in (values, desired):
        if 0 not in mapping or any(type(key) is not int or key < 0 for key in mapping):
            raise AccountingError("explicit cash and positive asset IDs required")
        if any(not isinstance(value, Decimal) or not value.is_finite() or value < 0 for value in mapping.values()):
            raise AccountingError("nonnegative finite Decimal values required")
    wealth = sum(values.values(), Decimal(0))
    if wealth <= 0 or sum(desired.values(), Decimal(0)) != 1:
        raise AccountingError("positive wealth and fully funded weights required")
    k = basis_points / Decimal(10000)
    keys = tuple(sorted((set(values) | set(desired)) - {0}))
    def residual(fee):
        return fee - k * sum((abs(desired.get(key, Decimal(0)) * (wealth-fee)
                                  - values.get(key, Decimal(0))) for key in keys), Decimal(0))
    if k == 0 or residual(Decimal(0)) == 0:
        return Decimal(0)
    lo, hi = Decimal(0), wealth
    for _ in range(128):
        mid = (lo+hi)/2
        if mid in (lo, hi):
            break
        if residual(mid) > 0:
            hi = mid
        else:
            lo = mid
    fee = (lo+hi)/2
    if abs(residual(fee)) > Decimal("1e-30") * max(wealth, Decimal(1)):
        raise AccountingError("fee equation failed to reconcile")
    return fee
