"""Append-message UDF — append one transcript entry + bump the chat counters.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. Stdlib-only. The future implementation:

  1. Writes the one ``{ kind:'human', text, dataSnapshot?, ts }`` line to
     ``<app_dir>/artifact-chats/<chat_id>.ndjson`` — opening in append mode and
     writing ``json.dumps(entry) + "\\n"``, atomic per line. The path is CONFINED
     to the real ``artifact-chats/`` directory before opening (``chat_id`` is
     caller-controlled — reuse the run-management ``_transcript_path`` confinement,
     repointed at ``artifact-chats/``); a traversal-shaped id is rejected.
  2. Under the ``artifactChats`` collection flock, bumps the record's
     ``messageCount += 1`` and ``lastActivityAt = now`` (whole-document RMW,
     atomic).

OWNERSHIP NOTE (mirrors run-management's resolved split — see SKILL.md "Division
of labor"; overview.md §11 L3/L5). This UDF owns the ONE
``{ kind:'human', text, dataSnapshot?, ts }`` transcript line ONLY. The streamed
assistant/tool/lifecycle lines — the raw run-thread ``TranscriptEntry``/``RunEvent``
union (``assistant``/``thinking``/``tool_call``/``tool_result``/``result`` + the
``init``/``system``/``stderr``/``stdout`` lifecycle kinds), NOT re-wrapped under
``kind:'event'`` — are appended by the APP's live-response loop (the artifact-chat
sibling of ``app/src/server/runs/launcher.ts``'s ``log.write(...)``), exactly as
runs append their NDJSON. The UDF is NOT in the per-event hot path; ``transcript``
stays a read-only snapshot. This keeps the run-management invariant: the UDF never
participates in the live append loop.

Params
------
chat_id : str
    The chat whose transcript to append to. Empty / traversal-shaped → not found.
entry_json : str
    The ``{ kind:'human', text, dataSnapshot?, ts }`` line as a JSON-encoded object
    (the only line this op writes — see spec.md for the full shape + L5).
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
dict
    The updated ``ArtifactChatRecord`` (with the bumped ``messageCount`` /
    ``lastActivityAt``), or ``{"ok": false, "error": "not found"}`` when the chat
    id is unknown (no record to bump — the entry is NOT written in that case).

File effects
------------
Appends one line to ``<app_dir>/artifact-chats/<chat_id>.ndjson`` (creating the
file on the first message) AND rewrites ``state/artifactChats.json`` (atomic).
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def append_message(chat_id: str = "", entry_json: str = "", app_dir: str = "") -> dict:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.append_message is a scaffold stub")
