-- CaseZero — remove Supabase public-schema default privileges, then opt in only
-- to the operations required by the API boundary.

revoke all on stakeholder_settings from anon, authenticated, service_role;
revoke all on settings_events from anon, authenticated, service_role;
revoke all on assistant_receipts from anon, authenticated, service_role;
revoke all on sequence settings_events_id_seq from anon, authenticated, service_role;

-- Signed-in clients may read only what RLS permits. They never write directly.
grant select on stakeholder_settings to authenticated;
grant select on settings_events to authenticated;
grant select on assistant_receipts to authenticated;

-- FastAPI owns the mutation boundary. Evidence tables remain append-only.
grant select, insert, update on stakeholder_settings to service_role;
grant select, insert on settings_events to service_role;
grant select, insert on assistant_receipts to service_role;
grant usage, select on sequence settings_events_id_seq to service_role;
