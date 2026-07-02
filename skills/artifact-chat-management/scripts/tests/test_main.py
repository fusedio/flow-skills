"""Core-behavior tests for the artifact-chat-management UDFs (storage §6.1).

Covers, against a temp ``app_dir``:
  - the ``app_dir`` precedence contract (param > env > default) for both
    ``state/artifactChats.json`` and the ``artifact-chats/<id>.ndjson`` transcript;
  - D6 find-or-create idempotency on the ``(project, artifactType, artifactStem)``
    key (``create`` twice → one record, no duplicate);
  - ``append_message`` writes ONLY the human line + bumps ``messageCount`` /
    ``lastActivityAt``; the not-found ack writes no line;
  - ``transcript`` tolerates a missing dir/file (→ ``[]``), confines a
    traversal-shaped ``chat_id`` (→ ``[]``), and skips a torn trailing line;
  - the whole-document RMW preserves every OTHER collection's file;
  - ``get`` / ``read`` filtering by project + artifact ref;
  - the ``asset`` artifact type: path-shaped stems (``assets/sales.parquet``) are
    opaque exact-match strings — round-trip verbatim, idempotent on the exact
    path, no cross-type collision, and survive ``clear``.
"""

import json
from pathlib import Path


def _chats_file(app_dir) -> Path:
    return Path(app_dir) / "state" / "artifactChats.json"


def _transcript_file(app_dir, chat_id) -> Path:
    return Path(app_dir) / "artifact-chats" / f"{chat_id}.ndjson"


def _create(load_udf, store_dir, **kw):
    defaults = dict(
        id="chat_1",
        project="p",
        artifact_type="widget",
        artifact_stem="sales",
        session_key="sk",
        app_dir=str(store_dir),
    )
    defaults.update(kw)  # kw may override any field, incl. app_dir (e.g. "" to test env fallback)
    return load_udf("create", "create")(**defaults)


# --- app_dir precedence ----------------------------------------------------


def test_app_dir_param_honored(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    rec = _create(load_udf, tmp_path)
    assert rec.get("id") == "chat_1"
    assert _chats_file(tmp_path).exists()


def test_env_fallback_when_param_omitted(load_udf, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(tmp_path))
    _create(load_udf, tmp_path, app_dir="")
    assert _chats_file(tmp_path).exists()


def test_param_overrides_env(load_udf, tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    param_dir = tmp_path / "param"
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(env_dir))
    _create(load_udf, param_dir, app_dir=str(param_dir))
    assert _chats_file(param_dir).exists()
    assert not _chats_file(env_dir).exists()


def test_transcript_path_honors_app_dir(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path)
    entry = json.dumps({"kind": "human", "text": "hi", "ts": "2026-01-01T00:00:00Z"})
    load_udf("append_message", "append_message")(
        chat_id="chat_1", entry_json=entry, app_dir=str(tmp_path)
    )
    assert _transcript_file(tmp_path, "chat_1").exists()
    got = load_udf("transcript", "transcript")(chat_id="chat_1", app_dir=str(tmp_path))
    assert got == [{"kind": "human", "text": "hi", "ts": "2026-01-01T00:00:00Z"}]
    # a different store sees no transcript
    assert load_udf("transcript", "transcript")(chat_id="chat_1", app_dir=str(tmp_path / "other")) == []


# --- D6 find-or-create idempotency -----------------------------------------


def test_create_is_idempotent_on_ref(load_udf, tmp_path, monkeypatch):
    """create twice on the same (project, type, stem) returns the SAME record
    (id/timestamps preserved) and writes no duplicate — D6, one chat per artifact."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    first = _create(load_udf, tmp_path, id="chat_first")
    # second call supplies a DIFFERENT id; the find-hit must ignore it and return
    # the existing record unchanged.
    second = _create(load_udf, tmp_path, id="chat_second")
    assert first["id"] == "chat_first"
    assert second["id"] == "chat_first"  # the existing record, NOT the new id
    assert second["createdAt"] == first["createdAt"]
    rows = load_udf("read", "read")(app_dir=str(tmp_path))
    assert len(rows) == 1


def test_create_record_shape(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    rec = _create(load_udf, tmp_path)
    assert rec == {
        "id": "chat_1",
        "project": "p",
        "artifactType": "widget",
        "artifactStem": "sales",
        "title": None,
        "createdAt": rec["createdAt"],
        "lastActivityAt": rec["lastActivityAt"],
        "messageCount": 0,
        "sessionKey": "sk",
    }
    assert rec["createdAt"] == rec["lastActivityAt"]
    assert rec["createdAt"].endswith("Z")


def test_create_distinct_refs_make_distinct_chats(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_w", artifact_type="widget", artifact_stem="a")
    _create(load_udf, tmp_path, id="chat_u", artifact_type="udf", artifact_stem="a")
    rows = load_udf("read", "read")(app_dir=str(tmp_path))
    assert {r["id"] for r in rows} == {"chat_w", "chat_u"}


# --- append_message: only the human line + counter bump --------------------


def test_append_message_bumps_counters_and_writes_one_line(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    created = _create(load_udf, tmp_path)
    assert created["messageCount"] == 0

    e1 = json.dumps({"kind": "human", "text": "q1", "ts": "t1"})
    r1 = load_udf("append_message", "append_message")(
        chat_id="chat_1", entry_json=e1, app_dir=str(tmp_path)
    )
    assert r1["messageCount"] == 1
    assert r1["lastActivityAt"] >= created["lastActivityAt"]

    e2 = json.dumps({"kind": "human", "text": "q2", "ts": "t2"})
    r2 = load_udf("append_message", "append_message")(
        chat_id="chat_1", entry_json=e2, app_dir=str(tmp_path)
    )
    assert r2["messageCount"] == 2

    # exactly the two human lines we appended — the UDF never writes an
    # assistant/tool/lifecycle line (that is the app lane's job, L3).
    lines = _transcript_file(tmp_path, "chat_1").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {"kind": "human", "text": "q1", "ts": "t1"},
        {"kind": "human", "text": "q2", "ts": "t2"},
    ]


def test_append_message_not_found_writes_no_line(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_1")
    ack = load_udf("append_message", "append_message")(
        chat_id="chat_missing",
        entry_json=json.dumps({"kind": "human", "text": "x"}),
        app_dir=str(tmp_path),
    )
    assert ack == {"ok": False, "error": "not found"}
    # no transcript was written for the unknown chat
    assert not _transcript_file(tmp_path, "chat_missing").exists()
    # the real chat's counter is untouched
    rows = load_udf("read", "read")(app_dir=str(tmp_path))
    assert rows[0]["messageCount"] == 0


def test_append_message_empty_id_is_not_found(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    ack = load_udf("append_message", "append_message")(
        chat_id="", entry_json="{}", app_dir=str(tmp_path)
    )
    assert ack == {"ok": False, "error": "not found"}


# --- transcript: missing / traversal / torn-line ---------------------------


def test_transcript_missing_dir_returns_empty(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    # no chat, no artifact-chats/ dir at all
    assert load_udf("transcript", "transcript")(chat_id="chat_1", app_dir=str(tmp_path)) == []
    # the read-only transcript op must NOT materialize the directory (storage §2.1)
    assert not (tmp_path / "artifact-chats").exists()


def test_transcript_empty_id_returns_empty(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    assert load_udf("transcript", "transcript")(chat_id="", app_dir=str(tmp_path)) == []


def test_transcript_confines_traversal_id(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    # Plant a sentinel that a traversal id would resolve onto, outside artifact-chats/.
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "secret.ndjson").write_text(json.dumps({"secret": True}) + "\n", encoding="utf-8")
    # A traversal-shaped chat_id whose resolved path escapes artifact-chats/ → [].
    assert load_udf("transcript", "transcript")(
        chat_id="../state/secret", app_dir=str(tmp_path)
    ) == []


def test_transcript_skips_torn_trailing_line(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    f = _transcript_file(tmp_path, "chat_1")
    f.parent.mkdir(parents=True, exist_ok=True)
    # two valid lines + a torn (truncated) trailing line, as a crash mid-write leaves.
    f.write_text(
        json.dumps({"kind": "human", "text": "a"}) + "\n"
        + json.dumps({"kind": "result", "text": "b"}) + "\n"
        + '{"kind": "human", "text": "tor',
        encoding="utf-8",
    )
    got = load_udf("transcript", "transcript")(chat_id="chat_1", app_dir=str(tmp_path))
    assert got == [{"kind": "human", "text": "a"}, {"kind": "result", "text": "b"}]


# --- whole-document RMW preserves other collections ------------------------


def test_create_preserves_other_collections(load_udf, tmp_path, monkeypatch):
    """The write must do a whole-document RMW that leaves every other collection's
    file byte-intact (storage §3 write discipline)."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    tasks = [{"id": "t1", "title": "keep me"}]
    runs = [{"id": "run_1", "taskId": "t1"}]
    serve_mcp = {"proj/widget": True}
    (state_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (state_dir / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    (state_dir / "serveMcp.json").write_text(json.dumps(serve_mcp, indent=2), encoding="utf-8")

    _create(load_udf, tmp_path)
    load_udf("append_message", "append_message")(
        chat_id="chat_1",
        entry_json=json.dumps({"kind": "human", "text": "q"}),
        app_dir=str(tmp_path),
    )
    load_udf("set_title", "set_title")(chat_id="chat_1", title="My chat", app_dir=str(tmp_path))

    # every other collection's file is untouched
    assert json.loads((state_dir / "tasks.json").read_text(encoding="utf-8")) == tasks
    assert json.loads((state_dir / "runs.json").read_text(encoding="utf-8")) == runs
    assert json.loads((state_dir / "serveMcp.json").read_text(encoding="utf-8")) == serve_mcp
    # and the chat write landed
    rows = load_udf("read", "read")(app_dir=str(tmp_path))
    assert rows[0]["title"] == "My chat" and rows[0]["messageCount"] == 1


def test_create_find_hit_does_not_rewrite_file(load_udf, tmp_path, monkeypatch):
    """A find-hit returns the existing record and writes nothing (the no-op save
    leaves artifactChats.json byte-identical)."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path)
    before = _chats_file(tmp_path).read_text(encoding="utf-8")
    _create(load_udf, tmp_path, id="chat_other")
    after = _chats_file(tmp_path).read_text(encoding="utf-8")
    assert before == after


# --- set_title -------------------------------------------------------------


def test_set_title_sets_and_clears(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path)
    r = load_udf("set_title", "set_title")(chat_id="chat_1", title="Title", app_dir=str(tmp_path))
    assert r["title"] == "Title"
    cleared = load_udf("set_title", "set_title")(chat_id="chat_1", title="", app_dir=str(tmp_path))
    assert cleared["title"] is None  # empty → null (nullable-field convention)


def test_set_title_not_found_ack(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    ack = load_udf("set_title", "set_title")(chat_id="nope", title="x", app_dir=str(tmp_path))
    assert ack == {"ok": False, "error": "not found"}


# --- clear: durable reset (wipe transcript + fresh session) ----------------


def test_clear_wipes_transcript_and_resets_record(load_udf, tmp_path, monkeypatch):
    """clear deletes the chat's .ndjson AND resets messageCount/title + mints a NEW
    sessionKey, keeping id + ref + createdAt — so the chat stays cleared on reopen."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    created = _create(load_udf, tmp_path, id="chat_1", session_key="sk-old")
    load_udf("append_message", "append_message")(
        chat_id="chat_1",
        entry_json=json.dumps({"kind": "human", "text": "q1", "ts": "t1"}),
        app_dir=str(tmp_path),
    )
    load_udf("set_title", "set_title")(chat_id="chat_1", title="My chat", app_dir=str(tmp_path))
    # precondition: a transcript file + a non-zero count exist before clearing.
    assert _transcript_file(tmp_path, "chat_1").exists()
    assert load_udf("read", "read")(app_dir=str(tmp_path))[0]["messageCount"] == 1

    reset = load_udf("clear", "clear")(chat_id="chat_1", app_dir=str(tmp_path))

    # the transcript file is gone (a reopen replays an empty transcript)
    assert not _transcript_file(tmp_path, "chat_1").exists()
    # the record is reset: count 0, title null, fresh session
    assert reset["messageCount"] == 0
    assert reset["title"] is None
    assert reset["sessionKey"] != "sk-old" and reset["sessionKey"]
    assert reset["lastActivityAt"].endswith("Z")
    # identity + ref + createdAt are KEPT (the chat is reset, not re-created)
    assert reset["id"] == "chat_1"
    assert reset["project"] == "p"
    assert reset["artifactType"] == "widget"
    assert reset["artifactStem"] == "sales"
    assert reset["createdAt"] == created["createdAt"]
    # and it durably persisted to the collection file
    persisted = load_udf("read", "read")(app_dir=str(tmp_path))[0]
    assert persisted["messageCount"] == 0
    assert persisted["sessionKey"] == reset["sessionKey"]


def test_clear_tolerates_missing_transcript(load_udf, tmp_path, monkeypatch):
    """A never-messaged chat has no .ndjson; clear still resets the record (no error)."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_1", session_key="sk-old")
    assert not _transcript_file(tmp_path, "chat_1").exists()
    reset = load_udf("clear", "clear")(chat_id="chat_1", app_dir=str(tmp_path))
    assert reset["messageCount"] == 0 and reset["sessionKey"] != "sk-old"


def test_clear_not_found_ack(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    assert load_udf("clear", "clear")(chat_id="nope", app_dir=str(tmp_path)) == {
        "ok": False,
        "error": "not found",
    }
    assert load_udf("clear", "clear")(chat_id="", app_dir=str(tmp_path)) == {
        "ok": False,
        "error": "not found",
    }


def test_clear_unknown_id_deletes_nothing(load_udf, tmp_path, monkeypatch):
    """An unknown chat_id whose path IS confined to artifact-chats/ must still delete
    nothing — the not-found ack returns before the transcript unlink, so a stray
    same-named .ndjson (no matching record) survives untouched."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    # A real (unrelated) chat so the collection file exists; the cleared id is absent.
    _create(load_udf, tmp_path, id="chat_real")
    # Plant a transcript whose confined path matches the unknown id we will clear.
    orphan = _transcript_file(tmp_path, "chat_orphan")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text(json.dumps({"kind": "human", "text": "stray"}) + "\n", encoding="utf-8")

    ack = load_udf("clear", "clear")(chat_id="chat_orphan", app_dir=str(tmp_path))
    assert ack == {"ok": False, "error": "not found"}
    # the unknown chat's transcript was NOT unlinked (not-found ack deletes nothing)
    assert orphan.exists()


def test_clear_confines_traversal_id(load_udf, tmp_path, monkeypatch):
    """A traversal-shaped chat_id whose resolved path escapes artifact-chats/ is
    rejected as not-found — it must not unlink files outside the chat dir."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    sentinel = state_dir / "secret.ndjson"
    sentinel.write_text(json.dumps({"secret": True}) + "\n", encoding="utf-8")
    ack = load_udf("clear", "clear")(chat_id="../state/secret", app_dir=str(tmp_path))
    assert ack == {"ok": False, "error": "not found"}
    assert sentinel.exists()  # the out-of-dir file was NOT unlinked


def test_clear_preserves_other_collections(load_udf, tmp_path, monkeypatch):
    """The reset write is a whole-document RMW that leaves every other collection's
    file byte-intact (storage §3 write discipline)."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    tasks = [{"id": "t1", "title": "keep me"}]
    runs = [{"id": "run_1", "taskId": "t1"}]
    (state_dir / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (state_dir / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")

    _create(load_udf, tmp_path, id="chat_1")
    load_udf("append_message", "append_message")(
        chat_id="chat_1",
        entry_json=json.dumps({"kind": "human", "text": "q"}),
        app_dir=str(tmp_path),
    )
    load_udf("clear", "clear")(chat_id="chat_1", app_dir=str(tmp_path))

    assert json.loads((state_dir / "tasks.json").read_text(encoding="utf-8")) == tasks
    assert json.loads((state_dir / "runs.json").read_text(encoding="utf-8")) == runs


# --- get / read filtering --------------------------------------------------


def test_get_resolves_one_record_or_none(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_a", project="p", artifact_type="widget", artifact_stem="x")
    got = load_udf("get", "get")(
        project="p", artifact_type="widget", artifact_stem="x", app_dir=str(tmp_path)
    )
    assert got["id"] == "chat_a"
    miss = load_udf("get", "get")(
        project="p", artifact_type="udf", artifact_stem="x", app_dir=str(tmp_path)
    )
    assert miss is None


def test_read_filters_by_project_and_ref(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_a", project="alpha", artifact_type="widget", artifact_stem="x")
    _create(load_udf, tmp_path, id="chat_b", project="alpha", artifact_type="udf", artifact_stem="y")
    _create(load_udf, tmp_path, id="chat_c", project="beta", artifact_type="widget", artifact_stem="x")

    assert {r["id"] for r in load_udf("read", "read")(app_dir=str(tmp_path))} == {
        "chat_a",
        "chat_b",
        "chat_c",
    }
    assert {r["id"] for r in load_udf("read", "read")(project="alpha", app_dir=str(tmp_path))} == {
        "chat_a",
        "chat_b",
    }
    scoped = load_udf("read", "read")(
        project="alpha", artifact_type="widget", artifact_stem="x", app_dir=str(tmp_path)
    )
    assert {r["id"] for r in scoped} == {"chat_a"}


def test_read_empty_store_returns_empty(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    assert load_udf("read", "read")(app_dir=str(tmp_path)) == []


# --- asset artifact type: path stems are opaque exact-match strings ---------


def test_create_asset_path_stem_roundtrips_verbatim(load_udf, tmp_path, monkeypatch):
    """An asset chat's stem is the asset's project-relative path — slashes and
    dots included — stored verbatim (no normalization) and returned as-is."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    rec = _create(
        load_udf, tmp_path, artifact_type="asset", artifact_stem="assets/sales.parquet"
    )
    assert rec["artifactType"] == "asset"
    assert rec["artifactStem"] == "assets/sales.parquet"
    # persisted verbatim, not just echoed
    persisted = load_udf("read", "read")(app_dir=str(tmp_path))[0]
    assert persisted["artifactType"] == "asset"
    assert persisted["artifactStem"] == "assets/sales.parquet"


def test_create_asset_is_idempotent_on_exact_path(load_udf, tmp_path, monkeypatch):
    """find-or-create keys on the exact path string (D6); a second create on the
    same path returns the existing record, while a different path (a rename/move)
    is a different identity — the old chat is detached, a new one is minted."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    first = _create(
        load_udf, tmp_path, id="chat_first",
        artifact_type="asset", artifact_stem="assets/sales.parquet",
    )
    second = _create(
        load_udf, tmp_path, id="chat_second",
        artifact_type="asset", artifact_stem="assets/sales.parquet",
    )
    assert second["id"] == first["id"] == "chat_first"
    # a moved asset is a new ref: the store does not follow renames
    moved = _create(
        load_udf, tmp_path, id="chat_moved",
        artifact_type="asset", artifact_stem="assets/archive/sales.parquet",
    )
    assert moved["id"] == "chat_moved"
    assert len(load_udf("read", "read")(app_dir=str(tmp_path))) == 2


def test_asset_stem_does_not_collide_across_types(load_udf, tmp_path, monkeypatch):
    """The type is part of the triple: a widget chat and an asset chat sharing the
    same stem string are distinct chats, and get/read scope by type."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, id="chat_w", artifact_type="widget", artifact_stem="assets/sales.parquet")
    _create(load_udf, tmp_path, id="chat_a", artifact_type="asset", artifact_stem="assets/sales.parquet")

    got = load_udf("get", "get")(
        project="p", artifact_type="asset", artifact_stem="assets/sales.parquet",
        app_dir=str(tmp_path),
    )
    assert got["id"] == "chat_a"
    scoped = load_udf("read", "read")(
        project="p", artifact_type="asset", artifact_stem="assets/sales.parquet",
        app_dir=str(tmp_path),
    )
    assert {r["id"] for r in scoped} == {"chat_a"}


def test_clear_keeps_asset_ref(load_udf, tmp_path, monkeypatch):
    """clear resets the chat but KEEPS the asset ref — type + path stem verbatim."""
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    _create(load_udf, tmp_path, artifact_type="asset", artifact_stem="assets/sales.parquet")
    reset = load_udf("clear", "clear")(chat_id="chat_1", app_dir=str(tmp_path))
    assert reset["messageCount"] == 0
    assert reset["artifactType"] == "asset"
    assert reset["artifactStem"] == "assets/sales.parquet"
