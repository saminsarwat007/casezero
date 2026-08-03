"""The auth seeder stays idempotent and never needs live credentials in tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.config import Settings
from api.db.seed_users import DEMO_USERS, seed_users, validate_password


class FakeAdmin:
    def __init__(self) -> None:
        self.users: dict[str, SimpleNamespace] = {}
        self.created = 0
        self.updated = 0

    def list_users(self, **_: object):
        return list(self.users.values())

    def create_user(self, attributes: dict):
        self.created += 1
        user = SimpleNamespace(id=f"user-{self.created}", email=attributes["email"])
        self.users[user.email] = user
        return SimpleNamespace(user=user)

    def update_user_by_id(self, uid: str, attributes: dict):
        self.updated += 1
        user = next(user for user in self.users.values() if user.id == uid)
        return SimpleNamespace(user=user)


class FakeQuery:
    def __init__(self, sink: list[dict]) -> None:
        self.sink = sink

    def upsert(self, row: dict, **_: object):
        self.sink.append(row)
        return self

    def execute(self):
        return SimpleNamespace(data=self.sink)


class FakeClient:
    def __init__(self) -> None:
        self.admin = FakeAdmin()
        self.auth = SimpleNamespace(admin=self.admin)
        self.rows: list[dict] = []

    def table(self, name: str):
        assert name == "app_users"
        return FakeQuery(self.rows)


def test_password_is_required_and_not_weak():
    for value in (None, "", "short"):
        with pytest.raises(ValueError, match="at least 12"):
            validate_password(value)


def test_seed_is_idempotent_and_covers_all_roles():
    client = FakeClient()
    cfg = Settings(_env_file=None, demo_user_password="correct-horse-staff")

    first = seed_users(settings=cfg, client=client)
    second = seed_users(settings=cfg, client=client)

    assert client.admin.created == 4
    assert client.admin.updated == 4
    assert {row["role"] for row in first} == {"OPS", "INVESTIGATOR", "COMPLIANCE", "ADMIN"}
    assert {row["state"] for row in first} == {"created"}
    assert {row["state"] for row in second} == {"updated"}
    assert {row["email"] for row in first} == {user.email for user in DEMO_USERS}
