from pathlib import Path

from app.config import load_config

CONFIG = Path(__file__).resolve().parents[1] / "config" / "visidata.yaml"


def test_loads_visidata_config():
    cfg = load_config(CONFIG)
    assert cfg.project.slug == "visidata"
    assert cfg.project.upstream_repo == "saulpw/visidata"
    assert cfg.limits.max_question_chars == 500
    assert cfg.models.answer_order, "at least the main model must be configured"


def test_ingests_only_stable_or_a_release_tag():
    import re

    ref = load_config(CONFIG).project.ref
    assert ref == "stable" or re.fullmatch(r"v\d+(\.\d+)*", ref), ref


def test_ingest_settings_live_in_config():
    cfg = load_config(CONFIG).project
    assert cfg.skip_files == ["README.md"] and cfg.max_piece_chars == 1500


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


def test_vector_index_setting_defaults_to_none_and_rejects_unknown_kinds(tmp_path):
    import pytest
    from pydantic import ValidationError

    assert load_config(CONFIG).search.vector_index == "none"
    text = CONFIG.read_text(encoding="utf-8").replace("vector_index: none", "vector_index: ivfflat")
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)
