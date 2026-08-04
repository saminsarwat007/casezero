-- Axiom public live demo: synthetic input, real execution, durable proof.
-- No table or function is callable from anon/authenticated PostgREST roles.

create sequence if not exists public.case_ref_seq;

select setval(
  'public.case_ref_seq',
  greatest(
    coalesce(
      (
        select max(right(case_ref, 6)::bigint)
        from public.cases
        where case_ref ~ '^MYB-[0-9]{4}-[0-9]{6}$'
      ),
      0
    ),
    1
  ),
  true
);

create or replace function public.allocate_case_ref()
returns text
language sql
security definer
set search_path = ''
as $$
  select
    'MYB-'
    || extract(year from timezone('UTC', now()))::int::text
    || '-'
    || lpad(nextval('public.case_ref_seq')::text, 6, '0');
$$;

revoke all on sequence public.case_ref_seq from anon, authenticated, service_role;
revoke execute on function public.allocate_case_ref() from public, anon, authenticated;
grant execute on function public.allocate_case_ref() to service_role;

create table public.public_demo_runs (
  id               uuid primary key default gen_random_uuid(),
  token            text not null unique,
  fingerprint_hash text not null,
  state            text not null default 'RUNNING'
                   check (state in ('RUNNING', 'COMPLETED', 'FAILED')),
  fixture          text not null default 'unauthorised_transaction_v1',
  case_id          uuid references public.cases(id) on delete set null,
  case_ref         text,
  proof            jsonb not null default '{}'::jsonb,
  error_code       text,
  started_at       timestamptz not null default now(),
  finished_at      timestamptz
);

create index public_demo_runs_started_idx
  on public.public_demo_runs (started_at desc);
create index public_demo_runs_fingerprint_idx
  on public.public_demo_runs (fingerprint_hash, started_at desc);

alter table public.public_demo_runs enable row level security;
revoke all on table public.public_demo_runs from anon, authenticated, service_role;
grant select, insert, update on table public.public_demo_runs to service_role;

create or replace function public.reserve_public_demo_run(
  p_fingerprint_hash text,
  p_token text,
  p_daily_limit int,
  p_hourly_limit int
)
returns public.public_demo_runs
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_daily_count int;
  v_hourly_count int;
  v_existing public.public_demo_runs;
  v_created public.public_demo_runs;
begin
  if length(p_fingerprint_hash) <> 64 or length(p_token) < 24 then
    raise exception using errcode = '22023', message = 'PUBLIC_DEMO_INVALID_RESERVATION';
  end if;

  -- One transaction-scoped lock makes both limits atomic across Vercel instances.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('casezero:public-live-demo', 0)
  );

  select count(*) into v_hourly_count
  from public.public_demo_runs
  where fingerprint_hash = p_fingerprint_hash
    and started_at >= now() - interval '1 hour';

  if v_hourly_count >= greatest(p_hourly_limit, 1) then
    select * into v_existing
    from public.public_demo_runs
    where fingerprint_hash = p_fingerprint_hash
      and state = 'COMPLETED'
      and started_at >= now() - interval '1 hour'
    order by finished_at desc nulls last
    limit 1;

    if found then
      return v_existing;
    end if;
    raise exception using errcode = 'P0001', message = 'PUBLIC_DEMO_HOURLY_LIMIT';
  end if;

  select count(*) into v_daily_count
  from public.public_demo_runs
  where started_at >= date_trunc('day', now());

  if v_daily_count >= greatest(p_daily_limit, 1) then
    raise exception using errcode = 'P0001', message = 'PUBLIC_DEMO_DAILY_LIMIT';
  end if;

  insert into public.public_demo_runs (token, fingerprint_hash)
  values (p_token, p_fingerprint_hash)
  returning * into v_created;

  return v_created;
end;
$$;

revoke execute on function public.reserve_public_demo_run(text, text, int, int)
  from public, anon, authenticated;
grant execute on function public.reserve_public_demo_run(text, text, int, int)
  to service_role;
