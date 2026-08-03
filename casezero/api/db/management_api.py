"""Supabase Management API — the DDL transport.

This network blocks the Postgres wire protocol entirely, so this HTTPS endpoint is
the *only* way to run DDL against the project. That makes it load-bearing, and a
load-bearing transport needs to tolerate a dropped connection rather than aborting
a migration halfway.

Retries cover connection resets and 5xx responses. A 4xx is a real SQL or auth
error and is raised immediately, because retrying a syntax error just wastes time.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from api.config import get_settings

#: Every attempt is bounded, so a hang can never block a build.
REQUEST_TIMEOUT = 45.0
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = (1.0, 2.5, 5.0)


class ManagementApiError(RuntimeError):
    pass


def _endpoint() -> tuple[str, str]:
    settings = get_settings()
    if not (settings.supabase_project_ref and settings.supabase_access_token):
        raise ManagementApiError(
            "SUPABASE_PROJECT_REF and SUPABASE_ACCESS_TOKEN are required. "
            "Create a token at https://supabase.com/dashboard/account/tokens"
        )
    url = (
        f"https://api.supabase.com/v1/projects/"
        f"{settings.supabase_project_ref}/database/query"
    )
    return url, settings.supabase_access_token


def run_sql(query: str) -> list[dict[str, Any]]:
    """Execute SQL as the database owner. Returns rows for SELECTs, [] otherwise.

    Runs with owner privileges, which is why this module is also what the tamper
    demo uses to simulate a compromised DBA — the application's own credentials
    cannot do it.
    """
    url, token = _endpoint()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    last_error: Exception | None = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = httpx.post(
                url, headers=headers, json={"query": query}, timeout=REQUEST_TIMEOUT
            )
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            last_error = exc
        else:
            if response.status_code < 400:
                try:
                    payload = response.json()
                except ValueError:
                    return []
                return payload if isinstance(payload, list) else []

            # 4xx means the request itself is wrong; retrying cannot help.
            if response.status_code < 500:
                raise ManagementApiError(
                    f"HTTP {response.status_code}: {response.text[:600]}"
                )
            last_error = ManagementApiError(
                f"HTTP {response.status_code}: {response.text[:300]}"
            )

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_SECONDS[attempt])

    raise ManagementApiError(
        f"Management API unreachable after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def ping() -> bool:
    run_sql("select 1;")
    return True
