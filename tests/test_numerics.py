from datetime import date
from decimal import Decimal as D
import json
import unittest
from backtest_tool.configuration import DEFAULT_ACCOUNTING, parse_accounting_specification, AccountingError
from backtest_tool.accounting import execute_target, SyntheticExecutionBar, mark_positions
from backtest_tool.traded_notional_cost import gross_notional_fee
from backtest_tool.analytics import calculate_performance


class NumericalReferenceTests(unittest.TestCase):
    def specification(self,bps='5'):
        return parse_accounting_specification(json.dumps(DEFAULT_ACCOUNTING|dict(transaction_cost_bps=bps)))
    def test_initial_gross_notional_fee_independent_formula(self):
        value=gross_notional_fee({0:D(1)},{0:D(0),990001:D(1)},D(5))
        # Entry fee solves fee = k*(1-fee), not k*initial capital.
        self.assertLess(abs(value-D('0.0005')/D('1.0005')),D('1e-27'))
    def test_fee_default_is_still_turnover_proxy(self):
        day=date(2020,2,3)
        bar=SyntheticExecutionBar(990001,day,None,D(0),D(100),'SYNTHETIC_COST_TEST')
        positions,event=execute_target(((0,D(1)),),((0,D(0)),(990001,D(1))),day,{(990001,day):bar},self.specification())
        self.assertEqual(event.fee_value,D('0.0005'))
    def test_unknown_configuration_and_empirical_policy_refused(self):
        with self.assertRaises(AccountingError):
            parse_accounting_specification(json.dumps(DEFAULT_ACCOUNTING|dict(unknown=True)))
        day=date(2020,2,3)
        bar=SyntheticExecutionBar(990001,day,date(2020,2,1),D(0),D(100),'SYNTHETIC_COST_TEST')
        with self.assertRaises(AccountingError):
            mark_positions(((0,D(0)),(990001,D(1))),date(2020,2,1),day,{(990001,day):bar},self.specification(),eligibility_policy=object())
    def test_zero_fee(self):
        self.assertEqual(gross_notional_fee({0:D(1)},{0:D(0),990001:D(1)},D(0)),0)
    def test_invalid_fee_inputs_refuse(self):
        for rate in (D(-1),D(10000),D('NaN')):
            with self.assertRaises(AccountingError):
                gross_notional_fee({0:D(1)},{0:D(0),990001:D(1)},rate)
    def test_monthly_moments_reference(self):
        result=calculate_performance((D('0.1'),D('-0.1')))
        self.assertEqual(result.geometric_cumulative_return.value,D('-0.01'))
        self.assertEqual(result.arithmetic_mean_monthly_return.value,0)
        self.assertEqual(result.maximum_drawdown.value,D('-0.1'))
        self.assertEqual(result.annualized_sharpe_ratio.value,0)
    def test_missing_analytics_refuses(self):
        with self.assertRaises(ValueError):
            calculate_performance((D(0),None))
    def test_constant_return_sharpe_undefined(self):
        result=calculate_performance((D('0.01'),D('0.01')))
        self.assertIsNone(result.annualized_sharpe_ratio.value)
        self.assertEqual(result.annualized_volatility.value,0)
