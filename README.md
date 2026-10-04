# ATLAS

Public monorepo for the career suite:

- `atlas-kit` (import `atlas_core`): shared contracts, config and the exchange. Imports no module.
- MERIT (`atlas-merit`): ledger, match, and the loopback debug UI `merit serve`.
- SAGE (`atlas-sage`): interview prep. The private vault stays in the sage checkout.
- ALFA (`atlas-alfa`): Tess, the interface you open. It imports Merit and does not import Sage.
- ORBIT: not in this tree.

Merit and Sage do not import each other. `merit rank` publishes a `DemandSignal`
into the vault exchange and Sage reads it to pick topics. Alfa is the shell, not
a fourth brain.
Decisions are recorded in `docs/adr/`.

Personal data never enters this repository.

## Contracts

Exchange item schemas live in `packages/atlas-core/schemas/` as JSON Schema
and are generated from `atlas_core.contracts`. The rationale is in
`docs/adr/0001-umbrella-monorepo.md`.

## Development

```
uv sync --all-packages --dev
uv run pytest && uv run ruff check packages && uv run lint-imports
```
