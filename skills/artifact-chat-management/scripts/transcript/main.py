"""Transcript UDF — returns a chat's NDJSON transcript from the app chat dir.

SCAFFOLD / CONTRACT STUB. This docstring is the contract; the body is a
placeholder. The future implementation mirrors run-management/transcript/main.py
VERBATIM, repointed from ``runs/`` to ``artifact-chats/``: stdlib-only, the path
confined to the real ``artifact-chats/`` directory before opening (``chat_id`` is
caller-controlled), torn trailing lines skipped (valid prefix preserved).

Reads ``<app_dir>/artifact-chats/<chat_id>.ndjson`` directly with stdlib (after
confining the resolved path to ``artifact-chats/``); no third-party imports.
``<app_dir>`` is the ``app_dir`` param, else ``$OPENFUSED_APP_DIR_STATE``
(verbatim), else ``~/.openfused/app`` — the same dir under which the app's
live-response loop appends ``artifact-chats/<chatId>.ndjson``.

READ-ONLY on the hot path: live streaming stays the app's SSE channel
(``GET /api/artifact-chats/:chatId/events``, reusing ``runs/stream.ts``). This UDF
returns a SNAPSHOT of the entries written so far, refreshed by re-resolving.
**Cross-agent read — this is the visibility op other agents call** to learn what
users have asked about an artifact.

Params
------
chat_id : str
    The chat id whose transcript to read. Empty string returns ``[]``.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
list[dict]
    The persisted ``TranscriptEntry`` lines for the chat, in file order, verbatim
    (each is either the ``{ kind:'human', … }`` line ``append_message`` wrote or a
    raw run-thread entry the app lane appended — overview.md §11 L5; this op does
    NOT interpret ``kind``). A missing file, an empty ``chat_id``, or a ``chat_id``
    whose resolved path would escape ``artifact-chats/`` returns ``[]``. Torn /
    invalid trailing lines are skipped (mirrors run-management ``transcript`` / the
    Express ``replayEvents``).

File effects
------------
None — read-only.
"""


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def transcript(chat_id: str = "", app_dir: str = "") -> list:
    """SCAFFOLD — see module docstring for the contract. Implementation deferred."""
    raise NotImplementedError("artifact-chat-management.transcript is a scaffold stub")
