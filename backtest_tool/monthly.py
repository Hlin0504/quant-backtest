"""Explicit complete-month evaluation over a verified daily accounting chain."""
from dataclasses import dataclass
from decimal import Decimal
from .configuration import AccountingError, fixed_decimal, ZERO, ONE

@dataclass(frozen=True, slots=True)
class MonthlyPath:
    year: int
    month: int
    gross_return: Decimal
    net_return: Decimal
    complete: bool
    reason: str | None


@fixed_decimal
def monthly_paths(days):
    """Observed-calendar completeness only, not exchange certification.

    Initial funded month lacks a previous funded month-close; the terminal
    month has no independently established complete endpoint. Keep both in
    wealth, flag them partial, exclude them from monthly moments/paired HAC.
    """
    if not days or tuple(row.session for row in days) != tuple(sorted({row.session for row in days})):
        raise AccountingError("ordered accounting days required")
    for row in days:
        if any(not isinstance(value,Decimal) or not value.is_finite() or value<=ZERO for value in
               (row.gross_wealth_before,row.gross_wealth_after,row.net_wealth_before,row.net_wealth_after)):
            raise AccountingError("finite positive portfolio wealth required")
    for previous,current in zip(days,days[1:]):
        if (current.previous_session != previous.session or current.gross_wealth_before != previous.gross_wealth_after
                or current.net_wealth_before != previous.net_wealth_after):
            raise AccountingError("accounting wealth/interval chain is broken")
    grouped = {}
    for row in days:
        grouped.setdefault((row.session.year, row.session.month), []).append(row)
    months = tuple(grouped)
    if any(b[0]*12+b[1] != a[0]*12+a[1]+1 for a,b in zip(months,months[1:])):
        raise AccountingError("missing whole accounting month")
    output = []
    for i, key in enumerate(months):
        rows = grouped[key]
        complete = 0 < i < len(months)-1
        reason = None if complete else "INITIAL_OR_TERMINAL_MONTH_COMPLETENESS_UNRESOLVED"
        output.append(MonthlyPath(*key, rows[-1].gross_wealth_after/rows[0].gross_wealth_before-ONE,
                                 rows[-1].net_wealth_after/rows[0].net_wealth_before-ONE, complete, reason))
    return tuple(output)
