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
