"""Explicit synthetic run/report CLI. No restricted provider or permit issuer."""
import argparse
from datetime import date, timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import sys

from .accounting import SyntheticExecutionBar
from .configuration import parse_accounting_specification, DEFAULT_ACCOUNTING
from .engine import BacktestRunner, Eligibility, RunConfiguration, SyntheticDataAdapter, ToolRefusal, need
from .reporting import from_synthetic_run, publish_synthetic, verify_synthetic_report


def _config(path,repo):
    p=Path(path).absolute()
    need(p.is_relative_to(repo/'examples/backtest_tool') and p.suffix=='.json','ONLY_BUNDLED_SYNTHETIC_CONFIGS_SUPPORTED')
    need(p.resolve(strict=True)==p and not p.is_symlink(),'ONLY_BUNDLED_SYNTHETIC_CONFIGS_SUPPORTED')
    def unique(pairs):
        out={}
        for k,v in pairs:need(k not in out);out[k]=v
        return out
    return json.loads(p.read_text(),object_pairs_hook=unique,parse_constant=lambda _:need(False))


def build_demo(dataset,strategy,repo):
    need(set(dataset)=={'version','kind','dataset_id','sessions','assets'}
         and dataset['version']=='1.0' and dataset['kind']=='synthetic_generated_v1'
         and dataset['dataset_id'].startswith('SYNTHETIC_'),'UNAUTHORIZED_DATA_SOURCE')
    need(type(dataset['sessions']) is int and 20 <= dataset['sessions'] <= 400,'INVALID_FIXTURE_SIZE')
    need(type(dataset['assets']) is list and 1 <= len(dataset['assets']) <= 10)
    sessions=tuple(date(2020,1,2)+timedelta(days=2*i) for i in range(dataset['sessions']))
    numbers=tuple(sorted(dataset['assets']))
    need(all(type(n) is int and 900000 <= n <= 999999 for n in numbers))
    bars=tuple(SyntheticExecutionBar(n,d,sessions[i-1] if i else None,
        D('0.002') if (i+n)%7 else D('-0.003'),D(100),dataset['dataset_id'])
        for n in numbers for i,d in enumerate(sessions))
    data=SyntheticDataAdapter(dataset['dataset_id'],sessions,numbers,bars)
    need(set(strategy)=={'version','strategy_id','assets','benchmark','cost_bps'} and strategy['version']=='1.0')
    base=dict(DEFAULT_ACCOUNTING);base['transaction_cost_bps']=strategy['cost_bps']
    accounting=parse_accounting_specification(json.dumps(base))
    p=Eligibility(('TR',),('D2',),('A',))
    config=RunConfiguration(strategy['strategy_id'],strategy['version'],tuple(strategy['assets']),strategy['benchmark'],
        sessions[0],sessions[-1],accounting,p,p,p)
    return data,config


def main(argv=None):
    parser=argparse.ArgumentParser(prog='backtest',description='Offline synthetic proof of concept; no restricted source access')
    commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('run');run.add_argument('--data',required=True);run.add_argument('--strategy',required=True)
    run.add_argument('--store',required=True,help='Existing private temporary directory; synthetic artifacts only')
    report=commands.add_parser('report');report.add_argument('--run-id',required=True);report.add_argument('--store',required=True)
    args=parser.parse_args(argv)
    try:
        repo=Path(__file__).resolve().parents[1]
        if args.command=='run':
            data,config=build_demo(_config(args.data,repo),_config(args.strategy,repo),repo)
            result=BacktestRunner.run(data,config)
            path=publish_synthetic(from_synthetic_run(result),args.store)
            print(json.dumps({'synthetic':True,'run_id':result.run_id,'report':str(path/'index.html')}))
        else:
            path=verify_synthetic_report(args.store,args.run_id)
            print(json.dumps({'synthetic':True,'report':str(path)}))
        return 0
    except ToolRefusal as error:
        print('BACKTEST_TOOL_REFUSED: '+str(error),file=sys.stderr)
        return 2
    except FileNotFoundError:
        print('BACKTEST_TOOL_REFUSED: MISSING_CONFIGURATION_OR_REPORT',file=sys.stderr)
        return 2
    except Exception:
        # argparse retains usage errors; operational exceptions are sanitized.
        print('BACKTEST_TOOL_REFUSED: unsupported input, permissions, configuration or output scope',file=sys.stderr)
        return 2
