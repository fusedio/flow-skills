# read — artifact-chat records from the App state file

```
read(project: str = "", artifact_type: str = "", artifact_stem: str = "") -> list[dict]
```

Returns `ArtifactChatRecord` dicts from `<app_dir>/state/artifactChats.json`,
oldest-first by `createdAt`. **Cross-agent read** — any agent may call it.

`project` filters to one project's chats (empty = all projects). `artifact_type`
(`widget`/`udf`/`reference`/`asset`) and `artifact_stem` further scope to one
artifact when non-empty. Both filters are exact string matches — an asset stem is
the asset's project-relative path (e.g. `assets/sales.parquet`), matched verbatim.
`get-one-by-id` is `SELECT * FROM {{read}} WHERE id = '...'`.

SQL shorthand (the read endpoint): `SELECT * FROM {{read}}` returns every chat;
pass `overrides: {"project": "..."}` (or filter in SQL) to scope.

## Record shape

Each row is the camelCase `ArtifactChatRecord` exactly as written by the app:

| field | type | notes |
|---|---|---|
| `id` | str | `chat_<hex>`, caller-supplied at create |
| `project` | str | |
| `artifactType` | str | `widget` / `udf` / `reference` / `asset` (documented union — stored verbatim, not runtime-enforced) |
| `artifactStem` | str | widget stem / udf name / reference name / asset path (project-relative, e.g. `assets/sales.parquet`) |
| `title` | str \| null | optional human label; null until set |
| `createdAt` | str | ISO-8601 `Z` |
| `lastActivityAt` | str | ISO-8601 `Z`; bumped on each message |
| `messageCount` | int | |
| `sessionKey` | str | agentbridge resume key (Claude Code session) |

The `(project, artifactType, artifactStem)` triple is the find-or-create key (D6).

## Notes

- Read-only. The Express app is the sole writer of chat records.
- Stdlib-only; reaches `artifactChats.json` directly.
- A missing / unparseable file yields an empty list, not an error.
