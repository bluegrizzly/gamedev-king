alter table if exists sources
  add column if not exists agent_ids text[];

update sources
set agent_ids = array[agent_id]
where agent_ids is null
  and agent_id is not null;

create index if not exists sources_agent_ids_gin on sources using gin(agent_ids);
