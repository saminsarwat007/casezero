"""Staff invitation boundary.

Only the Admin API route constructs this service. Supabase owns delivery and the
password-reset token; CaseZero owns the role row consumed by Postgres RLS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.config import Settings, get_settings
from api.db.client import service_client

ROLES = ("OPS", "INVESTIGATOR", "COMPLIANCE", "ADMIN")


class InvitationError(RuntimeError):
    """A safe, operator-readable invitation failure."""


@dataclass(frozen=True)
class StaffInvite:
    email: str
    full_name: str
    role: str


class StaffInvitationService:
    def __init__(self, client: Any | None = None, settings: Settings | None = None) -> None:
        self.sb = client or service_client()
        self.settings = settings or get_settings()

    def list_staff(self) -> list[dict[str, Any]]:
        return (
            self.sb.table("app_users")
            .select("id,email,full_name,role,created_at")
            .order("created_at")
            .execute()
            .data
        )

    def invite(self, invite: StaffInvite) -> dict[str, Any]:
        email = invite.email.strip().lower()
        full_name = " ".join(invite.full_name.split())
        role = invite.role.upper()
        if role not in ROLES:
            raise InvitationError(f"Role must be one of: {', '.join(ROLES)}.")

        existing = (
            self.sb.table("app_users")
            .select("id")
            .eq("email", email)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            raise InvitationError("That work email already has a CaseZero role.")

        redirect_to = f"{self.settings.dashboard_base_url.rstrip('/')}/set-password"
        response = self.sb.auth.admin.invite_user_by_email(
            email,
            {
                "redirect_to": redirect_to,
                "data": {"full_name": full_name, "role": role},
            },
        )
        identity = response.user
        if identity is None:
            raise InvitationError("Supabase accepted no identity for this invitation.")

        try:
            row = (
                self.sb.table("app_users")
                .upsert(
                    {
                        "id": str(identity.id),
                        "email": email,
                        "full_name": full_name,
                        "role": role,
                    },
                    on_conflict="id",
                )
                .execute()
                .data[0]
            )
        except Exception:
            # Do not leave an invited identity without an RLS role.
            self.sb.auth.admin.delete_user(str(identity.id))
            raise

        return {**row, "invitation": "SENT", "redirect_to": redirect_to}


def invitation_service() -> StaffInvitationService:
    return StaffInvitationService()
