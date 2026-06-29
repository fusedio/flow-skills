"""Create UDF — find-or-create the one artifact-chat for an artifact ref.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. The future implementation mirrors run-management/create/main.py: it
takes the exclusive flock on the `artifactChats` collection across the whole
load->modify->save, does a whole-document read-modify-write that preserves every
other top-level key, and writes atomically (tmp + os.replace). Stdlib-only.

**Idempotent find-or-create on the ref (D6 — one chat per artifact).** If a chat
already exists for ``(project, artifactType, artifactStem)``, the existing record
is returned UNCHANGED (no duplicate, no overwrite — id/timestamps preserved). The
lock makes the find + insert one transaction, so a concurrent racer on the same
ref cannot produce a duplicate.

Params
------
id : str
    The caller-supplied chat id (``chat_<hex>``). The app mints it before
    persisting because it also keys an in-memory live buffer by it, so this UDF
    does NOT mint a new one. Used only when a chat is actually created.
project : str
    The artifact's project.
artifact_type : str
    ``"widget"`` / ``"udf"`` / ``"reference"``.
artifact_stem : str
    The widget stem / udf name / reference name.
session_key : str
    The agentbridge resume key (Claude Code session) for this chat lane.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
dict
    The existing-or-created camelCase ``ArtifactChatRecord``. On create:
    ``title=null``, ``createdAt=lastActivityAt=now``, ``messageCount=0``,
    ``sessionKey=session_key``.

File effects
------------
Writes ``<app_dir>/state/artifactChats.json`` (whole-document RMW, atomic) ONLY
when a new chat is appended; a find-hit writes nothing. Never touches the
transcript file (an empty chat has no ``.ndjson`` yet — `append_message` creates
it on the first message).
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def create(
    id: str = "",
    project: str = "",
    artifact_type: str = "",
    artifact_stem: str = "",
    session_key: str = "",
    app_dir: str = "",
) -> dict:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.create is a scaffold stub")
