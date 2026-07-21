alter table users
  add column if not exists password_hash text,
  add column if not exists password_changed_at timestamptz,
  add column if not exists password_reset_required boolean not null default false,
  add column if not exists token_version integer not null default 0;

alter table signup_requests
  add column if not exists password_hash text;

create index if not exists users_password_reset_idx on users (password_reset_required) where password_reset_required;

insert into schema_migrations (version)
values ('003_sql_auth')
on conflict (version) do nothing;
