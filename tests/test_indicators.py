"""Invented histories only; no real assets, dates or returns are imported."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D, localcontext, Context, ROUND_HALF_EVEN
import unittest

from backtest_tool import indicators as i


def points(count=220, value=D('0.001')):
    sessions = tuple(date(2020,1,2)+timedelta(days=2*k) for k in range(count))
    result=[]
    with localcontext(Context(prec=34,rounding=ROUND_HALF_EVEN)):
        index=D(100)
        for k, day in enumerate(sessions):
            if k:
                index *= 1+value
            result.append(i.SyntheticPoint(990001, day, sessions[k-1] if k else None,
                                          value,index,1,'SYNTHETIC_INDICATOR'))
    return tuple(result),sessions


class IndicatorTests(unittest.TestCase):
    def setUp(self):
        self.rows,self.sessions=points()
    def run_feature(self,name,rows=None,day=None):
        return getattr(i,name)(self.rows if rows is None else rows,self.sessions,990001,self.sessions[-1] if day is None else day)
    def test_exact_trend_boundary(self):
        self.assertEqual(self.run_feature('trend_200',day=self.sessions[198]).reason,'INSUFFICIENT_HISTORY')
        self.assertTrue(self.run_feature('trend_200',day=self.sessions[199]).valid)
        with localcontext(Context(prec=34,rounding=ROUND_HALF_EVEN)):
            expected=sum((p.total_return_index for p in self.rows[-200:]),D(0))/D(200)
        result=self.run_feature('trend_200')
        self.assertEqual(result.value,expected)
        self.assertEqual(result.state,'ABOVE')
    def test_exact_relative_strength_boundary(self):
        self.assertEqual(self.run_feature('relative_strength_63',day=self.sessions[62]).reason,'INSUFFICIENT_HISTORY')
        result=self.run_feature('relative_strength_63',day=self.sessions[63])
        self.assertTrue(result.valid)
        with localcontext(Context(prec=34,rounding=ROUND_HALF_EVEN)):
            expected=D(1)
            for _ in range(63):expected*=D('1.001')
            expected-=1
        self.assertEqual(result.value,expected)
    def test_exact_volatility_boundary_and_zero(self):
        self.assertEqual(self.run_feature('realized_volatility_20',day=self.sessions[19]).reason,'INSUFFICIENT_HISTORY')
        result=self.run_feature('realized_volatility_20',day=self.sessions[20])
        self.assertTrue(result.valid)
        self.assertEqual(result.value,0)
    def test_equal_trend(self):
        rows,sessions=points(value=D(0))
        self.assertEqual(i.trend_200(rows,sessions,990001,sessions[-1]).state,'EQUAL')
    def test_sample_variance_divisor_and_annualization(self):
        with localcontext(Context(prec=34,rounding=ROUND_HALF_EVEN)):
            rows=[];value=D(100)
            for k,p in enumerate(self.rows):
                ret=D('0.01') if k%2 else D('-0.01')
                if k:value*=1+ret
                rows.append(replace(p,total_return=ret,total_return_index=value))
            returns=[p.total_return for p in rows[-20:]]
            mean=sum(returns,D(0))/20
            expected=(sum(((r-mean)**2 for r in returns),D(0))/19).sqrt()*D(252).sqrt()
        self.assertEqual(self.run_feature('realized_volatility_20',tuple(rows)).value,expected)
    def test_missing_return_and_endpoint_refused(self):
        for field in ('total_return','total_return_index'):
            rows=self.rows[:-1]+(replace(self.rows[-1],**{field:None}),)
            self.assertEqual(self.run_feature('trend_200',rows).reason,'MISSING_RETURN_OR_INDEX')
    def test_segment_boundary_refused(self):
        rows=self.rows[:-1]+(replace(self.rows[-1],segment=2),)
        self.assertEqual(self.run_feature('relative_strength_63',rows).reason,'SEGMENT_BOUNDARY_OR_UNDEFINED')
    def test_adjacency_and_missing_sessions_refused(self):
        rows=self.rows[:-1]+(replace(self.rows[-1],previous_session=self.sessions[-3]),)
        self.assertEqual(self.run_feature('relative_strength_63',rows).reason,'NONCONSECUTIVE_INTERVAL')
        self.assertEqual(self.run_feature('trend_200',self.rows[:-1]).reason,'MISSING_DUPLICATE_OR_UNORDERED_SESSION')
    def test_first_window_endpoint_interval_is_checked(self):
        rows=tuple(replace(p,previous_session=None) if p.session==self.sessions[-200] else p for p in self.rows)
        self.assertEqual(self.run_feature('trend_200',rows).reason,'NONCONSECUTIVE_INTERVAL')
    def test_unknown_or_false_eligibility_refused(self):
        for flag,reason in ((None,'UNKNOWN_ELIGIBILITY'),(False,'INELIGIBLE_WINDOW')):
            rows=self.rows[:-1]+(replace(self.rows[-1],eligible=flag),)
            self.assertEqual(self.run_feature('trend_200',rows).reason,reason)
    def test_unsupported_flags_refused(self):
        for field in ('price_flag','duration_flag','trading_status_flag'):
            rows=self.rows[:-1]+(replace(self.rows[-1],**{field:'UNKNOWN'}),)
            self.assertEqual(self.run_feature('trend_200',rows).reason,'UNSUPPORTED_SOURCE_FLAGS')
    def test_mixed_or_real_source_refused(self):
        for source in ('SYNTHETIC_OTHER','REAL_SOURCE'):
            rows=self.rows[:-1]+(replace(self.rows[-1],source_reference=source),)
            self.assertFalse(self.run_feature('trend_200',rows).valid)
    def test_future_values_do_not_change_past(self):
        cutoff=self.sessions[201]
        changed=tuple(replace(p,total_return=None,total_return_index=None,segment=None,eligible=None)
                      if p.session>cutoff else p for p in self.rows)
        for name in ('trend_200','relative_strength_63','realized_volatility_20'):
            self.assertEqual(self.run_feature(name,day=cutoff),self.run_feature(name,changed,cutoff))
    def test_bad_index_consistency_refused(self):
        rows=self.rows[:-1]+(replace(self.rows[-1],total_return_index=D(999)),)
        self.assertEqual(self.run_feature('trend_200',rows).reason,'INDEX_RETURN_INCONSISTENCY')
    def test_late_start_does_not_fill_warmup(self):
        self.assertFalse(self.run_feature('trend_200',self.rows[50:]).valid)
    def test_repeatability_and_decimal_context(self):
        expected=self.run_feature('trend_200')
        with localcontext() as ctx:
            ctx.prec=8
            self.assertEqual(self.run_feature('trend_200'),expected)
