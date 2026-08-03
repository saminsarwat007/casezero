-- CaseZero — governed, hash-chained policy activation.

create table if not exists policy_events (
  id          bigserial primary key,
  proposal_id uuid not null references policy_proposals(id) on delete cascade,
  seq         int not null,
  event_type  text not null,
  actor       text not null,
  payload     jsonb not null,
  prev_hash   text not null,
  hash        text not null,
  created_at  timestamptz not null default now(),
  unique (proposal_id, seq)
);

create index if not exists policy_events_proposal_seq
  on policy_events (proposal_id, seq);

alter table policy_events enable row level security;

drop policy if exists policy_events_read on policy_events;
create policy policy_events_read on policy_events for select using (
  current_app_role() in ('OPS', 'COMPLIANCE', 'ADMIN')
);

revoke update, delete, truncate on policy_events
  from anon, authenticated, service_role;

-- Deactivate then activate inside one database transaction. The application only
-- receives success after the unique-active-pack invariant has been restored.
create or replace function activate_rule_pack(
  p_category dispute_category,
  p_version int
) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not exists (
    select 1 from rule_packs
    where category = p_category and version = p_version
  ) then
    raise exception 'No rule pack % version % exists', p_category, p_version;
  end if;

  update rule_packs
     set is_active = false
   where category = p_category and is_active;

  update rule_packs
     set is_active = true
   where category = p_category and version = p_version;
end;
$$;

revoke all on function activate_rule_pack(dispute_category, int)
  from public, anon, authenticated;
grant execute on function activate_rule_pack(dispute_category, int)
  to service_role;

