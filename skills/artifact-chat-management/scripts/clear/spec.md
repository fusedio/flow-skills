# clear — durably reset a chat (wipe transcript + fresh session)

```
clear(chat_id: str = "") -> dict
```

Durably *clears* one chat so it stays cleared after the popover is reopened / the
page reloaded: it deletes the flat transcript file
`<app_dir>/artifact-chats/<chat_id>.ndjson` (path-confined, tolerating a missing
file) AND resets the record in `state/artifactChats.json` to a fresh session
(whole-document RMW, atomic). Returns the reset record, or `{"ok": false, "error":
"not found"}` for an unknown `chat_id`. Mirrors `set_title`/`append_message`.

**APP-ONLY WRITE op** — NOT a cross-agent read. Only the app calls it, when the user
clears a chat.

## Inputs (all strings)

| Param | Default | Description |
|---|---|---|
| `chat_id` | `""` | The chat to reset; empty / traversal-shaped → not found |

## What is reset vs kept

| field | after `clear` |
|---|---|
| `messageCount` | `0` |
| `lastActivityAt` | `now` (ISO-8601 `Z`, ms) |
| `sessionKey` | a NEW key (fresh agentbridge session — the next turn resumes nothing), minted like `create` mints its fields |
| `title` | `null` |
| `id`, `project`, `artifactType`, `artifactStem`, `createdAt` | **kept** (the chat is reset, not re-created) |

## Output ack shape

Returns the reset `ArtifactChatRecord` (the 9 camelCase fields with the resets
above), or `{"ok": false, "error": "not found"}` for an unknown `chat_id` (the
transcript is NOT deleted in that case — no `chat_id`, nothing to clear).

## Behaviour

1. Resolve + confine the transcript path to the real `artifact-chats/` dir (reuse
   the run-management `_transcript_path` confinement, repointed); reject an
   empty / traversal-shaped id → not-found ack, no unlink, no write.
2. Under the `artifactChats` flock, find the record. Missing → not-found ack.
3. Delete `<app_dir>/artifact-chats/<chat_id>.ndjson` (tolerating a missing file —
   an empty chat has none yet).
4. Reset `messageCount=0`, `lastActivityAt=now`, mint a new `sessionKey`,
   `title=null`; write the collection atomically (tmp + `os.replace`), preserving
   all other top-level keys; release the lock.
5. Return the reset record.

Unconditional setter — no state-machine validation (the app gates legality before
calling; e.g. it refuses to clear a chat with a turn in flight, returning 409).
