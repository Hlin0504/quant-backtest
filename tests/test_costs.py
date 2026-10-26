from decimal import Decimal
import unittest

from backtest_tool.costs import (
    CASH_ASSET_ID,
    calculate_turnover,
    drift_pretrade_weights,
    proportional_transaction_cost,
)


class PortfolioAccountingTests(unittest.TestCase):
    def test_drifted_weights_are_independently_calculated(self) -> None:
        drifted = drift_pretrade_weights(
            {"A": Decimal("0.5"), "B": Decimal("0.5"), CASH_ASSET_ID: Decimal("0")},
            {"A": Decimal("0.2"), "B": Decimal("-0.2")},
            cash_return=Decimal("0"),
        )
        self.assertEqual(drifted["A"], Decimal("0.6"))
        self.assertEqual(drifted["B"], Decimal("0.4"))
        self.assertEqual(drifted[CASH_ASSET_ID], Decimal("0"))

    def test_turnover_uses_pretrade_drifted_weights(self) -> None:
        turnover = calculate_turnover(
            {"A": Decimal("0.6"), "B": Decimal("0.4"), CASH_ASSET_ID: Decimal("0")},
            {"A": Decimal("0.5"), "B": Decimal("0.5"), CASH_ASSET_ID: Decimal("0")},
        )
        self.assertEqual(turnover, Decimal("0.1"))

    def test_initial_cash_to_fully_invested_turnover_is_one(self) -> None:
        turnover = calculate_turnover(
            {CASH_ASSET_ID: Decimal("1")},
            {"A": Decimal("0.5"), "B": Decimal("0.5"), CASH_ASSET_ID: Decimal("0")},
        )
        self.assertEqual(turnover, Decimal("1"))

    def test_proportional_cost_converts_basis_points(self) -> None:
        self.assertEqual(
            proportional_transaction_cost(Decimal("0.25"), Decimal("100")),
            Decimal("0.0025"),
        )


if __name__ == "__main__":
    unittest.main()
