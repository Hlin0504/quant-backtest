"""Small daily long-only orchestration over existing accounting primitives.

Only explicitly synthetic adapters are executable in this first proof of concept.
Real data is unsupported and must never be relabeled synthetic.
"""
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal as D
import json
from typing import Protocol

from .accounting import (
    CASH, AccountingDay, SyntheticExecutionBar, mark_positions, execute_target,
)
from .configuration import AccountingSpecification, fixed_decimal
from .analytics import calculate_performance
from .monthly import monthly_paths
from .common import canonical, policy_hash
# Standalone fixed-window indicators; no empirical-data or authorization adapter.
from .indicators import trend_200, relative_strength_63, realized_volatility_20


class ToolRefusal(ValueError):
    """Only fixed codes cross the application boundary."""


def need(condition, code="INVALID_BACKTEST_INPUT"):
    if not condition:
        raise ToolRefusal(code)


@dataclass(frozen=True)
class Eligibility:
    price_flags: tuple[str, ...]
    duration_flags: tuple[str, ...]
    status_flags: tuple[str, ...]

    def check(self, bar, *, execution=False, require_return=False):
        need(bar is not None, "MISSING_OBSERVATION")
        need(bar.price_flag in self.price_flags and bar.duration_flag in self.duration_flags
             and bar.trading_status_flag in self.status_flags, "INELIGIBLE_SOURCE_FLAGS")
        if require_return:
            need(bar.total_return is not None, "MISSING_REQUIRED_RETURN")
        if execution:
            need(bar.price_flag == "TR" and bar.close is not None and bar.close > 0,
                 "MISSING_VALID_EXECUTION_MARK")


@dataclass(frozen=True)
class History:
    as_of: date
    sessions: tuple[date, ...]
    asset_ids: tuple[int, ...]
    observations: tuple[SyntheticExecutionBar, ...]


class DataAdapter(Protocol):
    """No provider discovery, network fallback, ticker keys or automatic loading."""
    sessions: tuple[date, ...]
    asset_ids: tuple[int, ...]
    bars: tuple[SyntheticExecutionBar, ...]
    source_id: str


@dataclass(frozen=True)
class SyntheticDataAdapter:
    source_id: str
    sessions: tuple[date, ...]
    asset_ids: tuple[int, ...]
    bars: tuple[SyntheticExecutionBar, ...]

    def __post_init__(self):
        need(type(self.source_id) is str and self.source_id.startswith("SYNTHETIC_"), "UNAUTHORIZED_DATA_SOURCE")
        need(type(self.sessions) is tuple and len(self.sessions) >= 3
             and all(type(d) is date for d in self.sessions)
             and self.sessions == tuple(sorted(set(self.sessions))))
        need(type(self.asset_ids) is tuple and self.asset_ids == tuple(sorted(set(self.asset_ids)))
             and bool(self.asset_ids) and all(type(i) is int and i > 0 for i in self.asset_ids))
        need(type(self.bars) is tuple and all(type(b) is SyntheticExecutionBar for b in self.bars),
             "UNAUTHORIZED_DATA_SOURCE")
        keys = tuple((b.asset_id,b.session) for b in self.bars)
        need(keys == tuple(sorted(set(keys))), "DUPLICATE_OR_UNORDERED_DATA")
        for b in self.bars:
            need(b.asset_id in self.asset_ids and b.session in self.sessions
                 and b.source_reference == self.source_id, "SOURCE_LINEAGE_MISMATCH")
            p = self.sessions.index(b.session)
            need(b.previous_session == (self.sessions[p-1] if p else None), "NONCONTIGUOUS_INTERVAL")

    def history(self, day):
        need(day in self.sessions)
        return History(day,tuple(d for d in self.sessions if d <= day),self.asset_ids,
                       tuple(b for b in self.bars if b.session <= day))

    def sha256(self):
        return policy_hash(self)


class Strategy(Protocol):
    def targets(self, history: History) -> tuple[tuple[int, D], ...]: ...


@dataclass(frozen=True)
class EqualWeightStrategy:
    """Versioned synthetic equal-weight example."""
    def targets(self, history):
        numbers = history.asset_ids
        allocated = D(0)
        result = []
        for n in numbers[:-1]:
            weight = D(1)/D(len(numbers)); allocated += weight; result.append((n,weight))
        return tuple(result + [(numbers[-1],D(1)-allocated)])


@dataclass(frozen=True)
class RunConfiguration:
    strategy_id: str
    strategy_version: str
    assets: tuple[int, ...]
    benchmark: int
    start: date
    end: date
    accounting: AccountingSpecification
    signal: Eligibility
    valuation: Eligibility
    execution: Eligibility
    schedule: str = "MONTH_END_NEXT_OBSERVED_CLOSE"
    cost_basis: str = "GROSS_RISKY_TRADED_NOTIONAL"
    version: str = "1.0"

    def __post_init__(self):
        need((self.strategy_id,self.strategy_version) == ("periodic_equal_weight","1.0"), "UNSUPPORTED_STRATEGY")
        need(self.version == "1.0" and self.schedule == "MONTH_END_NEXT_OBSERVED_CLOSE"
             and self.cost_basis == "GROSS_RISKY_TRADED_NOTIONAL", "UNSUPPORTED_CONFIGURATION")
        need(type(self.benchmark) is int and self.benchmark > 0
             and type(self.start) is date and type(self.end) is date and self.start < self.end)
        need(type(self.assets) is tuple and bool(self.assets) and self.assets == tuple(sorted(set(self.assets)))
             and all(type(n) is int and n > 0 for n in self.assets))
        need(type(self.accounting) is AccountingSpecification
             and self.accounting.to_dict()["terminal_policy"] == "MARK_WITHOUT_LIQUIDATION")
        for p in (self.signal,self.valuation,self.execution):
            need(type(p) is Eligibility and bool(p.price_flags) and bool(p.duration_flags) and bool(p.status_flags))
            need(set(p.price_flags) <= {"BA","TR"} and p.duration_flags == ("D2",) and p.status_flags == ("A",),
                 "UNSUPPORTED_SYNTHETIC_POLICY")
        need(self.execution.price_flags == ("TR",))


@dataclass(frozen=True)
class PathResult:
    name: str
    days: tuple[AccountingDay, ...]
    decisions: tuple


@dataclass(frozen=True)
class RunResult:
    run_id: str
    manifest_json: str
    paths: tuple[PathResult, ...]
    production_authorized: bool = False


class BacktestRunner:
    @staticmethod
    @fixed_decimal
    def run(data, config):
        need(type(data) is SyntheticDataAdapter and type(config) is RunConfiguration, "UNAUTHORIZED_DATA_SOURCE")
        need(config.benchmark in data.asset_ids and set(config.assets) <= set(data.asset_ids)
             and config.start in data.sessions and config.end in data.sessions)
        sessions = tuple(d for d in data.sessions if config.start <= d <= config.end)
        formations = tuple(a for a,b in zip(sessions,sessions[1:]) if (a.year,a.month) != (b.year,b.month))
        need(bool(formations), "NO_SUPPORTED_FORMATION")
        strategy = EqualWeightStrategy()
        paths = tuple(BacktestRunner._path(data,config,sessions,formations,strategy,benchmark)
                      for benchmark in (False,True))
        payload = dict(schema_version="1.0",scope="SYNTHETIC_ONLY_NOT_INVESTMENT_EVIDENCE",
            dataset_sha256=data.sha256(),configuration_sha256=policy_hash(config),configuration=config,
            source_id=data.source_id,source_classification="PUBLIC_OR_SHAREABLE",synthetic=True,
            output_sha256=policy_hash(paths),production_authorized=False,
            # Full source inventory: future numerical changes produce new run IDs.
            implementation_sha256=implementation_hash())
        return RunResult(policy_hash(payload),canonical(payload),paths)

    @staticmethod
    def _path(data,config,sessions,formations,strategy,benchmark):
        lookup = {(b.asset_id,b.session):b for b in data.bars}
        net = gross = ((CASH,D(1)),)
        previous = None; pending = None; days = []; decisions = []
        zero = config.accounting.to_dict(); zero["transaction_cost_bps"] = "0"
        from .configuration import parse_accounting_specification
        gross_spec = parse_accounting_specification(json.dumps(zero))
        for day in sessions:
            opening = net; nb = sum(dict(net).values()); gb = sum(dict(gross).values()); evidence = ()
            if previous is not None:
                for n,v in net:
                    if n and v: config.valuation.check(lookup.get((n,day)),require_return=True)
                net,evidence = mark_positions(net,previous,day,lookup,config.accounting,price_flags=config.valuation.price_flags)
                gross,_ = mark_positions(gross,previous,day,lookup,config.accounting,price_flags=config.valuation.price_flags)
            marked = net; events = ()
            if pending is not None and pending[0] == day:
                weights = pending[1]
                for n in sorted((set(dict(net))|set(dict(weights)))-{CASH}):
                    config.execution.check(lookup.get((n,day)),execution=True)
                net,event = execute_target(net,weights,day,lookup,config.accounting,
                    cost_basis=config.cost_basis,price_flags=("TR",))
                gross,_ = execute_target(gross,weights,day,lookup,gross_spec,
                    cost_basis=config.cost_basis,price_flags=("TR",))
                events = (event,); pending = None
            formation = None
            if day in formations and (not benchmark or day == formations[0]):
                universe = (config.benchmark,) if benchmark else config.assets
                for n in universe: config.signal.check(lookup.get((n,day)),require_return=True)
                history = replace(data.history(day),asset_ids=universe)
                weights = ((config.benchmark,D(1)),) if benchmark else strategy.targets(history)
                need(type(weights) is tuple and bool(weights), "UNKNOWN_TARGET_REFUSED")
                need(all(type(n) is int and n in universe and type(w) is D and w.is_finite() and w >= 0 for n,w in weights)
                     and len(dict(weights)) == len(weights) and sum(w for _,w in weights) == 1, "INVALID_LONG_ONLY_TARGET")
                execution = sessions[sessions.index(day)+1]
                pending = (execution,((CASH,D(0)),)+weights)
                formation = (day,execution,weights); decisions.append(formation)
            na = sum(dict(net).values()); ga = sum(dict(gross).values())
            days.append(AccountingDay(day,previous,opening,marked,net,gb,ga,nb,na,
                ga/gb-1,na/nb-1,evidence,formation,events)); previous = day
        need(pending is None,"UNSUPPORTED_TERMINAL_EXECUTION")
        return PathResult("BENCHMARK" if benchmark else "periodic_equal_weight",tuple(days),tuple(decisions))


def implementation_hash():
    """Explicit call-time provenance; never import-time filesystem activity."""
    from pathlib import Path
    import hashlib
    root = Path(__file__).resolve().parents[1]
    files = sorted((root/"backtest_tool").glob("*.py"))
    return policy_hash(tuple((str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in files))


@fixed_decimal
def summarize(result):
    need(type(result) is RunResult and result.production_authorized is False)
    rows = []
    for path in result.paths:
        days = path.days
        monthly = calculate_performance(tuple(m.net_return for m in monthly_paths(days) if m.complete))
        elapsed = D((days[-1].session-days[0].session).days)
        need(elapsed > 0)
        wealth = days[-1].net_wealth_after
        peak = D(1); drawdown = D(0)
        for day in days:
            peak = max(peak,day.net_wealth_after); drawdown = min(drawdown,day.net_wealth_after/peak-1)
        rows.append(dict(strategy=path.name,cagr=str(wealth**(D("365.25")/elapsed)-1),
            volatility=None if monthly.annualized_volatility.value is None else str(monthly.annualized_volatility.value),
            sharpe=None if monthly.annualized_sharpe_ratio.value is None else str(monthly.annualized_sharpe_ratio.value),
            max_drawdown=str(drawdown),turnover=str(sum(e.turnover for d in days for e in d.executions)),
            fees=str(sum(e.fee_value for d in days for e in d.executions))))
    return tuple(rows)
