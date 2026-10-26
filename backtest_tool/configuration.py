"""Small closed synthetic accounting configuration, independent of any study."""
from dataclasses import dataclass
from decimal import Decimal
import json
from .common import AccountingError, fixed_decimal, ONE, ZERO, canonical, policy_hash

DEFAULT_ACCOUNTING = {
    "version": "1.0", "transaction_cost_bps": "0",
    "terminal_policy": "MARK_WITHOUT_LIQUIDATION",
    "synthetic_price_flags": ["TR"], "synthetic_duration_flags": ["D2"],
    "synthetic_trading_status_flags": ["A"],
}

@dataclass(frozen=True, slots=True)
class AccountingSpecification:
    canonical_configuration: str

    def __post_init__(self):
        try:
            value = json.loads(self.canonical_configuration)
            if canonical(value) != self.canonical_configuration or type(value) is not dict:
                raise ValueError()
            if type(value['transaction_cost_bps']) is not str:
                raise ValueError()
            cost = Decimal(value['transaction_cost_bps'])
            if not cost.is_finite() or not ZERO <= cost < 10000:
                raise ValueError()
            baseline = dict(value)
            baseline['transaction_cost_bps'] = '0'
            if baseline != DEFAULT_ACCOUNTING:
                raise ValueError()
        except (ValueError, TypeError, KeyError, ArithmeticError):
            raise AccountingError('unsupported accounting configuration') from None

    def to_dict(self):
        return json.loads(self.canonical_configuration)

    @property
    def sha256(self):
        return policy_hash(self.to_dict())

def parse_accounting_specification(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AccountingError('duplicate configuration field')
            result[key] = value
        return result
    def reject(value):
        raise AccountingError('nonfinite configuration')
    return AccountingSpecification(canonical(json.loads(text, object_pairs_hook=unique, parse_constant=reject)))
