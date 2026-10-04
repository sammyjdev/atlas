# ADR 0004: Alfa is the Tess interface shell

**Status:** Accepted
**Date:** 2026-10-02

## Context

ADR 0002 says modules integrate through core contracts and the exchange.
The product needs a UI that reads and writes the Merit ledger in process.
`merit serve` already proves FastAPI + Jinja + htmx on `127.0.0.1`, and it
stays a debug UI. Product requirements live in the CanDo docs repo
(`adr-tess.md`), not in this tree.

## Decision

1. `atlas-alfa` (import `atlas_alfa`, console script `alfa`) is the interface
   shell. Public name: Tess. Version lockstep with the other packages (`0.1.0`).
2. Alfa imports `atlas_merit` on the hot path, including `track.log` for a
   pasted thread. It does not call `merit serve` over HTTP and it does not
   create applications.
3. Alfa does not import `atlas_sage` or `atlas_orbit`. Prep reads the
   interviews `sage --interview` already wrote under `ATLAS_VAULT`. No
   subprocess and no model call.
4. One SQLite file: `MERIT_DB` or `$ATLAS_HOME/merit/merit.db`, dossier beside it.
5. Active list hides `track.TERMINAL` (`rejected`, `withdrawn`, `accepted`,
   `archived`). `offer` stays.
6. A draft is optional and local. Without `MERIT_API_KEY` the page says so
   and does not invent text. The prompt carries the career canon. A substring
   guard drops a draft that breaks it. Alfa never sends LinkedIn or email.
7. `alfa` binds `127.0.0.1` only. No Caddy, systemd, or public webhook in this
   change.
8. Alfa never calls Gmail. An agent runs the search and pipes the result into
   `alfa gmail-candidatos`; the owner confirms or discards each item
   (`docs/gmail-intake.md`).

## Consequences

- ADR 0002's exchange-only rule does not apply to this shell. Merit and Sage
  stay independent of each other.
- Import-linter forbids Alfa from importing Sage or Orbit.
