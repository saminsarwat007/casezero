-- ═══════════════════════════════════════════════════════════════════════════
-- CaseZero — 002_audit_hardening.sql
--
-- Replaces the append-only RULES from 001 with privilege revocation.
--
-- WHY: `create rule ... do instead nothing` did block tampering, but it also
-- rewrote the referential-integrity query behind `cases.on delete cascade`, so
-- deleting a case failed with:
--     referential integrity query on "cases" from constraint
--     "case_events_case_id_fkey" gave unexpected result
-- A control that makes ordinary operations impossible is not a control, it is a
-- bug. Rules are the wrong tool here.
--
-- REVOKE is the idiomatic mechanism, and it produces a strictly better security
-- story because the two layers are now cleanly separated:
--
--   Layer 1 — the application, at its highest privilege (service_role), is denied
--             UPDATE and DELETE by Postgres itself. Not a policy it could switch
--             off; a privilege it does not hold.
--   Layer 2 — a compromised DBA connecting as the table owner CAN rewrite a row.
--             Nothing stops that, and pretending otherwise would be dishonest.
--             The hash chain is what catches it, naming the exact altered event.
--
-- That layering is the actual answer to "how do we know the record wasn't
-- edited?", and it is what the demo shows at 4:40.
-- ═══════════════════════════════════════════════════════════════════════════

drop rule if exists case_events_no_update on case_events;
drop rule if exists case_events_no_delete on case_events;

-- The audit trail is append-only for every application role. INSERT and SELECT
-- are all the kernel has ever needed.
revoke update, delete, truncate on case_events from anon, authenticated, service_role;

-- Journal entries are equally immutable: a posted double-entry is corrected by
-- posting a reversing entry, never by editing history.
revoke update, delete, truncate on journal_entries from anon, authenticated, service_role;

-- Applied rule-pack versions are immutable too. The Policy Composer creates a NEW
-- version and flips is_active; it never edits a version that has been live.
-- (is_active itself must stay updatable for that flip to work, so UPDATE is left
-- in place here and the immutability of `yaml` is enforced by the trigger below.)
create or replace function rule_packs_yaml_is_immutable() returns trigger
language plpgsql as $$
begin
  if new.yaml is distinct from old.yaml then
    raise exception
      'rule_packs.yaml is immutable for version % of %. Insert a new version instead.',
      old.version, old.category;
  end if;
  return new;
end;
$$;

drop trigger if exists rule_packs_no_yaml_edit on rule_packs;
create trigger rule_packs_no_yaml_edit
  before update on rule_packs
  for each row execute function rule_packs_yaml_is_immutable();

-- ─── Analytics ──────────────────────────────────────────────────────────────
-- Aggregation belongs in the database. These back the dashboard metrics the spec
-- names explicitly, and are reached over PostgREST RPC.

create or replace function dashboard_metrics()
returns jsonb
language sql stable security definer set search_path = public as $$
  with base as (
    select
      count(*)                                                        as total,
      count(*) filter (where status = 'QUARANTINED')                  as quarantined,
      count(*) filter (where status in ('FINANCIALLY_RESOLVED','COMMUNICATED','CLOSED'))
                                                                      as resolved,
      count(*) filter (where status = 'REVIEW_PENDING')               as awaiting_human,
      count(*) filter (where sla_due < now()
                         and status not in ('CLOSED','QUARANTINED'))  as breached,
      count(*) filter (where sla_due < now() + interval '1 day'
                         and sla_due >= now()
                         and status not in ('CLOSED','QUARANTINED'))  as due_soon,
      avg(extract(epoch from (resolved_at - created_at)))
        filter (where resolved_at is not null)                        as avg_resolution_seconds
    from cases
  ),
  spend as (
    select coalesce(sum(cost_rm), 0) as total_cost_rm,
           count(distinct case_id)   as cases_with_calls
    from llm_calls
  )
  select jsonb_build_object(
    'total_cases',            base.total,
    'resolved',               base.resolved,
    'awaiting_human',         base.awaiting_human,
    'quarantined',            base.quarantined,
    'sla_breached',           base.breached,
    'sla_due_soon',           base.due_soon,
    'avg_resolution_seconds', round(coalesce(base.avg_resolution_seconds, 0)),
    'automation_rate',        case when base.total > 0
                                   then round(base.resolved::numeric / base.total, 4)
                                   else 0 end,
    'total_cost_rm',          round(spend.total_cost_rm, 6),
    'cost_per_case_rm',       case when spend.cases_with_calls > 0
                                   then round(spend.total_cost_rm / spend.cases_with_calls, 6)
                                   else 0 end
  )
  from base, spend;
$$;

create or replace function category_volumes()
returns table (category dispute_category, n bigint, share numeric)
language sql stable security definer set search_path = public as $$
  select c.category,
         count(*) as n,
         round(count(*)::numeric / nullif(sum(count(*)) over (), 0), 4) as share
  from cases c
  where c.category is not null
  group by c.category
  order by n desc;
$$;

-- Workload distribution — a spec-named metric, and the one that tells a
-- supervisor whether the queue is fair rather than merely moving.
create or replace function investigator_workload()
returns table (investigator text, assigned bigint, overdue bigint)
language sql stable security definer set search_path = public as $$
  select coalesce(u.full_name, 'Unassigned') as investigator,
         count(*)                            as assigned,
         count(*) filter (where c.sla_due < now()
                            and c.status not in ('CLOSED','QUARANTINED')) as overdue
  from cases c
  left join app_users u on u.id = c.assigned_to
  where c.status in ('REVIEW_PENDING','VERIFIED')
  group by coalesce(u.full_name, 'Unassigned')
  order by assigned desc;
$$;

-- Fraud-Ring Radar: cross-case correlation no single reviewer would ever see,
-- because each case looks unremarkable on its own.
create or replace function detect_fraud_rings(min_cases int default 3)
returns table (
  signal_type  text,
  signal_value text,
  case_count   bigint,
  total_rm     numeric,
  account_nos  text[]
)
language sql stable security definer set search_path = public as $$
  select 'merchant'                          as signal_type,
         t.merchant                          as signal_value,
         count(distinct t.account_no)        as case_count,
         sum(t.amount_rm)                    as total_rm,
         array_agg(distinct t.account_no)    as account_nos
  from transactions t
  where t.merchant is not null
    and t.direction = 'DEBIT'
  group by t.merchant
  having count(distinct t.account_no) >= min_cases

  union all

  select 'device',
         t.device_id,
         count(distinct t.account_no),
         sum(t.amount_rm),
         array_agg(distinct t.account_no)
  from transactions t
  where t.device_id is not null
    and t.direction = 'DEBIT'
  group by t.device_id
  having count(distinct t.account_no) >= min_cases

  order by case_count desc, total_rm desc;
$$;

grant execute on function dashboard_metrics()      to anon, authenticated, service_role;
grant execute on function category_volumes()       to anon, authenticated, service_role;
grant execute on function investigator_workload()  to anon, authenticated, service_role;
grant execute on function detect_fraud_rings(int)  to anon, authenticated, service_role;
