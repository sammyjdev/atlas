# Gmail intake: how the agent pulls actionable mail

The Tess shows actionable mail (proposta, horario, teste, feedback) as pending
items and Sammy confirms each one into an active process or discards it. The
Tess process never talks to Gmail. An agent session that already has the Gmail
MCP authenticated does the read and pipes the result in.

## Steps

1. Run `alfa gmail-query`. It prints the Gmail search query: last 30 days,
   inbox only, sent mail and promotions out, the senders in
   `gmail.NOISE_SENDERS` excluded, subjects limited to the action terms.
2. Call `search_threads` on the Gmail MCP with that exact query.
3. Pipe the returned messages, as one JSON list, into
   `alfa gmail-candidatos` on the same host as `merit.db`:
   `alfa gmail-candidatos < messages.json`.
   - stdout prints how many new items landed.
   - stderr prints `ignorados: N` when some messages were malformed and skipped.
   - Exit `2` with `uso:` means the input was not a JSON list.
   - Exit `2` with `pendentes ilegivel` means the pending file is corrupt.
     Nothing was written. Inspect the file by hand before pulling again.
4. Open the Tess at `/gmail`. Confirm each item into an active process, or
   discard it. A confirmed or discarded sender and subject does not come back
   on later pulls, even with a new message id.

## Where it lands

- `gmail-pendentes.json` sits next to the resolved `merit.db` (inside
  `ATLAS_HOME` by default, or wherever `MERIT_DB` points), mode `0600`, with a
  sidecar `.lock` file. It moves with `ATLAS_HOME` in the Linux copy.
- A confirm writes one entry in the process `notes` file, tagged
  `gmail: <message id>`. A retry of the same confirm writes nothing new.

## Rules that do not bend

- Only `search_threads` may be called on the Gmail MCP for this flow. No
  `get_thread`, no labels, no archive, no trash, no drafts.
- The Tess never sends mail and never writes to the mailbox. Replies are
  written and sent by Sammy in Gmail.
- A confirm never creates an application and never writes a reminder.
- Do not paste the raw MCP output into tracked files. It carries real
  addresses.
