# set_title — the optional human label

```
set_title(chat_id: str = "", title: str = "") -> dict
```

Sets `title` on an existing chat in `<app_dir>/state/artifactChats.json`
unconditionally; empty string → JSON `null` (clears the label). Returns the updated
record, or `{"ok": false, "error": "not found"}` for an unknown `chat_id`. Mirrors
run-management `set_prompt`.

## Inputs (all strings)

| Param | Default | Description |
|---|---|---|
| `chat_id` | `""` | The chat to label |
| `title` | `""` | The new title; empty → `null` |

## Behaviour

1. Under the `artifactChats` flock, load the collection; find the record. Missing →
   not-found ack.
2. Set `title` (empty → `null`).
3. Write the collection atomically (tmp + `os.replace`); release the lock.
4. Return the updated record.

Unconditional setter — no validation (the app gates legality before calling).
