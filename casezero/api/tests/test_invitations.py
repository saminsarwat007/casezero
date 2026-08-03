from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.config import Settings
from api.db.invitations import InvitationError, StaffInvitationService, StaffInvite


class Query:
    def __init__(self, client, table: str):
        self.client = client
        self.table_name = table
        self.operation = "select"
        self.row = None
        self.email = None

    def select(self, *_): return self
    def order(self, *_): return self
    def limit(self, *_): return self
    def eq(self, key, value):
        if key == "email": self.email = value
        return self
    def upsert(self, row, **_):
        self.operation = "upsert"; self.row = row; return self
    def execute(self):
        if self.operation == "upsert":
            self.client.rows.append(self.row)
            return SimpleNamespace(data=[self.row])
        rows = self.client.rows
        if self.email is not None:
            rows = [row for row in rows if row["email"] == self.email]
        return SimpleNamespace(data=rows)


class Admin:
    def __init__(self):
        self.invites = []
        self.deleted = []

    def invite_user_by_email(self, email, options):
        self.invites.append((email, options))
        return SimpleNamespace(user=SimpleNamespace(id="invited-user", email=email))

    def delete_user(self, user_id): self.deleted.append(user_id)


class Client:
    def __init__(self):
        self.rows = []
        self.admin = Admin()
        self.auth = SimpleNamespace(admin=self.admin)

    def table(self, name): return Query(self, name)


def service(client=None):
    return StaffInvitationService(
        client=client or Client(),
        settings=Settings(_env_file=None, dashboard_base_url="https://casezero.test"),
    )


def test_invite_creates_auth_identity_and_rls_role():
    client = Client()
    result = service(client).invite(StaffInvite(" New.User@Bank.My ", "  Nur  Iman ", "ops"))

    assert result["email"] == "new.user@bank.my"
    assert result["full_name"] == "Nur Iman"
    assert result["role"] == "OPS"
    assert result["invitation"] == "SENT"
    assert client.admin.invites[0][1]["redirect_to"] == "https://casezero.test/set-password"


def test_existing_email_is_refused_before_auth_invite():
    client = Client()
    client.rows.append({"id": "u1", "email": "ops@casezero.my"})
    with pytest.raises(InvitationError, match="already"):
        service(client).invite(StaffInvite("ops@casezero.my", "Ops", "OPS"))
    assert client.admin.invites == []


def test_unknown_role_is_refused():
    with pytest.raises(InvitationError, match="Role must"):
        service().invite(StaffInvite("new@bank.my", "New User", "OWNER"))
