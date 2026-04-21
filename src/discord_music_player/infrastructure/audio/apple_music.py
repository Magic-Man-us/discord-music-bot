"""Apple Music catalog client backed by the public ``amp-api`` endpoint.

Apple Music playlist / album pages are entirely client-rendered, so HTML
scraping yields nothing useful. The web player does obtain an anonymous
bearer token (JWT, ~6-month TTL) from its JS bundle and uses it to call
``amp-api.music.apple.com``. We replay the same dance: scrape the token
once, cache it, and talk to the public catalog endpoint.

This intentionally does **not** require an Apple Developer account.
"""

from __future__ import annotations

import asyncio
import re
import time
import urllib.error
import urllib.request
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ...domain.shared.types import NonEmptyStr
from ...utils.logging import get_logger

logger = get_logger(__name__)


class AppleResourceType(StrEnum):
    PLAYLIST = "playlists"
    ALBUM = "albums"
    SONG = "songs"


_AMP_API_BASE = "https://amp-api.music.apple.com/v1/catalog"
_APPLE_MUSIC_BASE = "https://music.apple.com"
_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

_BOUNDARY_CONFIG = ConfigDict(frozen=True, extra="ignore")

_INDEX_JS_PATTERN = re.compile(r"/assets/(index~[a-f0-9]+\.js)")
_JWT_PATTERN = re.compile(r"eyJhbGci[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

_PLAYLIST_URL = re.compile(
    r"^https?://music\.apple\.com/([a-z]{2})/playlist/[^/]+/(pl\.[A-Za-z0-9_.-]+)"
)
_ALBUM_URL = re.compile(r"^https?://music\.apple\.com/([a-z]{2})/album/[^/]+/(\d+)")
_SONG_URL = re.compile(r"^https?://music\.apple\.com/([a-z]{2})/song/[^/]+/(\d+)")
_TRACK_QUERY = re.compile(r"[?&]i=(\d+)")


class AppleMusicResource(BaseModel):
    model_config = ConfigDict(frozen=True)

    resource_type: AppleResourceType
    country: str
    resource_id: str


class AppleMusicError(RuntimeError):
    pass


class _TrackAttributes(BaseModel):
    model_config = _BOUNDARY_CONFIG

    name: NonEmptyStr
    # Only song rows carry ``artistName``; the root playlist/album resource
    # has ``name`` alone. Shared model, so keep it optional.
    artistName: NonEmptyStr | None = None


class _TracksRelation(BaseModel):
    model_config = _BOUNDARY_CONFIG

    data: list[_Resource] = []


class _Relationships(BaseModel):
    model_config = _BOUNDARY_CONFIG

    tracks: _TracksRelation | None = None


class _Resource(BaseModel):
    model_config = _BOUNDARY_CONFIG

    id: str
    type: str
    attributes: _TrackAttributes | None = None
    relationships: _Relationships | None = None


class _CatalogResponse(BaseModel):
    model_config = _BOUNDARY_CONFIG

    data: list[_Resource] = []


_Resource.model_rebuild()
_Relationships.model_rebuild()
_TracksRelation.model_rebuild()


class AppleMusicPlaylist(BaseModel):
    """Result of fetching an Apple Music playlist/album/song."""

    model_config = ConfigDict(frozen=True)

    queries: list[NonEmptyStr]
    name: NonEmptyStr | None = None


def parse_apple_music_url(url: str) -> AppleMusicResource | None:
    """``/album/<name>/<id>?i=<track>`` is treated as a song lookup because
    that's the row the UI highlights."""
    if (m := _PLAYLIST_URL.match(url)) is not None:
        return AppleMusicResource(
            resource_type=AppleResourceType.PLAYLIST,
            country=m.group(1),
            resource_id=m.group(2),
        )

    if (m := _ALBUM_URL.match(url)) is not None:
        track_match = _TRACK_QUERY.search(url)
        if track_match is not None:
            return AppleMusicResource(
                resource_type=AppleResourceType.SONG,
                country=m.group(1),
                resource_id=track_match.group(1),
            )
        return AppleMusicResource(
            resource_type=AppleResourceType.ALBUM,
            country=m.group(1),
            resource_id=m.group(2),
        )

    if (m := _SONG_URL.match(url)) is not None:
        return AppleMusicResource(
            resource_type=AppleResourceType.SONG,
            country=m.group(1),
            resource_id=m.group(2),
        )

    return None


class AppleMusicClient:
    """Token fetch and refresh are serialized through an asyncio lock so
    concurrent callers never stampede the scrape."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_playlist(self, url: str) -> AppleMusicPlaylist:
        """Fetch the playlist/album/song as search queries + playlist name.

        Empty ``queries`` is a valid response (empty playlist). Raises
        ``AppleMusicError`` on unknown URLs or API failures.
        """
        resource = parse_apple_music_url(url)
        if resource is None:
            raise AppleMusicError(f"Not an Apple Music URL: {url}")

        data = await self._fetch_catalog(resource)
        queries = self._extract_queries(resource.resource_type, data)
        name = self._extract_root_name(data)
        return AppleMusicPlaylist(queries=queries, name=name)

    @staticmethod
    def _extract_root_name(catalog: _CatalogResponse) -> str | None:
        if not catalog.data:
            return None
        attrs = catalog.data[0].attributes
        return attrs.name if attrs is not None else None

    async def _fetch_catalog(self, resource: AppleMusicResource) -> _CatalogResponse:
        is_song = resource.resource_type is AppleResourceType.SONG
        include = "?l=en-US" if is_song else "?include=tracks&l=en-US"
        target = (
            f"{_AMP_API_BASE}/{resource.country}/{resource.resource_type.value}/"
            f"{resource.resource_id}{include}"
        )

        token = await self._get_token(force_refresh=False)
        try:
            body = await asyncio.to_thread(self._http_get, target, token)
        except _UnauthorizedError:
            logger.info("Apple Music token rejected — refreshing")
            token = await self._get_token(force_refresh=True)
            body = await asyncio.to_thread(self._http_get, target, token)

        return _CatalogResponse.model_validate_json(body)

    @staticmethod
    def _extract_queries(
        resource_type: AppleResourceType, catalog: _CatalogResponse
    ) -> list[str]:
        if not catalog.data:
            return []

        root = catalog.data[0]

        if resource_type is AppleResourceType.SONG:
            if root.attributes is None or root.attributes.artistName is None:
                return []
            return [f"{root.attributes.artistName} - {root.attributes.name}"]

        if root.relationships is None or root.relationships.tracks is None:
            return []

        queries: list[str] = []
        for track in root.relationships.tracks.data:
            attrs = track.attributes
            if attrs is None or attrs.artistName is None:
                continue
            queries.append(f"{attrs.artistName} - {attrs.name}")
        return queries

    async def _get_token(self, *, force_refresh: bool) -> str:
        async with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._token is not None
                and now - self._token_fetched_at < _TOKEN_TTL_SECONDS
            ):
                return self._token

            token = await asyncio.to_thread(self._scrape_token)
            self._token = token
            self._token_fetched_at = now
            logger.info("Refreshed Apple Music anonymous bearer token")
            return token

    @staticmethod
    def _scrape_token() -> str:
        try:
            html = _read(_APPLE_MUSIC_BASE + "/us/browse", limit=500_000)
        except Exception as exc:
            raise AppleMusicError(f"Failed to fetch Apple Music page: {exc}") from exc

        js_match = _INDEX_JS_PATTERN.search(html)
        if js_match is None:
            raise AppleMusicError("Could not locate Apple Music JS bundle URL")

        js_url = f"{_APPLE_MUSIC_BASE}/assets/{js_match.group(1)}"
        try:
            js = _read(js_url, limit=5_000_000)
        except Exception as exc:
            raise AppleMusicError(f"Failed to fetch Apple Music JS bundle: {exc}") from exc

        jwt_match = _JWT_PATTERN.search(js)
        if jwt_match is None:
            raise AppleMusicError("Could not extract bearer token from Apple Music JS")

        return jwt_match.group(0)

    @staticmethod
    def _http_get(url: str, token: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": _APPLE_MUSIC_BASE,
                "Referer": _APPLE_MUSIC_BASE + "/",
                "User-Agent": _USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _UnauthorizedError() from exc
            raise AppleMusicError(f"amp-api error {exc.code}: {exc.reason}") from exc
        except Exception as exc:
            raise AppleMusicError(f"amp-api request failed: {exc}") from exc


class _UnauthorizedError(Exception):
    pass


def _read(url: str, *, limit: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(limit).decode("utf-8", errors="replace")
