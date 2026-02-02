alter table if exists sources
  add column if not exists agent_id text;

create index if not exists sources_agent_id_idx on sources(agent_id);
