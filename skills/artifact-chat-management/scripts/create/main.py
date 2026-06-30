"""Create UDF — find-or-create the one artifact-chat for an artifact ref.

Mirrors run-management/create/main.py: takes the exclusive flock on the
`artifactChats` collection across the whole load->modify->save, does a
whole-document read-modify-write that preserves every other top-level key, and
writes atomically (tmp + os.replace). Stdlib-only.

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


@udf  # ty: ignore[unresolved-reference]  # noqa: F821 — injected by the exec runtime
def create(
    id: str = "",
    project: str = "",
    artifact_type: str = "",
    artifact_stem: str = "",
    session_key: str = "",
    app_dir: str = "",
) -> dict:
    """Find-or-create the one chat for the ref with the caller-supplied id.

    Idempotent on ``(project, artifactType, artifactStem)`` (D6): a find-hit
    returns the existing record unchanged; otherwise a fresh record is appended.

    Args:
        id: the chat id (``chat_<hex>``); supplied by the caller, never minted here.
        project: the artifact's project.
        artifact_type: ``widget`` / ``udf`` / ``reference``.
        artifact_stem: the widget stem / udf name / reference name.
        session_key: the agentbridge resume key (Claude Code session).
        app_dir: storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).
    """
    if app_dir:
        os.environ["OPENFUSED_APP_DIR_STATE"] = app_dir
    doc = _load_doc("artifactChats")
    chats: list[dict] = doc.get("artifactChats") or []

    existing = next(
        (
            c
            for c in chats
            if c.get("project") == project
            and c.get("artifactType") == artifact_type
            and c.get("artifactStem") == artifact_stem
        ),
        None,
    )
    if existing is not None:
        _save_doc(doc)  # no-op write (serialization unchanged), releases the lock
        return existing

    # ISO-8601 with milliseconds + Z suffix (matches new Date().toISOString()).
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    record: dict = {
        "id": id,
        "project": project,
        "artifactType": artifact_type,
        "artifactStem": artifact_stem,
        "title": None,
        "createdAt": now,
        "lastActivityAt": now,
        "messageCount": 0,
        "sessionKey": session_key,
    }

    chats.append(record)
    doc["artifactChats"] = chats
    _save_doc(doc)
    return record
