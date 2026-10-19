from pathlib import Path

from app.config import load_config

CONFIG = Path(__file__).resolve().parents[1] / "config" / "visidata.yaml"


def test_loads_visidata_config():
    cfg = load_config(CONFIG)
    assert cfg.project.slug == "visidata"
    assert cfg.project.upstream_repo == "saulpw/visidata"
    assert cfg.limits.max_question_chars == 500
    assert cfg.models.answer_order, "at least the main model must be configured"


def test_never_ingests_develop_branch():
    assert load_config(CONFIG).project.ref != "develop"


def test_pricing_table_values_are_input_output_pairs():
    cfg = load_config(CONFIG)
    for model, (inp, out) in cfg.models.neurons_per_m_tokens.items():
        assert inp > 0 and out > 0, model


def test_misspelled_key_is_an_error_not_silently_ignored(tmp_path):
    import pytest
    from pydantic import ValidationError

    bad = CONFIG.read_text(encoding="utf-8").replace("max_question_chars", "max_question_char")
    path = tmp_path / "bad.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)
