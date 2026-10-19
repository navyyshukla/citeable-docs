from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Unknown or misspelled keys are an error, never silently ignored."""

    model_config = ConfigDict(extra="forbid")


class ProjectCfg(_Strict):
    name: str
    slug: str
    upstream_repo: str
    ref: str
    docs_path: str
    site_base_url: str
    license_note: str
    issues_url: str


class SearchCfg(_Strict):
    top_k: int = 5
    rrf_k: int = 60
    evidence_threshold: float = 0.0


class LimitsCfg(_Strict):
    max_question_chars: int = 500
    max_answer_tokens: int = 400
    max_completion_tokens: int = 3000
    global_daily_cap: int = 150
    per_visitor_daily_cap: int = 10


class ModelsCfg(_Strict):
    embedding: str
    embedding_dim: int
    embedding_batch: int = 20
    answer_order: list[str]
    neurons_per_m_tokens: dict[str, tuple[float, float]] = Field(default_factory=dict)


class Config(_Strict):
    project: ProjectCfg
    search: SearchCfg = SearchCfg()
    limits: LimitsCfg = LimitsCfg()
    models: ModelsCfg


def load_config(path: Path | str) -> Config:
    with open(path, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
