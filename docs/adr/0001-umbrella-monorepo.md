# ADR 0001: ATLAS umbrella monorepo for the career modules

**Status:** Proposed
**Date:** 2026-09-16

## Context

MERIT (job postings and evidence matching), SAGE (interview study from
markdown) and the new ORBIT (AI research radar) are three tools built by
one person around one profile. Today MERIT and SAGE are separate repos,
each with its own LLM gateway, its own config loading and no shared
contract. SAGE derives interview topics from a hand-fed `inputs/jds/`
folder even though MERIT already knows which skills the market demands.
ORBIT needs the same profile axes MERIT uses to judge evidence.

Constraints that shaped the decision:

- The public product must be usable by other developers, so code and
  personal data must live apart.
- Each module must keep working alone; a user who wants only SAGE must
  not need MERIT.
- Storage choices differ per module and are deliberate: SAGE keeps
  markdown as the source of truth, MERIT keeps a LangGraph SQLite
  checkpoint, ORBIT needs a vector index.
- The runtime is GitHub Actions on a self-hosted runner at home for now,
  with a VPS as a later host swap that must not change code.
- On PyPI the names `atlas` and `atlas-core` belong to unrelated projects.

## Decision

1. One public monorepo `atlas` (uv workspace) holds the three modules and
   a core package. Distribution names: `atlas-kit` (core, import name
   `atlas_core`), `atlas-merit`, `atlas-orbit`, `atlas-sage` (import
   names `atlas_merit`, `atlas_orbit`, `atlas_sage`). The CLI facade is
   `atlas`.
2. Three layers: interfaces (`atlas` CLI, local FastAPI plus htmx UI,
   GitHub Actions workflows), modules, core. Modules import only
   `atlas_core`; `atlas_core` imports no module. import-linter enforces
   both rules in CI.
3. Core owns: the profile (single source of truth for the honesty rule,
   skills with evidence and source, aliases, interest axes), the exchange
   contracts (`JobPosting`, `DemandSignal`, `ResearchItem`, reserved
   `StudyRequest`) exported as JSON Schema with a `schema_version`, the
   LLM gateway (pluggable providers, fallback, per-call cost), the eval
   harness (golden sets with a per-module floor), and config
   (`~/.atlas/config.toml`, secrets only in env or keychain).
4. Each module owns its storage. MERIT keeps SQLite checkpoint, ORBIT
   uses SQLite with a vector extension, SAGE keeps markdown.
5. Modules integrate through an append-only exchange: one immutable JSON
   file per item under `exchange/<channel>/<id>.json`, id sortable by
   publish time, one cursor per consumer, no module edits another
   module's files. There is no central orchestrator; each module has its
   own trigger and reads the exchange when it runs. Integrations are
   opt-in via config.
6. v1 flow: MERIT publishes `DemandSignal`; ORBIT weights profile axes
   with it; SAGE prioritizes topics with it (replacing `inputs/jds/`).
   ORBIT publishes `ResearchItem`; SAGE turns it into study material.
   `StudyRequest` (SAGE to ORBIT) is reserved and not implemented.
7. Three repositories: `atlas` (public, code only), `atlas-vault`
   (private: SAGE vault, ORBIT drafts, LinkedIn drafts, synced to
   Obsidian), `atlas-ops` (private: scheduled workflows for the
   self-hosted runner). Personal data (InMails, dossiers, ledger, real
   profile values) never enters git.
8. The self-hosted runner attaches only to private repos. Public `atlas`
   runs CI on hosted runners only.
9. Module capture policy: API and RSS only, no crawling. MERIT may fetch
   one public guest job card per posting the owner's own alerts already
   delivered.

## Consequences

- MERIT and SAGE are imported with history preserved, after their
  personal-data paths are stripped, because published claims (C-MERIT-001)
  rest on that history.
- The two LLM gateways collapse into one in core; both modules change
  their imports and nothing else in that step.
- SAGE's `inputs/jds/` becomes a legacy input once `DemandSignal` exists.
- Adding a module means adding a workspace package plus one line in the
  import-linter independence contract; nothing else in core changes.
- Hosted-mode users get the same image and workflows with a different
  `runs-on` and a git-backed exchange store; that store is deferred until
  hosted mode is built.
- Package naming diverges from the umbrella name for the core
  distribution (`atlas-kit`). Renaming later touches only `name` fields.
- Rejected alternatives: separate repos with a shared library on PyPI
  (three release cadences for one author), a central orchestrator
  (single point of failure at home, and modules stop being standalone),
  and a shared database (breaks SAGE's markdown principle and couples
  storage).
