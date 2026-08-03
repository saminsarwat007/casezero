-- CaseZero — stakeholder control register and Wajar action receipts.
--
-- These tables are in the exposed public schema, so access is opt-in: explicit
-- grants expose only SELECT to authenticated users, RLS narrows those reads by
-- CaseZero role, and every write remains behind the service-role API boundary.

create table if not exists stakeholder_settings (
  id                           text primary key default 'primary'
                               check (id = 'primary'),
  bank_display_name            text not null default 'MYBank Berhad'
                               check (char_length(bank_display_name) between 2 and 120),
  complaints_email             text not null default 'complaints@mybank.com.my'
                               check (complaints_email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  timezone                     text not null default 'Asia/Kuala_Lumpur'
                               check (timezone in ('Asia/Kuala_Lumpur', 'UTC')),
  sla_warning_hours            int not null default 24
                               check (sla_warning_hours between 1 and 120),
  default_workspace            text not null default '/simple'
                               check (default_workspace in ('/simple', '/pro')),
  wajar_enabled                boolean not null default true,
  automatic_resolution_enabled boolean not null default true,
  updated_by                   uuid references app_users(id) on delete set null,
  updated_at                   timestamptz not null default now()
);

insert into stakeholder_settings (id)
values ('primary')
on conflict (id) do nothing;

create table if not exists settings_events (
  id          bigserial primary key,
  seq         int not null unique,
  event_type  text not null,
  actor       text not null,
  payload     jsonb not null,
  prev_hash   text not null,
  hash        text not null,
  created_at  timestamptz not null default now()
);

create table if not exists assistant_receipts (
  receipt_id   text primary key,
  actor_id     uuid references app_users(id) on delete set null,
  actor_role   app_role not null,
  action       text not null,
  command_hash text not null,
  parameters   jsonb not null default '{}'::jsonb,
  outcome      text not null check (outcome in ('READ', 'NAVIGATED', 'EXECUTED', 'REFUSED')),
  result       jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);

create index if not exists assistant_receipts_created_at
  on assistant_receipts (created_at desc);

alter table stakeholder_settings enable row level security;
alter table settings_events enable row level security;
alter table assistant_receipts enable row level security;

drop policy if exists stakeholder_settings_read on stakeholder_settings;
create policy stakeholder_settings_read
  on stakeholder_settings for select
  to authenticated
  using (current_app_role() in ('OPS', 'INVESTIGATOR', 'COMPLIANCE', 'ADMIN'));

drop policy if exists settings_events_read on settings_events;
create policy settings_events_read
  on settings_events for select
  to authenticated
  using (current_app_role() in ('COMPLIANCE', 'ADMIN'));

drop policy if exists assistant_receipts_read on assistant_receipts;
create policy assistant_receipts_read
  on assistant_receipts for select
  to authenticated
  using (current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN'));

-- Current Supabase projects may require explicit Data API exposure. Authenticated
-- users only need reads; FastAPI performs all writes with the server-only key.
grant select on stakeholder_settings to authenticated;
grant select on settings_events to authenticated;
grant select on assistant_receipts to authenticated;
grant select, insert, update on stakeholder_settings to service_role;
grant select, insert on settings_events to service_role;
grant select, insert on assistant_receipts to service_role;
grant usage, select on sequence settings_events_id_seq to service_role;
revoke insert, update, delete, truncate on stakeholder_settings
  from anon, authenticated;
revoke insert, update, delete, truncate on settings_events
  from anon, authenticated;
revoke insert, update, delete, truncate on assistant_receipts
  from anon, authenticated;

-- Evidence tables are append-only even for service-role application code.
revoke update, delete, truncate on settings_events
  from anon, authenticated, service_role;
revoke update, delete, truncate on assistant_receipts
  from anon, authenticated, service_role;
