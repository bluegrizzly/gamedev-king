alter table sources
  add column if not exists scope text default 'generic',
  add column if not exists project_key text;

alter table chunks
  add column if not exists scope text default 'generic',
  add column if not exists project_key text;

update sources
  set scope = 'generic',
      project_key = null
  where scope is null;

update chunks
  set scope = 'generic',
      project_key = null
  where scope is null;

alter table sources
  alter column scope set default 'generic',
  alter column scope set not null;

alter table chunks
  alter column scope set default 'generic',
  alter column scope set not null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'sources_scope_check') then
    alter table sources
      add constraint sources_scope_check check (scope in ('generic', 'project'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'sources_scope_project_check') then
    alter table sources
      add constraint sources_scope_project_check check (
        (scope = 'generic' and project_key is null)
        or (scope = 'project' and project_key is not null)
      );
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chunks_scope_check') then
    alter table chunks
      add constraint chunks_scope_check check (scope in ('generic', 'project'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chunks_scope_project_check') then
    alter table chunks
      add constraint chunks_scope_project_check check (
        (scope = 'generic' and project_key is null)
        or (scope = 'project' and project_key is not null)
      );
  end if;
end $$;

create index if not exists sources_scope_project_idx on sources (scope, project_key);
create index if not exists chunks_scope_project_idx on chunks (scope, project_key);
