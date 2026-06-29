"""Set-title UDF — set the optional human label on an artifact-chat.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. The future implementation mirrors run-management/set_prompt/main.py:
stdlib-only, take the exclusive flock on the `artifactChats` collection, whole-
document read-modify-write (preserve every other top-level key), atomic write.

Sets ``title`` on an existing chat unconditionally (no state-machine validation —
the app gates legality before calling). Empty string clears the label to JSON
``null`` (the nullable-field convention).

Params
------
chat_id : str
    The chat id to label.
title : str
    The new title; empty string → JSON ``null``.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
dict
    The updated ``ArtifactChatRecord``, or ``{"ok": false, "error": "not found"}``
    for an unknown ``chat_id``.

File effects
------------
Rewrites ``<app_dir>/state/artifactChats.json`` (whole-document RMW, atomic) when
the title changes. Never touches the transcript file.
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def set_title(chat_id: str = "", title: str = "", app_dir: str = "") -> dict:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.set_title is a scaffold stub")
