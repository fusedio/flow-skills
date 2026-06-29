"""Read UDF — returns artifact-chat records from the live app state file.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. The future implementation mirrors run-management/read/main.py:
stdlib-only, per-entity-file load (the `artifactChats` collection), an exclusive
flock-per-collection sentinel for writers (this is a pure read, so it takes no
lock), and the highest-precedence `app_dir` resolution chain.

Reads ``<app_dir>/state/artifactChats.json`` directly with stdlib; no third-party
imports. ``<app_dir>`` is the ``app_dir`` param, else ``$OPENFUSED_APP_DIR_STATE``
(verbatim), else ``~/.openfused/app``.

Params
------
project : str
    Filter to one project's chats (matched against the camelCase ``project``
    field). Empty string (default) returns all chats across all projects.
artifact_type : str
    Optional further scope — ``"widget"`` / ``"udf"`` / ``"reference"`` — applied
    only when non-empty.
artifact_stem : str
    Optional further scope — the widget stem / udf name / reference name — applied
    only when non-empty.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
list[dict]
    Raw camelCase ``ArtifactChatRecord`` dicts (9 fields), oldest-first by
    ``createdAt``. A missing / unparseable file yields ``[]``, not an error.

File effects
------------
None — read-only. The Express app is the sole writer of chat records.
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def read(
    project: str = "",
    artifact_type: str = "",
    artifact_stem: str = "",
    app_dir: str = "",
) -> list:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.read is a scaffold stub")
