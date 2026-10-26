"""Weight drift, turnover, and proportional transaction-cost arithmetic."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping


CASH_ASSET_ID = "__CASH__"
_WEIGHT_TOLERANCE = Decimal("1e-24")


def with_cash_weight(
    security_weights: tuple[tuple[str, Decimal], ...], cash_weight: Decimal
) -> dict[str, Decimal]:
    weights = {security_id: weight for security_id, weight in security_weights}
    weights[CASH_ASSET_ID] = cash_weight
    _validate_weights(weights)
    return weights


def _validate_weights(weights: Mapping[str, Decimal]) -> None:
    if not weights:
        raise ValueError("weight map cannot be empty")
    if any(not isinstance(weight, Decimal) or not weight.is_finite() or weight < 0 for weight in weights.values()):
        raise ValueError("weights must be finite non-negative Decimals")
    if abs(sum(weights.values(), Decimal("0")) - Decimal("1")) > _WEIGHT_TOLERANCE:
        raise ValueError("weights must sum to one")


def calculate_turnover(
    pretrade_weights: Mapping[str, Decimal], target_weights: Mapping[str, Decimal]
) -> Decimal:
    """Return one-way turnover: one half of total absolute weight changes."""
    _validate_weights(pretrade_weights)
    _validate_weights(target_weights)
    assets = set(pretrade_weights) | set(target_weights)
    return sum(
        (abs(target_weights.get(asset, Decimal("0")) - pretrade_weights.get(asset, Decimal("0"))) for asset in assets),
        Decimal("0"),
    ) / Decimal("2")


def proportional_transaction_cost(turnover: Decimal, basis_points: Decimal) -> Decimal:
    if not turnover.is_finite() or not Decimal("0") <= turnover <= Decimal("1"):
        raise ValueError("turnover must be between zero and one")
    if not basis_points.is_finite() or basis_points < 0:
        raise ValueError("transaction-cost basis points must be finite and non-negative")
    return turnover * basis_points / Decimal("10000")


def drift_pretrade_weights(
    target_weights: Mapping[str, Decimal],
    realized_returns: Mapping[str, Decimal],
    *,
    cash_return: Decimal,
    terminal_security_ids: frozenset[str] = frozenset(),
) -> dict[str, Decimal]:
    """Drift target weights through holding returns for the next rebalance.

    Terminal securities transfer any nonzero terminal proceeds to cash. An
    all-loss portfolio has no normalizable weights and raises explicitly.
    """
    _validate_weights(target_weights)
    if not cash_return.is_finite() or cash_return < Decimal("-1"):
        raise ValueError("cash return must be finite and no smaller than -1")

    ending_values: dict[str, Decimal] = {}
    cash_value = target_weights.get(CASH_ASSET_ID, Decimal("0")) * (Decimal("1") + cash_return)
    for asset, weight in target_weights.items():
        if asset == CASH_ASSET_ID:
            continue
        if asset not in realized_returns:
            raise ValueError(f"missing realized return for {asset}")
        realized = realized_returns[asset]
        if not realized.is_finite() or realized < Decimal("-1"):
            raise ValueError(f"invalid realized return for {asset}")
        ending_value = weight * (Decimal("1") + realized)
        if asset in terminal_security_ids:
            cash_value += ending_value
        else:
            ending_values[asset] = ending_value
    ending_values[CASH_ASSET_ID] = cash_value
    total = sum(ending_values.values(), Decimal("0"))
    if total <= 0:
        raise ValueError("portfolio ending wealth is non-positive; drift weights are undefined")

    ordered_assets = sorted(ending_values)
    normalized: dict[str, Decimal] = {}
    allocated = Decimal("0")
    for asset in ordered_assets[:-1]:
        normalized[asset] = ending_values[asset] / total
        allocated += normalized[asset]
    normalized[ordered_assets[-1]] = Decimal("1") - allocated
    _validate_weights(normalized)
    return normalized
