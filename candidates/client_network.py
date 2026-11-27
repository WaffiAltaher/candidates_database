"""Client network (truncated IP) and country lookup for access logging.

The full client address only lives in memory here; callers log the truncated
network, never the address itself.
"""

import ipaddress
import logging
import os
import threading

logger = logging.getLogger(__name__)

DEFAULT_GEOIP_PATH = "/app/geoip/dbip-country-lite.mmdb"

_lock = threading.Lock()
_reader = None
_unavailable = False


def _parse(value: str | None):
    if not value:
        return None
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def client_ip(request) -> str | None:
    """X-Real-IP if present and parseable, else the TCP peer. X-Forwarded-For is ignored."""
    header = request.headers.get("X-Real-IP")
    if header and _parse(header) is not None:
        return header.strip()
    if request.client:
        return request.client.host
    return None


def truncate(ip: str | None) -> str:
    addr = _parse(ip)
    if addr is None:
        return "-"
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))


def _get_reader():
    global _reader, _unavailable
    if _reader is not None or _unavailable:
        return _reader
    with _lock:
        if _reader is None and not _unavailable:
            path = os.environ.get("GEOIP_DB_PATH", DEFAULT_GEOIP_PATH)
            try:
                import maxminddb

                _reader = maxminddb.open_database(path)
            except Exception as exc:
                logger.warning("GeoIP database unavailable (%s): %s", path, exc)
                _unavailable = True
    return _reader


def reset_cache() -> None:
    """Forget the opened database (used by tests)."""
    global _reader, _unavailable
    with _lock:
        _reader = None
        _unavailable = False


def country(ip: str | None) -> str:
    addr = _parse(ip)
    if addr is None:
        return "-"
    reader = _get_reader()
    if reader is None:
        return "-"
    try:
        record = reader.get(str(addr))
        return record["country"]["iso_code"] or "-"
    except Exception:
        return "-"
