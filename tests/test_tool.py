"""SYNTHETIC ONLY: personal tool plumbing, no licensed artifacts or metrics."""
from contextlib import redirect_stdout,redirect_stderr
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest_tool import engine as e
from backtest_tool import reporting as r
from backtest_tool import cli
from backtest_tool.common import policy_hash

ROOT=Path(__file__).resolve().parents[1]


def fixture():
    ds=json.loads((ROOT/'examples/backtest_tool/synthetic_data_v1.json').read_text())
    st=json.loads((ROOT/'examples/backtest_tool/equal_weight_v1.json').read_text())
    return cli.build_demo(ds,st,ROOT)


class ToolEngineTests(unittest.TestCase):
    def setUp(self):self.data,self.cfg=fixture()
    def test_new_strategy_and_separate_benchmark(self):
        out=e.BacktestRunner.run(self.data,self.cfg)
        self.assertEqual(len(out.paths),2)
        self.assertEqual({n for _,_,w in out.paths[0].decisions for n,_ in w},set(self.cfg.assets))
        self.assertNotIn(self.cfg.benchmark,self.cfg.assets)
        self.assertEqual({n for _,_,w in out.paths[1].decisions for n,_ in w},{self.cfg.benchmark})
        self.assertFalse(out.production_authorized)
    def test_repeated_evaluation_deterministic(self):
        self.assertEqual(e.BacktestRunner.run(self.data,self.cfg),e.BacktestRunner.run(self.data,self.cfg))
    def test_fixed_decimal_context(self):
        a=e.BacktestRunner.run(self.data,self.cfg)
        with localcontext() as ctx:
            ctx.prec=8; b=e.BacktestRunner.run(self.data,self.cfg)
        self.assertEqual(a,b)
    def test_unknown_strategy(self):
        with self.assertRaises(e.ToolRefusal):replace(self.cfg,strategy_id='unknown')
    def test_restricted_adapter_refused(self):
        with self.assertRaises(e.ToolRefusal):replace(self.data,source_id='LICENSED_SOURCE')
        with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(object(),self.cfg)
    def test_duplicate_dates(self):
        with self.assertRaises(e.ToolRefusal):replace(self.data,sessions=self.data.sessions+(self.data.sessions[-1],))
    def test_duplicate_observations(self):
        with self.assertRaises(e.ToolRefusal):replace(self.data,bars=self.data.bars+self.data.bars[-1:])
    def test_wrong_row_source(self):
        b=replace(self.data.bars[0],source_reference='SYNTHETIC_OTHER')
        with self.assertRaises(e.ToolRefusal):replace(self.data,bars=(b,)+self.data.bars[1:])
    def test_nonconsecutive_interval(self):
        b=replace(self.data.bars[1],previous_session=None)
        with self.assertRaises(e.ToolRefusal):replace(self.data,bars=(self.data.bars[0],b)+self.data.bars[2:])
    def test_old_holdings_through_next_close(self):
        out=e.BacktestRunner.run(self.data,self.cfg)
        path=out.paths[0];f,ex,_=path.decisions[0]
        formation=next(d for d in path.days if d.session==f)
        execution=next(d for d in path.days if d.session==ex)
        self.assertEqual(formation.closing_net_positions,((0,D(1)),))
        self.assertEqual(execution.marked_net_positions,((0,D(1)),))
        following=path.days[path.days.index(execution)+1]
        self.assertEqual(following.opening_net_positions,execution.closing_net_positions)
        self.assertTrue(following.return_inputs)
    def test_later_execution_still_marks_old_holdings_first(self):
        path=e.BacktestRunner.run(self.data,self.cfg).paths[0]
        day=next(d for d in path.days if d.executions and d.session>path.decisions[0][1])
        lookup={(b.asset_id,b.session):b for b in self.data.bars}
        for n,v in day.opening_net_positions:
            if n and v:
                self.assertLess(abs(dict(day.marked_net_positions)[n]-v*(1+lookup[n,day.session].total_return)),D('1e-27'))
    def test_fee_identity_and_self_financing(self):
        out=e.BacktestRunner.run(self.data,self.cfg)
        for path in out.paths:
            for day in path.days:
                for event in day.executions:
                    notional=sum(abs(t.signed_net_value) for t in event.trades)
                    self.assertLess(abs(event.fee_value-D('0.0005')*notional),D('1e-28'))
                    self.assertLess(abs(event.pretrade_net_wealth-event.posttrade_net_wealth-event.fee_value),D('1e-28'))
    def test_terminal_holdings_preserved(self):
        out=e.BacktestRunner.run(self.data,self.cfg)
        for path in out.paths:
            self.assertTrue(any(n and v for n,v in path.days[-1].closing_net_positions))
            self.assertFalse(any(x.terminal_liquidation for x in path.days[-1].executions))
    def bad(self,day,**changes):
        return replace(self.data,bars=tuple(replace(b,**changes) if b.asset_id==self.cfg.assets[0] and b.session==day else b
                                           for b in self.data.bars))
    def test_future_perturbation_does_not_change_past_decisions(self):
        a=e.BacktestRunner.run(self.data,self.cfg)
        cut=self.data.sessions[95]
        data=replace(self.data,bars=tuple(replace(b,total_return=D('0.01')) if b.session>cut else b for b in self.data.bars))
        b=e.BacktestRunner.run(data,self.cfg)
        self.assertEqual(tuple(d for d in a.paths[0].days if d.session<=cut),tuple(d for d in b.paths[0].days if d.session<=cut))
        self.assertNotEqual(a.run_id,b.run_id)
    def test_future_marks_not_used_to_select_earlier_target(self):
        base=e.BacktestRunner.run(self.data,self.cfg);ex=base.paths[0].decisions[0][1]
        captured=[]
        def targets(strategy,h):
            self.assertTrue(all(b.session<=h.as_of for b in h.observations));captured.append(h.as_of)
            return original(strategy,h)
        original=e.EqualWeightStrategy.targets
        with patch.object(e.EqualWeightStrategy,'targets',targets):
            with self.assertRaises(Exception):e.BacktestRunner.run(self.bad(ex,price_flag='BA'),self.cfg)
        self.assertEqual(captured,[base.paths[0].decisions[0][0]])
    def test_missing_held_valuation_refuses(self):
        base=e.BacktestRunner.run(self.data,self.cfg);ex=base.paths[0].decisions[0][1]
        day=self.data.sessions[self.data.sessions.index(ex)+1]
        with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(self.bad(day,total_return=None),self.cfg)
    def test_signal_and_execution_policies_independent(self):
        base=e.BacktestRunner.run(self.data,self.cfg);f=base.paths[0].decisions[0][0]
        cfg=replace(self.cfg,signal=e.Eligibility(('BA','TR'),('D2',),('A',)))
        e.BacktestRunner.run(self.bad(f,price_flag='BA'),cfg)
        with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(self.bad(f,price_flag='BA'),self.cfg)
    def test_missing_execution_mark(self):
        base=e.BacktestRunner.run(self.data,self.cfg);ex=base.paths[0].decisions[0][1]
        with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(self.bad(ex,close=None),self.cfg)
    def test_unknown_target_refuses(self):
        with patch.object(e.EqualWeightStrategy,'targets',return_value=()):
            with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(self.data,self.cfg)
    def test_short_or_leveraged_target_refuses(self):
        for w in (((990001,D(2)),),((990001,D('-1')),(990002,D(2)))):
            with patch.object(e.EqualWeightStrategy,'targets',return_value=w):
                with self.assertRaises(e.ToolRefusal):e.BacktestRunner.run(self.data,self.cfg)
    def test_hashes_cover_configuration_and_rows(self):
        a=e.BacktestRunner.run(self.data,self.cfg)
        c=replace(self.cfg,assets=(self.cfg.assets[0],))
        b=e.BacktestRunner.run(self.data,c)
        self.assertNotEqual(a.run_id,b.run_id)
        m=json.loads(a.manifest_json)
        self.assertEqual(m['dataset_sha256'],self.data.sha256())
        self.assertEqual(m['configuration_sha256'],policy_hash(self.cfg))
    def test_indicator_api_is_local_only(self):
        from backtest_tool import indicators
        for name in ('trend_200','relative_strength_63','realized_volatility_20'):
            self.assertIs(getattr(e,name),getattr(indicators,name))
    def test_no_data_read_grant_route(self):
        with self.assertRaises(TypeError):
            e.BacktestRunner.run(self.data,self.cfg,read_grant=object())



class ReporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=r.from_synthetic_run(e.BacktestRunner.run(*fixture()))
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='SYNTHETIC_personal_report_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.root.chmod(0o700)
    def test_self_contained_html(self):
        html=r.ReportGenerator.render(self.report)
        self.assertIn('Content-Security-Policy',html);self.assertIn('<svg',html)
        self.assertNotIn('<script',html);self.assertNotIn('https://',html)
        self.assertEqual(html,r.ReportGenerator.render(self.report))
    def test_escaped_untrusted_text(self):
        html=r.ReportGenerator.render(replace(self.report,title='<script>bad()</script>'))
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
    def test_restricted_report_requires_scope(self):
        with self.assertRaisesRegex(e.ToolRefusal,'RESTRICTED_REPORT_OUTPUT_SCOPE_REQUIRED'):
            r.ReportGenerator.render(replace(self.report,synthetic=False,classification='LICENSED_RESTRICTED'))
        self.assertFalse(list(self.root.iterdir()))
    def test_summary_no_invented_wealth(self):
        doc=replace(self.report,quality='SUMMARY_BASED',wealth=())
        self.assertNotIn('<svg',r.ReportGenerator.render(doc))
        with self.assertRaises(e.ToolRefusal):r.ReportGenerator.render(replace(doc,wealth=self.report.wealth))
    def test_atomic_closed_inventory_permissions_and_reload(self):
        target=r.publish_synthetic(self.report,self.root)
        self.assertEqual({p.name for p in target.iterdir()},{'index.html','report.json','manifest.json'})
        self.assertEqual(target.stat().st_mode&0o777,0o500)
        self.assertTrue(all(p.stat().st_mode&0o777==0o400 for p in target.iterdir()))
        self.assertEqual(r.verify_synthetic_report(self.root,self.report.run_id),target/'index.html')
    def test_no_overwrite(self):
        target=r.publish_synthetic(self.report,self.root);before=(target/'index.html').read_bytes()
        with self.assertRaises(e.ToolRefusal):r.publish_synthetic(self.report,self.root)
        self.assertEqual(before,(target/'index.html').read_bytes())
    def test_no_overwrite_at_atomic_publication_boundary(self):
        native=r._rename_exclusive
        def race(fd,stage,target):
            os.mkdir(target,0o700,dir_fd=fd)
            return native(fd,stage,target)
        with patch.object(r,'_rename_exclusive',side_effect=race):
            with self.assertRaises(Exception):r.publish_synthetic(self.report,self.root)
        self.assertEqual([p.name for p in self.root.iterdir()],[self.report.run_id])
        self.assertEqual(list((self.root/self.report.run_id).iterdir()),[])
    def test_failure_cleanup(self):
        with patch.object(r,'_rename_exclusive',side_effect=OSError('SYNTHETIC_FAILURE')):
            with self.assertRaises(OSError):r.publish_synthetic(self.report,self.root)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_post_publication_durability_error_keeps_complete_package(self):
        native=r.os.fsync;calls=0
        def sync(fd):
            nonlocal calls
            calls+=1
            if calls==5:raise OSError('SYNTHETIC_DURABILITY_FAILURE')
            return native(fd)
        with patch.object(r.os,'fsync',side_effect=sync):
            with self.assertRaisesRegex(e.ToolRefusal,'REPORT_PUBLISHED_DURABILITY_UNCONFIRMED_NO_RETRY'):
                r.publish_synthetic(self.report,self.root)
        self.assertEqual(r.verify_synthetic_report(self.root,self.report.run_id).name,'index.html')
    def test_corrupt_artifact(self):
        target=r.publish_synthetic(self.report,self.root);p=target/'index.html';p.chmod(0o600);p.write_bytes(b'bad');p.chmod(0o400)
        with self.assertRaises(e.ToolRefusal):r.verify_synthetic_report(self.root,self.report.run_id)
    def test_path_traversal_and_symlink(self):
        for v in ('../escape','a'*63,'a'*65):
            with self.assertRaises(e.ToolRefusal):r.verify_synthetic_report(self.root,v)
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(e.ToolRefusal):r.publish_synthetic(self.report,link)
    def test_git_workspace_refusal(self):
        (self.root/'.git').mkdir()
        with self.assertRaises(e.ToolRefusal):r.publish_synthetic(self.report,self.root)
    def test_no_network_fallback(self):
        with patch('socket.create_connection',side_effect=AssertionError('NO_NETWORK')):
            r.ReportGenerator.render(self.report)
            e.BacktestRunner.run(*fixture())
    def test_no_import_time_application_io(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('NO_IO')),patch.object(Path,'read_bytes',side_effect=AssertionError('NO_IO')):
            spec=importlib.util.spec_from_file_location('backtest_tool._import_safety',Path(r.__file__))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def test_cli_run_then_report(self):
        out=io.StringIO()
        with redirect_stdout(out):
            code=cli.main(['run','--data','examples/backtest_tool/synthetic_data_v1.json',
                '--strategy','examples/backtest_tool/equal_weight_v1.json','--store',str(self.root)])
        self.assertEqual(code,0)
        value=json.loads(out.getvalue());out=io.StringIO()
        with redirect_stdout(out):self.assertEqual(cli.main(['report','--run-id',value['run_id'],'--store',str(self.root)]),0)
        self.assertTrue(Path(json.loads(out.getvalue())['report']).exists())
    def test_cli_refuses_arbitrary_dataset_file_and_sanitizes(self):
        stderr=io.StringIO()
        with redirect_stderr(stderr):
            code=cli.main(['run','--data',str(self.root/'PRIVATE_SOURCE.json'),
                '--strategy','examples/backtest_tool/equal_weight_v1.json','--store',str(self.root)])
        self.assertEqual(code,2);self.assertNotIn(str(self.root),stderr.getvalue())
        self.assertIn('ONLY_BUNDLED_SYNTHETIC_CONFIGS_SUPPORTED',stderr.getvalue())
        self.assertEqual(list(self.root.iterdir()),[])
