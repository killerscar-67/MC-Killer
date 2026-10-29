-- Backend-only reusable rosters; apply before deploying the roster workflow.
create table mc_killer.rosters (
  id text primary key,
  owner text not null references mc_killer.users(id),
  title text not null,
  school_year text not null,
  version integer not null default 1 check (version > 0),
  students jsonb not null default '[]'::jsonb,
  created double precision not null,
  updated double precision not null
);
create table mc_killer.roster_audit (
  id bigint generated always as identity primary key,
  roster text not null references mc_killer.rosters(id),
  actor text not null references mc_killer.users(id),
  at double precision not null,
  action text not null,
  detail jsonb not null
);
create index rosters_owner on mc_killer.rosters(owner);
create index roster_audit_roster on mc_killer.roster_audit(roster,id);
create index roster_audit_actor on mc_killer.roster_audit(actor);
alter table mc_killer.rosters enable row level security;
alter table mc_killer.roster_audit enable row level security;
create policy backend_rosters on mc_killer.rosters to mc_killer_backend using (true) with check (true);
create policy backend_roster_audit_read on mc_killer.roster_audit for select to mc_killer_backend using (true);
create policy backend_roster_audit_insert on mc_killer.roster_audit for insert to mc_killer_backend with check (true);
revoke all on mc_killer.rosters,mc_killer.roster_audit from public;
-- The private schema has no anonymous/authenticated grants or policies.
grant select,insert,update on mc_killer.rosters to mc_killer_backend;
grant select,insert on mc_killer.roster_audit to mc_killer_backend;
grant usage,select on sequence mc_killer.roster_audit_id_seq to mc_killer_backend;
