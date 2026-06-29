"""Clear UDF — durably reset one artifact-chat (wipe transcript + fresh session).

Stdlib-only. This UDF durably *clears* a chat so it stays cleared after the
popover is reopened / the page reloaded: it both wipes the persisted transcript
and resets the record's live-conversation state. Concretely it:

  1. Deletes the flat transcript file ``<app_dir>/artifact-chats/<chat_id>.ndjson``
     if present (tolerating a missing file — an empty chat has none yet). The path
     is CONFINED to the real ``artifact-chats/`` directory before unlinking
     (``chat_id`` is caller-controlled — reuse the run-management ``_transcript_path``
     confinement, repointed at ``artifact-chats/``); a traversal-shaped id is
     rejected (not found, no unlink).
  2. Under the ``artifactChats`` collection flock, resets the record in a
     whole-document read-modify-write (preserves every other top-level key):
     ``messageCount = 0``, ``lastActivityAt = now``, a NEW ``sessionKey`` (so the
     agentbridge session is fresh — the next turn resumes nothing — minted the same
     way ``create`` mints the create-time fields), and ``title = null``. The
     identity + ref fields are kept: ``id``, ``project``, ``artifactType``,
     ``artifactStem`` (``createdAt`` is also preserved — the chat itself is not
     re-created, only reset).

This is an APP-ONLY WRITE op (NOT a cross-agent read): only the app calls it, when
the user clears a chat.

Params
------
chat_id : str
    The chat to reset. Empty / traversal-shaped → not found.
app_dir : str
    Storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).

Returns
-------
dict
    The reset ``ArtifactChatRecord`` (``messageCount=0``, fresh ``sessionKey``,
    ``title=null``, bumped ``lastActivityAt``), or ``{"ok": false, "error": "not
    found"}`` when the chat id is unknown (the not-found ack the other ops use — no
    throw, and the transcript is NOT deleted in that case).

File effects
------------
Removes ``<app_dir>/artifact-chats/<chat_id>.ndjson`` (if present) AND rewrites
``state/artifactChats.json`` (whole-document RMW, atomic).
"""

import atexit
import fcntl
import json
import os
import uuid
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
    absolute path, a symlink) must not let the UDF unlink ``.ndjson`` files
    outside ``artifact-chats/``. The directory is created first (so realpath
    resolves a real dir even on a never-written store), then the resolved real
    path must be a direct child of the real ``artifact-chats/`` directory;
    otherwise return ``None`` (rejected — no unlink).
    """
    chats_dir = os.path.join(_app_dir(), "artifact-chats")
    os.makedirs(chats_dir, exist_ok=True)
    chats_dir = os.path.realpath(chats_dir)
    path = os.path.realpath(os.path.join(chats_dir, f"{chat_id}.ndjson"))
    if os.path.dirname(path) != chats_dir:
        return None
    return path


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def clear(chat_id: str = "", app_dir: str = "") -> dict:
    """Durably reset a chat: wipe its transcript + reset the record to a fresh session.

    Mirrors ``set_title``/``append_message`` (a missing record returns the
    not-found ack; no state-machine validation — the app gates legality before
    calling). The reset record keeps its identity (``id``) + ref (``project`` /
    ``artifactType`` / ``artifactStem``) + ``createdAt``, but resets
    ``messageCount`` to 0, bumps ``lastActivityAt``, mints a NEW ``sessionKey``, and
    clears ``title`` to ``null``.

    Args:
        chat_id: the chat to reset; empty / traversal-shaped → not found.
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

    # Wipe the persisted transcript so the chat stays cleared after reopen/reload.
    # Tolerate a missing file (an empty chat has no .ndjson yet).
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

    # Reset the live-conversation state. A fresh sessionKey makes the next turn's
    # agentbridge session brand-new (resumes nothing) — minted like `create` mints
    # its create-time fields (uuid hex, no separators, so it stays a flat key).
    chat["messageCount"] = 0
    chat["lastActivityAt"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    chat["sessionKey"] = uuid.uuid4().hex
    chat["title"] = None
    doc["artifactChats"] = chats
    _save_doc(doc)
    return chat
