# get — the one artifact-chat for an artifact ref

```
get(project: str = "", artifact_type: str = "", artifact_stem: str = "") -> dict | None
```

Returns the single `ArtifactChatRecord` whose `(project, artifactType,
artifactStem)` triple matches the params — the **D6 find half** (one chat per
artifact). Returns `null` when no chat exists for the ref. **Cross-agent read.**

The match is exact string equality on all three params (`artifact_type` is one of
`widget` / `udf` / `reference` / `asset`). An asset chat's stem is the asset's
project-relative path (e.g. `artifact_stem: "assets/sales.parquet"`), passed
verbatim — no normalization; a renamed/moved asset therefore misses (its chat is
detached, D6).

Because the result is a single record (not tabular), prefer the UDF endpoint:

```
POST /api/exec/udf?workspace=_core&project=artifact-chat-management
{"udf": "get", "overrides": {"project": "p", "artifact_type": "widget", "artifact_stem": "sales"}}
```

The app uses this on the `GET …/chat` find-or-create path: `get` first; if `null`,
`create` mints the chat (idempotent — `create` is itself find-or-create on the same
key, so a concurrent racer cannot produce a duplicate).

## Notes

- Read-only, stdlib-only.
- The record shape is the camelCase `ArtifactChatRecord` (see `read/spec.md`).
