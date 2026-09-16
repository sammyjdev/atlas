# ATLAS

Public monorepo for three career tools that share one core:

- MERIT: job postings, evidence matching and application tracking.
- ORBIT: AI research radar ranked against the user's profile.
- SAGE: interview study material from markdown.

Modules depend only on `atlas-core` (import name `atlas_core`) and never on
each other. They exchange data through an append-only local exchange.
Decisions are recorded in `docs/adr/`.

Personal data never enters this repository.

## Contracts

Exchange item schemas live in `packages/atlas-core/schemas/` as JSON Schema
and are generated from `atlas_core.contracts`. The rationale is in
`docs/adr/0001-umbrella-monorepo.md`.
