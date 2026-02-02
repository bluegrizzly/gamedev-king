create or replace function public.match_chunks(
  query_embedding vector(1536),
  match_count int,
  source_filter uuid default null,
  agent_filter text default null
)
returns table (
  source_id uuid,
  chunk_index int,
  content text,
  distance float4,
  title text
)
language sql
as $$
  select
    chunks.source_id,
    chunks.chunk_index,
    chunks.content,
    (chunks.embedding <-> query_embedding) as distance,
    sources.title
  from chunks
  join sources on sources.id = chunks.source_id
  where chunks.embedding is not null
    and (source_filter is null or chunks.source_id = source_filter)
    and (agent_filter is null or sources.agent_id = agent_filter)
  order by chunks.embedding <-> query_embedding
  limit match_count;
$$;
