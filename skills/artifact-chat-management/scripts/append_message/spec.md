# append_message — append a transcript entry + bump counters

```
append_message(chat_id: str = "", entry_json: str = "") -> dict
```

Appends one `TranscriptEntry` to `<app_dir>/artifact-chats/<chat_id>.ndjson`
(path-confined, creating the file on the first message) AND bumps the record's
`messageCount += 1` and `lastActivityAt = now` in `state/artifactChats.json`
(whole-document RMW, atomic).

## Inputs (all strings)

| Param | Default | Description |
|---|---|---|
| `chat_id` | `""` | The chat to append to; empty / traversal-shaped → not found |
| `entry_json` | `""` | The `{ kind:'human', text, dataSnapshot?, ts }` line as a JSON-encoded object (the only line this op writes — see shape below) |

## TranscriptEntry shape (overview.md §11 L5 — authoritative)

One persisted NDJSON line per entry. The transcript interleaves human turns and the
assistant's streamed response. There are exactly two persisted line shapes, and the
assistant/tool/lifecycle lines carry **no extra `{kind:'event', payload}` wrapper**:

| persisted line | written by | shape |
|---|---|---|
| **human turn** | **this UDF** (`append_message`) | `{ kind:'human', text, dataSnapshot?, ts }` — the question + the bounded on-screen `dataSnapshot` (overview.md §6) + `ts`. The ONLY line this UDF writes. |
| **assistant / tool / lifecycle turn** | the **app** live-response loop | the raw run-thread `TranscriptEntry`/`RunEvent` union used by `useRunEvents`/`useTaskThread` verbatim — `{ kind:'assistant', ts, text }`, `{ kind:'thinking', … }`, `{ kind:'tool_call', ts, name, input?, callId? }`, `{ kind:'tool_result', ts, callId?, output?, isError? }`, `{ kind:'result', ts, text?, usage?, costUsd? }`, plus `init`/`system`/`stderr`/`stdout`. **NOT** re-wrapped under `kind:'event'`, and there is no separate `summary` kind — the final assistant text is the terminal `{ kind:'result', text? }`. |

`append_message` writes the `{ kind:'human', … }` line; the
assistant/tool/lifecycle lines are appended by the app's streaming loop, NOT this
UDF (see SKILL.md "Division of labor"). The on-disk line is the *entry* itself; the
SSE channel wraps it as `{ payload: <entry> }` so the client's
`JSON.parse(msg.data).payload` matches the persisted shape.

## Output ack shape

Returns the updated `ArtifactChatRecord` (bumped `messageCount` /
`lastActivityAt`), or `{"ok": false, "error": "not found"}` for an unknown
`chat_id` (the entry is NOT written in that case).

## Behaviour

1. Resolve + confine the transcript path to the real `artifact-chats/` dir (reuse
   the run-management `_transcript_path` confinement, repointed); reject a
   traversal-shaped id → not-found ack, no write.
2. Under the `artifactChats` flock, find the record. Missing → not-found ack.
3. Append `json.dumps(entry) + "\n"` to the `.ndjson` (append mode).
4. Bump `messageCount` / `lastActivityAt`; write the collection atomically.
5. Return the updated record.

Unconditional setter — no state-machine validation (the app gates legality).
