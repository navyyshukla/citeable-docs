from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name: str) -> tuple[str, dict]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def triggers(data: dict) -> dict:
    return data.get("on") or data[True]  # YAML reads a bare `on:` key as the boolean True


def test_pages_permissions_are_exactly_the_three_it_needs():
    _, data = load("pages.yml")
    assert data["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}


def test_pages_workflow_reads_no_secrets():
    text, _ = load("pages.yml")
    assert "secrets." not in text


def test_pages_triggers_on_push_to_main_only():
    _, data = load("pages.yml")
    on = triggers(data)
    assert set(on) == {"push"}
    assert on["push"]["branches"] == ["main"]
    assert set(on["push"]["paths"]) >= {"site/**", "config/visidata.yaml",
                                        "scripts/build_site.py"}


def test_pages_builds_the_page_and_deploys_with_the_pages_actions():
    text, _ = load("pages.yml")
    assert "python scripts/build_site.py page --out _site" in text
    assert "site/public" in text
    for action in ("actions/upload-pages-artifact", "actions/deploy-pages"):
        assert action in text


def test_ci_runs_the_site_tests_with_node():
    text, data = load("ci.yml")
    steps = [s for job in data["jobs"].values() for s in job["steps"]]
    assert any(str(s.get("uses", "")).startswith("actions/setup-node") for s in steps)
    # a glob, not the directory form: the directory form fails on current Node (ledger, Task 5)
    assert "node --test site/tests/*.test.js" in text
