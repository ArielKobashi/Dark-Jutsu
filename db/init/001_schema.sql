create extension if not exists pgcrypto;

create table if not exists schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists import_runs (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  source_path text,
  source_hash text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  totals jsonb not null default '{}'::jsonb,
  notes text,
  raw_metadata jsonb not null default '{}'::jsonb
);

create table if not exists users (
  id text primary key,
  firebase_uid text unique,
  nickname text not null,
  nickname_key text generated always as (lower(trim(nickname))) stored,
  badge text,
  sector text,
  role text not null default 'op',
  active boolean not null default true,
  password_status text,
  created_at timestamptz,
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create unique index if not exists users_nickname_key_active_idx
  on users (nickname_key)
  where active;

create index if not exists users_role_idx on users (role);
create index if not exists users_sector_idx on users (sector);

drop trigger if exists trg_users_updated_at on users;
create trigger trg_users_updated_at
before update on users
for each row execute function set_updated_at();

create table if not exists signup_requests (
  id text primary key,
  requested_uid text,
  nickname text not null,
  nickname_key text generated always as (lower(trim(nickname))) stored,
  password_plain_legacy text,
  badge text,
  sector text,
  status text not null default 'pendente',
  duplicated boolean not null default false,
  created_at timestamptz,
  decided_at timestamptz,
  decided_by text references users(id),
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists signup_requests_status_idx on signup_requests (status);
create index if not exists signup_requests_nickname_badge_idx on signup_requests (nickname_key, badge);

create table if not exists banned_users (
  user_id text primary key,
  nickname text,
  badge text,
  sector text,
  banned_at timestamptz,
  banned_by text references users(id),
  reason text,
  raw_data jsonb not null default '{}'::jsonb
);

create table if not exists inventory_items (
  id bigserial primary key,
  legacy_key text unique,
  protheus_code text,
  protheus_key text,
  cooperat_code text,
  description text,
  primary_address text,
  primary_warehouse text,
  balance numeric,
  min_qty numeric,
  max_qty numeric,
  reorder_qty numeric,
  limit_source text,
  min_source text,
  max_source text,
  reorder_source text,
  is_dead boolean not null default false,
  status text,
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create unique index if not exists inventory_items_protheus_active_idx
  on inventory_items (protheus_code)
  where protheus_code is not null and protheus_code <> '' and is_dead = false;

create index if not exists inventory_items_cooperat_idx on inventory_items (cooperat_code);
create index if not exists inventory_items_description_idx on inventory_items using gin (to_tsvector('portuguese', coalesce(description, '')));
create index if not exists inventory_items_status_idx on inventory_items (status);
create index if not exists inventory_items_dead_idx on inventory_items (is_dead);

drop trigger if exists trg_inventory_items_updated_at on inventory_items;
create trigger trg_inventory_items_updated_at
before update on inventory_items
for each row execute function set_updated_at();

create table if not exists inventory_item_addresses (
  id bigserial primary key,
  item_id bigint references inventory_items(id) on delete cascade,
  item_legacy_key text,
  address text,
  warehouse text,
  balance numeric,
  source text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists inventory_item_addresses_item_idx on inventory_item_addresses (item_id);
create index if not exists inventory_item_addresses_address_idx on inventory_item_addresses (address);
create index if not exists inventory_item_addresses_warehouse_idx on inventory_item_addresses (warehouse);

create table if not exists inventory_item_limits (
  id bigserial primary key,
  item_id bigint references inventory_items(id) on delete cascade,
  item_legacy_key text,
  source text not null,
  min_qty numeric,
  max_qty numeric,
  reorder_qty numeric,
  previous_balance numeric,
  applied boolean not null default false,
  imported_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists inventory_item_limits_item_idx on inventory_item_limits (item_id);
create index if not exists inventory_item_limits_source_idx on inventory_item_limits (source);

create table if not exists inventory_adjustments (
  id bigserial primary key,
  item_id bigint references inventory_items(id) on delete set null,
  item_legacy_key text,
  legacy_key text,
  min_qty numeric,
  max_qty numeric,
  reorder_qty numeric,
  reason text,
  updated_by_user_id text references users(id),
  updated_by_name text,
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists inventory_adjustments_item_idx on inventory_adjustments (item_id);
create index if not exists inventory_adjustments_legacy_key_idx on inventory_adjustments (legacy_key);

create table if not exists inventory_balance_history (
  id bigserial primary key,
  item_id bigint references inventory_items(id) on delete set null,
  item_legacy_key text,
  event_at timestamptz,
  event_date_label text,
  previous_balance numeric,
  current_balance numeric,
  delta numeric,
  event_type text,
  source text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists inventory_balance_history_item_time_idx
  on inventory_balance_history (item_id, event_at desc);

create index if not exists inventory_balance_history_legacy_time_idx
  on inventory_balance_history (item_legacy_key, event_at desc);

create table if not exists inventory_movements (
  id bigserial primary key,
  item_id bigint references inventory_items(id) on delete set null,
  item_legacy_key text,
  source text,
  source_document text,
  movement_at timestamptz,
  movement_type text,
  quantity numeric,
  status text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists inventory_movements_item_time_idx on inventory_movements (item_id, movement_at desc);
create index if not exists inventory_movements_source_idx on inventory_movements (source);

create table if not exists inventory_snapshots (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  saved_at timestamptz not null default now(),
  hash_before text,
  hash_after text,
  updated_by text,
  item_count integer,
  dead_item_count integer,
  payload jsonb not null,
  raw_metadata jsonb not null default '{}'::jsonb
);

create index if not exists inventory_snapshots_saved_at_idx on inventory_snapshots (saved_at desc);

create table if not exists counting_sessions (
  id uuid primary key default gen_random_uuid(),
  legacy_path text unique,
  session_date date,
  user_id text references users(id),
  user_name text,
  uid text,
  machine text,
  started_at timestamptz,
  created_at timestamptz,
  total_items integer,
  total_quantity_items integer,
  total_empty_checks integer,
  is_draft boolean not null default false,
  source text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists counting_sessions_date_user_idx on counting_sessions (session_date desc, user_name);
create index if not exists counting_sessions_machine_idx on counting_sessions (machine);

create table if not exists counting_items (
  id bigserial primary key,
  session_id uuid not null references counting_sessions(id) on delete cascade,
  item_id bigint references inventory_items(id) on delete set null,
  item_legacy_key text,
  protheus_code text,
  cooperat_code text,
  description text,
  warehouse text,
  address text,
  system_balance numeric,
  reorder_qty numeric,
  counted_qty numeric,
  diverges boolean,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists counting_items_session_idx on counting_items (session_id);
create index if not exists counting_items_item_idx on counting_items (item_id);
create index if not exists counting_items_diverges_idx on counting_items (diverges);

create table if not exists counting_empty_checks (
  id bigserial primary key,
  session_id uuid not null references counting_sessions(id) on delete cascade,
  address text,
  warehouse text,
  status text,
  machine text,
  section text,
  shelf text,
  box text,
  description text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists counting_empty_checks_session_idx on counting_empty_checks (session_id);
create index if not exists counting_empty_checks_status_idx on counting_empty_checks (status);

create table if not exists counting_drafts (
  id uuid primary key default gen_random_uuid(),
  user_id text references users(id),
  uid text,
  user_name text,
  cycle text,
  machine text,
  updated_at timestamptz not null default now(),
  values_json jsonb not null default '{}'::jsonb,
  empty_checks_json jsonb not null default '{}'::jsonb,
  system_balances_json jsonb not null default '{}'::jsonb,
  session_json jsonb not null default '{}'::jsonb,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists counting_drafts_uid_idx on counting_drafts (uid);
create index if not exists counting_drafts_cycle_user_idx on counting_drafts (cycle, user_name);

create table if not exists counting_machine_status (
  id bigserial primary key,
  cycle text not null,
  machine_key text not null,
  user_key text not null,
  user_id text references users(id),
  user_name text,
  open boolean,
  stage text,
  group_name text,
  machine_label text,
  counted integer,
  total integer,
  completed boolean,
  item_key text,
  item_index integer,
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb,
  unique (cycle, machine_key, user_key)
);

create index if not exists counting_machine_status_cycle_idx on counting_machine_status (cycle);
create index if not exists counting_machine_status_updated_idx on counting_machine_status (updated_at desc);

create table if not exists counting_control_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  cycle text,
  created_at timestamptz not null default now(),
  created_by text references users(id),
  raw_data jsonb not null default '{}'::jsonb
);

create table if not exists label_print_jobs (
  id uuid primary key default gen_random_uuid(),
  legacy_path text unique,
  user_id text references users(id),
  user_name text,
  job_date date,
  created_at timestamptz,
  total_labels integer,
  total_codes_submitted integer,
  by_size jsonb not null default '{}'::jsonb,
  had_missing_codes boolean not null default false,
  source text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists label_print_jobs_date_user_idx on label_print_jobs (job_date desc, user_name);

create table if not exists label_user_ranking (
  user_key text primary key,
  user_name text,
  total_labels integer not null default 0,
  events integer not null default 0,
  updated_at timestamptz
);

create table if not exists dashboard_panels (
  id text primary key,
  title text,
  row_limit integer not null default 8,
  hidden_codes text[] not null default array[]::text[],
  updated_at timestamptz not null default now(),
  updated_by text references users(id),
  raw_data jsonb not null default '{}'::jsonb
);

drop trigger if exists trg_dashboard_panels_updated_at on dashboard_panels;
create trigger trg_dashboard_panels_updated_at
before update on dashboard_panels
for each row execute function set_updated_at();

create table if not exists purchase_evaluations (
  id bigserial primary key,
  legacy_key text unique,
  item_id bigint references inventory_items(id) on delete set null,
  item_code text not null,
  decision text not null,
  kanban_status text,
  note text,
  evaluated_at timestamptz,
  evaluated_by text,
  updated_at timestamptz not null default now(),
  updated_by text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists purchase_evaluations_item_code_idx on purchase_evaluations (item_code);
create index if not exists purchase_evaluations_decision_idx on purchase_evaluations (decision);
create index if not exists purchase_evaluations_kanban_idx on purchase_evaluations (kanban_status);

drop trigger if exists trg_purchase_evaluations_updated_at on purchase_evaluations;
create trigger trg_purchase_evaluations_updated_at
before update on purchase_evaluations
for each row execute function set_updated_at();

create table if not exists cooperat_import_runs (
  id uuid primary key default gen_random_uuid(),
  generated_at timestamptz,
  description text,
  quantity_rule text,
  value_rule text,
  event_limit_per_code integer,
  source_files jsonb not null default '[]'::jsonb,
  total_codes integer,
  total_events integer,
  source_hash text,
  imported_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create table if not exists cooperat_purchase_codes (
  code text primary key,
  latest_description text,
  total_events integer not null default 0,
  total_purchase_qty numeric,
  total_requested_qty numeric,
  total_supplied_qty numeric,
  total_low_value numeric,
  first_date date,
  last_date date,
  avg_purchase_qty numeric,
  avg_requested_qty numeric,
  avg_supplied_qty numeric,
  avg_low_value numeric,
  import_run_id uuid references cooperat_import_runs(id) on delete set null,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists cooperat_purchase_codes_last_date_idx on cooperat_purchase_codes (last_date desc);
create index if not exists cooperat_purchase_codes_desc_idx on cooperat_purchase_codes using gin (to_tsvector('portuguese', coalesce(latest_description, '')));

create table if not exists cooperat_purchase_events (
  id bigserial primary key,
  code text not null references cooperat_purchase_codes(code) on delete cascade,
  requisition text,
  event_date date,
  event_date_label text,
  description text,
  unit text,
  requested_qty numeric,
  supplied_qty numeric,
  low_value numeric,
  purchase_qty numeric,
  source text,
  origin text,
  import_run_id uuid references cooperat_import_runs(id) on delete set null,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists cooperat_purchase_events_code_date_idx on cooperat_purchase_events (code, event_date desc);
create index if not exists cooperat_purchase_events_requisition_idx on cooperat_purchase_events (requisition);

create table if not exists occurrences (
  id text primary key,
  source_path text,
  created_at timestamptz,
  date_label text,
  time_label text,
  operator_user_id text references users(id),
  operator_name text,
  operator_badge text,
  operator_sector text,
  involved_name text,
  involved_badge text,
  involved_sector text,
  type text,
  severity text,
  item_code text,
  item_description text,
  quantity numeric,
  description text,
  status text,
  responsible_user_id text references users(id),
  responsible_name text,
  responsible_badge text,
  responsible_sector text,
  responsible_assigned_at timestamptz,
  treatment_text text,
  treatment_signature text,
  treatment_at timestamptz,
  treatment_by_user_id text references users(id),
  treatment_by_name text,
  treatment_document jsonb not null default '{}'::jsonb,
  updated_at timestamptz,
  updated_by text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists occurrences_status_idx on occurrences (status);
create index if not exists occurrences_created_at_idx on occurrences (created_at desc);
create index if not exists occurrences_severity_idx on occurrences (severity);
create index if not exists occurrences_item_code_idx on occurrences (item_code);

create table if not exists occurrence_history (
  id bigserial primary key,
  occurrence_id text not null references occurrences(id) on delete cascade,
  legacy_key text,
  event_at timestamptz,
  by_user_id text references users(id),
  by_name text,
  action text,
  value text,
  raw_data jsonb not null default '{}'::jsonb
);

create index if not exists occurrence_history_occurrence_idx on occurrence_history (occurrence_id, event_at);

create table if not exists chat_rooms (
  id text primary key,
  label text,
  public boolean not null default false,
  password_hash text,
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

drop trigger if exists trg_chat_rooms_updated_at on chat_rooms;
create trigger trg_chat_rooms_updated_at
before update on chat_rooms
for each row execute function set_updated_at();

create table if not exists chat_messages (
  id bigserial primary key,
  legacy_key text,
  room_id text not null references chat_rooms(id) on delete cascade,
  user_id text references users(id),
  name text,
  text text,
  time_label text,
  created_at timestamptz,
  message_type text,
  event text,
  session_id text,
  raw_data jsonb not null default '{}'::jsonb,
  unique (room_id, legacy_key)
);

create index if not exists chat_messages_room_time_idx on chat_messages (room_id, created_at desc);

create table if not exists chat_read_states (
  user_id text not null references users(id) on delete cascade,
  room_id text not null references chat_rooms(id) on delete cascade,
  last_seen_at timestamptz,
  raw_data jsonb not null default '{}'::jsonb,
  primary key (user_id, room_id)
);

create table if not exists app_settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now(),
  updated_by text references users(id),
  raw_data jsonb not null default '{}'::jsonb
);

drop trigger if exists trg_app_settings_updated_at on app_settings;
create trigger trg_app_settings_updated_at
before update on app_settings
for each row execute function set_updated_at();

create table if not exists automus_releases (
  id bigserial primary key,
  channel text not null default 'latest',
  version text,
  package_url text,
  notes text,
  published_at timestamptz not null default now(),
  published_by text,
  raw_manifest jsonb not null default '{}'::jsonb
);

create unique index if not exists automus_releases_channel_version_idx on automus_releases (channel, version);
create index if not exists automus_releases_published_idx on automus_releases (published_at desc);

create table if not exists stg_files (
  id uuid primary key default gen_random_uuid(),
  source_name text not null,
  source_path text,
  source_hash text,
  imported_at timestamptz not null default now(),
  row_count integer,
  raw_metadata jsonb not null default '{}'::jsonb
);

create table if not exists stg_rows (
  id bigserial primary key,
  stg_file_id uuid not null references stg_files(id) on delete cascade,
  sheet_name text,
  row_number integer,
  row_data jsonb not null
);

create index if not exists stg_rows_file_idx on stg_rows (stg_file_id);
create index if not exists stg_rows_sheet_idx on stg_rows (sheet_name);

create or replace view v_label_user_ranking as
select
  coalesce(user_name, 'desconhecido') as user_name,
  count(*)::integer as events,
  coalesce(sum(total_labels), 0)::integer as total_labels,
  max(created_at) as updated_at
from label_print_jobs
group by coalesce(user_name, 'desconhecido');

insert into chat_rooms (id, label, public)
values
  ('publica', 'Publica', true),
  ('sala1', 'Sala 1', false),
  ('sala2', 'Sala 2', false),
  ('sala3', 'Sala 3', false)
on conflict (id) do nothing;

insert into schema_migrations (version)
values ('001_schema')
on conflict (version) do nothing;
