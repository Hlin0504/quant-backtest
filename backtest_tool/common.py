"""Deterministic JSON and fixed Decimal arithmetic; no import-time I/O."""
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from functools import wraps
import hashlib
import json

class PolicyError(ValueError):
    pass

ZERO, ONE = Decimal(0), Decimal(1)

def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise PolicyError("timezone-aware timestamp required")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


def canonical(value):
    return json.dumps(plain(value),sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)


def policy_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def fixed_decimal(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext(Context(prec=34, rounding=ROUND_HALF_EVEN)):
            return function(*args, **kwargs)
    return wrapped


class AccountingError(ValueError):
    """Refusal: no partial result is returned as a valid research run."""
