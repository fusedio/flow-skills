"""Append-message UDF — append one transcript entry + bump the chat counters.

Stdlib-only. This UDF:

  1. Writes the one ``{ kind:'human', text, dataSnapshot?, ts }`` line to
     ``<app_dir>/artifact-chats/<chat_id>.ndjson`` — opening in append mode and
     writing ``json.dumps(entry) + "\\n"``. The path is CONFINED to the real
     ``artifact-chats/`` directory before opening (``chat_id`` is caller-controlled
     — reuse the run-management ``_transcript_path`` confinement, repointed at
     ``artifact-chats/``); a traversal-shaped id is rejected. The dir is created
     ``mkdir -p`` before opening (the UDF may be the first writer on either path —
     storage §2.1 directory contract).
  2. Under the ``artifactChats`` collection flock, bumps the record's
     ``messageCount += 1`` and ``lastActivityAt = now`` (whole-document RMW,
     atomic).

OWNERSHIP NOTE (mirrors run-management's resolved split — see SKILL.md "Division
of labor"; overview.md §11 L3/L5). This UDF owns the ONE
``{ kind:'human', text, dataSnapshot?, ts }`` transcript line ONLY. The streamed
assistant/tool/lifecycle lines — the raw run-thread ``TranscriptEntry``/``RunEvent``
union — are appended by the APP's live-response loop, exactly as runs append their
NDJSON. The UDF is NOT in the per-event hot path; ``transcript`` stays a read-only
snapshot.

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
dir + file on the first message) AND rewrites ``state/artifactChats.json`` (atomic).
"""

import atexit
import fcntl
import json
import os
from datetime import UTC, datetime

# --- per-entity state helpers -------------------------------
# Each top-level collection is its own <app_dir>/state/<key>.json. A write UDF
# names the collection(s) it mutates in `_load_doc(...)`; the helper holds an
# exclusive flock on each `<app_dir>/state/.<key>.lock` sentinel across the whole
# load->save section so concurrent same-collection writers serialize (no lost
# updates). Locking a stable sentinel (never renamed) survives the atomic
# tmp+rename of the data file. This UDF runs as a one-shot subprocess (exactly
# one load->save), so the module-level lock fds + snapshot need no extra guard.
_COLLECTION_KEYS = (
    "tasks",
    "runs",
    "comments",
    "inbox",
    "cards",
    "serveMcp",
    "costEvents",
    "gatePolicies",
    "onboarding",
    "dismissedFeedbackKeys",
    "artifactChats",
)
_COLLECTION_DEFAULTS = {
    "serveMcp": {},
    "gatePolicies": {},
    "onboarding": {"completed": False, "version": 1},
}
_HELD_LOCKS: list[int] = []
_SNAPSHOT: dict[str, str] = {}


def _release_locks() -> None:
    """Release every held flock (idempotent). Registered with atexit so a write
    UDF that returns early or raises before _save_doc still frees its locks
    promptly rather than only on interpreter teardown."""
    while _HELD_LOCKS:
        fd = _HELD_LOCKS.pop()
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except OSError:
            pass


atexit.register(_release_locks)


def _state_dir() -> str:
    """Resolve <app_dir>/state. ``OPENFUSED_APP_DIR_STATE`` (a DIRECTORY) is used
    verbatim when set (no expanduser); else ~/.openfused/app."""
    env_val = os.environ.get("OPENFUSED_APP_DIR_STATE")
    app_dir = env_val if env_val else os.path.expanduser("~/.openfused/app")
    return os.path.join(app_dir, "state")


def _collection_default(key: str):
    default = _COLLECTION_DEFAULTS.get(key)
    return dict(default) if default is not None else []


def _load_doc(*lock_collections: str) -> dict:
    """Assemble the document from the per-entity files. For each collection in
    *lock_collections* (those this UDF will mutate) hold an exclusive flock on its
    sentinel lock file across load->save (released in ``_save_doc``). A
    present-but-corrupt file RAISES on the write path (so a later save cannot
    clobber it) and falls back to the default on a pure read."""
    state_dir = _state_dir()
    os.makedirs(state_dir, exist_ok=True)
    for col in sorted(lock_collections):
        fd = os.open(os.path.join(state_dir, f".{col}.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        _HELD_LOCKS.append(fd)
    doc: dict = {}
    for key in _COLLECTION_KEYS:
        path = os.path.join(state_dir, f"{key}.json")
        try:
            with open(path, encoding="utf-8") as fh:
                doc[key] = json.load(fh)
        except FileNotFoundError:
            doc[key] = _collection_default(key)
        except json.JSONDecodeError as exc:
            if key in lock_collections:
                raise RuntimeError(
                    f"{path} is corrupt and could not be parsed ({exc}); "
                    "inspect or restore it before retrying this write."
                ) from exc
            doc[key] = _collection_default(key)
    _SNAPSHOT.clear()
    for key in _COLLECTION_KEYS:
        _SNAPSHOT[key] = json.dumps(doc[key], indent=2, ensure_ascii=False)
    return doc


def _save_doc(doc: dict) -> None:
    """Write each collection whose serialization changed since ``_load_doc`` to its
    own <key>.json via a crash-safe tmp+rename, then release every held lock."""
    state_dir = _state_dir()
    os.makedirs(state_dir, exist_ok=True)
    try:
        for key in _COLLECTION_KEYS:
            if key not in doc:
                continue
            text = json.dumps(doc[key], indent=2, ensure_ascii=False)
            if text == _SNAPSHOT.get(key):
                continue
            dest = os.path.join(state_dir, f"{key}.json")
            tmp = dest + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, dest)
            _SNAPSHOT[key] = text
    finally:
        _release_locks()


# --- end per-entity state helpers ------------------------------------------


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
    absolute path, a symlink) must not let the UDF write ``.ndjson`` files
    outside ``artifact-chats/``. The directory is created first (the UDF may be the
    first writer — storage §2.1), then the resolved real path must be a direct
    child of the real ``artifact-chats/`` directory; otherwise return ``None``.
    """
    chats_dir = os.path.join(_app_dir(), "artifact-chats")
    os.makedirs(chats_dir, exist_ok=True)
    chats_dir = os.path.realpath(chats_dir)
    path = os.path.realpath(os.path.join(chats_dir, f"{chat_id}.ndjson"))
    if os.path.dirname(path) != chats_dir:
        return None
    return path


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def append_message(chat_id: str = "", entry_json: str = "", app_dir: str = "") -> dict:
    """Append the one human line to the chat transcript + bump the record counters.

    Args:
        chat_id: the chat to append to; empty / traversal-shaped → not found.
        entry_json: the ``{ kind:'human', text, dataSnapshot?, ts }`` line, JSON-encoded.
        app_dir: storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).
    """
    if app_dir:
        os.environ["OPENFUSED_APP_DIR_STATE"] = app_dir
    if not chat_id:
        return {"ok": False, "error": "not found"}
    path = _transcript_path(chat_id)
    if path is None:
        return {"ok": False, "error": "not found"}

    doc = _load_doc("artifactChats")
    chats: list[dict] = doc.get("artifactChats") or []

    chat = next((c for c in chats if c.get("id") == chat_id), None)
    if chat is None:
        return {"ok": False, "error": "not found"}

    # Append the one human line (the entry rides as a JSON-encoded object).
    entry = json.loads(entry_json) if entry_json else {}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    chat["messageCount"] = int(chat.get("messageCount") or 0) + 1
    chat["lastActivityAt"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    doc["artifactChats"] = chats
    _save_doc(doc)
    return chat
