from pathlib import Path

import pytest

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


def test_api_and_retention_settings_live_in_config():
    cfg = load_config(CONFIG)
    assert cfg.api.cors_origins, "the allowlist must not be empty"
    assert cfg.limits.global_daily_neurons == 8000
    assert cfg.limits.retention_days == 30


def test_production_cors_list_has_only_https_origins():
    assert all(o.startswith("https://") for o in load_config(CONFIG).api.cors_origins)


def _variant(tmp_path, change):
    import yaml

    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "variant.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_site_section_is_required_and_strict(tmp_path):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d.pop("site", None)))
    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d["site"].update(surprise="x")))
    assert load_config(CONFIG).site.title  # the shipped file has the section


@pytest.mark.parametrize("count", [0, 7])
def test_starter_questions_need_one_to_six(tmp_path, count):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d["site"].update(
            starter_questions=[f"q{i}?" for i in range(count)])))


def test_starter_questions_one_and_six_are_accepted(tmp_path):
    for count in (1, 6):
        cfg = load_config(_variant(tmp_path, lambda d: d["site"].update(
            starter_questions=[f"q{i}?" for i in range(count)])))
        assert len(cfg.site.starter_questions) == count


def test_privacy_notice_names_the_providers_and_retention():
    cfg = load_config(CONFIG)
    for word in ("Cloudflare", "Groq", "Render", "Neon", str(cfg.limits.retention_days)):
        assert word in cfg.site.privacy_notice, word


def test_site_urls_are_https_and_the_known_wrong_ids_are_listed():
    cfg = load_config(CONFIG)
    assert cfg.site.url.startswith("https://") and cfg.site.api_base_url.startswith("https://")
    assert set(cfg.site.known_wrong) == {"d-001", "k-004"}


@pytest.mark.parametrize("key", ["brand", "greeting", "tagline", "about_url"])
def test_new_site_keys_are_required_and_non_empty(tmp_path, key):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d["site"].pop(key)))
    if key != "about_url":
        with pytest.raises(ValidationError):
            load_config(_variant(tmp_path, lambda d: d["site"].update({key: ""})))


@pytest.mark.parametrize("key", ["about_url", "intro_video_url", "getting_started_url"])
@pytest.mark.parametrize("bad", ["javascript:alert(1)", "http://x.example",
                                 "https://x.example/a b", 'https://x.example/"onclick='])
def test_site_urls_must_be_https_without_unsafe_characters(tmp_path, key, bad):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d["site"].update({key: bad})))


def test_intro_video_url_is_optional(tmp_path):
    cfg = load_config(_variant(tmp_path, lambda d: d["site"].pop("intro_video_url", None)))
    assert cfg.site.intro_video_url is None  # leaving it out is allowed
    assert load_config(CONFIG).site.intro_video_url.startswith("https://")  # the shipped file sets it
    cfg = load_config(_variant(tmp_path, lambda d: d["site"].update(
        intro_video_url="https://video.example/watch")))
    assert cfg.site.intro_video_url == "https://video.example/watch"


def test_intro_key_is_gone(tmp_path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(_variant(tmp_path, lambda d: d["site"].update(intro="old text")))


def test_getting_started_url_is_optional_and_shipped():
    assert load_config(CONFIG).site.getting_started_url == "https://www.visidata.org/docs/"
