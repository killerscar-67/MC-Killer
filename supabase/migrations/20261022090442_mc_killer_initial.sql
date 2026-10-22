-- Backend-only schema. No Supabase browser/Data API access is granted.
create schema if not exists mc_killer;
revoke all on schema mc_killer from public;

do $$
begin
  if not exists (select 1 from pg_roles where rolname='mc_killer_backend') then
    create role mc_killer_backend nologin;
  end if;
end $$;

grant usage on schema mc_killer to mc_killer_backend;

create table mc_killer.users (
  id text primary key,
  email text not null unique,
  password text not null default '',
  google_sub text unique,
  enabled smallint not null default 1 check (enabled in (0,1))
);
create table mc_killer.jobs (
  id text primary key,
  owner text not null references mc_killer.users(id),
  title text not null,
  subject text not null,
  level text not null,
  state text not null check (state in ('queued','processing','ready','failed')),
  created double precision not null,
  updated double precision not null,
  config jsonb not null,
  results jsonb not null default '[]'::jsonb,
  error text not null default '',
  finalized smallint not null default 0 check (finalized in (0,1))
);
create table mc_killer.audit (
  id bigint generated always as identity primary key,
  job text not null references mc_killer.jobs(id),
  actor text not null references mc_killer.users(id),
  at double precision not null,
  action text not null,
  detail jsonb not null
);

create index jobs_owner_created on mc_killer.jobs(owner,created desc);
create index jobs_queued_created on mc_killer.jobs(created) where state='queued';
create index audit_job_id on mc_killer.audit(job,id desc);
create index audit_actor on mc_killer.audit(actor);

alter table mc_killer.users enable row level security;
alter table mc_killer.jobs enable row level security;
alter table mc_killer.audit enable row level security;
create policy backend_users on mc_killer.users to mc_killer_backend using (true) with check (true);
create policy backend_jobs on mc_killer.jobs to mc_killer_backend using (true) with check (true);
create policy backend_audit on mc_killer.audit for insert to mc_killer_backend with check (true);
create policy backend_audit_read on mc_killer.audit for select to mc_killer_backend using (true);
revoke all on all tables in schema mc_killer from public;
grant select,insert,update on mc_killer.users,mc_killer.jobs to mc_killer_backend;
grant select,insert on mc_killer.audit to mc_killer_backend;
grant usage,select on all sequences in schema mc_killer to mc_killer_backend;
