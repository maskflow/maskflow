"""Shared fixtures. Importing maskflow registers every pack's PIIType, so
Mapping.from_json / PIIType.register calls in tests always resolve."""

from collections.abc import Iterator

import maskflow  # noqa: F401  -- import side effect: register recognizers/PIITypes
import pytest
from fastapi.testclient import TestClient
from helpers import ANTHROPIC_BASE, OPENAI_BASE
from maskflow_gateway.app import create_app
from maskflow_gateway.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai_base_url=OPENAI_BASE,
        anthropic_base_url=ANTHROPIC_BASE,
        redis_url=None,
        ner=False,
        json_logs=False,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
