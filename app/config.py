import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    skip_files: list[str] = Field(default_factory=lambda: ["README.md"])
    max_piece_chars: int = 1500


class SearchCfg(_Strict):
    top_k: int = 5
    rrf_k: int = 60
    evidence_threshold: float = 0.0
    # "none": exact vector search (fast for thousands of pieces); "hnsw": approximate index for
    # large docs sets. Measured in spike S11: exact is 35 ms at 14k pieces, the index 0.3 ms.
    vector_index: Literal["none", "hnsw"] = "none"


class LimitsCfg(_Strict):
    max_question_chars: int = 500
    max_answer_tokens: int = 400
    # Request cap where hidden thinking counts toward it (gemma with thinking on, gpt-oss).
    max_completion_tokens: int = 3000
    # Request cap for gemma with thinking off: the longest answer in spike S10 was 351 tokens.
    max_completion_tokens_no_thinking: int = 1000
    global_daily_cap: int = 150
    per_visitor_daily_cap: int = 10
    # Cloudflare's free allowance is 10,000 neurons/day; leave room for evals and the fallback.
    global_daily_neurons: float = 8000
    retention_days: int = 30


class ModelsCfg(_Strict):
    embedding: str
    embedding_dim: int
    embedding_batch: int = 20
    answer_order: list[str]
    neurons_per_m_tokens: dict[str, tuple[float, float]] = Field(default_factory=dict)
    # Cloudflare models with a thinking switch: model -> enable_thinking (D17: gemma off).
    thinking: dict[str, bool] = Field(default_factory=dict)
    # Models that do not think: capped at limits.max_answer_tokens, the visible-answer budget.
    non_reasoning: list[str] = Field(default_factory=list)


class ApiCfg(_Strict):
    # Browser origins allowed to call the API (CORS). Not a secret: it is the public site.
    cors_origins: list[str]


class SiteCfg(_Strict):
    """The public chat page. Text lives here, not in code (project specifics are config)."""
    url: str  # where the page is served; the invite link is built from it
    api_base_url: str
    title: str
    brand: str = Field(min_length=1)  # short name shown in the top bar
    greeting: str = Field(min_length=1)  # big line on the welcome screen
    tagline: str = Field(min_length=1)  # one plain sentence for visitors who have never used it
    about_url: str  # "What is ...?" link
    intro_video_url: str | None = None  # optional; the link is left out when unset
    starter_questions: list[str] = Field(min_length=1, max_length=6)
    privacy_notice: str
    # eval question id -> a note shown on /evals for answers that are wrong because of the docs
    known_wrong: dict[str, str] = {}

    @field_validator("about_url", "intro_video_url")
    @classmethod
    def _safe_https_url(cls, v):
        # These go into href attributes: https only, and no character that could break out.
        if v is not None and not (v.startswith("https://") and not re.search(r"[\s\"'<>`\\]", v)):
            raise ValueError("must be an https:// URL without spaces or quote/angle characters")
        return v


class Config(_Strict):
    project: ProjectCfg
    search: SearchCfg = SearchCfg()
    limits: LimitsCfg = LimitsCfg()
    models: ModelsCfg
    api: ApiCfg
    site: SiteCfg


def load_config(path: Path | str) -> Config:
    with open(path, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
