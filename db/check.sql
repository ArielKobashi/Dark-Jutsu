select current_database() as database_name, current_user as user_name, now() as checked_at;

select count(*) as application_tables
from information_schema.tables
where table_schema = 'public'
  and table_type = 'BASE TABLE';

select table_name
from information_schema.tables
where table_schema = 'public'
  and table_type = 'BASE TABLE'
order by table_name;

select version
from schema_migrations
order by applied_at;

select rolname
from pg_roles
where rolname in ('dark_jutsu_readonly', 'dark_jutsu_app', 'dark_jutsu_service')
order by rolname;

select
  count(*) filter (where relrowsecurity) as tables_with_rls,
  count(*) as application_tables_checked
from pg_class
where relkind = 'r'
  and relnamespace = 'public'::regnamespace
  and relname not like 'pg_%';

select count(*) as rls_policies
from pg_policies
where schemaname = 'public';

select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in ('audit_events', 'security_events')
order by table_name;
