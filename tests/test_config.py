from pathlib import Path

import pytest
import yaml

from yonetmelik_asistani.config import CONFIG_DIR, LLMConfig, load_config


def test_default_config_loads_plan_values():
    cfg = load_config(env={})
    assert cfg.llm.model == "qwen3.5:9b"
    assert cfg.llm.think is False
    assert cfg.llm.num_ctx == 8192
    assert cfg.section("retrieval")["rrf_k"] == 60


def test_local_override_and_env_precedence(tmp_path: Path):
    (tmp_path / "default.yaml").write_text(
        (CONFIG_DIR / "default.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "local.yaml").write_text(
        yaml.safe_dump({"llm": {"model": "gemma4:e4b", "temperature": 0.0}}), encoding="utf-8"
    )
    cfg = load_config(tmp_path, env={"YA_LLM_BASE_URL": "http://gpu:11434"})
    assert cfg.llm.model == "gemma4:e4b"          # local.yaml
    assert cfg.llm.temperature == 0.0
    assert cfg.llm.num_ctx == 8192                # default.yaml'dan korunur
    assert cfg.llm.base_url == "http://gpu:11434"  # ortam değişkeni en son


def test_data_dir_from_env(tmp_path: Path):
    cfg = load_config(env={"YA_DATA_DIR": str(tmp_path)})
    assert cfg.data_dir == tmp_path


def test_invalid_backend_rejected():
    with pytest.raises(ValueError):
        LLMConfig(backend="bilinmeyen")


def test_manifest_is_valid_yaml_with_unique_ids():
    data = yaml.safe_load((CONFIG_DIR / "corpus_manifest.yaml").read_text(encoding="utf-8"))
    ids = [b["id"] for b in data["belgeler"]] + [k["id"] for k in data["kaldirilmis"]]
    assert len(ids) == len(set(ids))
    known = {b["id"] for b in data["belgeler"]}
    assert all(k["yonlendir"] in known for k in data["kaldirilmis"])
