"""Token-refresh coalesce behavior for AppleMusicClient."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from discord_music_player.infrastructure.audio.apple_music import (
    AppleMusicClient,
    AppleResourceType,
    _CatalogResponse,
)


class TestTokenRefreshCoalesce:
    @pytest.mark.asyncio
    async def test_force_refresh_reuses_fresh_peer_token(self) -> None:
        """Two concurrent 401-retry paths must only scrape once."""
        client = AppleMusicClient()
        scrape_calls = 0

        def fake_scrape() -> str:
            nonlocal scrape_calls
            scrape_calls += 1
            return f"token-{scrape_calls}"

        with patch.object(AppleMusicClient, "_scrape_token", staticmethod(fake_scrape)):
            # Prime a cached token, then simulate it aging past the grace
            # window (i.e. genuinely expired server-side, 401 returned).
            first = await client._get_token(force_refresh=False)
            assert first == "token-1"
            assert scrape_calls == 1
            client._token_fetched_at = time.monotonic() - 3600

            # Two concurrent force-refreshes from racing 401 handlers.
            a, b = await asyncio.gather(
                client._get_token(force_refresh=True),
                client._get_token(force_refresh=True),
            )

            # Lock serialises them: the first acquirer scrapes, the second
            # sees a newly-written token < grace seconds old and reuses it.
            assert scrape_calls == 2
            assert a == b == "token-2"

    @pytest.mark.asyncio
    async def test_force_refresh_scrapes_when_token_is_stale(self) -> None:
        """A forced refresh after the grace window elapsed must scrape again."""
        client = AppleMusicClient()
        scrape_calls = 0

        def fake_scrape() -> str:
            nonlocal scrape_calls
            scrape_calls += 1
            return f"token-{scrape_calls}"

        with patch.object(AppleMusicClient, "_scrape_token", staticmethod(fake_scrape)):
            await client._get_token(force_refresh=False)
            # Backdate the cache so the grace window no longer applies.
            client._token_fetched_at = time.monotonic() - 3600
            await client._get_token(force_refresh=True)

        assert scrape_calls == 2

    @pytest.mark.asyncio
    async def test_cache_hit_skips_scrape(self) -> None:
        client = AppleMusicClient()
        scrape_calls = 0

        def fake_scrape() -> str:
            nonlocal scrape_calls
            scrape_calls += 1
            return "token"

        with patch.object(AppleMusicClient, "_scrape_token", staticmethod(fake_scrape)):
            a = await client._get_token(force_refresh=False)
            b = await client._get_token(force_refresh=False)

        assert scrape_calls == 1
        assert a == b


class TestExtractQueriesSongFilter:
    """Albums commonly include music-videos alongside songs in tracks.data;
    the queue should only get the audio rows."""

    def test_skips_music_videos(self) -> None:
        catalog = _CatalogResponse.model_validate(
            {
                "data": [
                    {
                        "id": "1234567890",
                        "type": "albums",
                        "attributes": {"name": "Test Album"},
                        "relationships": {
                            "tracks": {
                                "data": [
                                    {
                                        "id": "1",
                                        "type": "songs",
                                        "attributes": {
                                            "name": "Track One",
                                            "artistName": "Artist A",
                                        },
                                    },
                                    {
                                        "id": "2",
                                        "type": "music-videos",
                                        "attributes": {
                                            "name": "Bonus Video",
                                            "artistName": "Artist A",
                                        },
                                    },
                                    {
                                        "id": "3",
                                        "type": "songs",
                                        "attributes": {
                                            "name": "Track Two",
                                            "artistName": "Artist A",
                                        },
                                    },
                                ]
                            }
                        },
                    }
                ]
            }
        )

        queries = AppleMusicClient._extract_queries(AppleResourceType.ALBUM, catalog)

        assert queries == ["Artist A - Track One", "Artist A - Track Two"]
