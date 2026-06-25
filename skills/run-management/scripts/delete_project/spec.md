# delete_project

Remove every run record for one project from the live app state, and delete each
removed run's per-run transcript file. The run-management half of the cross-skill
**project-delete** cascade.

This is the **first destructive write op** in run-management (only `bulk_seed`
wrote before; `transcript` stays read-only). It REUSES the `runs/`-confined
`_transcript_path` helper (copied from `transcript`/`bulk_seed`) so a
traversal-shaped run id can never delete a file outside `runs/`.

## Inputs (all strings)

| Param | Default | Description |
|---|---|---|
| `project` | `""` | The project slug whose run records (and transcripts) are removed. `""`/whitespace → no-op |

## Output ack shape

```json
{
  "runsRemoved": 3,
  "transcriptsRemoved": 2
}
```

- `runsRemoved` — run records dropped from `runs.json` (matched on the camelCase
  `project` field).
- `transcriptsRemoved` — `runs/<runId>.ndjson` files actually deleted. A removed
  run whose transcript file was already absent — or whose id resolves outside
  `runs/` — counts as skipped, not removed, so `transcriptsRemoved ≤ runsRemoved`.

## Behaviour

1. **Empty-project guard.** `""`/whitespace `project` → return zero counts, no
   lock, no write, never an error.
2. `_load_doc("runs")` (exclusive flock on the `runs` collection across
   load→save); raises on a corrupt-but-present `runs.json`.
3. Collect the `id` of every run whose `project` equals `project`; drop those
   records from `doc["runs"]`. Every other collection is left untouched.
4. `_save_doc(doc)` — writes only the changed `runs` collection (dirty-snapshot
   logic) via atomic `tmp` + `os.replace`, then releases the lock.
5. **Transcripts**: for each removed run id, resolve `runs/<runId>.ndjson` with
   the `runs/`-confined `_transcript_path` (a traversal-shaped id → skip); if the
   file exists, `os.remove` it and count it; a missing file or a racing deleter
   leaves nothing to remove (skip, never raise).
6. Return the runs-removed + transcripts-removed counts.

## Idempotency

Re-running `delete_project` on an already-deleted project (or one that never had
runs) finds no matching records, returns `{"runsRemoved": 0, "transcriptsRemoved":
0}`, and writes nothing. Transcript deletion is best-effort, so a partially-deleted
project re-run cleans up whatever remains without crashing.
