"""Trusted client-IP resolution for supplementary request metadata.

``X-Forwarded-For`` is client-controlled unless the request arrived from a
proxy we operate. The rule here:

* Start from ``REMOTE_ADDR`` — the actual peer socket address.
* Only when that peer is listed in ``TRUSTED_PROXY_IPS`` (exact address or
  CIDR) is the forwarded chain consulted.
* Walk the chain right-to-left, skipping trusted proxies, and return the first
  untrusted hop. This is the only hop a client cannot forge.
* Anything that is not a valid IP address is ignored, and the fallback is the
  peer address (or ``None``), never a forwarded value.

The result is supplementary metadata only. It is never used for
authentication, authorization, organization identity, or rate-limit keys.
"""

import ipaddress

from django.conf import settings


def _trusted_networks():
    raw = getattr(settings, "TRUSTED_PROXY_IPS", ()) or ()
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    networks = []
    for value in raw:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            # A malformed configured entry is ignored: trusting nothing is
            # safer than trusting an arbitrary string.
            continue
    return networks


def _is_trusted(address: ipaddress._BaseAddress, networks) -> bool:
    return any(address in network for network in networks)


def get_client_ip(request):
    """Return the trusted client IP string, or ``None`` when unavailable."""
    if request is None:
        return None
    peer_raw = (getattr(request, "META", {}) or {}).get("REMOTE_ADDR", "") or ""
    try:
        peer = ipaddress.ip_address(peer_raw.strip())
    except ValueError:
        return None

    networks = _trusted_networks()
    if not _is_trusted(peer, networks):
        return str(peer)

    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if not forwarded:
        return str(peer)

    hops = []
    for part in forwarded.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            hops.append(ipaddress.ip_address(candidate))
        except ValueError:
            continue

    for hop in reversed(hops):
        if _is_trusted(hop, networks):
            continue
        return str(hop)
    return str(peer)
