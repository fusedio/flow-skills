"""Get UDF — find the ONE artifact-chat for an artifact ref.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. The future implementation mirrors run-management's read helpers
(stdlib-only, per-entity-file load of the `artifactChats` collection, no write
lock — pure read) and resolves the D6 find half.

Reads ``<app_dir>/state/artifactChats.json`` and returns the single record whose
``(project, artifactType, artifactStem)`` triple matches the params (the D6
find-or-create key — `create` is find-or-create on the same key). This is the find
half the app calls before deciding whether to mint a new chat.

Params
------
project : str
    The artifact's project.
artifact_type : str
    ``"widget"`` / ``"udf"`` / ``"reference"``.
artifact_stem : str
    The widget stem / udf name / reference name.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
dict | None
    The matching ``ArtifactChatRecord`` dict, or ``None`` when no chat exists for
    the ref. (`dev serve` returns Python ``None`` as JSON ``null``.)

File effects
------------
None — read-only. **Cross-agent read.**
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def get(
    project: str = "",
    artifact_type: str = "",
    artifact_stem: str = "",
    app_dir: str = "",
) -> dict | None:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.get is a scaffold stub")
