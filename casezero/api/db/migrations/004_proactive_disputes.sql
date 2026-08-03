-- CaseZero - customer-confirmed proactive dispute alerts.

create table if not exists proactive_alerts (
  id            uuid primary key default gen_random_uuid(),
  token         text not null unique default encode(gen_random_bytes(24), 'hex'),
  account_no    text not null references accounts(account_no) on delete cascade,
  txn_ref       text not null references transactions(txn_ref) on delete cascade,
  amount_rm     numeric(14,2) not null check (amount_rm > 0),
  merchant      text not null,
  occurred_at   timestamptz,
  status        text not null default 'PENDING'
                check (status in ('PENDING','CONFIRMED','DISPUTED','EXPIRED')),
  case_id       uuid references cases(id) on delete set null,
  expires_at    timestamptz not null default now() + interval '48 hours',
  created_at    timestamptz not null default now(),
  responded_at  timestamptz
);

create index if not exists proactive_alerts_status_expiry
  on proactive_alerts (status, expires_at);

alter table proactive_alerts enable row level security;

-- Public reads and responses go only through the token-scoped FastAPI boundary.
-- Staff can inspect alert state, but direct client writes are never permitted.
drop policy if exists proactive_alerts_staff_read on proactive_alerts;
create policy proactive_alerts_staff_read on proactive_alerts for select using (
  current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN')
);

revoke insert, update, delete, truncate on proactive_alerts
  from anon, authenticated;

