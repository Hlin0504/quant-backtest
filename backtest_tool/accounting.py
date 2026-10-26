"""Synthetic daily valuation/trading kernels. No empirical adapter or loader."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from .configuration import AccountingError, AccountingSpecification, fixed_decimal, ONE, ZERO
from .common import policy_hash as sha256_json
from .costs import calculate_turnover, proportional_transaction_cost

CASH = 0
TOLERANCE = Decimal('1e-30')

def _flag_check(bar, configuration, price_flags=None, *, policy=None, execution=False):
    # Full empirical-policy objects are deliberately not exported or supported.
    if policy is not None or type(bar) is not SyntheticExecutionBar:
        raise AccountingError('unsupported input evidence; synthetic bars only')
    if price_flags is not None and (type(price_flags) is not tuple or not price_flags
            or any(flag not in ('BA','TR') for flag in price_flags)):
        raise AccountingError('invalid explicit synthetic price policy')
    if (bar.price_flag not in (configuration['synthetic_price_flags'] if price_flags is None else price_flags)
            or bar.duration_flag not in configuration['synthetic_duration_flags']
            or bar.trading_status_flag not in configuration['synthetic_trading_status_flags']):
        raise AccountingError('unapproved synthetic price/duration/status flag')

def _number(value, *, minimum=None):
    if (not isinstance(value, Decimal) or not value.is_finite()
            or (minimum is not None and value < minimum)):
        raise AccountingError("finite Decimal outside permitted bounds")
    return value


def _positions(values):
    if CASH not in values or any(type(key) is not int or key < 0 for key in values):
        raise AccountingError("positions require positive asset IDs and explicit cash key 0")
    for value in values.values():
        _number(value, minimum=ZERO)
    return tuple(sorted((key, value) for key, value in values.items() if value != ZERO or key == CASH))


def _read_positions(positions):
    if not isinstance(positions, tuple):
        raise AccountingError("positions must be immutable key-value tuples")
    values = dict(positions)
    if len(values) != len(positions):
        raise AccountingError("duplicate position keys")
    return dict(_positions(values))


@fixed_decimal
def drift_weights(positions):
    """Normalize current marked values, not last month's intended weights."""
    values = _read_positions(positions)
    total = sum(values.values(), ZERO)
    if total <= ZERO:
        raise AccountingError("zero wealth has undefined portfolio weights; evaluation stops")
    ordered = sorted(values)
    output, allocated = {}, ZERO
    for number in ordered[:-1]:
        output[number] = values[number] / total
        allocated += output[number]
    output[ordered[-1]] = ONE - allocated
    if any(value < ZERO for value in output.values()):
        raise AccountingError("invalid rounded drift weights")
    return tuple(sorted(output.items()))


@dataclass(frozen=True, slots=True)
class SyntheticExecutionBar:
    asset_id: int
    session: date
    previous_session: date | None
    total_return: Decimal | None
    close: Decimal | None
    source_reference: str
    price_flag: str = "TR"
    duration_flag: str = "D2"
    trading_status_flag: str = "A"

    def __post_init__(self):
        if (type(self.asset_id) is not int or self.asset_id <= 0 or type(self.session) is not date
                or self.previous_session is not None and type(self.previous_session) is not date
                or not isinstance(self.source_reference, str) or not self.source_reference.startswith("SYNTHETIC_")):
            raise AccountingError("explicit synthetic observation identity/provenance required")
        if self.total_return is not None:
            _number(self.total_return, minimum=-ONE)
        if self.close is not None:
            _number(self.close, minimum=ZERO)


@dataclass(frozen=True, slots=True)
class ModeledTrade:
    asset_id: int
    signed_net_value: Decimal
    modeled_close: Decimal
    source_reference: str
    execution_observation: SyntheticExecutionBar


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    session: date
    formation_date: date | None
    terminal_liquidation: bool
    pretrade_weights: tuple
    target_weights: tuple
    turnover: Decimal
    fee_fraction: Decimal
    fee_value: Decimal
    pretrade_net_wealth: Decimal
    posttrade_net_wealth: Decimal
    cash_before: Decimal
    cash_after: Decimal
    trades: tuple[ModeledTrade, ...]
    target_lineage: object | None
    accounting_configuration_sha256: str
    execution_identity_evidence: tuple = ()


@dataclass(frozen=True, slots=True)
class AccountingDay:
    session: date
    previous_session: date | None
    opening_net_positions: tuple
    marked_net_positions: tuple
    closing_net_positions: tuple
    gross_wealth_before: Decimal
    gross_wealth_after: Decimal
    net_wealth_before: Decimal
    net_wealth_after: Decimal
    gross_return: Decimal
    net_return: Decimal
    return_inputs: tuple[SyntheticExecutionBar, ...]
    formation: object | None
    executions: tuple[ExecutionEvent, ...]


@fixed_decimal
def mark_positions(positions, previous_session, session, bars, specification, *, price_flags=None, eligibility_policy=None):
    """Apply interval returns to EXISTING holdings, before close-event trades."""
    if price_flags is not None and (not isinstance(price_flags,tuple) or not price_flags
            or any(flag not in ("BA","TR") for flag in price_flags)):
        raise AccountingError("invalid explicit synthetic price policy")
    configuration = specification.to_dict()
    result, evidence = _read_positions(positions), []
    for number, value in sorted(result.items()):
        if number == CASH or value == ZERO:
            continue  # Cash earns explicitly zero; no unheld returns are needed.
        bar = bars.get((number, session))
        if bar is None or bar.total_return is None:
            raise AccountingError("missing held return; no filling or implicit liquidation")
        if not type(bar) is SyntheticExecutionBar or bar.asset_id != number or bar.session != session:
            raise AccountingError("return lookup identity/date mismatch")
        if bar.previous_session != previous_session:
            raise AccountingError("noncontiguous held-return interval")
        _flag_check(bar, configuration, price_flags, policy=eligibility_policy)
        result[number] = value * (ONE + bar.total_return)
        evidence.append(bar)
    _positions(result)
    if sum(result.values(), ZERO) <= ZERO:
        raise AccountingError("portfolio exhausted: no normalization or subsequent returns defined")
    return _positions(result), tuple(evidence)


@fixed_decimal
def execute_target(positions, weights, session, bars, specification, *, target=None, terminal=False,
                   cost_basis="TURNOVER_PROXY", price_flags=None, eligibility_policy=None):
    """Charge the declared turnover-proxy fee, then fund post-fee targets.

    The explicit gross-notional extension solves its self-financing fee equation;
    the default remains the unchanged historical turnover-proxy convention.
    Cost is NOT an estimate of actual quote-based commissions. Actual risky
    notional changes are reported separately from the pre-fee turnover proxy.
    """
    if price_flags is not None and price_flags != ("TR",):
        raise AccountingError("TR execution policy required")
    values = _read_positions(positions)
    pretrade = dict(drift_weights(tuple(values.items())))
    desired = dict(weights)
    if (CASH not in desired or len(desired) != len(weights)
            or any(type(key) is not int or key < 0 for key in desired)):
        raise AccountingError("invalid or duplicate target keys")
    for value in desired.values():
        _number(value, minimum=ZERO)
    if sum(desired.values(), ZERO) != ONE:
        raise AccountingError("target weights must sum exactly to one")
    turnover = calculate_turnover({str(k): v for k, v in pretrade.items()}, {str(k): v for k, v in desired.items()})
    configuration = specification.to_dict()
    fraction = proportional_transaction_cost(turnover, Decimal(configuration["transaction_cost_bps"]))
    before = sum(values.values(), ZERO)
    fee = before * fraction
    if cost_basis == "GROSS_RISKY_TRADED_NOTIONAL":
        from .traded_notional_cost import gross_notional_fee
        fee = ZERO if turnover == ZERO else gross_notional_fee(values, desired, Decimal(configuration["transaction_cost_bps"]))
        fraction = fee / before
    elif cost_basis != "TURNOVER_PROXY":
        raise AccountingError("unknown transaction-cost basis")
    after = before - fee
    if after <= ZERO:
        raise AccountingError("fees exhaust portfolio wealth")
    # Residual goes to the final positive target, not an unapproved cash sleeve.
    positive = sorted(key for key, value in desired.items() if value > ZERO)
    result, allocated = {CASH: ZERO}, ZERO
    for number in positive[:-1]:
        result[number] = after * desired[number]
        allocated += result[number]
    result[positive[-1]] = after - allocated
    if turnover == ZERO:
        result = values.copy()  # Do not manufacture tiny round-trip trades.
    trades = []
    for number in sorted((set(values) | set(result)) - {CASH}):
        delta = result.get(number, ZERO) - values.get(number, ZERO)
        if delta == ZERO:
            continue
        bar = bars.get((number, session))
        if bar is None or bar.close is None or bar.close <= ZERO:
            raise AccountingError("missing positive execution-close mark; no assumed fill or delay")
        if not type(bar) is SyntheticExecutionBar or bar.asset_id != number or bar.session != session:
            raise AccountingError("execution lookup identity/date mismatch")
        if price_flags is not None and (price_flags != ("TR",) or bar.price_flag != "TR"):
            raise AccountingError("TR execution evidence required; BA is valuation only")
        _flag_check(bar, configuration, price_flags, policy=eligibility_policy, execution=True)
        trades.append(ModeledTrade(number, delta, bar.close, bar.source_reference, bar))
    cash_after_ledger = values[CASH] - sum((trade.signed_net_value for trade in trades), ZERO) - fee
    if abs(cash_after_ledger - result[CASH]) > TOLERANCE * max(ONE, before):
        raise AccountingError("self-financing cash ledger does not reconcile")
    if abs(sum(result.values(), ZERO) + fee - before) > TOLERANCE * max(ONE, before):
        raise AccountingError("portfolio value conservation failed")
    event = ExecutionEvent(session, None if target is None else target.formation_date, terminal,
                           tuple(sorted(pretrade.items())), tuple(sorted(desired.items())), turnover,
                           fraction, fee, before, after, values[CASH], result[CASH], tuple(trades),
                           target, specification.sha256 if cost_basis == "TURNOVER_PROXY" else
                           sha256_json({"accounting":specification.sha256,"cost_basis":cost_basis}))
    return _positions(result), event
