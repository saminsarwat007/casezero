"""Supabase JWT authentication with the role read through Postgres RLS."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from api.db.client import Database, anon_client, get_db, user_client


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    role: str
    full_name: str
    access_token: str | None = None

    def require(self, *roles: str) -> "AuthUser":
        if self.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {self.role} cannot perform this action.",
            )
        return self


async def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Supabase bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token is empty.")

    try:
        response = anon_client().auth.get_user(token)
        identity = response.user
        if identity is None:
            raise ValueError("Supabase returned no user")
        rows = (
            user_client(token)
            .table("app_users")
            .select("id,email,full_name,role")
            .eq("id", str(identity.id))
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001 - normalise SDK/auth failures
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from exc

    if not rows:
        raise HTTPException(
            status_code=403,
            detail="The authenticated account has no CaseZero role.",
        )
    row = rows[0]
    return AuthUser(
        id=str(row["id"]),
        email=str(row["email"]),
        full_name=str(row["full_name"]),
        role=str(row["role"]),
        access_token=token,
    )


def service_database() -> Database:
    return get_db()


def rls_database(user: AuthUser = Depends(current_user)) -> Database:
    """A repository whose reads carry the caller's JWT and cannot bypass RLS."""
    return Database(user_client(user.access_token)) if user.access_token else get_db()
