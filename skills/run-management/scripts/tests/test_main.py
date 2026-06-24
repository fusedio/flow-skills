"""Storage-location resolution tests for the run-management UDFs.

Covers the precedence contract: explicit ``app_dir`` param > OPENFUSED_APP_DIR_STATE
env var > ~/.openfused/app default — for both the state file and run transcripts.
"""

import json
from pathlib import Path


def _runs_file(app_dir) -> Path:
    return Path(app_dir) / "state" / "runs.json"


def test_app_dir_param_honored(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    run = load_udf("create", "create")(id="run_1", task_id="t", prompt="p", app_dir=str(tmp_path))
    assert run.get("id") == "run_1"
    assert _runs_file(tmp_path).exists()


def test_env_fallback_when_param_omitted(load_udf, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(tmp_path))
    load_udf("create", "create")(id="run_1", task_id="t", prompt="p")
    assert _runs_file(tmp_path).exists()


def test_param_overrides_env(load_udf, tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    param_dir = tmp_path / "param"
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(env_dir))
    load_udf("create", "create")(id="run_1", task_id="t", prompt="p", app_dir=str(param_dir))
    assert _runs_file(param_dir).exists()
    assert not _runs_file(env_dir).exists()


def test_transcript_path_honors_app_dir(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    runs = json.dumps([{"id": "run_x", "taskId": "t", "status": "completed"}])
    transcripts = json.dumps({"run_x": [{"type": "msg", "text": "hi"}]})
    load_udf("bulk_seed", "bulk_seed")(runs=runs, transcripts=transcripts, app_dir=str(tmp_path))
    # transcript lands under <app_dir>/runs/, read back via the same param
    assert (tmp_path / "runs" / "run_x.ndjson").exists()
    events = load_udf("transcript", "transcript")(run_id="run_x", app_dir=str(tmp_path))
    assert events == [{"type": "msg", "text": "hi"}]
    # a different store sees no transcript
    assert load_udf("transcript", "transcript")(run_id="run_x", app_dir=str(tmp_path / "other")) == []
