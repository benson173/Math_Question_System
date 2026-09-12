-- Math Question System - Supabase schema
--
-- Three tables, as the guide names them. Run this once in the SQL editor.
--
--   source_documents   one row per distinct PDF, keyed by content hash
--   extraction_runs    one row per pipeline run over a document
--   questions          one row per question per run
--
-- Re-ingesting the same PDF adds a new run and marks the previous one
-- is_current = false, so history is kept and "the questions" for a paper is
-- always the current run's rows.

create extension if not exists "pgcrypto";

create table if not exists source_documents (
  id             uuid primary key default gen_random_uuid(),
  sha256         text not null unique,
  file_name      text not null,
  page_count     integer not null,
  byte_size      bigint not null,
  first_seen_at  timestamptz not null default now()
);

create table if not exists extraction_runs (
  id                       uuid primary key default gen_random_uuid(),
  run_id                   text not null unique,
  source_document_id       uuid not null references source_documents(id) on delete cascade,
  extracted_at             timestamptz not null,
  extraction_version       text not null,
  question_object_version  text not null,
  model                    text not null,
  question_count           integer not null,
  issue_count              integer not null,
  blocking                 boolean not null default false,
  issues                   jsonb not null default '[]'::jsonb,
  repairs                  jsonb not null default '[]'::jsonb,
  is_current               boolean not null default true,
  created_at               timestamptz not null default now()
);

create table if not exists questions (
  id                   uuid primary key default gen_random_uuid(),
  extraction_run_id    uuid not null references extraction_runs(id) on delete cascade,
  source_document_id   uuid not null references source_documents(id) on delete cascade,
  source_question_id   text not null,
  position             integer not null,
  question_type        text not null default 'open',
  question_text        text not null,
  options              jsonb not null default '[]'::jsonb,
  marks                numeric,
  group_marks          numeric,
  group_marks_scope    text,
  answer               text,
  worked_solution      text,
  page_start           integer not null,
  page_end             integer not null,
  diagram_required     boolean not null default false,
  diagram_region       jsonb,
  table_regions        jsonb not null default '[]'::jsonb,
  extraction_notes     jsonb not null default '[]'::jsonb,
  images               jsonb not null default '[]'::jsonb,
  unique (extraction_run_id, source_question_id)
);

create index if not exists questions_document_idx  on questions (source_document_id);
create index if not exists questions_type_idx      on questions (question_type);
create index if not exists runs_document_idx       on extraction_runs (source_document_id);
create index if not exists runs_current_idx        on extraction_runs (source_document_id) where is_current;

-- The questions of the current run for every paper.
create or replace view current_questions as
  select q.*
  from questions q
  join extraction_runs r on r.id = q.extraction_run_id
  where r.is_current;
