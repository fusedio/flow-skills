"""Storage-location resolution tests for the task-management UDFs.

Covers the precedence contract: explicit ``app_dir`` param > OPENFUSED_APP_DIR_STATE
env var > ~/.openfused/app default — and that reads honor the same param.
"""

from pathlib import Path


def _tasks_file(app_dir) -> Path:
    return Path(app_dir) / "state" / "tasks.json"


def test_app_dir_param_honored(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    create = load_udf("create", "create")
    task = create(project="p", title="t", app_dir=str(tmp_path))
    assert "id" in task
    assert _tasks_file(tmp_path).exists()


def test_env_fallback_when_param_omitted(load_udf, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(tmp_path))
    create = load_udf("create", "create")
    create(project="p", title="t")
    assert _tasks_file(tmp_path).exists()


def test_param_overrides_env(load_udf, tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    param_dir = tmp_path / "param"
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(env_dir))
    create = load_udf("create", "create")
    create(project="p", title="t", app_dir=str(param_dir))
    assert _tasks_file(param_dir).exists()
    assert not _tasks_file(env_dir).exists()


def test_read_round_trip_honors_app_dir(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    created = load_udf("create", "create")(project="p", title="t", app_dir=str(tmp_path))
    rows = load_udf("read", "read")(app_dir=str(tmp_path))
    assert any(r["id"] == created["id"] for r in rows)
    # a different, empty store sees nothing
    assert load_udf("read", "read")(app_dir=str(tmp_path / "other")) == []


# --- delete_project --------------------------------------------------------


def test_delete_project_removes_only_named_project(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    create = load_udf("create", "create")
    add_comment = load_udf("add_comment", "add_comment")

    a1 = create(project="alpha", title="a1", app_dir=str(tmp_path))
    a2 = create(project="alpha", title="a2", app_dir=str(tmp_path))
    b1 = create(project="beta", title="b1", app_dir=str(tmp_path))
    add_comment(task_id=a1["id"], author="u", body="on a1", app_dir=str(tmp_path))
    add_comment(task_id=b1["id"], author="u", body="on b1", app_dir=str(tmp_path))

    ack = load_udf("delete_project", "delete_project")(project="alpha", app_dir=str(tmp_path))

    # only alpha's tasks deleted (sorted ids), one comment removed (a1's)
    assert ack == {
        "deletedTaskIds": sorted([a1["id"], a2["id"]]),
        "tasksRemoved": 2,
        "commentsRemoved": 1,
    }

    # beta's task survives; alpha's are gone
    remaining_ids = {t["id"] for t in load_udf("read", "read")(app_dir=str(tmp_path))}
    assert remaining_ids == {b1["id"]}

    # b1's comment stays, a1's is gone
    b1_comments = load_udf("list_comments", "list_comments")(task_id=b1["id"], app_dir=str(tmp_path))
    assert [c["body"] for c in b1_comments] == ["on b1"]
    assert load_udf("list_comments", "list_comments")(task_id=a1["id"], app_dir=str(tmp_path)) == []


def test_delete_project_idempotent_rerun_and_empty(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    create = load_udf("create", "create")
    delete_project = load_udf("delete_project", "delete_project")

    keep = create(project="beta", title="b1", app_dir=str(tmp_path))
    only = create(project="alpha", title="a1", app_dir=str(tmp_path))

    first = delete_project(project="alpha", app_dir=str(tmp_path))
    assert first == {"deletedTaskIds": [only["id"]], "tasksRemoved": 1, "commentsRemoved": 0}

    # re-running on the now-empty project is a zero-count no-op
    second = delete_project(project="alpha", app_dir=str(tmp_path))
    assert second == {"deletedTaskIds": [], "tasksRemoved": 0, "commentsRemoved": 0}

    # an empty/whitespace project deletes nothing (never touches other projects)
    assert delete_project(project="", app_dir=str(tmp_path)) == {
        "deletedTaskIds": [],
        "tasksRemoved": 0,
        "commentsRemoved": 0,
    }
    assert delete_project(project="   ", app_dir=str(tmp_path)) == {
        "deletedTaskIds": [],
        "tasksRemoved": 0,
        "commentsRemoved": 0,
    }

    # beta untouched throughout
    assert {t["id"] for t in load_udf("read", "read")(app_dir=str(tmp_path))} == {keep["id"]}
