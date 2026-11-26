"""Security utilities for the consulting-agent backend.

SSRF Protection
---------------
Any user-supplied URL that the backend might fetch (web research, webhook
callbacks, file imports, …) MUST be validated with :func:`validate_url`
**before** an outbound HTTP request is made.

Blocked address ranges
~~~~~~~~~~~~~~~~~~~~~~
* Loopback  : ``127.0.0.0/8``, ``::1``
* Private   : ``10.0.0.0/8``, ``172.16.0.0/12``, ``192.168.0.0/16``
* Link-local: ``169.254.0.0/16`` (includes AWS/GCP/Azure metadata)
* ULA IPv6  : ``fc00::/7``
* Multicast : ``224.0.0.0/4``, ``ff00::/8``
* Unspecified / loopback IPv6 : ``::`` / ``::1``

The check is performed both on the literal IP address (if the hostname *is*
an IP) **and** on the resolved address(es) so that DNS-rebinding attacks are
mitigated.

.. warning::
   DNS-rebinding attacks can still succeed if the DNS TTL expires between
   validation and the actual request.  For highest security, perform the
   resolution yourself and pass the resolved IP directly in the request
   (using the ``Host`` header to preserve the original hostname), or use a
   network-level egress firewall.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Private blocked networks
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 private / special-purpose
    ipaddress.ip_network("0.0.0.0/8"),           # "This" network
    ipaddress.ip_network("10.0.0.0/8"),           # Class A private
    ipaddress.ip_network("100.64.0.0/10"),        # Shared address space (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),          # Loopback
    ipaddress.ip_network("169.254.0.0/16"),       # Link-local / metadata
    ipaddress.ip_network("172.16.0.0/12"),        # Class B private
    ipaddress.ip_network("192.0.0.0/24"),         # IETF Protocol Assignments
    ipaddress.ip_network("192.168.0.0/16"),       # Class C private
    ipaddress.ip_network("198.18.0.0/15"),        # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),      # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),       # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("224.0.0.0/4"),          # Multicast
    ipaddress.ip_network("240.0.0.0/4"),          # Reserved
    ipaddress.ip_network("255.255.255.255/32"),   # Broadcast
    # IPv6 private / special-purpose
    ipaddress.ip_network("::1/128"),              # Loopback
    ipaddress.ip_network("::/128"),               # Unspecified
    ipaddress.ip_network("fc00::/7"),             # ULA
    ipaddress.ip_network("fe80::/10"),            # Link-local
    ipaddress.ip_network("ff00::/8"),             # Multicast
    ipaddress.ip_network("::ffff:0:0/96"),        # IPv4-mapped
    ipaddress.ip_network("64:ff9b::/96"),         # IPv4-IPv6 translation
    ipaddress.ip_network("100::/64"),             # Discard prefix
]

# Well-known cloud metadata endpoint – belt-and-suspenders in case the
# network range check is somehow bypassed.
_METADATA_LITERAL_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",   # AWS / GCP / Azure IMDS
        "fd00:ec2::254",     # AWS IMDSv2 IPv6
        "metadata.google.internal",
    }
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _is_blocked_ip(addr: str) -> bool:
    """Return ``True`` if *addr* falls within any blocked network or is a
    known metadata IP literal."""
    if addr in _METADATA_LITERAL_IPS:
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Not a valid IP string – handled separately via DNS resolution.
        return False

    return any(ip in net for net in _BLOCKED_NETWORKS)


def _resolve_and_check(hostname: str) -> bool:
    """Resolve *hostname* to its IP addresses and return ``True`` if **all**
    resolved addresses are safe (i.e. NOT blocked).

    Returns ``False`` (== blocked) when:
    * DNS resolution fails (treat unknown hosts as unsafe).
    * Any resolved address falls within a blocked network.
    """
    try:
        results = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Cannot resolve – block to be safe.
        return False

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_safe_url(url: str) -> bool:
    """Return ``True`` only if *url* is safe to fetch (no SSRF risk).

    Checks performed
    ~~~~~~~~~~~~~~~~
    1. The URL must parse correctly and use ``http`` or ``https``.
    2. The host must not be an empty string.
    3. If the host is an IP literal it must not fall in a blocked range.
    4. If the host is a hostname it is resolved; every returned address must
       be non-blocked (a single blocked address causes rejection).
    5. Explicit port numbers are stripped before the IP check; the port
       itself is not restricted here (use firewall rules for that).

    Args:
        url: Absolute URL supplied by the user or external system.

    Returns:
        ``True`` if the URL is considered safe, ``False`` otherwise.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.hostname  # lowercased, brackets stripped for IPv6
    if not host:
        return False

    # Reject known metadata hostnames by name before even resolving.
    if host in _METADATA_LITERAL_IPS:
        return False

    # Check if host is an IP literal.
    try:
        ipaddress.ip_address(host)
        # It is an IP literal – check directly.
        return not _is_blocked_ip(host)
    except ValueError:
        pass  # Not an IP literal – fall through to DNS resolution.

    # Hostname: resolve and check all returned addresses.
    return _resolve_and_check(host)


def validate_url(url: str) -> str:
    """Validate *url* for safety and return it unchanged if valid.

    This is the **primary function** callers should use before making any
    outbound HTTP request with a user-supplied URL.

    Args:
        url: Absolute URL to validate.

    Returns:
        The original *url* string (unchanged) if it passes all checks.

    Raises:
        ValueError: With a human-readable message if the URL is rejected.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"URL scheme {parsed.scheme!r} is not allowed. Only 'http' and 'https' are permitted."
        )

    if not parsed.hostname:
        raise ValueError("URL must include a valid hostname.")

    if not is_safe_url(url):
        raise ValueError(
            "The supplied URL resolves to a private, link-local, or otherwise "
            "restricted IP address and cannot be fetched for security reasons."
        )

    return url
