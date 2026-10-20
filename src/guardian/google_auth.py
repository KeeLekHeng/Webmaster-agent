"""Refresh a separately authorized read-only Google grant; never persist tokens."""
import json
import os
import time
from dataclasses import dataclass, field

import httpx

from .network import enabled

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REFRESH_KEYS = ("GUARDIAN_GSC_CLIENT_ID", "GUARDIAN_GSC_CLIENT_SECRET", "GUARDIAN_GSC_REFRESH_TOKEN")


@dataclass(frozen=True)
class GoogleAccess:
    status: str
    token: str | None = field(default=None, repr=False)


def search_console_access(client=None):
    """Prefer configured refresh credentials to a possibly expired manual token."""
    enabled()
    values = [os.getenv(key, "").strip() for key in REFRESH_KEYS]
    if not any(values):
        token = os.getenv("GUARDIAN_GSC_ACCESS_TOKEN", "").strip()
        return GoogleAccess("manual-token" if token else "not-connected", token or None)
    if not all(values):
        return GoogleAccess("refresh-config-incomplete")
    client_id, client_secret, refresh_token = values
    if not client_id.endswith(".apps.googleusercontent.com"):
        return GoogleAccess("refresh-config-invalid")
    form = {"client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token"}

    def exchange(session):
        started = time.monotonic()
        with session.stream("POST", TOKEN_ENDPOINT, data=form, timeout=15,
                            follow_redirects=False) as response:
            raw = bytearray()
            for chunk in response.iter_bytes():
                enabled()
                raw.extend(chunk)
                if len(raw) > 65536 or time.monotonic() - started > 30:
                    return GoogleAccess("refresh-failed")
            if response.status_code != 200:
                # Classify known codes only, never descriptions or arbitrary strings.
                try:
                    error = json.loads(raw).get("error")
                except (ValueError, AttributeError):
                    error = None
                if error == "invalid_grant":
                    return GoogleAccess("reauthorization-required")
                if error in ("invalid_client", "unauthorized_client"):
                    return GoogleAccess("refresh-config-invalid")
                return GoogleAccess("refresh-failed")
        enabled()
        data = json.loads(raw)
        token = data.get("access_token")
        expires = data.get("expires_in")
        scopes = data.get("scope")
        if not isinstance(scopes, str) or set(scopes.split()) != {SCOPE}:
            return GoogleAccess("refresh-scope-rejected")
        if (data.get("token_type", "").lower() != "bearer" or
                not isinstance(token, str) or not 1 <= len(token) <= 16384 or
                any(ord(c) <= 32 or ord(c) >= 127 for c in token) or
                type(expires) is not int or not 60 <= expires <= 86400):
            return GoogleAccess("refresh-failed")
        if data.get("refresh_token", refresh_token) != refresh_token:
            # No silent credential changes; a changed grant requires human review.
            return GoogleAccess("reauthorization-required")
        return GoogleAccess("refreshed", token)

    try:
        if client is not None:
            return exchange(client)
        with httpx.Client(trust_env=False) as session:
            return exchange(session)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        enabled()  # Kill switch takes precedence over an unavailable credential.
        return GoogleAccess("refresh-failed")


AUTH_NOTICES = {
    "unknown": "Google authorization provenance is unspecified for this input.",
    "manual-token": "Manual Google access token used; it is short-lived and is not automatically refreshed.",
    "not-connected": "Search Console is not connected; no Google search request was made.",
    "refreshed": "Google access token refreshed using the configured read-only grant; token retained in memory only.",
    "refresh-config-incomplete": "Google refresh configuration is incomplete; provide client ID, client secret and refresh token. Manual-token fallback is disabled when refresh is configured.",
    "refresh-config-invalid": "Google OAuth client configuration is invalid; check that the client ID/secret match the refresh grant.",
    "reauthorization-required": "Google grant is expired, revoked or changed; owner reauthorization is required. No automatic consent or credential replacement was performed.",
    "refresh-scope-rejected": "Google refresh response did not confirm exactly the read-only Search Console scope; access was rejected.",
    "refresh-failed": "Google token refresh unavailable or invalid; raw response omitted. No fallback to a potentially stale token was attempted.",
}
