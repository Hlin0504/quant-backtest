# Development instructions

Work as a single agent. This repository supports offline synthetic backtesting,
not live trading or a data-provider integration. Do not add data or credentials.
Preserve explicit calendar, stable asset identity, as-of histories, independent
signal/valuation/execution checks, next-close timing and self-financing costs.
Unknown targets, missing held returns and invalid required trades must refuse.
Never relabel real observations as synthetic or fill missing values silently.
Use Python 3.12 and standard-library unittest. Run the complete offline suite
before changes are handed off. Document changed formulas or interface contracts.
No network access, dependency installation, external publication, data-license
decision, deletion of user data or broker integration without explicit approval.
The code license remains pending owner confirmation. Do not add MIT by inference.
