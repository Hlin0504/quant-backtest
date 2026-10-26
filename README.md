# Quant Backtest

A small, deterministic Python foundation for **offline synthetic backtesting**
and self-contained local HTML reports. It is a developer starting point, not a
live-trading system, investment recommendation or general real-market platform.

**Release status:** local release candidate. License and publication are pending
owner approval. No MIT or other redistribution license has been granted yet.

## Setup / installation

Use Python **3.12** on macOS or Linux with POSIX private-file permissions and
exclusive atomic rename support. Windows report publication is not supported.
There are no third-party runtime or test dependencies.
After the approved repository is published, clone it and use a source checkout:

```sh
git clone https://github.com/Hlin0504/quant-backtest.git
cd quant-backtest
python3.12 -m venv .venv
source .venv/bin/activate
python -m backtest_tool --help
```

Before publication, use the prepared local directory in place of the clone step.
Run commands from the checkout root. This v1 uses source-checkout installation:
**no `pip install`, wheel build, private configuration or package download is
needed**. Wheel/editable-install packaging is not implemented or claimed.

## Synthetic strategy and HTML report

The bundled inputs generate three invented assets on an artificial two-day
calendar. They contain no real prices, returns, security identities or source
extracts. The example allocates equally to two explicitly configured assets;
a third is an independent buy-and-hold benchmark, never an implicit holding.

```sh
BACKTEST_DEMO_STORE=$(python -c 'from pathlib import Path; import tempfile; print(Path(tempfile.mkdtemp(prefix="quant-demo-")).resolve())')
python -m backtest_tool run \
  --data examples/backtest_tool/synthetic_data_v1.json \
  --strategy examples/backtest_tool/equal_weight_v1.json \
  --store "$BACKTEST_DEMO_STORE"
```

The command prints a deterministic synthetic run ID and HTML location. Read and
verify the existing report without rerunning the backtest:

```sh
python -m backtest_tool report \
  --run-id RUN_ID_PRINTED_ABOVE --store "$BACKTEST_DEMO_STORE"
```

Open the printed index.html manually in a browser. No browser or upload is
started automatically. The self-contained report has no JavaScript, remote
fonts, analytics or other network resources. It reports synthetic—not empirical—
performance and a synthetic wealth series. A new run directory refuses overwrite.
Only existing owner-private temporary stores outside Git are supported. Report
directories are 0500 and their three files (HTML, report JSON, manifest) are 0400.

## Numerical and execution conventions

- Immutable ordered sessions, positive stable asset IDs, unique asset/session
  keys and exact preceding-session links. Ticker is not a key.
- Strategies receive an immutable History through formation close only. Form
  on the last declared session of a month; execute at the next declared close.
  Old holdings earn through that execution close; new holdings earn afterward.
- Signal, held-valuation and required-trade eligibility are separate. The toy
  flags are explicit fixture conventions, not a real-market taxonomy. Midpoint
  marks may be explicitly allowed for valuation; execution requires trade marks.
- Cash starts at one and earns zero. Missing held returns, unknown targets,
  unsupported flags, invalid required marks, shorts and leverage refuse; no
  fallback asset, delayed execution, imputation or silent liquidation.
- The runner explicitly uses gross risky buy-plus-sell notional fees. The
  primitive-level default remains the turnover proxy; fee basis is never changed
  implicitly. Fees are self-financing and target weights apply to post-fee wealth.
- Decimal arithmetic uses precision 34 / ROUND_HALF_EVEN. Terminal holdings are
  marked without forced liquidation or an invented next-session execution.
- Full-funded CAGR/daily drawdown retain the full path. Monthly moments exclude
  initial and terminal months whose completeness is unverified. Sharpe uses a
  zero reference, not an independently verified risk-free series.

## Modules and strategy extension

`engine.py` owns History, Strategy, SyntheticDataAdapter, RunConfiguration and
BacktestRunner. `accounting.py`, `costs.py` and `traded_notional_cost.py` own
valuation and fee funding. `indicators.py` provides guarded fixed 200-endpoint
trend, 63-return momentum and 20-return sample volatility on SyntheticPoint
windows. `analytics.py` and `monthly.py` evaluate supported return paths.
`reporting.py` / `storage.py` render and verify private synthetic reports.

There is currently **one executable strategy builtin**, periodic_equal_weight
v1.0. The Strategy protocol is a development interface, not a dynamic plugin
registry. To extend it:

1. Add a new pure `targets(History)` implementation with a new strategy ID/version.
2. Explicitly extend the runner dispatch and RunConfiguration allowlist; do not
   overload the existing equal-weight identity or pass future data to History.
3. Add a versioned bundled JSON example with explicit assets, benchmark and costs.
   No strategy may substitute assets silently or use the benchmark implicitly.
4. Add exact numerical, warm-up, missingness, cost, next-close, terminal,
   future-perturbation and deterministic replay tests. Run the entire suite.

Indicator inputs require complete, eligible, adjacent, same-segment synthetic
windows. They return explicit invalid reasons instead of filling history; they
are not an adaptation of any proprietary dataset or its permission contracts.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -v
```

## Limitations and data responsibilities

Generic CSV/Parquet market-data loading, arbitrary real-data strategies, strategy
plugins, empirical authorization, provider acquisition, cross-sectional rotation,
parameter fitting, live brokers and trading are **not implemented**. Do not
rename real observations SYNTHETIC to bypass this scope. Artificial session dates
are not exchange-calendar evidence. Simulated fees/close marks are not actual
fills, capacity, spread, impact, taxes or executable investment performance.

No third-party or licensed dataset is bundled. Users must obtain and comply with
all data licenses before any future real-data adapter is introduced. A future
code license would not grant redistribution rights to market data or reports.
Keep credentials, data and generated outputs outside Git; `.gitignore` is not a
substitute for reviewing staged files and repository history.

See `docs/RELEASE_INVENTORY.md` for included/excluded files and validation scope.
