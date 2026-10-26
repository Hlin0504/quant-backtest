"""Monthly performance arithmetic only; no data or inference platform."""
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

class MissingValuePolicy(StrEnum):
    ERROR = "error"
    DROP = "drop"


class InferenceInputError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Statistic:
    value: Decimal | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.reason is None):
            raise ValueError("a statistic must have either a value or an undefined reason")

    @property
    def is_defined(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, slots=True)
class PreparedSeries:
    values: tuple[Decimal, ...]
    input_count: int
    missing_count: int


def prepare_series(
    values: Iterable[Decimal | None], missing_value_policy: MissingValuePolicy
) -> PreparedSeries:
    raw = tuple(values)
    prepared: list[Decimal] = []
    missing_count = 0
    for index, value in enumerate(raw):
        if value is None:
            missing_count += 1
            if missing_value_policy is MissingValuePolicy.ERROR:
                raise InferenceInputError("missing_value", f"return at zero-based index {index} is missing")
            continue
        if not isinstance(value, Decimal) or not value.is_finite():
            raise InferenceInputError(
                "invalid_value", f"return at zero-based index {index} must be a finite Decimal or None"
            )
        prepared.append(value)
    return PreparedSeries(tuple(prepared), len(raw), missing_count)

class AnalyticsInputError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class PerformanceConfig:
    periods_per_year: int = 12
    monthly_risk_free_rate: Decimal = Decimal("0")
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.ERROR

    def __post_init__(self) -> None:
        if (
            isinstance(self.periods_per_year, bool)
            or not isinstance(self.periods_per_year, int)
            or self.periods_per_year < 1
        ):
            raise ValueError("periods_per_year must be a positive integer")
        if (
            not isinstance(self.monthly_risk_free_rate, Decimal)
            or not self.monthly_risk_free_rate.is_finite()
            or self.monthly_risk_free_rate < Decimal("-1")
        ):
            raise ValueError("monthly_risk_free_rate must be a finite simple return no smaller than -1")
        if not isinstance(self.missing_value_policy, MissingValuePolicy):
            raise ValueError("missing_value_policy must be a MissingValuePolicy")


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    input_count: int
    observation_count: int
    missing_count: int
    arithmetic_mean_monthly_return: Statistic
    geometric_cumulative_return: Statistic
    geometric_annualized_return: Statistic
    annualized_volatility: Statistic
    annualized_sharpe_ratio: Statistic
    maximum_drawdown: Statistic
    periods_per_year: int
    risk_free_rate_convention: str
    volatility_convention: str = "sample monthly standard deviation (n-1) times sqrt(periods_per_year)"
    drawdown_convention: str = "minimum compounded wealth / prior peak - 1; reported as non-positive return"


def _undefined(reason: str) -> Statistic:
    return Statistic(None, reason)


def calculate_performance(
    returns: Iterable[Decimal | None], config: PerformanceConfig | None = None
) -> PerformanceMetrics:
    """Calculate performance from monthly simple returns only."""
    config = config or PerformanceConfig()
    prepared = prepare_series(returns, config.missing_value_policy)
    values = prepared.values
    for index, value in enumerate(values):
        if value < Decimal("-1"):
            raise AnalyticsInputError(
                "return_below_minus_one",
                f"used return at zero-based index {index} is below -1",
            )
    n = len(values)
    risk_free_convention = (
        f"constant simple monthly risk-free return {config.monthly_risk_free_rate}; "
        "Sharpe uses monthly arithmetic excess returns and sqrt(periods_per_year) scaling"
    )
    if n == 0:
        reason = "no_observations"
        return PerformanceMetrics(
            input_count=prepared.input_count,
            observation_count=0,
            missing_count=prepared.missing_count,
            arithmetic_mean_monthly_return=_undefined(reason),
            geometric_cumulative_return=_undefined(reason),
            geometric_annualized_return=_undefined(reason),
            annualized_volatility=_undefined(reason),
            annualized_sharpe_ratio=_undefined(reason),
            maximum_drawdown=_undefined(reason),
            periods_per_year=config.periods_per_year,
            risk_free_rate_convention=risk_free_convention,
        )

    mean = sum(values, Decimal("0")) / Decimal(n)
    growth = Decimal("1")
    peak = Decimal("1")
    maximum_drawdown = Decimal("0")
    for value in values:
        growth *= Decimal("1") + value
        if growth > peak:
            peak = growth
        drawdown = growth / peak - Decimal("1")
        if drawdown < maximum_drawdown:
            maximum_drawdown = drawdown
    cumulative = growth - Decimal("1")
    if growth == 0:
        annualized = Decimal("-1")
    else:
        exponent = Decimal(config.periods_per_year) / Decimal(n)
        annualized = growth ** exponent - Decimal("1")

    if n < 2:
        annualized_volatility = _undefined("requires_at_least_two_observations")
        sharpe = _undefined("requires_at_least_two_observations")
    else:
        sum_squared = sum(((value - mean) ** 2 for value in values), Decimal("0"))
        monthly_standard_deviation = (sum_squared / Decimal(n - 1)).sqrt()
        annualized_volatility = Statistic(
            monthly_standard_deviation * Decimal(config.periods_per_year).sqrt()
        )
        if monthly_standard_deviation == 0:
            sharpe = _undefined("zero_excess_return_variance")
        else:
            mean_excess = mean - config.monthly_risk_free_rate
            sharpe = Statistic(
                mean_excess
                / monthly_standard_deviation
                * Decimal(config.periods_per_year).sqrt()
            )

    return PerformanceMetrics(
        input_count=prepared.input_count,
        observation_count=n,
        missing_count=prepared.missing_count,
        arithmetic_mean_monthly_return=Statistic(mean),
        geometric_cumulative_return=Statistic(cumulative),
        geometric_annualized_return=Statistic(annualized),
        annualized_volatility=annualized_volatility,
        annualized_sharpe_ratio=sharpe,
        maximum_drawdown=Statistic(maximum_drawdown),
        periods_per_year=config.periods_per_year,
        risk_free_rate_convention=risk_free_convention,
    )
