"""Delete-project UDF — remove every run record (and its transcript) for one project.

Writes ``~/.openfused/app/state.json`` (or the directory named by
``OPENFUSED_APP_DIR_STATE``) directly with stdlib; no third-party imports.

This is the run-management half of the cross-skill **project-delete** cascade:
it deletes the run records whose camelCase ``project`` field equals the named
project, and removes each removed run's per-run transcript
``<app_dir>/runs/<runId>.ndjson``. It is the FIRST destructive write op in
run-management — only ``bulk_seed`` wrote before (``transcript`` stays read-only,
``create``/``finish``/… only mutate single records). It REUSES ``_transcript_path``
(copied from ``transcript``/``bulk_seed``) so a traversal-shaped run id can never
delete an ``.ndjson`` file outside ``runs/``.

Params
------
project : str
    The project slug whose run records (and their transcripts) are removed.

Returns
-------
dict
    A camelCase ack::

        {
            "runsRemoved": N,
            "transcriptsRemoved": N,
        }

Idempotency
-----------
An empty/whitespace ``project`` — and any project with no matching runs — is a
no-op that returns zero counts and writes nothing. A removed run whose transcript
file is already absent (or whose id resolves outside ``runs/``) counts as skipped,
so a re-run never raises.
"""

import atexit
import fcntl
import json
import os

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


def _app_dir() -> str:
    """Resolve the app directory (the dir that holds state/ and runs/).

    ``OPENFUSED_APP_DIR_STATE`` is a DIRECTORY; when set it is used verbatim (no
    expanduser). Otherwise fall back to ``~/.openfused/app``.
    Distinct from ``_state_dir()`` (which appends ``state``) so the caller can
    join ``runs/<id>.ndjson`` — copied from ``transcript/main.py``.
    """
    env_val = os.environ.get("OPENFUSED_APP_DIR_STATE")
    if env_val:
        return env_val
    return os.path.expanduser("~/.openfused/app")


def _state_dir() -> str:
    """Resolve <app_dir>/state. ``OPENFUSED_APP_DIR_STATE`` (a DIRECTORY) is used
    verbatim when set (no expanduser); else ~/.openfused/app."""
    env_val = os.environ.get("OPENFUSED_APP_DIR_STATE")
    app_dir = env_val if env_val else os.path.expanduser("~/.openfused/app")
    return os.path.join(app_dir, "state")


def _transcript_path(run_id: str) -> str | None:
    """Resolve the transcript path, confined to the ``runs/`` directory.

    ``run_id`` is caller-controlled, so a traversal-shaped value (``..``, an
    absolute path, a symlink) must not let the UDF write ``.ndjson`` files outside
    ``runs/``. The resolved real path must be a direct child of the real ``runs/``
    directory; otherwise return ``None`` (the caller counts it as skipped). A valid
    run id is a flat ``run_<hex>`` with no separators. Copied from
    ``transcript/main.py``.
    """
    runs_dir = os.path.realpath(os.path.join(_app_dir(), "runs"))
    path = os.path.realpath(os.path.join(runs_dir, f"{run_id}.ndjson"))
    if os.path.dirname(path) != runs_dir:
        return None
    return path


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
def delete_project(project: str = "", app_dir: str = "") -> dict:
    """Remove every run record for ``project`` and its per-run transcript file.

    One atomic ``_load_doc → mutate → _save_doc`` cycle over ``runs``, then a
    best-effort delete of each removed run's ``runs/<runId>.ndjson`` (path-confined
    via ``_transcript_path`` — a traversal-shaped id is skipped). Idempotent: an
    empty/whitespace ``project`` — or one with no runs — returns zero counts and
    writes nothing; a missing transcript file counts as skipped.

    Args:
        project: the project slug whose run records (and their transcripts) are removed.
        app_dir: storage location override (precedence over OPENFUSED_APP_DIR_STATE / default).
    """
    if app_dir:
        os.environ["OPENFUSED_APP_DIR_STATE"] = app_dir

    # No-op for an empty/whitespace project: never lock or write, never raise.
    if not project.strip():
        return {"runsRemoved": 0, "transcriptsRemoved": 0}

    doc = _load_doc("runs")
    runs: list[dict] = doc.get("runs") or []

    # Collect this project's run ids, then drop those records.
    removed_ids = [r.get("id") for r in runs if r.get("project") == project]
    remaining_runs = [r for r in runs if r.get("project") != project]
    runs_removed = len(runs) - len(remaining_runs)

    doc["runs"] = remaining_runs
    _save_doc(doc)

    # Delete each removed run's transcript. A missing file, or an id that resolves
    # outside runs/, counts as skipped (not removed).
    transcripts_removed = 0
    for run_id in removed_ids:
        if not run_id:
            continue
        path = _transcript_path(run_id)
        if path is None or not os.path.exists(path):
            continue
        try:
            os.remove(path)
            transcripts_removed += 1
        except OSError:
            # A racing deleter (or a vanished file) leaves nothing to remove.
            pass

    return {"runsRemoved": runs_removed, "transcriptsRemoved": transcripts_removed}
