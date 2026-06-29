# transcript — a chat's NDJSON transcript

```
transcript(chat_id: str = "") -> list[dict]
```

Reads `<app_dir>/artifact-chats/<chat_id>.ndjson` and returns the chat's persisted
`TranscriptEntry` lines in file order (verbatim). `<app_dir>` is the `app_dir` param, else
`$OPENFUSED_APP_DIR_STATE` (verbatim), else `~/.openfused/app` — the same dir under
which the app's live-response loop appends `artifact-chats/<chatId>.ndjson`.
**Cross-agent read — the visibility op other agents call.**

Each line is one persisted entry: the `{ kind:'human', … }` line `append_message`
writes, or a raw run-thread `TranscriptEntry`/`RunEvent` line the app lane appends
(`assistant`/`thinking`/`tool_call`/`tool_result`/`result` + `init`/`system`/
`stderr`/`stdout` — no `kind:'event'` wrapper; see `append_message/spec.md` and
overview.md §11 L5). This op returns them verbatim, in file order, and does NOT
interpret the `kind`. Because the result is non-tabular, prefer the UDF endpoint:

```
POST /api/exec/udf?workspace=_core&project=artifact-chat-management
{"udf": "transcript", "overrides": {"chat_id": "chat_…"}}
```

## Behavior

- Empty `chat_id` → `[]`.
- A `chat_id` whose resolved path would escape `artifact-chats/` (traversal via
  `..`, an absolute path, or a symlink) → `[]`. The path is confined to the real
  `artifact-chats/` directory before opening, since `chat_id` is caller-controlled.
- Missing transcript file → `[]` (not an error). A chat with zero messages has no
  file yet.
- **Snapshot, not a stream.** Returns the entries written so far; the caller
  re-resolves to refresh. Live streaming stays the app's SSE channel
  (`GET /api/artifact-chats/:chatId/events`, reusing `runs/stream.ts`).
- **Torn-line tolerance.** The NDJSON is append-as-you-go, so a crash mid-response
  can leave a torn final line. Invalid-JSON lines are skipped and the valid prefix
  is returned — mirrors run-management `transcript` / the Express `replayEvents`.

## Notes

- Read-only, stdlib-only; reads the file directly. Implementation is
  run-management/transcript/main.py verbatim, repointed at `artifact-chats/`.
