-- Math Question System - Supabase schema
--
-- Run this once in the SQL editor. It is safe to run again: it creates what is
-- missing and leaves everything else alone.
--
--   source_documents   one row per distinct PDF, keyed by content hash
--   extraction_runs    one row per pipeline run over a document
--   questions          one row per question per run
--
-- Re-ingesting the same PDF adds a new run and marks the previous one
-- is_current = false, so history is kept and "the questions" for a paper is
-- always the current run's rows.
--
-- If you already created these three tables yourself - for example with the
-- Supabase table editor, which gives a new table only "id" and "created_at" -
-- the second half of this file adds every column the pipeline writes, keeping
-- your rows and matching your own id type. Nothing is ever dropped.

-- Only real problems, not a "column already exists" for every column.
set client_min_messages = warning;

create extension if not exists "pgcrypto";


-- ---------------------------------------------------------------- new tables

create table if not exists source_documents (
  id             uuid primary key default gen_random_uuid(),
  sha256         text not null,
  file_name      text not null,
  page_count     integer not null,
  byte_size      bigint not null,
  level          text,                      -- F1-F6, null if unknown
  year           text,                      -- "2025" or "2025-26"
  term           text,                      -- 1st | 2nd | mid | final
  exam_type      text,                      -- test | exam | mock | dse | quiz | homework
  paper_number   integer,
  school         text,
  topics         jsonb not null default '[]'::jsonb,
  first_seen_at  timestamptz not null default now()
);

create table if not exists extraction_runs (
  id                       uuid primary key default gen_random_uuid(),
  run_id                   text not null,
  source_document_id       uuid,
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
  extraction_run_id    uuid,
  source_document_id   uuid,
  source_question_id   text not null,
  question_key         text,                -- <sha12>:<source_question_id>; stable across runs
  depends_on           jsonb not null default '[]'::jsonb,
  level                text,                -- F1-F6, copied from the document
  position             integer not null,
  question_type        text not null default 'open',
  question_text        text not null,
  options              jsonb not null default '[]'::jsonb,
  marks                numeric,
  group_marks          numeric,
  group_marks_scope    text,
  answer               text,
  worked_solution      text,
  page_start           integer,
  page_end             integer,
  diagram_required     boolean not null default false,
  diagram_region       jsonb,
  table_regions        jsonb not null default '[]'::jsonb,
  extraction_notes     jsonb not null default '[]'::jsonb,
  images               jsonb not null default '[]'::jsonb
);


-- ------------------------------------------------- tables that already existed
--
-- Adds any column the pipeline writes that is not there yet. Added columns are
-- nullable whatever the definitions above say, because an existing row cannot
-- satisfy NOT NULL retroactively - the pipeline always writes every one of
-- them, so nothing is lost. The two foreign-key columns are typed from the
-- parent table's own id, so a bigint id from the table editor works as well as
-- a uuid one.

do $$
declare
  doc_id_type  text;
  run_id_type  text;
  target       record;
begin
  -- Every table needs an id the pipeline can read back after an insert.
  for target in
    select unnest(array['source_documents', 'extraction_runs', 'questions']) as name
  loop
    if not exists (select 1 from pg_attribute
                    where attrelid = target.name::regclass
                      and attname = 'id' and attnum > 0 and not attisdropped) then
      execute format('alter table %I add column id uuid not null default gen_random_uuid()',
                     target.name);
      execute format('create unique index if not exists %I on %I (id)',
                     target.name || '_id_key', target.name);
    end if;
  end loop;

  select format_type(atttypid, atttypmod) into doc_id_type
    from pg_attribute
   where attrelid = 'source_documents'::regclass and attname = 'id' and attnum > 0;
  select format_type(atttypid, atttypmod) into run_id_type
    from pg_attribute
   where attrelid = 'extraction_runs'::regclass and attname = 'id' and attnum > 0;

  for target in
    select * from (values
      ('source_documents', 'sha256',                  'text'),
      ('source_documents', 'file_name',               'text'),
      ('source_documents', 'page_count',              'integer'),
      ('source_documents', 'byte_size',               'bigint'),
      ('source_documents', 'level',                   'text'),
      ('source_documents', 'year',                    'text'),
      ('source_documents', 'term',                    'text'),
      ('source_documents', 'exam_type',               'text'),
      ('source_documents', 'paper_number',            'integer'),
      ('source_documents', 'school',                  'text'),
      ('source_documents', 'topics',                  'jsonb default ''[]''::jsonb'),
      ('source_documents', 'first_seen_at',           'timestamptz default now()'),
      ('extraction_runs',  'run_id',                  'text'),
      ('extraction_runs',  'source_document_id',      doc_id_type),
      ('extraction_runs',  'extracted_at',            'timestamptz'),
      ('extraction_runs',  'extraction_version',      'text'),
      ('extraction_runs',  'question_object_version', 'text'),
      ('extraction_runs',  'model',                   'text'),
      ('extraction_runs',  'question_count',          'integer'),
      ('extraction_runs',  'issue_count',             'integer'),
      ('extraction_runs',  'blocking',                'boolean default false'),
      ('extraction_runs',  'issues',                  'jsonb default ''[]''::jsonb'),
      ('extraction_runs',  'repairs',                 'jsonb default ''[]''::jsonb'),
      ('extraction_runs',  'is_current',              'boolean default true'),
      ('extraction_runs',  'created_at',              'timestamptz default now()'),
      ('questions',        'extraction_run_id',       run_id_type),
      ('questions',        'source_document_id',      doc_id_type),
      ('questions',        'source_question_id',      'text'),
      ('questions',        'question_key',            'text'),
      ('questions',        'depends_on',              'jsonb default ''[]''::jsonb'),
      ('questions',        'level',                   'text'),
      ('questions',        'position',                'integer'),
      ('questions',        'question_type',           'text default ''open'''),
      ('questions',        'question_text',           'text'),
      ('questions',        'options',                 'jsonb default ''[]''::jsonb'),
      ('questions',        'marks',                   'numeric'),
      ('questions',        'group_marks',             'numeric'),
      ('questions',        'group_marks_scope',       'text'),
      ('questions',        'answer',                  'text'),
      ('questions',        'worked_solution',         'text'),
      ('questions',        'page_start',              'integer'),
      ('questions',        'page_end',                'integer'),
      ('questions',        'diagram_required',        'boolean default false'),
      ('questions',        'diagram_region',          'jsonb'),
      ('questions',        'table_regions',           'jsonb default ''[]''::jsonb'),
      ('questions',        'extraction_notes',        'jsonb default ''[]''::jsonb'),
      ('questions',        'images',                  'jsonb default ''[]''::jsonb')
    ) as columns(table_name, column_name, column_type)
  loop
    execute format('alter table %I add column if not exists %I %s',
                   target.table_name, target.column_name, target.column_type);
  end loop;
end $$;


-- -------------------------------------------------------------------- indexes
--
-- The unique index on sha256 is not decoration: it is what lets the pipeline
-- upsert a document on its hash, so the same PDF is one row however often it
-- is ingested.

create unique index if not exists source_documents_sha256_key on source_documents (sha256);
create unique index if not exists extraction_runs_run_id_key  on extraction_runs (run_id);
-- Unique on position, not on the printed number: a paper that prints "17"
-- twice is a DUPLICATE_QUESTION_ID issue to look at, not a reason to lose the
-- whole run at insert time.
drop index if exists questions_run_question_key;
create unique index if not exists questions_run_position_key  on questions (extraction_run_id, position);
create index        if not exists questions_key_idx           on questions (question_key);

create index if not exists questions_document_idx  on questions (source_document_id);
create index if not exists questions_type_idx      on questions (question_type);
create index if not exists questions_level_idx     on questions (level);
create index if not exists runs_document_idx        on extraction_runs (source_document_id);
create index if not exists runs_current_idx         on extraction_runs (source_document_id) where is_current;


-- ----------------------------------------------------------------------- view
--
-- The questions of the current run for every paper. Dropped and recreated
-- rather than "create or replace", because replacing cannot change the column
-- list and questions gained a column in this file.

drop view if exists current_questions;
create view current_questions as
  select q.*
  from questions q
  join extraction_runs r on r.id = q.extraction_run_id
  where r.is_current;
