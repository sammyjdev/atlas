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
- On PyPI the names `atlas` and `atlas-core` belong to unrelated projects; `atlas-kit`, `atlas-merit`, `atlas-orbit` and `atlas-sage` were free when checked on 2026-09-16.

## Decision

1. One public monorepo `atlas` (uv workspace) holds the three modules and
   a core package. Distribution names: `atlas-kit` (core, import name
   `atlas_core`), `atlas-merit`, `atlas-orbit`, `atlas-sage` (import
   names `atlas_merit`, `atlas_orbit`, `atlas_sage`). The CLI facade is
   `atlas`, shipped as a console script by `atlas-kit`; the unrelated PyPI `atlas` project may ship the same script name, so the install docs warn about the collision.
2. Three layers: interfaces (`atlas` CLI, local FastAPI plus htmx UI,
   GitHub Actions workflows), modules, core. Modules import only
   `atlas_core`; `atlas_core` imports no module. import-linter enforces
   both rules in CI.
3. Core owns: the profile (single source of truth for the honesty rule,
   skills with evidence and source, aliases, interest axes), the exchange
   contracts (`JobPosting`, `DemandSignal`, `ResearchItem`, reserved
   `StudyRequest`) exported as JSON Schema with a `schema_version`, the
   LLM gateway (pluggable providers, fallback, per-call cost), the eval
   harness (golden sets with a per-module acceptance floor, each floor set and justified in that module's own ADR), and config
   (`~/.atlas/config.toml`; secrets only in environment variables, or the OS keyring where one exists - the dev machine is macOS, the runner is Linux).
4. Each module owns its storage. MERIT keeps SQLite checkpoint, ORBIT
   uses SQLite with a vector extension (`sqlite-vec` is the candidate; support on the target platform is not verified yet), SAGE keeps markdown.
5. Modules integrate through an append-only exchange: one immutable JSON
   file per item under `exchange/<channel>/<id>.json`, id sortable by
   publish time, one cursor per consumer, no module edits another
   module's files. Ids are a zero-padded nanosecond timestamp plus a random suffix, so lexicographic order equals publish order on one host. A cursor is the last id a consumer processed and it reads only ids above it, so an item written below an advanced cursor is never seen; today one runner serializes every job, so that case cannot arise, and the first second producer or the git-backed store supersedes this rule. The exchange grows without bound: no retention or compaction policy exists yet. There is no `ExchangeStore` interface: only the local file store exists, and the abstraction waits until the git-backed hosted-mode store is a real second implementation. There is no central orchestrator; each module has its
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
8. The self-hosted runner attaches only to private repos, because a pull request from a fork of the public repo would otherwise execute arbitrary code on the home host. Public `atlas` runs CI on hosted runners only. Host swaps stay code-free because every module runs from one image with state under a single volume; only `runs-on` changes.
9. Module capture policy: public APIs and feeds only, no crawlers and no authenticated endpoints. One exception: MERIT fetches the public LinkedIn guest job card for a posting the owner's own job alerts already delivered, one request per posting, no discovery and no pagination. The bound is the alert inbox, not a code check, so it is an exception and not a precedent: it may be blocked at any time, MERIT's BACKLOG standing constraint is updated to name it, and any new capture path that is not an API or a feed needs its own ADR.

## Consequences

- MERIT and SAGE are imported with `git filter-repo`, which strips their personal-data paths and rewrites every commit hash. Dates, authorship and ordering survive; the original hashes do not, so the private repos are kept archived as the resolvable anchor for published claims such as C-MERIT-001 (MERIT's benchmark claim, whose evidence cites that history). SAGE is private today and its history carries real job postings, a vault and run state, so publishing a rewritten copy is irreversible: the import lands only after a file listing over every rewritten commit proves those paths are gone.
- The two LLM gateways collapse into one in core. They were written independently, so the merged gateway carries the union of both provider configs and both cost-accounting paths; the migration is not a pure import rewrite.
- SAGE's `inputs/jds/` stops being the topic source once `DemandSignal` exists and stays supported as a manual override.
- Adding a module means adding a workspace package plus one line in the import-linter independence contract. Core changes only when the new module needs a new exchange contract, since contracts live in core.
- Hosted-mode users get the same image and workflows with a different
  `runs-on` and a git-backed exchange store; that store is deferred until
  hosted mode is built.
- Package naming diverges from the umbrella name for the core
  distribution (`atlas-kit`). Renaming later touches only the `name` fields, and after the first release it also breaks the install command for anyone who already installed `atlas-kit`.
- Rejected alternatives: separate repos with a shared library on PyPI (every contract change becomes a publish-then-bump dance across three repos for one author; the monorepo does not remove releases, it removes the cross-repo version pinning); a single `atlas` distribution with extras (simplest to release, rejected because a user who wants only SAGE would still pull the other modules' dependency trees, which breaks the standalone constraint); a central orchestrator (single point of failure at home, and modules stop being standalone); a shared database (SAGE's markdown source of truth is a product decision, not an implementation detail, and one schema would couple three deliberately different storage models).
