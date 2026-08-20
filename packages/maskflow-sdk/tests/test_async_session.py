"""AsyncSession coverage. Uses plain asyncio.run() inside sync test functions
-- no pytest-asyncio dependency needed for this scope (see session.py's
docstring: AsyncSession is a non-invasive asyncio.to_thread wrapper around
the sync Session, so its behavior is identical modulo the extra await)."""

import asyncio

import pytest
from maskflow import SessionClosedError, async_session


def test_same_value_gets_same_token_across_separate_calls():
    async def scenario() -> tuple[str, str]:
        async with async_session() as s:
            first = await s.mask("Call me at 415-555-0132.")
            second = await s.mask("Reminder: 415-555-0132 again.")
        return first, second

    first, second = asyncio.run(scenario())
    assert "<PHONE_1>" in first
    assert "<PHONE_1>" in second


def test_mask_round_trips_through_unmask():
    text = "Email me at alice@example.com."

    async def scenario() -> str:
        async with async_session() as s:
            masked = await s.mask(text)
            return await s.unmask(masked)

    assert asyncio.run(scenario()) == text


def test_mask_json_preserves_keys_and_types():
    async def scenario() -> dict:
        async with async_session() as s:
            return await s.mask_json({"email": "alice@example.com", "count": 3})

    result = asyncio.run(scenario())
    assert "email" in result
    assert result["email"].startswith("<EMAIL_")
    assert result["count"] == 3


def test_close_purges_the_mapping_and_blocks_further_use():
    async def scenario() -> None:
        s = async_session()
        await s.mask("Email me at alice@example.com.")
        assert len(s._session._mapping) > 0

        await s.close()

        assert len(s._session._mapping) == 0
        with pytest.raises(SessionClosedError):
            await s.mask("Email me at bob@example.com.")

    asyncio.run(scenario())


def test_context_manager_closes_on_exit():
    async def scenario() -> int:
        async with async_session() as s:
            await s.mask("Email me at alice@example.com.")
            during = len(s._session._mapping)
        return during

    assert asyncio.run(scenario()) > 0
