create table if not exists projects (
  project_key text primary key,
  display_name text not null,
  project_path text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
