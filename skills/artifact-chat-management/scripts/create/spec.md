# create — find-or-create the one artifact-chat for a ref

Appends a new chat record to `<app_dir>/state/artifactChats.json`, OR returns the
existing one for the ref unchanged. **Idempotent find-or-create on
`(project, artifactType, artifactStem)`** (D6 — one chat per artifact).

## Inputs (all strings)

| Param | Default | Description |
|---|---|---|
| `id` | `""` | The chat id (`chat_<hex>`); **caller-supplied**, never minted here. Used only on create. |
| `project` | `""` | The artifact's project |
| `artifact_type` | `""` | `widget` / `udf` / `reference` |
| `artifact_stem` | `""` | widget stem / udf name / reference name |
| `session_key` | `""` | agentbridge resume key (Claude Code session) |

The id is caller-supplied because the app mints `chat_<hex>` before persisting — it
also keys an in-memory live buffer by it — so a fresh id here would orphan that
buffer. (Same discipline as run-management `create`.)

## Output ack shape

Returns the existing-or-created `ArtifactChatRecord` (9 camelCase fields). On
create:

```json
{
  "id": "chat_<hex>",
  "project": "<project>",
  "artifactType": "widget",
  "artifactStem": "<stem>",
  "title": null,
  "createdAt": "2026-06-29T17:00:00.000Z",
  "lastActivityAt": "2026-06-29T17:00:00.000Z",
  "messageCount": 0,
  "sessionKey": "<session_key>"
}
```

## Behaviour

1. Take the exclusive flock on `artifactChats`; load the collection (raises on a
   corrupt-but-present file; default `[]` when missing).
2. **Find** a record whose `(project, artifactType, artifactStem)` matches. If
   found, return it unchanged (no write).
3. Otherwise build the record with `title=null`, `createdAt=lastActivityAt=now`,
   `messageCount=0`, `sessionKey=session_key`; append it.
4. Write the collection back atomically (tmp + `os.replace`), preserving all
   top-level keys; release the lock.
5. Return the existing-or-created record.

The find + insert run under one lock, so a concurrent racer on the same ref never
produces a duplicate.
