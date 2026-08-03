-- ═══════════════════════════════════════════════════════════════════════════
-- CaseZero — 001_init.sql
-- Contract-first schema. Locked before feature code (MASTERPLAN §9).
-- Target: Supabase Postgres 15. Run in the SQL editor or via psql $DATABASE_URL.
--
-- Two invariants this schema enforces at the DATABASE level, not in app code:
--   1. case_events is append-only and hash-chained  -> tamper evidence
--   2. RBAC is RLS, so the database refuses          -> not a UI checkbox
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── Enums (spec vocabulary, verbatim — the judges wrote these words) ────────

create type case_status as enum (
  'RECEIVED',
  'CLASSIFIED',
  'VERIFIED',
  'REVIEW_PENDING',
  'FINANCIALLY_RESOLVED',
  'COMMUNICATED',
  'CLOSED',
  'QUARANTINED'
);

create type dispute_category as enum (
  'unauthorized_transaction',   -- 35% of volume
  'billing_error',              -- 22%
  'mis_selling',                -- 18%
  'atm_debit_card',             -- 12%
  'insurance_takaful',          --  6%
  'loan_financing',             --  5%
  'emoney_digital'              --  2%
);

create type urgency_level    as enum ('High', 'Medium', 'Low');
create type verification_res as enum ('PASS', 'FAIL', 'MANUAL_REVIEW');
create type journal_kind     as enum ('REVERSAL', 'CREDIT_ADJUSTMENT');
create type app_role         as enum ('OPS', 'INVESTIGATOR', 'COMPLIANCE', 'ADMIN');
create type intake_channel   as enum (
  'IMAP',
  'WORKBUDDY_EMAIL_MCP',   -- WorkBuddy agent: Email MCP + pdf skill
  'BRANCH_BOT',            -- branch officer logging a walk-in
  'PROACTIVE',             -- the dispute that files itself
  'MANUAL_INJECT'          -- demo / .eml replay
);
create type case_outcome as enum (
  'RESOLVED_IN_FULL',
  'PARTIALLY_RESOLVED',
  'REJECTED',
  'CUSTOMER_DISSATISFIED',
  'PENDING'
);
create type proposal_status as enum ('DRAFT', 'APPLIED', 'REJECTED');

-- ─── Roles (mirrors auth.users so RLS can read a role without a join storm) ──

create table app_users (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null unique,
  full_name  text not null,
  role       app_role not null default 'OPS',
  created_at timestamptz not null default now()
);

-- Single source of truth for "what role is the caller?" Used by every policy.
create or replace function current_app_role() returns app_role
language sql stable security definer set search_path = public as $$
  select role from app_users where id = auth.uid();
$$;

-- ─── Mock core banking + CRM (what the MCP servers read/write) ───────────────

create table customers (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  nric_enc    text not null,              -- Fernet ciphertext, never plaintext
  nric_last4  text not null,              -- for masked display
  email       text not null,
  phone       text,
  segment     text not null default 'retail',   -- retail | sme | vulnerable
  risk_flags  jsonb not null default '[]'::jsonb,
  joined_at   timestamptz not null default now()
);

create table accounts (
  account_no   text primary key,
  customer_id  uuid not null references customers(id) on delete cascade,
  product_type text not null,                    -- savings | current | credit_card | financing
  balance_rm   numeric(14,2) not null default 0,
  status       text not null default 'ACTIVE',
  opened_at    timestamptz not null default now()
);

create table transactions (
  id          uuid primary key default gen_random_uuid(),
  txn_ref     text not null unique,
  account_no  text not null references accounts(account_no) on delete cascade,
  merchant    text,
  amount_rm   numeric(14,2) not null,
  direction   text not null default 'DEBIT',     -- DEBIT | CREDIT
  channel     text,                              -- pos | atm | online | duitnow | fpx
  country     text default 'MY',
  device_id   text,                              -- fuels Fraud-Ring Radar clustering
  posted_at   timestamptz not null,
  is_disputed boolean not null default false
);

create index on transactions (account_no, posted_at desc);
create index on transactions (merchant);
create index on transactions (device_id);

-- ─── Cases ──────────────────────────────────────────────────────────────────

create table cases (
  id                  uuid primary key default gen_random_uuid(),
  case_ref            text not null unique,          -- MYB-2026-000123
  status              case_status not null default 'RECEIVED',
  channel             intake_channel not null default 'IMAP',

  -- Classification + governance stamp
  category            dispute_category,
  urgency             urgency_level,
  confidence          numeric(4,3),                  -- < floor => MANUAL_REVIEW, by design
  rule_pack_version   int,

  -- Parties. PII is encrypted at rest ON TOP OF Supabase at-rest encryption.
  customer_id         uuid references customers(id),
  account_no_enc      text,
  account_last4       text,
  nric_enc            text,
  claimant_email      text,

  -- Claim
  amount_rm           numeric(14,2),
  txn_refs            text[] not null default '{}',
  summary             text,

  -- SLA. Working days, not calendar days (BNM).
  sla_start           timestamptz,
  sla_working_days    int,
  sla_due             timestamptz,

  -- Outcome
  verification_result verification_res,
  outcome             case_outcome not null default 'PENDING',
  assigned_to         uuid references app_users(id),
  resolved_at         timestamptz,

  -- Customer tracker (magic-link PWA)
  track_token         text unique default encode(gen_random_bytes(16), 'hex'),

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index on cases (status);
create index on cases (category, urgency);
create index on cases (sla_due) where status not in ('CLOSED', 'QUARANTINED');
create index on cases (assigned_to);

-- ─── Append-only, hash-chained event bus == the audit trail ──────────────────

create table case_events (
  id         bigserial primary key,
  case_id    uuid not null references cases(id) on delete cascade,
  seq        int  not null,
  event_type text not null,
  actor      text not null,          -- 'agent:classifier' | 'user:<uuid>' | 'kernel'
  payload    jsonb not null,
  prev_hash  text not null,          -- 64 zeroes for the genesis event
  hash       text not null,          -- sha256(prev_hash || canonical_json(payload))
  created_at timestamptz not null default now(),
  unique (case_id, seq)
);

create index on case_events (case_id, seq);

-- Append-only, enforced by the database. This is what makes verify_chain()
-- meaningful: a tamperer must UPDATE, and UPDATE is impossible through the API.
-- (The live demo tampers via the service role in the SQL editor, which is
-- exactly the "trusted insider" threat a hash chain is designed to expose.)
create rule case_events_no_update as on update to case_events do instead nothing;
create rule case_events_no_delete as on delete to case_events do instead nothing;

-- ─── Double-entry ledger ────────────────────────────────────────────────────

create table journal_entries (
  id               uuid primary key default gen_random_uuid(),
  case_id          uuid not null references cases(id) on delete cascade,
  entry_type       journal_kind not null,
  debit_account    text not null,
  credit_account   text not null,
  amount_rm        numeric(14,2) not null check (amount_rm > 0),
  narrative        text not null,
  posted_by        text not null,                       -- 'agent:resolver' or a user id
  dual_control_by  uuid references app_users(id),        -- required above threshold
  posted_at        timestamptz not null default now(),
  check (debit_account <> credit_account)
);

create index on journal_entries (case_id);

-- ─── Policy as code, versioned ──────────────────────────────────────────────

create table rule_packs (
  id             uuid primary key default gen_random_uuid(),
  category       dispute_category not null,
  version        int not null,
  yaml           text not null,
  is_active      boolean not null default false,
  change_summary text,
  parent_version int,
  created_by     text not null default 'system',
  created_at     timestamptz not null default now(),
  unique (category, version)
);

-- Exactly one active pack per category, enforced by the database.
create unique index rule_packs_one_active
  on rule_packs (category) where is_active;

-- Policy Composer drafts: an LLM proposal is never live until a human applies it.
create table policy_proposals (
  id                 uuid primary key default gen_random_uuid(),
  nl_request         text not null,               -- what the ops lead actually typed
  target_category    dispute_category not null,
  base_version       int not null,
  proposed_yaml      text not null,
  diff_json          jsonb not null,
  plain_english_diff text not null,
  eval_impact        jsonb,                       -- simulated over the corpus BEFORE apply
  risk_flag          text,                        -- e.g. 'RAISES_SLA_BREACH_RISK'
  status             proposal_status not null default 'DRAFT',
  author             uuid references app_users(id),
  decided_by         uuid references app_users(id),
  created_at         timestamptz not null default now(),
  decided_at         timestamptz
);

-- ─── Measurement (we state real numbers, never claimed ones) ─────────────────

create table eval_runs (
  id                uuid primary key default gen_random_uuid(),
  corpus_version    text not null,
  rule_pack_state   jsonb not null,
  n_cases           int  not null,
  accuracy          numeric(5,4),
  urgency_accuracy  numeric(5,4),
  confusion         jsonb,
  p50_ms            int,
  p95_ms            int,
  cost_rm_per_case  numeric(10,6),
  injection_caught  int,
  injection_total   int,
  notes             text,
  run_at            timestamptz not null default now()
);

create table llm_calls (
  id         bigserial primary key,
  case_id    uuid references cases(id) on delete set null,
  agent      text not null,
  provider   text not null,
  model      text not null,
  tokens_in  int  not null default 0,
  tokens_out int  not null default 0,
  latency_ms int  not null default 0,
  cost_rm    numeric(12,8) not null default 0,
  ok         boolean not null default true,
  created_at timestamptz not null default now()
);

create index on llm_calls (case_id);
create index on llm_calls (created_at desc);

-- ─── Cross-case intelligence + security ─────────────────────────────────────

create table fraud_rings (
  id           uuid primary key default gen_random_uuid(),
  signal_type  text not null,               -- merchant | device | counterparty
  signal_value text not null,
  case_ids     uuid[] not null default '{}',
  severity     text not null default 'MEDIUM',
  intel_brief  text,
  detected_at  timestamptz not null default now(),
  unique (signal_type, signal_value)
);

create table quarantine (
  id          uuid primary key default gen_random_uuid(),
  case_id     uuid references cases(id) on delete cascade,
  reason      text not null,
  detector    text not null,                -- which layer caught it
  raw_excerpt text not null,                -- preserved: never silently dropped
  created_at  timestamptz not null default now()
);

-- Customer PWA push subscriptions
create table push_subscriptions (
  id          uuid primary key default gen_random_uuid(),
  customer_id uuid not null references customers(id) on delete cascade,
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now()
);

-- ─── updated_at ─────────────────────────────────────────────────────────────

create or replace function touch_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger cases_touch before update on cases
  for each row execute function touch_updated_at();

-- ═══════════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY
-- The CISO question is "can an investigator see everything?" The answer has to
-- be the database saying no, not the UI hiding a column.
-- ═══════════════════════════════════════════════════════════════════════════

alter table app_users        enable row level security;
alter table cases            enable row level security;
alter table case_events      enable row level security;
alter table journal_entries  enable row level security;
alter table customers        enable row level security;
alter table accounts         enable row level security;
alter table transactions     enable row level security;
alter table rule_packs       enable row level security;
alter table policy_proposals enable row level security;
alter table eval_runs        enable row level security;
alter table llm_calls        enable row level security;
alter table fraud_rings      enable row level security;
alter table quarantine       enable row level security;
alter table push_subscriptions enable row level security;

-- Everyone signed in sees their own row; ADMIN sees all.
create policy app_users_self on app_users for select
  using (id = auth.uid() or current_app_role() = 'ADMIN');

-- CASES
--   OPS / COMPLIANCE / ADMIN : all cases
--   INVESTIGATOR             : ONLY cases assigned to them, and only those that
--                              actually need a human. This is the live demo:
--                              switch role, rows vanish.
create policy cases_read on cases for select using (
  current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN')
  or (
    current_app_role() = 'INVESTIGATOR'
    and assigned_to = auth.uid()
    and status in ('REVIEW_PENDING', 'VERIFIED')
  )
);

create policy cases_write on cases for update using (
  current_app_role() in ('OPS', 'ADMIN')
  or (current_app_role() = 'INVESTIGATOR' and assigned_to = auth.uid())
);

-- Audit trail: readable by anyone who can read the case. Writes go through the
-- service role only, because the kernel owns the chain.
create policy case_events_read on case_events for select using (
  exists (select 1 from cases c where c.id = case_id)
);

-- Money: only COMPLIANCE and ADMIN read the ledger.
create policy journal_read on journal_entries for select
  using (current_app_role() in ('COMPLIANCE', 'ADMIN'));

-- PII tables: INVESTIGATOR is deliberately excluded from raw customer records.
create policy customers_read on customers for select
  using (current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN'));

create policy accounts_read on accounts for select
  using (current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN'));

create policy transactions_read on transactions for select
  using (current_app_role() in ('OPS', 'INVESTIGATOR', 'COMPLIANCE', 'ADMIN'));

-- Policy as code: everyone reads, only COMPLIANCE/ADMIN can apply a change.
create policy rule_packs_read on rule_packs for select using (auth.uid() is not null);

create policy proposals_read on policy_proposals for select using (auth.uid() is not null);
create policy proposals_draft on policy_proposals for insert
  with check (current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN'));
create policy proposals_decide on policy_proposals for update
  using (current_app_role() in ('COMPLIANCE', 'ADMIN'));

-- Measurement + intel: readable by all signed-in staff.
create policy evals_read     on eval_runs   for select using (auth.uid() is not null);
create policy llm_calls_read on llm_calls   for select using (auth.uid() is not null);
create policy rings_read     on fraud_rings for select using (auth.uid() is not null);

-- Quarantine is a security surface: COMPLIANCE / ADMIN only.
create policy quarantine_read on quarantine for select
  using (current_app_role() in ('COMPLIANCE', 'ADMIN'));

-- Push subs are written by the service role on behalf of a customer.
create policy push_admin on push_subscriptions for select
  using (current_app_role() = 'ADMIN');
