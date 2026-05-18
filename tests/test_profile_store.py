import json

import pytest

from app.core.config import AppConfig
from app.core.profile_store import ProfileStore


def test_profile_store_saves_lists_loads_switches_and_deletes_profiles_without_api_keys(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    config = AppConfig(
        api={"api_key": "sk-secret-material", "api_key_source": "env:OPENAI_API_KEY"},
        input={"mode": "generate"},
        image={"n": 2, "size": "1024x1024"},
        prompt={"template": "Generate {index}"},
        execution={"concurrency": 3},
    )

    saved_path = store.save("studio-large", config)

    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert payload["api"]["api_key_source"] == "env:OPENAI_API_KEY"
    assert "api_key" not in payload["api"]
    assert "sk-secret" not in saved_path.read_text(encoding="utf-8")
    assert store.list_profiles() == ["studio-large"]

    loaded = store.load("studio-large")
    assert loaded.prompt.template == "Generate {index}"
    assert loaded.image.n == 2
    assert loaded.execution.concurrency == 3
    assert loaded.api.api_key is None

    store.switch("studio-large")
    assert store.active_profile() == "studio-large"
    assert store.load_active().image.size == "1024x1024"

    assert store.delete("studio-large") is True
    assert store.list_profiles() == []
    assert store.active_profile() is None


@pytest.mark.parametrize(
    "name",
    ["../escape", "with space", ".hidden", "CON", "bad/name", "bad\\name", ""],
)
def test_profile_store_rejects_unsafe_profile_names(tmp_path, name):
    store = ProfileStore(tmp_path / "profiles")

    with pytest.raises(ValueError, match="profile name"):
        store.save(name, AppConfig())
