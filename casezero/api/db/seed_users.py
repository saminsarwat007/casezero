"""Create the four synthetic staff identities used to prove database-enforced RBAC.

Run after the SQL migrations::

    DEMO_USER_PASSWORD='a unique 12+ character value' \
      .venv/bin/python -m api.db.seed_users

The command is idempotent. Existing identities are retained, their password is
updated to the supplied demo value, and their ``app_users`` role row is upserted.
No password is stored in source control or printed to the terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.config import Settings, get_settings
from api.db.client import service_client


@dataclass(frozen=True)
class DemoUser:
    email: str
    full_name: str
    role: str


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser("ops@casezero.my", "Nurul Aisyah", "OPS"),
    DemoUser("investigator@casezero.my", "Faizal Rahman", "INVESTIGATOR"),
    DemoUser("compliance@casezero.my", "Mei Ling Tan", "COMPLIANCE"),
    DemoUser("admin@casezero.my", "Ravi Kumaran", "ADMIN"),
)


def validate_password(password: str | None) -> str:
    """Refuse insecure or absent demo credentials before making any API call."""
    if not password or len(password) < 12:
        raise ValueError("DEMO_USER_PASSWORD must contain at least 12 characters.")
    return password


def seed_users(
    *,
    settings: Settings | None = None,
    client: Any | None = None,
) -> list[dict[str, str]]:
    """Create/update Auth identities and mirror them into ``app_users``."""
    cfg = settings or get_settings()
    password = validate_password(cfg.demo_user_password)
    sb = client or service_client()
    existing = {
        str(user.email).lower(): user
        for user in sb.auth.admin.list_users(page=1, per_page=1000)
        if user.email
    }
    results: list[dict[str, str]] = []

    for spec in DEMO_USERS:
        identity = existing.get(spec.email)
        state = "updated"
        attributes = {
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": spec.full_name, "role": spec.role},
        }
        if identity is None:
            response = sb.auth.admin.create_user({"email": spec.email, **attributes})
            identity = response.user
            state = "created"
        else:
            response = sb.auth.admin.update_user_by_id(str(identity.id), attributes)
            identity = response.user

        if identity is None:
            raise RuntimeError(f"Supabase returned no identity for {spec.email}.")
        sb.table("app_users").upsert(
            {
                "id": str(identity.id),
                "email": spec.email,
                "full_name": spec.full_name,
                "role": spec.role,
            },
            on_conflict="id",
        ).execute()
        results.append({"email": spec.email, "role": spec.role, "state": state})

    return results


def main() -> None:
    rows = seed_users()
    print("CaseZero staff identities are ready (password was not printed):")
    for row in rows:
        print(f"  {row['state']:<7} {row['email']:<34} {row['role']}")


if __name__ == "__main__":
    main()
