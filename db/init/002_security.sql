create table if not exists audit_events (
  id bigserial primary key,
  occurred_at timestamptz not null default now(),
  actor_user_id text,
  actor_role text,
  action text not null,
  entity_table text,
  entity_id text,
  request_id text,
  ip_address inet,
  user_agent text,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists audit_events_occurred_at_idx on audit_events (occurred_at desc);
create index if not exists audit_events_actor_idx on audit_events (actor_user_id, occurred_at desc);
create index if not exists audit_events_entity_idx on audit_events (entity_table, entity_id);

create table if not exists security_events (
  id bigserial primary key,
  occurred_at timestamptz not null default now(),
  severity text not null default 'info',
  event_type text not null,
  actor_user_id text,
  request_id text,
  ip_address inet,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists security_events_time_idx on security_events (occurred_at desc);
create index if not exists security_events_type_idx on security_events (event_type, severity);

create or replace function app_user_id()
returns text
language sql
stable
as $$
  select nullif(current_setting('app.user_id', true), '')
$$;

create or replace function app_role()
returns text
language sql
stable
as $$
  select coalesce(nullif(current_setting('app.role', true), ''), 'anonymous')
$$;

create or replace function app_is_admin()
returns boolean
language sql
stable
as $$
  select app_role() in ('admin', 'service')
$$;

create or replace function app_is_staff()
returns boolean
language sql
stable
as $$
  select app_role() in ('admin', 'mod', 'service')
$$;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_readonly') then
    create role dark_jutsu_readonly nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_app') then
    create role dark_jutsu_app nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_service') then
    create role dark_jutsu_service nologin;
  end if;
end;
$$;

grant usage on schema public to dark_jutsu_readonly, dark_jutsu_app, dark_jutsu_service;
grant select on all tables in schema public to dark_jutsu_readonly;
grant select, insert, update, delete on all tables in schema public to dark_jutsu_app;
grant select, insert, update, delete on all tables in schema public to dark_jutsu_service;
grant usage, select on all sequences in schema public to dark_jutsu_app, dark_jutsu_service;

alter default privileges in schema public grant select on tables to dark_jutsu_readonly;
alter default privileges in schema public grant select, insert, update, delete on tables to dark_jutsu_app;
alter default privileges in schema public grant select, insert, update, delete on tables to dark_jutsu_service;
alter default privileges in schema public grant usage, select on sequences to dark_jutsu_app, dark_jutsu_service;

revoke all on signup_requests from dark_jutsu_readonly;
grant select (
  id,
  requested_uid,
  nickname,
  nickname_key,
  badge,
  sector,
  status,
  duplicated,
  created_at,
  decided_at,
  decided_by
) on signup_requests to dark_jutsu_readonly;

revoke all on chat_rooms from dark_jutsu_readonly;
grant select (id, label, public, updated_at) on chat_rooms to dark_jutsu_readonly;

create or replace view v_users_safe as
select
  id,
  firebase_uid,
  nickname,
  badge,
  sector,
  role,
  active,
  created_at,
  updated_at
from users;

create or replace view v_signup_requests_safe as
select
  id,
  requested_uid,
  nickname,
  badge,
  sector,
  status,
  duplicated,
  created_at,
  decided_at,
  decided_by
from signup_requests;

create or replace view v_chat_rooms_safe as
select
  id,
  label,
  public,
  updated_at
from chat_rooms;

grant select on v_users_safe, v_signup_requests_safe, v_chat_rooms_safe to dark_jutsu_readonly, dark_jutsu_app, dark_jutsu_service;

alter table users enable row level security;
alter table import_runs enable row level security;
alter table signup_requests enable row level security;
alter table banned_users enable row level security;
alter table inventory_items enable row level security;
alter table inventory_item_addresses enable row level security;
alter table inventory_item_limits enable row level security;
alter table inventory_adjustments enable row level security;
alter table inventory_balance_history enable row level security;
alter table inventory_movements enable row level security;
alter table inventory_snapshots enable row level security;
alter table counting_sessions enable row level security;
alter table counting_items enable row level security;
alter table counting_empty_checks enable row level security;
alter table counting_drafts enable row level security;
alter table counting_machine_status enable row level security;
alter table counting_control_events enable row level security;
alter table label_print_jobs enable row level security;
alter table label_user_ranking enable row level security;
alter table dashboard_panels enable row level security;
alter table purchase_evaluations enable row level security;
alter table cooperat_import_runs enable row level security;
alter table cooperat_purchase_codes enable row level security;
alter table cooperat_purchase_events enable row level security;
alter table occurrences enable row level security;
alter table occurrence_history enable row level security;
alter table chat_rooms enable row level security;
alter table chat_messages enable row level security;
alter table chat_read_states enable row level security;
alter table app_settings enable row level security;
alter table automus_releases enable row level security;
alter table stg_files enable row level security;
alter table stg_rows enable row level security;
alter table audit_events enable row level security;
alter table security_events enable row level security;

create policy users_admin_all on users
  for all using (app_is_admin()) with check (app_is_admin());

create policy users_self_read on users
  for select using (id = app_user_id() or firebase_uid = app_user_id() or app_is_staff());

create policy import_runs_service_all on import_runs
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy import_runs_admin_read on import_runs
  for select using (app_is_admin());

create policy signup_admin_all on signup_requests
  for all using (app_is_admin()) with check (app_is_admin());

create policy signup_public_insert on signup_requests
  for insert with check (status = 'pendente');

create policy banned_admin_all on banned_users
  for all using (app_is_admin()) with check (app_is_admin());

create policy inventory_active_read on inventory_items
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy inventory_staff_write on inventory_items
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_addresses_read on inventory_item_addresses
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy inventory_addresses_staff_write on inventory_item_addresses
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_limits_read on inventory_item_limits
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy inventory_limits_staff_write on inventory_item_limits
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_adjustments_read on inventory_adjustments
  for select using (app_role() in ('mod', 'admin', 'service'));

create policy inventory_adjustments_staff_write on inventory_adjustments
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_history_read on inventory_balance_history
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy inventory_history_staff_write on inventory_balance_history
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_movements_read on inventory_movements
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy inventory_movements_staff_write on inventory_movements
  for all using (app_is_staff()) with check (app_is_staff());

create policy inventory_snapshots_service_only on inventory_snapshots
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy counting_sessions_read on counting_sessions
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_sessions_write on counting_sessions
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_sessions_staff_update on counting_sessions
  for update using (app_is_staff()) with check (app_is_staff());

create policy counting_sessions_service_maintenance on counting_sessions
  for delete using (app_role() = 'service');

create policy counting_items_read on counting_items
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_items_write on counting_items
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_items_service_maintenance on counting_items
  for delete using (app_role() = 'service');

create policy counting_empty_read on counting_empty_checks
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_empty_write on counting_empty_checks
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_empty_service_maintenance on counting_empty_checks
  for delete using (app_role() = 'service');

create policy counting_drafts_owner_all on counting_drafts
  for all using (uid = app_user_id() or user_id = app_user_id() or app_is_staff())
  with check (uid = app_user_id() or user_id = app_user_id() or app_is_staff());

create policy counting_machine_status_read on counting_machine_status
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy counting_machine_status_write on counting_machine_status
  for all using (user_id = app_user_id() or app_is_staff())
  with check (user_id = app_user_id() or app_is_staff());

create policy counting_control_staff_all on counting_control_events
  for all using (app_is_staff()) with check (app_is_staff());

create policy label_jobs_read on label_print_jobs
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy label_jobs_write on label_print_jobs
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy label_jobs_service_maintenance on label_print_jobs
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy label_ranking_read on label_user_ranking
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy label_ranking_service_write on label_user_ranking
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy dashboard_panels_read on dashboard_panels
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy dashboard_panels_staff_write on dashboard_panels
  for all using (app_is_staff()) with check (app_is_staff());

create policy purchase_eval_read on purchase_evaluations
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy purchase_eval_staff_write on purchase_evaluations
  for all using (app_is_staff()) with check (app_is_staff());

create policy cooperat_read on cooperat_purchase_codes
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy cooperat_events_read on cooperat_purchase_events
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy cooperat_import_service_all on cooperat_import_runs
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy cooperat_codes_service_write on cooperat_purchase_codes
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy cooperat_events_service_write on cooperat_purchase_events
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy occurrences_read on occurrences
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy occurrences_insert on occurrences
  for insert with check (operator_user_id = app_user_id() or app_is_staff());

create policy occurrences_update_allowed on occurrences
  for update using (app_is_staff() or operator_user_id = app_user_id() or responsible_user_id = app_user_id())
  with check (app_is_staff() or operator_user_id = app_user_id() or responsible_user_id = app_user_id());

create policy occurrences_service_maintenance on occurrences
  for delete using (app_role() = 'service');

create policy occurrence_history_read on occurrence_history
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy occurrence_history_write on occurrence_history
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy occurrence_history_service_maintenance on occurrence_history
  for delete using (app_role() = 'service');

create policy chat_rooms_read on chat_rooms
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy chat_rooms_admin_write on chat_rooms
  for all using (app_is_admin()) with check (app_is_admin());

create policy chat_messages_read on chat_messages
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy chat_messages_write on chat_messages
  for insert with check (app_role() in ('op', 'mod', 'admin', 'service'));

create policy chat_read_owner_all on chat_read_states
  for all using (user_id = app_user_id() or app_is_staff())
  with check (user_id = app_user_id() or app_is_staff());

create policy app_settings_read on app_settings
  for select using (app_role() in ('op', 'mod', 'admin', 'service'));

create policy app_settings_staff_write on app_settings
  for all using (app_is_staff()) with check (app_is_staff());

create policy automus_releases_admin_all on automus_releases
  for all using (app_is_admin()) with check (app_is_admin());

create policy staging_service_all_files on stg_files
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy staging_service_all_rows on stg_rows
  for all using (app_role() = 'service') with check (app_role() = 'service');

create policy audit_admin_read on audit_events
  for select using (app_is_admin());

create policy audit_service_write on audit_events
  for insert with check (app_role() = 'service' or app_is_staff());

create policy security_admin_read on security_events
  for select using (app_is_admin());

create policy security_service_write on security_events
  for insert with check (app_role() = 'service' or app_is_staff());

insert into schema_migrations (version)
values ('002_security')
on conflict (version) do nothing;
