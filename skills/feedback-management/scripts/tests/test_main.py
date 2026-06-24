"""Storage-location resolution tests for the feedback-management UDFs.

Covers the precedence contract: explicit ``app_dir`` param > OPENFUSED_APP_DIR_STATE
env var > ~/.openfused/app default — and that reads honor the same param.
"""

from pathlib import Path

PAYLOAD = '{"widget": {}}'


def _cards_file(app_dir) -> Path:
    return Path(app_dir) / "state" / "cards.json"


def test_app_dir_param_honored(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    card = load_udf("create_card", "create_card")(
        project="p", task_id="t", effect="reply", payload=PAYLOAD, app_dir=str(tmp_path)
    )
    assert "id" in card
    assert _cards_file(tmp_path).exists()


def test_env_fallback_when_param_omitted(load_udf, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(tmp_path))
    load_udf("create_card", "create_card")(
        project="p", task_id="t", effect="reply", payload=PAYLOAD
    )
    assert _cards_file(tmp_path).exists()


def test_param_overrides_env(load_udf, tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    param_dir = tmp_path / "param"
    monkeypatch.setenv("OPENFUSED_APP_DIR_STATE", str(env_dir))
    load_udf("create_card", "create_card")(
        project="p", task_id="t", effect="reply", payload=PAYLOAD, app_dir=str(param_dir)
    )
    assert _cards_file(param_dir).exists()
    assert not _cards_file(env_dir).exists()


def test_list_cards_round_trip_honors_app_dir(load_udf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENFUSED_APP_DIR_STATE", raising=False)
    created = load_udf("create_card", "create_card")(
        project="p", task_id="t", effect="reply", payload=PAYLOAD, app_dir=str(tmp_path)
    )
    rows = load_udf("list_cards", "list_cards")(app_dir=str(tmp_path))
    assert any(c["id"] == created["id"] for c in rows)
    assert load_udf("list_cards", "list_cards")(app_dir=str(tmp_path / "other")) == []
