"""Tests for TorBox check_cached method."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.providers.torbox.client import TorBoxClient


def _mock_transport(
    responses: list[httpx.Response],
) -> httpx.MockTransport:
    """Return a transport that yields responses in order."""
    call_index = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_index
        response = responses[call_index]
        call_index += 1
        return response

    return httpx.MockTransport(handler)


def _cached_response(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "data": data},
    )


class TestCheckCached:
    @pytest.mark.asyncio
    async def test_empty_hashes_returns_empty_dict(self) -> None:
        transport = _mock_transport([])
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_single_cached_hash(self) -> None:
        transport = _mock_transport(
            [
                _cached_response({"abc123": {"name": "Some Torrent", "size": 1000}}),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["abc123"])
        assert result == {"abc123": True}

    @pytest.mark.asyncio
    async def test_uncached_hash_null_value(self) -> None:
        transport = _mock_transport(
            [
                _cached_response({"abc123": None}),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["abc123"])
        assert result == {"abc123": False}

    @pytest.mark.asyncio
    async def test_uncached_hash_missing_from_data(self) -> None:
        transport = _mock_transport(
            [
                _cached_response({}),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["abc123"])
        assert result == {"abc123": False}

    @pytest.mark.asyncio
    async def test_mixed_cached_uncached(self) -> None:
        transport = _mock_transport(
            [
                _cached_response(
                    {
                        "hash1": {"name": "Cached Torrent"},
                        "hash2": None,
                        "hash3": {"name": "Also Cached"},
                    }
                ),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["hash1", "hash2", "hash3"])
        assert result == {"hash1": True, "hash2": False, "hash3": True}

    @pytest.mark.asyncio
    async def test_batches_over_100_hashes(self) -> None:
        hashes = [f"hash{i}" for i in range(150)]
        batch1_data = {h: {"name": "cached"} for h in hashes[:100]}
        batch2_data = dict.fromkeys(hashes[100:], None)
        transport = _mock_transport(
            [
                _cached_response(batch1_data),
                _cached_response(batch2_data),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(hashes)
        assert len(result) == 150
        assert all(result[h] is True for h in hashes[:100])
        assert all(result[h] is False for h in hashes[100:])

    @pytest.mark.asyncio
    async def test_api_error_marks_batch_uncached(self) -> None:
        transport = _mock_transport(
            [
                httpx.Response(500, json={"success": False, "error": "Server error"}),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["hash1", "hash2"])
        assert result == {"hash1": False, "hash2": False}

    @pytest.mark.asyncio
    async def test_non_dict_data_marks_uncached(self) -> None:
        transport = _mock_transport(
            [
                httpx.Response(200, json={"success": True, "data": []}),
            ]
        )
        async with TorBoxClient(api_key="test", transport=transport) as client:
            result = await client.check_cached(["hash1"])
        assert result == {"hash1": False}
