"""SSRF guard for user-supplied URLs.

This app runs inside a private network, so a fetch of an attacker-chosen URL
must never be able to reach LAN hosts, loopback services, or cloud metadata.
Every hop (including each redirect) is validated: scheme, port, credentials,
and DNS resolution — every resolved address must be globally routable.

Known limitation (documented deliberately): validation resolves DNS and the
HTTP client then re-resolves, so an attacker running a rebinding DNS server
has a small TOCTOU window. Combined with the response-size cap, timeouts and
the LAN firewall this is an accepted risk for a demo; pinning connections to
the validated IP would close it fully.
"""
import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}


class BlockedURL(ValueError):
    pass


def validate_public_url(url: str) -> str:
    """Raise BlockedURL unless every resolved address of `url` is public.

    Returns the hostname for logging.
    """
    try:
        p = urlparse(url)
    except ValueError as exc:
        raise BlockedURL("That is not a valid URL.") from exc
    if p.scheme not in ALLOWED_SCHEMES:
        raise BlockedURL("Only http(s) URLs are allowed.")
    if not p.hostname:
        raise BlockedURL("URL has no host.")
    if p.username or p.password:
        raise BlockedURL("Credentials in URLs are not allowed.")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise BlockedURL("Only ports 80 and 443 are allowed.")

    try:
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedURL("Host could not be resolved.") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global is False for loopback, RFC1918, link-local (incl. 169.254
        # cloud metadata), unique-local, and reserved space.
        if not ip.is_global or ip.is_multicast:
            raise BlockedURL("Target resolves to a private or reserved address.")
    return p.hostname
