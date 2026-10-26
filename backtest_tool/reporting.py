"""Self-contained local HTML and SYNTHETIC-only artifact persistence.

No remote assets, JavaScript, licensed-data reads or implicit report approval.
Restricted and real-data report publication is not supported.
"""
from dataclasses import dataclass
from decimal import Decimal as D
import hashlib
from html import escape
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

from .storage import _rename_exclusive, _open_directory
from .common import canonical, policy_hash
from .engine import RunResult, ToolRefusal, need, summarize


@dataclass(frozen=True)
class Report:
    title: str
    run_id: str
    provenance: str
    synthetic: bool
    classification: str
    quality: str
    rows: tuple[dict, ...]
    details: tuple[tuple[str,str], ...]
    limitations: tuple[str, ...]
    wealth: tuple[tuple[str,str], ...] = ()


def from_synthetic_run(result):
    need(type(result) is RunResult and result.production_authorized is False)
    m = json.loads(result.manifest_json)
    need(m['synthetic'] is True and m['scope'] == 'SYNTHETIC_ONLY_NOT_INVESTMENT_EVIDENCE')
    return Report('Personal Backtest — Synthetic Demo',result.run_id,result.manifest_json,True,
        'PUBLIC_OR_SHAREABLE','SYNTHETIC_VERIFIED_RUN',summarize(result),
        (('Strategy','Monthly equal-weight; separate buy-and-hold benchmark'),
         ('Execution','Signals after close; next observed-session close; old holdings retain exposure through execution'),
         ('Costs','Explicit gross risky buy-plus-sell notional; self-financing'),
         ('Evaluation','Full-funded wealth; cash earns zero; terminal holdings marked without forced liquidation')),
        ('Artificial observations and calendar, not investment evidence.',
         'Monthly volatility/zero-reference Sharpe exclude initial and terminal partial months.',
         'Missing valuation, UNKNOWN targets and invalid required trades refuse the whole run.',
         'No capacity, market impact, taxes, fills or independently verified risk-free series.',
         'Period attribution and paired inference are not computed by this generic proof of concept.'),
        tuple((str(d.session),str(d.net_wealth_after)) for d in result.paths[0].days))


class ReportGenerator:
    @staticmethod
    def render(report):
        need(type(report) is Report)
        need(report.synthetic is True and report.classification == 'PUBLIC_OR_SHAREABLE',
             'RESTRICTED_REPORT_OUTPUT_SCOPE_REQUIRED')
        need(report.quality in ('SUMMARY_BASED','SYNTHETIC_VERIFIED_RUN'))
        need(report.quality != 'SUMMARY_BASED' or not report.wealth, 'SUMMARY_HAS_NO_VERIFIED_CURVE')
        e = lambda value: escape(str(value),quote=True)
        def number(value,percent=False):
            if value is None:return 'Unavailable'
            v=D(value);need(v.is_finite())
            return e(format(v*100 if percent else v,'.2f'))+('%' if percent else '')
        rows=[]
        for r in report.rows:
            need(set(r) == {'strategy','cagr','volatility','max_drawdown','sharpe','turnover','fees'})
            need(r['fees'] is None or D(r['fees']).is_finite())
            rows.append('<tr><th>'+e(r['strategy'])+'</th>'+''.join('<td>'+number(r[k],k in ('cagr','volatility','max_drawdown'))+'</td>'
                for k in ('cagr','volatility','max_drawdown','sharpe'))+
                '<td>'+number(r['turnover'])+'</td><td>'+('Unavailable' if r['fees'] is None else e(format(D(r['fees']),'.6f')))+'</td></tr>')
        chart='<p>No retained wealth series. No curve or drawdown history has been reconstructed.</p>'
        if report.wealth:
            dates=tuple(x[0] for x in report.wealth)
            from datetime import date
            need(tuple(map(date.fromisoformat,dates)) == tuple(sorted(set(map(date.fromisoformat,dates)))))
            values=tuple(D(v) for _,v in report.wealth)
            need(len(values)>1 and all(v.is_finite() and v>0 for v in values))
            lo,hi=min(values),max(values);scale=hi-lo or D(1)
            points=' '.join(f'{i*900/(len(values)-1):.2f},{180-float((v-lo)/scale)*160:.2f}' for i,v in enumerate(values))
            chart='<svg viewBox="0 0 900 200" role="img" aria-label="Synthetic net wealth; scaled to series range"><polyline fill="none" stroke="#0b8c79" stroke-width="3" points="'+points+'"/></svg><p>Net wealth • '+e(dates[0])+' to '+e(dates[-1])+' • scaled to range '+e(lo)+'–'+e(hi)+'</p>'
        return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>'''+e(report.title)+'''</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f0f4f7;color:#192b3d;font:16px/1.6 system-ui,sans-serif}
main{max-width:1200px;margin:auto;padding:40px 24px}header{background:#142c43;color:#fff;padding:32px;border-radius:18px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.2;margin:8px 0}h2{margin-top:0;font-size:23px}.badge{color:#ffd98a;font-weight:700;letter-spacing:.08em}
section{background:#fff;margin:24px 0;padding:28px;border-radius:16px;box-shadow:0 4px 20px #193c5610}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td,th{padding:14px 10px;border-bottom:1px solid #e5ebef;text-align:right}th:first-child{text-align:left}thead{background:#f0f5f7}.scroll{overflow-x:auto}
dt{font-weight:700;color:#147260}dd{margin:0 0 16px}code{word-break:break-all;font-size:12px}svg{width:100%;height:auto}footer{color:#516478}li{margin:8px 0}
@media print{body{background:white}main{padding:0}section{box-shadow:none;break-inside:avoid}header{color:#142c43;background:white;border-bottom:3px solid #147260}}
</style></head><body><main><header><span class="badge">'''+e(report.quality)+'''</span><h1>'''+e(report.title)+'''</h1><p>Local, offline backtest review • not executable investment evidence</p></header>
<section><h2>Performance at a glance</h2><div class="scroll"><table><thead><tr><th>Path</th><th>Net CAGR</th><th>Volatility¹</th><th>Max drawdown</th><th>Sharpe¹</th><th>Turnover²</th><th>Fees³</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div><p>¹ Annualized monthly moments, zero-reference Sharpe. ² Cumulative half-L1 cash-inclusive turnover. ³ Wealth units, initial capital one.</p></section>
<section><h2>Wealth and evidence availability</h2>'''+chart+'''</section><section><h2>What was tested</h2><dl>'''+''.join('<dt>'+e(k)+'</dt><dd>'+e(v)+'</dd>' for k,v in report.details)+'''</dl></section>
<section><h2>Practical interpretation and limitations</h2><ul>'''+''.join('<li>'+e(s)+'</li>' for s in report.limitations)+'''</ul></section><footer><strong>'''+e(report.classification)+'''</strong><p>Run: <code>'''+e(report.run_id)+'''</code></p><p>Evidence digest: <code>'''+policy_hash(report.provenance)+'''</code></p><p>Browser Print → Save as PDF is optional manual export, not automatic publication.</p></footer></main></body></html>'''


def _destination(directory):
    path=Path(directory)
    need(path.is_absolute() and path.resolve(strict=True)==path,'UNSAFE_REPORT_DESTINATION')
    for p in (path,*path.parents):
        need(not p.is_symlink() and not (p/'.git').exists() and not (p/'.git').is_symlink(),'UNSAFE_REPORT_DESTINATION')
    temp=Path(tempfile.gettempdir()).resolve(strict=True)
    need(path.is_relative_to(temp) and path != temp,'SYNTHETIC_OUTPUT_REQUIRES_PRIVATE_TEMP_DIRECTORY')
    info=path.stat();need(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'UNSAFE_REPORT_DESTINATION')
    return path


def publish_synthetic(report, directory):
    """No restricted publisher: fresh exact output authorization is still needed."""
    html=ReportGenerator.render(report)
    parent=_destination(directory)
    need(len(report.run_id)==64 and all(c in '0123456789abcdef' for c in report.run_id))
    target=parent/report.run_id;need(not target.exists() and not target.is_symlink(),'REPORT_EXISTS')
    data={'index.html':html.encode(),'report.json':(canonical(report)+'\n').encode()}
    m=dict(schema_version='1.0',synthetic=True,classification='PUBLIC_OR_SHAREABLE',run_id=report.run_id,
        files=[dict(path=k,sha256=hashlib.sha256(v).hexdigest(),size=len(v)) for k,v in sorted(data.items())])
    data['manifest.json']=(canonical(m)+'\n').encode()
    fd=_open_directory(parent);stage='.synthetic-report-'+uuid.uuid4().hex
    stage_fd=None;created=[];staging=False;published=False
    try:
        os.mkdir(stage,0o700,dir_fd=fd);staging=True
        stage_fd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        for name,payload in data.items():
            child=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stage_fd)
            created.append(name)
            with os.fdopen(child,'wb') as f:
                f.write(payload);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),0o400)
        os.fchmod(stage_fd,0o500);os.fsync(stage_fd)
        _destination(parent)
        current=parent.stat();opened=os.fstat(fd)
        need((current.st_ino,current.st_dev)==(opened.st_ino,opened.st_dev),'REPORT_PARENT_CHANGED')
        _rename_exclusive(fd,stage,target.name);published=True
        try:os.fsync(fd)
        except OSError:
            raise ToolRefusal('REPORT_PUBLISHED_DURABILITY_UNCONFIRMED_NO_RETRY') from None
    finally:
        try:
            if staging and not published:
                try:
                    info=os.stat(stage,dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:
                    raise ToolRefusal('PUBLICATION_STATUS_UNCERTAIN_NO_RETRY') from None
                if stage_fd is not None:
                    opened=os.fstat(stage_fd)
                    need((info.st_ino,info.st_dev)==(opened.st_ino,opened.st_dev),'REPORT_STAGE_CHANGED')
                    os.fchmod(stage_fd,0o700)
                    for name in created:os.unlink(name,dir_fd=stage_fd)
                os.rmdir(stage,dir_fd=fd)
        finally:
            if stage_fd is not None:os.close(stage_fd)
            os.close(fd)
    return target


def verify_synthetic_report(directory,run_id):
    parent=_destination(directory)
    need(len(run_id)==64 and all(c in '0123456789abcdef' for c in run_id),'INVALID_RUN_ID')
    target=parent/run_id
    need(not target.is_symlink() and target.is_dir(),'REPORT_NOT_FOUND')
    from .storage import _read_files, _json
    raw=_read_files(target,('report.json','index.html','manifest.json'))
    m=_json(raw['manifest.json']);r=_json(raw['report.json'])
    need(m['schema_version']=='1.0' and m['synthetic'] is True and m['classification']=='PUBLIC_OR_SHAREABLE'
         and m['run_id']==run_id and r['run_id']==run_id and r['synthetic'] is True
         and r['classification']=='PUBLIC_OR_SHAREABLE','UNAUTHORIZED_REPORT')
    need(len(m['files'])==2 and {x['path'] for x in m['files']}=={'report.json','index.html'})
    for record in m['files']:
        blob=raw[record['path']]
        need(len(blob)==record['size'] and hashlib.sha256(blob).hexdigest()==record['sha256'],'CORRUPT_REPORT')
    return target/'index.html'
