from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from fpl_agent.source_policy import SourcePolicy, load_source_policy

ROOT = Path(__file__).resolve().parents[1]


def test_source_policy_tracks_current_disabled_and_expired_reviews():
    policy = load_source_policy(ROOT / "examples/research-sources.yaml")
    current = policy.evaluate(date(2026, 9, 12))
    assert current[0].current is True
    assert current[0].reason == "current"
    assert current[1].current is False
    assert current[1].reason == "disabled"
    assert policy.current_domains(date(2026, 9, 12)) == ["news.example.invalid"]

    expired = policy.evaluate(date(2027, 9, 12))
    assert expired[0].current is False
    assert expired[0].reason == "review_expired"


def test_source_policy_rejects_urls_and_duplicate_domains():
    with pytest.raises(ValidationError, match="bare hostname"):
        SourcePolicy.model_validate(
            {
                "sources": [
                    {
                        "name": "Bad source",
                        "domain": "https://news.example.invalid/path",
                        "terms_url": "https://news.example.invalid/terms",
                        "reviewed_at": "2026-09-11",
                        "purpose": "Test validation.",
                    }
                ]
            }
        )

    source = {
        "name": "Repeated source",
        "domain": "news.example.invalid",
        "terms_url": "https://news.example.invalid/terms",
        "reviewed_at": "2026-09-11",
        "purpose": "Test uniqueness.",
    }
    with pytest.raises(ValidationError, match="unique"):
        SourcePolicy.model_validate({"sources": [source, source]})


def test_source_policy_rejects_future_review_at_evaluation_time():
    policy = load_source_policy(ROOT / "examples/research-sources.yaml")
    status = policy.evaluate(date(2026, 1, 1))[0]
    assert status.current is False
    assert status.reason == "review_in_future"


def test_source_policy_blocks_automated_fpl_game_domains():
    with pytest.raises(ValidationError, match="blocked"):
        SourcePolicy.model_validate(
            {
                "sources": [
                    {
                        "name": "FPL game",
                        "domain": "fantasy.premierleague.com",
                        "terms_url": "https://fantasy.premierleague.com/help/terms",
                        "reviewed_at": "2026-09-11",
                        "purpose": "This must remain outside automation.",
                    }
                ]
            }
        )
