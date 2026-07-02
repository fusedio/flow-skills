---
name: artifact-chat-management
description: Read and write the durable per-artifact chat store (records + per-chat NDJSON transcripts) in the Fused App store. The cross-agent-visible system of record for artifact chats — the strictly read-only conversation attached to a widget / UDF / reference / project asset. Use when inspecting or persisting artifact-chat state, or — from ANY agent — to learn what users have asked about an artifact.
disable-model-invocation: true
---

# artifact-chat-management

> SCAFFOLD / CONTRACT SPEC. The `scripts/<op>/main.py` files in this project carry
> **contract docstrings only** (inputs / outputs / file effects), not finished
> Python logic — they are the implementation seam for a future build (see
> `spec/artifact-chat/storage.md` §Implementation plan). The byte-for-byte format,
> path-confinement, and lock discipline are inherited verbatim from
> `run-management`; this file states the contract a future engineer fills in.

The App artifact-chat store exposed as live UDFs — the **durable, cross-agent
system of record for artifact chats** (spec/artifact-chat/overview.md §3, D5). A
chat is the strictly read-only conversation attached to ONE artifact (a widget, a
UDF, a reference, or a project asset — a data file such as
`assets/sales.parquet`). Reads and writes `~/.openfused/app/state/artifactChats.json`
(chat records) and reads `~/.openfused/app/artifact-chats/<chatId>.ndjson`
(per-chat transcripts). These UDFs own that local store; an agent drives them over
the local execution layer started with `fused dev serve`.

## Why this is a `_core` collection (cross-agent), not an app-only noun

The chat is **cross-agent visible**: a build agent working a task may want to read
what a user asked about an artifact ("why is this value high?") before changing it.
A `_core` UDF project is reachable from any agent over the shared `dev serve`,
whereas an app-only `store-core.ts` `COLLECTION_FILES` noun (the `costEvents`
pattern) is reachable only by the Express app process. D5 therefore makes
artifact-chat a `run-management`-style collection. The cross-agent READ ops are
`read`, `get`, and `transcript` (below) — **any agent may call them**; they never
mutate. The WRITE ops (`create`, `append_message`, `set_title`, `clear`) are
called by the **app only**.

## What this project is

Seven UDFs over the App artifact-chat state — three reads and four writes:

- `read` — `ArtifactChatRecord` rows from `artifactChats.json`, filterable by
  `project` and/or artifact ref. **Cross-agent read.**
- `get` — find the ONE chat for a `(project, artifactType, artifactStem)` ref (the
  D6 find half). **Cross-agent read.**
- `transcript` — a single chat's NDJSON transcript (read-only on the hot path; the
  app appends it line-by-line as a chat response streams). **Cross-agent read —
  this is the visibility op other agents call to learn what was asked.**
- `create` — find-or-create the one chat for an artifact ref (caller-supplied id),
  idempotent on the ref (D6, one chat per artifact).
- `append_message` — append one transcript entry AND bump the record's
  `messageCount` + `lastActivityAt`.
- `set_title` — set the optional human label.
- `clear` — durably reset a chat: wipe its transcript file AND reset the record
  (`messageCount=0`, fresh `sessionKey`, `title=null`), keeping the id + ref. So a
  cleared chat stays cleared after reopen/reload, with a brand-new session.
  **App-only write** — NOT a cross-agent read; only the app calls it (when the user
  clears a chat).

Every UDF touches the App files directly with stdlib; no third-party imports in
UDF logic (the resolver deps in `pyproject.toml` exist only so the `read` UDF can
be rendered as a `sql-table` widget).

## Division of labor — record vs effect (mirrors run-management exactly)

These UDFs own the **durable chat record** and the **non-live transcript file
ops**. The app keeps the **in-memory chat orchestration** a sandboxed UDF cannot
perform: the `dispatchArtifactChat()` lane that spawns the read-only `hub.run()`
(overview.md §3 D3), the live SSE buffer (`GET /api/artifact-chats/:chatId/events`,
reusing `runs/stream.ts`), and the cancel.

**Transcript-write ownership follows run-management's resolved split (do not
invent a new one).** In run-management, `runs/stream.ts` reads the NDJSON back as a
snapshot through the `transcript` UDF, while the live NDJSON is **appended by the
app** as events stream — the `fs.createWriteStream(runLogPath(runId), {flags:"a"})`
+ `log.write(...)` loop in `app/src/server/runs/launcher.ts`. The UDF NEVER writes
the live file; `transcript` stays read-only on the hot path. Artifact-chat follows
the identical split with ONE deliberate difference:

- The **human message entry** — the one `{ kind:'human', text, dataSnapshot?, ts }`
  line (overview.md §11 L5) — is a discrete record write, not a streamed event, so
  `append_message` (a UDF write) owns appending THAT line, and ONLY that line.
- Every **assistant/tool/lifecycle line** of the streamed response — the raw
  run-thread `TranscriptEntry`/`RunEvent` union (`assistant`/`thinking`/`tool_call`/
  `tool_result`/`result` + `init`/`system`/`stderr`/`stdout`), NOT re-wrapped under
  `kind:'event'` and with no separate `summary` kind (L5) — is appended by the
  **app's live-response loop** (the artifact-chat sibling of launcher.ts), exactly
  as runs do — the UDF is not in the per-event hot path.
- `transcript` stays a read-only **snapshot**; live streaming stays the app's SSE
  channel (overview.md §4, reusing `runs/stream.ts` `subscribe`/`replayEvents`).

So a chat's *effects* (spawn / stream / cancel) stay app-side while its *record*
and its *human-turn* transcript lines are owned here. Like the run UDFs, each write
is a whole-document read-modify-write that preserves every other noun, so
`artifactChats.json` is a single-collection writer reconciled last-write-wins.

## Access pattern

Start the local execution layer. `fused dev serve` binds a loopback server,
prints ONE JSON handshake line, then runs in the foreground:

```
fused dev serve
{"origin": "http://127.0.0.1:<port>", "port": <port>, "token": "<token>", "pid": <pid>}

ORIGIN=http://127.0.0.1:<port>
TOKEN=<token>

# read — POST to the SQL endpoint; {{read}} is backed by the read UDF
curl -s -X POST "$ORIGIN/api/exec/sql?t=$TOKEN&workspace=_core&project=artifact-chat-management" \
  -d '{"sql": "SELECT * FROM {{read}} WHERE project = '\''my-project'\''"}'

# get / transcript / writes — POST to the UDF endpoint (single-record or chat-scoped)
curl -s -X POST "$ORIGIN/api/exec/udf?t=$TOKEN&workspace=_core&project=artifact-chat-management" \
  -d '{"udf": "get", "overrides": {"project": "my-project", "artifact_type": "widget", "artifact_stem": "sales"}}'
# an asset chat's stem is the asset's project-relative path, sent verbatim
curl -s -X POST "$ORIGIN/api/exec/udf?t=$TOKEN&workspace=_core&project=artifact-chat-management" \
  -d '{"udf": "get", "overrides": {"project": "my-project", "artifact_type": "asset", "artifact_stem": "assets/sales.parquet"}}'
curl -s -X POST "$ORIGIN/api/exec/udf?t=$TOKEN&workspace=_core&project=artifact-chat-management" \
  -d '{"udf": "transcript", "overrides": {"chat_id": "chat_…"}}'
```

Response shape: `{"data": <result>, "error": null}` on success;
`{"data": null, "error": "<message>"}` on failure.

## State files

The app directory is resolved per operation, highest precedence first (mirrors
run-management exactly):

1. The `app_dir` parameter on any operation — use this to run the skill standalone
   against your own store, no environment setup required.
2. The `$OPENFUSED_APP_DIR_STATE` env var when it names an app directory.
3. `~/.openfused/app` (default).

- Chat records: `<app_dir>/state/artifactChats.json`.
- Transcripts: `<app_dir>/artifact-chats/<chatId>.ndjson` (one entry per line).

Every operation (including `transcript`) accepts the optional `app_dir` string
param; when omitted the env-var/default chain applies, so existing callers are
unaffected.

Records are camelCase JSON. Writes go through whole-document read-modify-write
(all top-level keys preserved) + atomic `tmp` + `os.replace`, matching the
Express app's `JSON.stringify(data, null, 2)` + `fs` writes byte-for-byte (the
shared per-entity-file convention — `store-core.ts` `COLLECTION_FILES` for the
app side, the `_COLLECTION_KEYS` helper for the Python side).

## ArtifactChatRecord shape

The 9-field camelCase record `read`/`get` return and the write UDFs produce
(spec/artifact-chat/storage.md §1; mirrors the `RunRecord` shape/discipline):

`id` (`chat_<hex>`, caller-supplied at create), `project`, `artifactType`
(`widget` / `udf` / `reference` / `asset`), `artifactStem` (widget stem / udf name /
reference name / asset path), `title` (str | null — optional human label, null
until set), `createdAt` (ISO, at create), `lastActivityAt` (ISO, bumped on each
message), `messageCount` (int), `sessionKey` (agentbridge resume key for the
Claude Code session). The `(project, artifactType, artifactStem)` triple is the
find-or-create key (D6, one chat per artifact).

**Stem semantics.** The store treats `artifactType` and `artifactStem` as opaque
exact-match strings — the type union above is the documented contract, not a
runtime check (same accept-verbatim posture as every other write: the app gates
legality before calling). An **asset** chat's stem is the asset's
project-relative path, e.g. `assets/sales.parquet` — slashes and dots included,
sent verbatim by the app with no store-side normalization. Path-shaped stems are
safe: the stem never becomes a filename (transcripts key on `chat_id` only).
Because the triple IS the chat's identity, renaming or moving an asset detaches
its chat — the same posture as renaming a widget stem (D6).

## Operations

All parameters arrive as strings. Empty string is the zero value for optional
params; for nullable record fields, empty string → JSON `null`.

### read

```
read(project: str = "", artifact_type: str = "", artifact_stem: str = "") -> list[dict]
```

Returns `ArtifactChatRecord` dicts, oldest-first by `createdAt`. Empty `project`
returns all chats; a non-empty `project` filters to that project; the optional
`artifact_type` / `artifact_stem` further scope to one artifact. **Cross-agent
read.** `get-one-by-id` is `SELECT * FROM {{read}} WHERE id = '...'`.

### get

```
get(project: str = "", artifact_type: str = "", artifact_stem: str = "") -> dict | None
```

Returns the ONE chat record for the `(project, artifactType, artifactStem)` ref,
or `null` when none exists (the D6 find half — `create` is find-or-create on the
same key). **Cross-agent read.**

### transcript

```
transcript(chat_id: str = "") -> list[dict]
```

Reads `<app_dir>/artifact-chats/<chat_id>.ndjson` and returns the chat's persisted
`TranscriptEntry` lines in file order, verbatim (the `{ kind:'human', … }` line
plus the raw run-thread entries — overview.md §11 L5; this op does NOT interpret
`kind`). Empty `chat_id`, a missing file, or a
`chat_id` whose resolved path would escape `artifact-chats/` returns `[]` — the
path is confined to the real `artifact-chats/` directory before opening, since
`chat_id` is caller-controlled. Torn trailing lines are skipped (the valid prefix
is preserved — mirrors `transcript`/`replayEvents`). This is a **snapshot**,
refreshed by re-resolving; live streaming stays the app's SSE channel.
**Cross-agent read — the visibility op other agents call.**

### create

```
create(id: str = "", project: str = "", artifact_type: str = "",
       artifact_stem: str = "", session_key: str = "") -> dict
```

Find-or-create the one chat for `(project, artifactType, artifactStem)` (D6). If a
chat already exists for the ref, returns it UNCHANGED (idempotent — no duplicate,
no overwrite). Otherwise appends a new record with the **caller-supplied `id`**
(`chat_<hex>`; the app mints it because it also keys the in-memory live buffer by
it — the UDF never mints one), `title=null`, `createdAt=lastActivityAt=now`,
`messageCount=0`, `sessionKey=session_key`. Returns the existing-or-created record.

### append_message

```
append_message(chat_id: str = "", entry_json: str = "") -> dict
```

Appends the one `{ kind:'human', text, dataSnapshot?, ts }` line (a JSON-encoded
object — overview.md §11 L5) to `<app_dir>/artifact-chats/<chat_id>.ndjson`
(path-confined, atomic) AND bumps the record's `messageCount += 1` and
`lastActivityAt = now` in `artifactChats.json` (whole-document RMW). This UDF owns
the **human-message** transcript line and ONLY that line; the streamed
assistant/tool/lifecycle lines (the raw run-thread entries, NOT re-wrapped under
`kind:'event'`) are appended by the app's live-response loop (see "Division of
labor"). Missing chat → `{"ok": false, "error": "not found"}`. Returns the updated
record.

### set_title

```
set_title(chat_id: str = "", title: str = "") -> dict
```

Sets the optional human `title` label on an existing chat; empty string → `null`.
Returns the updated record. Missing chat → `{"ok": false, "error": "not found"}`.

### clear

```
clear(chat_id: str = "") -> dict
```

Durably **resets** a chat so it stays cleared after reopen/reload: deletes the flat
transcript file `<app_dir>/artifact-chats/<chat_id>.ndjson` (path-confined,
tolerating a missing file) AND resets the record in `artifactChats.json`
(whole-document RMW, atomic) — `messageCount=0`, `lastActivityAt=now`, a NEW
`sessionKey` (fresh agentbridge session, resumes nothing), `title=null` — while
KEEPING `id`, `project`, `artifactType`, `artifactStem`, `createdAt`. Empty /
traversal-shaped id, or a missing chat → `{"ok": false, "error": "not found"}` (no
unlink, no write in that case). **App-only write** — only the app calls it (when the
user clears a chat). Returns the reset record.

- Writes are **unconditional setters** (like run-management): no state-machine
  validation in the UDF — the app gates legality before calling.
- UDF logic is stdlib-only; no imports from `openfused.*` (the exec sandbox
  shadows the package with a shim). Reach the App files directly.
- All params are strings.

## Rendering as a `sql-table` widget

The `read` UDF is enough to render the artifact-chat log as a table. A saved
`sql-table` widget reads through `{{_core.artifact-chat-management.read}}`. Ships
inside the wheel at `artifact-chat-management/widgets/chats_table.json` (deferred —
a future authoring step; not required for the POC), materializing to
`~/.openfused/core/artifact-chat-management/widgets/chats_table.json`.

> **Where it resolves.** The `{{_core.*}}` cross-project ref needs an `_core`
> resolve context, which today means the flow app's dev serve
> (`fused dev serve`).

## Layout (skill-folder convention)

```
scripts/
├── pyproject.toml          # project deps (duckdb/pandas/pyarrow for the SQL resolver)
├── read/                   # {main.py, spec.md}  — cross-agent read
├── get/                    # find-one-for-ref     — cross-agent read
├── transcript/             # NDJSON snapshot      — cross-agent read
├── create/                 # find-or-create (caller-supplied id)
├── append_message/         # append human entry + bump counters
├── set_title/              # optional label
└── clear/                  # durable reset — wipe transcript + fresh session (app-only write)
```

Source lives in the wheel under `fused/_core/artifact-chat-management/`
(read-only). The local-backend venv materializes at
`~/.openfused/core/artifact-chat-management/scripts/.venv` on first startup.
Adding a new op = add `scripts/<name>/{main.py,spec.md}`.
