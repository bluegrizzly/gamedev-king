-- When no project is selected (project_key_filter is null), hybrid mode
-- should still return project-scoped chunks so the agent sees all content
-- (e.g. on Mac when activeProjectKey is not set in localStorage).
-- Also use case-insensitive project_key comparison for cross-platform consistency.
create or replace function public.match_chunks(
  query_embedding vector(1536),
  match_count int,
  source_filter uuid default null,
  agent_filter text[] default null,
  scope_mode text default 'hybrid',
  project_key_filter text default null
)
returns table (
  source_id uuid,
  chunk_index int,
  content text,
  distance float4,
  title text,
  scope text,
  project_key text
)
language sql
as $$
  select
    chunks.source_id,
    chunks.chunk_index,
    chunks.content,
    (chunks.embedding <-> query_embedding) as distance,
    sources.title,
    chunks.scope,
    chunks.project_key
  from chunks
  join sources on sources.id = chunks.source_id
  where chunks.embedding is not null
    and (source_filter is null or chunks.source_id = source_filter)
    and (
      agent_filter is null
      or (sources.agent_ids is not null and sources.agent_ids && agent_filter)
      or (sources.agent_id is not null and sources.agent_id = any(agent_filter))
    )
    and (
      (scope_mode = 'generic' and chunks.scope = 'generic')
      or (
        scope_mode = 'project'
        and chunks.scope = 'project'
        and project_key_filter is not null
        and lower(chunks.project_key) = lower(project_key_filter)
      )
      or (
        scope_mode = 'hybrid'
        and (
          chunks.scope = 'generic'
          or (
            chunks.scope = 'project'
            and (
              project_key_filter is null
              or (project_key_filter is not null and lower(chunks.project_key) = lower(project_key_filter))
            )
          )
        )
      )
    )
  order by
    (chunks.embedding <-> query_embedding)
    - case
        when scope_mode = 'hybrid' and chunks.scope = 'project' then 0.02
        else 0
      end
  limit match_count;
$$;
