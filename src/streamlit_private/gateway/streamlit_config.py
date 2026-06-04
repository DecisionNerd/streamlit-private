"""How to run Streamlit headless behind the gateway, and what to proxy.

These values are verified against Streamlit 1.58 source (config defaults and the
Starlette route table in ``starlette_routes.py`` / ``starlette_websocket.py``).
The guiding rule from that research: **forward everything under ``/`` to
Streamlit, with a WebSocket upgrade on ``/_stcore/stream``** — there is a single
root ``StaticFiles`` mount, so ``static/*``, ``favicon.png``, and ``manifest.json``
are all served from ``/`` and need no special-casing.

Note the prefix spelling: the *core* endpoints are under ``_stcore`` (with the
leading underscore), while user media and the SPA bundle are under ``media`` and
``static`` (no underscore). Getting this wrong is a classic proxy bug.
"""

from __future__ import annotations

# Streamlit's single WebSocket endpoint. Must be proxied with the Upgrade /
# Connection: upgrade headers or the app loads but never connects.
WEBSOCKET_PATH = "/_stcore/stream"

# Route prefixes Streamlit serves. We forward *everything* to Streamlit (it is
# the only upstream), so this map is documentation + the basis for assertions in
# tests, not an allowlist the proxy enforces.
CORE_PREFIX = "/_stcore/"  # stream (WS), health, host-config, upload_file, metrics, bidi-components
MEDIA_PREFIX = "/media/"  # st.image/audio/video/download_button — supports HTTP Range (206)
COMPONENT_PREFIX = "/component/"  # v1 custom component assets

# Hop-by-hop headers (RFC 7230 §6.1) must not be forwarded verbatim by a proxy;
# the ASGI server manages the real connection/upgrade semantics itself.
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def streamlit_server_args(
    *,
    host: str = "127.0.0.1",
    port: int = 8501,
    public_url: str | None = None,
) -> list[str]:
    """Build the ``streamlit run`` flags for running headless behind the gateway.

    - Binds to loopback by default so Streamlit is unreachable except through the
      gateway (single-container isolation, ADR-0011).
    - Keeps XSRF **and** CORS enabled (Streamlit couples them — disabling CORS
      while XSRF is on is rejected and silently re-enabled). The proxy instead
      preserves Origin/Host so the same-origin checks pass.
    - ``public_url`` sets ``browser.serverAddress``/``serverPort`` so Streamlit's
      generated URLs and XSRF origin checks match what the browser actually hits.
    """
    args = [
        "--server.headless=true",
        f"--server.address={host}",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    if public_url is not None:
        from urllib.parse import urlparse

        parsed = urlparse(public_url)
        if parsed.hostname:
            args.append(f"--browser.serverAddress={parsed.hostname}")
        scheme_default = 443 if parsed.scheme == "https" else 80
        args.append(f"--browser.serverPort={parsed.port or scheme_default}")
    return args


def is_websocket_path(path: str) -> bool:
    """True if ``path`` is Streamlit's WebSocket endpoint (exact match)."""
    return path.rstrip("/") == WEBSOCKET_PATH


def strip_hop_by_hop(headers: dict[str, str]) -> dict[str, str]:
    """Return ``headers`` without hop-by-hop entries (case-insensitive)."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}
