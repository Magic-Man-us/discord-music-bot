"""HTTP StreamProbe: a ranged GET that tells whether a stream URL still authorizes.

SSRF-hardened: the URL originates from yt-dlp resolving user-supplied queries, so the
probe refuses to contact non-public hosts and never follows redirects to an unvetted host.
"""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Final

from ...application.interfaces.stream_probe import StreamProbe
from ...domain.shared.types import HttpHeaders, HttpUrlStr
from ...utils.logging import get_logger

logger = get_logger(__name__)

_PROBE_TIMEOUT_SECONDS: Final[float] = 8.0
_PROBE_RANGE_HEADER: Final[str] = "bytes=0-1"
_HTTP_CLIENT_ERROR_FLOOR: Final[int] = 400
_LOG_URL_TRUNCATE: Final[int] = 80
_DEFAULT_HTTPS_PORT: Final[int] = 443
_DEFAULT_HTTP_PORT: Final[int] = 80


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a public URL can't bounce the probe to an internal host."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: http.client.HTTPResponse,
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


_OPENER: Final = urllib.request.build_opener(_NoRedirectHandler())


def _host_is_public(url: str) -> bool:
    """Reject embedded credentials and any host resolving to a private/reserved IP."""
    parts = urllib.parse.urlsplit(url)
    if "@" in (parts.netloc or ""):
        return False
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return False
    port = parts.port or (_DEFAULT_HTTPS_PORT if parts.scheme == "https" else _DEFAULT_HTTP_PORT)
    try:
        addrinfos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    if not addrinfos:
        return False
    for addrinfo in addrinfos:
        try:
            address = ipaddress.ip_address(addrinfo[4][0])
        except ValueError:
            return False
        if not address.is_global:
            return False
    return True


class HttpStreamProbe(StreamProbe):
    async def is_playable(self, url: HttpUrlStr, headers: HttpHeaders | None = None) -> bool:
        return await asyncio.to_thread(self._probe_sync, url, headers)

    def _probe_sync(self, url: HttpUrlStr, headers: HttpHeaders | None) -> bool:
        if not _host_is_public(url):
            logger.warning("Stream probe blocked non-public host: %s", url[:_LOG_URL_TRUNCATE])
            return False
        request = urllib.request.Request(url, method="GET")
        request.add_header("Range", _PROBE_RANGE_HEADER)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with _OPENER.open(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
                return response.status < _HTTP_CLIENT_ERROR_FLOOR
        except urllib.error.HTTPError as error:
            # A 3xx is returned (not followed) — the URL still authorized, so treat it as ok.
            logger.debug("Stream probe %s -> HTTP %s", url[:_LOG_URL_TRUNCATE], error.code)
            return error.code < _HTTP_CLIENT_ERROR_FLOOR
        except Exception:
            logger.debug("Stream probe failed to reach %s", url[:_LOG_URL_TRUNCATE])
            return False
