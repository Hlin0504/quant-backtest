# Local release candidate inventory

This candidate is a source-only, synthetic-workflow export. It contains no
inherited history, study results, private settings, source-verification receipts,
protected report publisher, data-provider client or licensed dataset. Code
licensing and external publication are **pending owner approval**. There is no
remote configured and no MIT license is implied.

## Exact tracked release inventory (25 files)

```text
.gitignore
AGENTS.md
README.md
pyproject.toml
backtest_tool/__init__.py
backtest_tool/__main__.py
backtest_tool/accounting.py
backtest_tool/analytics.py
backtest_tool/cli.py
backtest_tool/common.py
backtest_tool/configuration.py
backtest_tool/costs.py
backtest_tool/engine.py
backtest_tool/indicators.py
backtest_tool/monthly.py
backtest_tool/reporting.py
backtest_tool/storage.py
backtest_tool/traded_notional_cost.py
docs/RELEASE_INVENTORY.md
examples/backtest_tool/equal_weight_v1.json
examples/backtest_tool/synthetic_data_v1.json
tests/test_costs.py
tests/test_indicators.py
tests/test_numerics.py
tests/test_tool.py
```

## Deliberate exclusions

All inherited Git metadata/tags/remotes; all original research documentation,
study configuration, identity calendars, receipt/provenance packages, importers,
restricted data/report publishers, original trusted empirical entry point,
source-specific contracts, credentials, environment files, raw/derived data,
real performance summaries and generated reports are excluded. Only generic
file-safety helpers from the old entry point were retained, with no private
identifiers or authorization path. Nothing external to the original Git source
was read or copied. A separate local audit manifest—not a public artifact—lists
the original tracked paths omitted and the partially selected source modules.

## Port boundaries

- Accounting, turnover, gross-notional fee solving, monthly completeness and
  performance arithmetic are selected reusable primitives. Asset keys use the
  generic name `asset_id`; mathematical behavior is preserved.
- The old study-specific configuration hash is replaced by a closed standalone
  accounting specification covering only actual synthetic workflow requirements.
  Costs remain explicit. Unknown fields and empirical-policy objects refuse.
- The study panel/authorization system is not exported. Indicators use a new
  explicit SyntheticPoint/window API with fixed formulas, complete-history,
  adjacency, index reconciliation, source, eligibility and same-segment checks.
  This is not an empirical-data adapter or an authorization bypass.
- HTML and synthetic temporary-store protections remain separate from any
  restricted reporting workflow; the latter is absent. No imports depend on the
  original package, repository, configuration or machine-specific directories.
- Indicator functions remain independent and are not silently turned into a
  new trading strategy. The executable builtin remains periodic equal weight.

## Validation

The relevant offline suite contains **67 passing synthetic tests**. It covers
the runner, separate benchmark, costs/cash conservation, next-close old-holding
exposure, terminal handling, unknown/missing inputs, as-of invariance, indicators,
HTML escaping, atomic publication, immutable permissions, closed inventory,
no overwrite, corrupt reports, paths/symlinks, import safety and no network.

A separate local differential check matched **nine synthetic scenarios / 18
strategy-and-benchmark paths** at 0/5/10 bps, two portfolio sizes and two sample
lengths. All daily positions, returns, cash, fees, trades and terminal holdings
matched after the mechanical identifier-field rename and exclusion of the
intentionally new configuration digest. This test used synthetic generation
only; no private data or empirical outcome was opened or exported.

Python 3.12 source-checkout installation in a fresh virtual environment and
local clone must pass the documented run/report commands before publication.
No third-party package installation is required. A conventional wheel/editable
package installer is not part of this minimal candidate.
