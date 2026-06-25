# delete_project UDF spec

Remove every task for one project, and the comments on those tasks, from the live
app state. The task-management half of the cross-skill **project-delete** cascade.

## Input

| Parameter | Type   | Default | Description                                    |
|-----------|--------|---------|------------------------------------------------|
| `project` | string | `""`    | The project slug whose tasks are removed.      |

## Behaviour

One atomic `_load_doc → mutate → _save_doc` cycle over `tasks` + `comments`.

### Steps

1. **Empty-project guard.** If `project` is empty or whitespace, return
   `{"deletedTaskIds": [], "tasksRemoved": 0, "commentsRemoved": 0}` immediately
   — no lock, no write, never an error.

2. **Collect task ids.** Gather the `id` of every task whose camelCase `project`
   field equals `project`. This set is the join key for comment removal.

3. **Remove tasks.** Drop every task whose `id` is in the collected set from
   `doc["tasks"]`.

4. **Remove comments.** Drop every comment whose `taskId` is in the collected set
   from `doc["comments"]`. Comments carry no `project` field of their own, so they
   join to the project via their task.

5. **Save.** Persist via atomic tmp+rename. Only `tasks` + `comments` are locked
   and rewritten; every other top-level collection (`runs`, `cards`, `costEvents`,
   `serveMcp`, `gatePolicies`, `onboarding`, …) is left untouched — those are
   deleted by their own owners on the project-delete path.

## Return value

```json
{
  "deletedTaskIds": ["task_abc", "task_def"],
  "tasksRemoved": 2,
  "commentsRemoved": 3
}
```

`deletedTaskIds` is the sorted list of removed task ids. Flow uses it to drive
per-task cleanup (`mcp/<taskId>.json`, sessions) outside this UDF.

## Notes

- **Idempotent.** A re-run on an already-deleted project (or one that never had
  tasks) collects an empty set and returns zero counts, writing nothing.
- **Scoped, not cascading.** Unlike `delete(id)` (which cascades one task's
  subtree across `runs`/`inbox`/`cards`/`costEvents`), `delete_project` deletes
  only this skill's own collections. Runs, transcripts, and cards for the project
  are removed by `run-management.delete_project` and
  `feedback-management.delete_project` respectively.
- Uses camelCase throughout to match the on-disk JSON format written by the
  TypeScript app.
