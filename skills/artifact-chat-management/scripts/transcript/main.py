"""Transcript UDF — returns a chat's NDJSON transcript from the app chat dir.

Reads ``<app_dir>/artifact-chats/<chat_id>.ndjson`` directly with stdlib (after
confining the resolved path to ``artifact-chats/`` — ``chat_id`` is
caller-controlled); no third-party imports. ``<app_dir>`` is the ``app_dir`` param,
else ``$OPENFUSED_APP_DIR_STATE`` (verbatim), else ``~/.openfused/app`` — the same
dir under which the app's live-response loop appends ``artifact-chats/<chatId>.ndjson``.

READ-ONLY on the hot path: live streaming stays the app's SSE channel
(``GET /api/artifact-chats/:runId/events``, reusing ``runs/stream.ts``). This UDF
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

import json
import os


def _app_dir() -> str:
    """Resolve the app directory (the dir that holds state/ and artifact-chats/).

    ``OPENFUSED_APP_DIR_STATE`` is a DIRECTORY; when set it is used verbatim
    (no expanduser). Otherwise fall back to ``~/.openfused/app``.
    """
    env_val = os.environ.get("OPENFUSED_APP_DIR_STATE")
    if env_val:
        return env_val
    return os.path.expanduser("~/.openfused/app")


def _transcript_path(chat_id: str) -> str | None:
    """Resolve the transcript path, confined to the ``artifact-chats/`` directory.

    ``chat_id`` is caller-controlled, so a traversal-shaped value (``..``, an
    absolute path, a symlink) must not let the UDF read ``.ndjson`` files
    outside ``artifact-chats/``. The resolved real path must be a direct child of
    the real ``artifact-chats/`` directory; otherwise return ``None`` (the caller
    maps that to an empty result, like a missing file). A valid chat id is a flat
    ``chat_<hex>`` with no separators.
    """
    chats_dir = os.path.realpath(os.path.join(_app_dir(), "artifact-chats"))
    path = os.path.realpath(os.path.join(chats_dir, f"{chat_id}.ndjson"))
    if os.path.dirname(path) != chats_dir:
        return None
    return path


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def transcript(chat_id: str = "", app_dir: str = "") -> list:
    """Return the TranscriptEntry list for ``chat_id`` from its NDJSON transcript.

    Args:
        chat_id: the chat id whose transcript to read; empty string returns [].
        app_dir: storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).
    """
    if app_dir:
        os.environ["OPENFUSED_APP_DIR_STATE"] = app_dir
    if not chat_id:
        return []
    path = _transcript_path(chat_id)
    if path is None:
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return []
    entries: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn/partial line (realistically only the last) — keep the
            # valid prefix rather than discarding the whole transcript.
            continue
    return entries
