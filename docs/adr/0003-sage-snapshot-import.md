# ADR 0003: SAGE enters the public monorepo as a snapshot

**Status:** Accepted
**Date:** 2026-09-23

## Context

ADR 0001 decided that MERIT and SAGE enter this repository through
`git filter-repo`, which strips personal-data paths and rewrites every
commit hash. MERIT's import is already done. SAGE is still private.
On 2026-09-23 that history is 229 commits. It carries personal paths
and company names. Publishing a rewritten copy is irreversible.

ADR 0002 made `ATLAS_HOME` (default `~/.atlas`) the single anchor for
module state. SAGE's markdown vault is not that state. It lives in the
private checkout, and the code finds it from the repository root
(`Path(__file__).resolve().parents[2]` in `src/sage/main.py`). An
installed package resolves that expression to site-packages, so the
root has to become an environment variable before that package is usable.

ADR 0001 also named a separate private `atlas-vault` repository for the
SAGE vault, and `atlas-ops` for scheduled workflows. Neither is what
the running bot uses.

No published claim cites a SAGE commit SHA. MERIT's claim C-MERIT-001
cites MERIT history and is outside this decision.

## Decision

1. SAGE enters public `atlas` as a snapshot of `src/sage/` plus tests
   that do not read personal fixtures. That is the whole copy. Scripts,
   the Actions workflow, and docs stay in the private repository. The
   git history stays there too and is not rewritten for publication.
   The copy lands as the `atlas-sage` package, import name `atlas_sage`,
   at `packages/atlas-sage/`. The import rename is part of that landing.
   This supersedes, for SAGE only, the ADR 0001 consequence that SAGE
   is imported with `git filter-repo` and rewritten hashes. MERIT's
   completed import is not reopened.
2. The copy in decision 1 is checked against this list, which is not a
   second definition of the tree. These paths stay out of public
   `atlas`: `vault/`, `exports/`, `state.json`, `STATUS.md`,
   `inputs/jds/`, `inputs/profile.md`, `inputs/job-search.yaml`,
   `reports/`, `.env`, any `*.apkg`, every other file under `inputs/`
   (including `inputs/syllabus.yaml`), and the local tool directories
   `.axon/`, `.forge/`, and `.claude/`. The path audit on 2026-09-23
   read `inputs/syllabus.yaml` as topic lists only (`llms`, `rag`,
   `java`) with no employer names. The public package does not read
   `inputs/`, so the file stays on the vault anyway. The reason is the
   one in the context: no published claim needs the private SHAs, and
   the history is personal data.
3. The private `sage` repository remains the vault and the runtime
   checkout. It installs the `atlas-sage` package. Its GitHub name
   stays `sage`. Its `src/sage` tree stays until one invocation of the
   installed package is observed as follows: the process starts with a
   working directory that is neither the private checkout nor the
   public `atlas` checkout; `git status` on the public tree shows no
   change from that run; writes inside the private checkout are limited
   to `vault/`, `exports/`, `state.json`, and `STATUS.md`. After that
   observation, the private tree is no longer the source of the library.
4. `ATLAS_VAULT` is that private checkout root. The process expands `~`
   when it reads the variable; the shell is not required to. It does
   not replace `ATLAS_HOME` for other modules. For SAGE, `state.json`,
   `STATUS.md`, the vault, exports, and `inputs/` are anchored here.
   That supersedes, for SAGE only, ADR 0002's sentence that `ATLAS_HOME`
   is the single anchor for module state. `SAGE_VAULT`, `SAGE_APKG`, and
   `SAGE_STATUS` stay as overrides. Setting any of them does not satisfy
   a missing `ATLAS_VAULT`, because state and `inputs/` have no override
   of their own. Defaults are `$ATLAS_VAULT/vault`,
   `$ATLAS_VAULT/exports/sage.apkg`, and `$ATLAS_VAULT/STATUS.md`.
   State is `$ATLAS_VAULT/state.json`. Syllabus, `inputs/jds/`, and
   `inputs/profile.md` are `$ATLAS_VAULT/inputs/...`. Importing the
   package and `--help` do not require `ATLAS_VAULT`. Any resolution of
   vault, state, inputs, exports, or STATUS that needs `ATLAS_VAULT`
   and finds it unset exits with an error. It does not fall back to the
   process working directory or to `Path(__file__)`. `--dry-run` still
   sends the vault to a temporary directory and writes nothing under
   `ATLAS_VAULT`.

`inputs/jds/` stays the manual topic override until `DemandSignal`
exists. This ADR does not change that ADR 0001 rule.

## Consequences

- ADR 0001's `git filter-repo` sentence remains the record of how MERIT
  was decided. For SAGE, that sentence is superseded by decision 1.
- ADR 0001's private `atlas-vault` repository is not the SAGE vault.
  The SAGE vault stays in the private `sage` checkout. SAGE's scheduled
  workflow stays in that same repository. This ADR does not create or
  retire `atlas-vault` or `atlas-ops`.
- For SAGE, ADR 0002's single `ATLAS_HOME` anchor is superseded by
  decision 4. MERIT stays on `ATLAS_HOME`.
- Inside the installed package, a vault, state, or inputs path built
  from `__file__` or the process working directory is a bug, not a
  default. A private script that still lives in the checkout is outside
  that rule.
- The copy into `packages/atlas-sage` does not land until a search of
  that tree shows none of the paths in decision 2. Accepting this ADR
  is the method. It is not that landing.
- The exclusion list is paths. It does not prove that a source file is
  free of a personal string. The search above is the content check, and
  this ADR does not claim that check has run.
- Rejected: importing SAGE with `git filter-repo`. A rewritten history
  is still a publication of a personal timeline, and nothing public
  needs those SHAs. Also rejected: resolving the vault from the current
  working directory, which is the defect an installed package hits.

## Limitations

- "No published claim cites a SAGE SHA" is the owner's assertion on
  2026-09-23. This ADR does not inventory talks, posts, or dossiers
  outside this repository. A later citation is resolved from the
  private repository, which is why the history stays there.
- The rejection of a rewritten SAGE history does not extend to MERIT.
  C-MERIT-001 cites MERIT's published history. SAGE has no equivalent
  citation. That asymmetry is accepted. This ADR does not reopen MERIT.
- The author of the private history is the author of this decision.
  The mitigation is the path exclusion list and keeping the only copy
  of the history private.
- The syllabus clearance is a read of one 43-line file on one date.
  A later edit can put an employer name back. The file stays on the
  vault, so that edit is not a public release.
- The private `sage` repository already commits its vault and run state.
  This ADR does not move that data into public git, and it does not add
  a gitignore that would stop the bot from committing it.
