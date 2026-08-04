"""Migration runner.

Run:  .venv/bin/python -m api.db.bootstrap

Two transports, tried in order, because Supabase connection pooling is the single
most common way a hackathon loses an hour:

1. **Direct asyncpg** over DATABASE_URL. Preferred. Uses statement_cache_size=0
   because the pooler runs in transaction mode, where prepared statements break.
2. **Supabase Management API**, authenticated with SUPABASE_ACCESS_TOKEN. Needs no
   database networking at all, so it works even when the pooler hostname will not
   resolve — which is exactly the failure noted in .env for this project.

Applied migrations are recorded with a content hash, so re-running is safe and an
edited migration is reported rather than silently skipped.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

from api.config import get_settings
from api.db.management_api import run_sql

LEGACY_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
SUPABASE_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"

LEDGER_DDL = """
create table if not exists _casezero_migrations (
  filename    text primary key,
  sha256      text not null,
  applied_at  timestamptz not null default now()
);
"""

DIM, OFF = "\033[2m", "\033[0m"
GREEN, RED, YELLOW = "\033[32m", "\033[31m", "\033[33m"


def discover() -> list[Path]:
    """Return legacy and Supabase CLI migrations in application order."""
    if not LEGACY_MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"No migrations directory at {LEGACY_MIGRATIONS_DIR}")
    legacy = sorted(LEGACY_MIGRATIONS_DIR.glob("*.sql"))
    standard = (
        sorted(SUPABASE_MIGRATIONS_DIR.glob("*.sql"))
        if SUPABASE_MIGRATIONS_DIR.is_dir()
        else []
    )
    return legacy + standard


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Transport:
    name = "base"

    async def execute(self, sql: str) -> None: ...
    async def fetch_applied(self) -> dict[str, str]: ...
    async def record(self, filename: str, sha: str) -> None: ...
    async def close(self) -> None: ...


class AsyncpgTransport(Transport):
    name = "asyncpg (direct)"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._conn = None

    async def connect(self) -> None:
        import asyncpg

        # statement_cache_size=0 is mandatory against the transaction-mode pooler.
        self._conn = await asyncio.wait_for(
            asyncpg.connect(self.dsn, statement_cache_size=0),
            timeout=15,
        )

    async def execute(self, sql: str) -> None:
        await self._conn.execute(sql)

    async def fetch_applied(self) -> dict[str, str]:
        rows = await self._conn.fetch("select filename, sha256 from _casezero_migrations")
        return {r["filename"]: r["sha256"] for r in rows}

    async def record(self, filename: str, sha: str) -> None:
        await self._conn.execute(
            "insert into _casezero_migrations (filename, sha256) values ($1, $2) "
            "on conflict (filename) do update set sha256 = excluded.sha256",
            filename,
            sha,
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()


class ManagementApiTransport(Transport):
    """HTTPS DDL. Retries live in api/db/management_api.py."""

    name = "Supabase Management API"

    async def _query(self, sql: str) -> list[dict]:
        # run_sql is synchronous and retrying; a thread keeps the event loop free.
        return await asyncio.to_thread(run_sql, sql)

    async def execute(self, sql: str) -> None:
        await self._query(sql)

    async def fetch_applied(self) -> dict[str, str]:
        rows = await self._query("select filename, sha256 from _casezero_migrations")
        return {r["filename"]: r["sha256"] for r in rows}

    async def record(self, filename: str, sha: str) -> None:
        await self._query(
            f"insert into _casezero_migrations (filename, sha256) "
            f"values ('{filename}', '{sha}') "
            f"on conflict (filename) do update set sha256 = excluded.sha256"
        )

    async def close(self) -> None:
        return None


async def pick_transport() -> Transport:
    settings = get_settings()

    if settings.database_url:
        candidate = AsyncpgTransport(settings.database_url)
        try:
            await candidate.connect()
            print(f"  transport   {GREEN}{candidate.name}{OFF}")
            return candidate
        except Exception as exc:  # noqa: BLE001 - fall through to the API transport
            reason = str(exc).split("\n")[0][:120]
            print(f"  transport   {YELLOW}direct connection unavailable{OFF} {DIM}({reason}){OFF}")

    if not (settings.supabase_project_ref and settings.supabase_access_token):
        raise SystemExit(
            "Cannot reach the database. Set a working DATABASE_URL, or set "
            "SUPABASE_PROJECT_REF and SUPABASE_ACCESS_TOKEN for the Management API."
        )
    transport = ManagementApiTransport()
    await transport.execute("select 1")
    print(f"  transport   {GREEN}{transport.name}{OFF}")
    return transport


async def main() -> int:
    settings = get_settings()
    print("=" * 68)
    print("  CaseZero - database bootstrap")
    print("=" * 68)
    print(f"  project     {settings.supabase_project_ref}")
    print(f"  region      {DIM}{getattr(settings, 'supabase_db_region', 'n/a')}{OFF}")

    transport = await pick_transport()
    try:
        await transport.execute(LEDGER_DDL)
        applied = await transport.fetch_applied()

        migrations = discover()
        print(f"  migrations  {len(migrations)} found, {len(applied)} already applied\n")

        for path in migrations:
            sha = digest(path)
            if path.name in applied:
                if applied[path.name] == sha:
                    print(f"  {DIM}skip   {path.name}{OFF}")
                else:
                    print(
                        f"  {YELLOW}CHANGED{OFF} {path.name} — already applied with a "
                        f"different hash. Add a new migration instead of editing this one."
                    )
                continue

            print(f"  apply  {path.name} {DIM}({path.stat().st_size:,} bytes){OFF}")
            try:
                await transport.execute(path.read_text())
            except Exception as exc:  # noqa: BLE001 - report and stop, never half-apply silently
                print(f"  {RED}FAILED{OFF} {path.name}\n         {str(exc)[:700]}")
                return 1
            await transport.record(path.name, sha)
            print(f"  {GREEN}ok{OFF}     {path.name}")

        print("\n" + "=" * 68)
        print(f"  {GREEN}schema is live{OFF}")
        print("=" * 68)
        return 0
    finally:
        await transport.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
