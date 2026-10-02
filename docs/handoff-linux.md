# Handoff: Tess to the Linux host

What to copy when the Tess moves from the laptop to the self-hosted Linux box.
Nobody runs this copy until the owner gives an explicit go-ahead. Until then
the laptop stays the only live copy.

## What moves

| Variable | What it points at | How it moves |
| --- | --- | --- |
| `ATLAS_HOME` | Merit state: `merit/merit.db` (applications ledger and LangGraph checkpoints in one file), `merit/applications/` (dossiers), `profile.yaml` | Copy the whole directory, one volume. Stop `alfa` and `merit` first so the SQLite file is not mid-write. |
| `ATLAS_VAULT` | Private `sage` checkout: `inputs/`, `vault/interview/`, `vault/screening/`, `state.json` | Copy the checkout as it is, local diff included. Do not pull or fast-forward it as part of the move. |
| `MERIT_API_KEY` | Model key used by the Tess draft and by `merit match` | Set it in the host environment. Never copy it into `ATLAS_HOME`, the vault, or git. Without it the draft panel says `Sem modelo` and nothing else breaks. |

`MERIT_DB` and `MERIT_PROFILE` are optional overrides. Leave them unset on the
host so both resolve under `ATLAS_HOME`.

## Rules that do not bend

- One SQLite. A second database for the Tess, the bot, or a cache is forbidden.
  The Tess, `merit` and the checkpoints all read and write the same
  `merit.db`. Two copies drift and there is no merge.
- One process for the Tess. A future Telegram webhook joins the same `alfa`
  app. It does not get its own server on the same database.
- `merit serve` stays bound to `127.0.0.1`. It is the debug UI, not the
  product, and it is never exposed.
- `alfa` also binds `127.0.0.1`. Any public reach (webhook, reverse proxy) is
  a separate decision and is not part of this copy.
- The Tess does not import `atlas_sage` and does not run `sage`. Prep only
  reads interviews already under `ATLAS_VAULT/vault/`.

## Check after the copy

1. `alfa` starts and `GET /` lists the same active processes as on the laptop.
2. One process page shows its thread, recruiter, research and reminder blocks.
3. The prep panel lists the vault interviews.
4. `ls "$ATLAS_HOME"/merit/*.db` shows exactly one file.

## Next act

Wait for the owner's explicit go-ahead. Do not SSH to the host, install units,
or open ports from this document.
