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
  module         text,                      -- compulsory | M1 | M2
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
  prompt_sha256            text,
  input_tokens             integer,
  output_tokens            integer,
  question_count           integer not null,
  issue_count              integer not null,
  blocking                 boolean not null default false,
  issues                   jsonb not null default '[]'::jsonb,
  repairs                  jsonb not null default '[]'::jsonb,
  marking_scheme_file_name text,
  marking_scheme_sha256    text,
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
  module               text,                -- compulsory | M1 | M2
  position             integer not null,
  question_type        text not null default 'open',
  question_text        text not null,
  options              jsonb not null default '[]'::jsonb,
  marks                numeric,
  group_marks          numeric,
  group_marks_scope    text,
  answer               text,
  answer_source        text,                -- paper | marking_scheme | null
  worked_solution      text,
  page_start           integer,
  page_end             integer,
  diagram_required     boolean not null default false,
  diagram_region       jsonb,
  table_regions        jsonb not null default '[]'::jsonb,
  extraction_notes     jsonb not null default '[]'::jsonb,
  images               jsonb not null default '[]'::jsonb
);


-- The controlled vocabularies (taxonomy/*.csv), pushed by db_push_taxonomy.
-- Analyses reference skill_id / error_id; nothing here is ever free text.

create table if not exists skills (
  skill_id       text primary key,
  strand         text not null,           -- na | ms | dh | fl
  unit           text not null,
  name_en        text not null,
  name_zh        text not null,
  form           text not null,           -- F1-F6
  foundation     text,                    -- foundation | non-foundation | enrichment | null
  prerequisites  jsonb not null default '[]'::jsonb,
  guide_ref      jsonb not null default '[]'::jsonb,   -- C&A Guide objectives, e.g. ["CP-1.4"]
  updated_at     timestamptz not null default now()
);

create table if not exists error_patterns (
  error_id       text primary key,
  name_en        text not null,
  name_zh        text not null,
  skills         jsonb not null default '[]'::jsonb,
  description    text,
  updated_at     timestamptz not null default now()
);

-- One row per question per Analyzer run. Hangs off question_key, so a
-- re-extraction of the paper does not orphan it.
create table if not exists question_analyses (
  id                  uuid primary key default gen_random_uuid(),
  question_key        text not null,
  source_sha256       text not null,
  source_question_id  text not null,
  analysis_run_id     text not null,
  analyzer_version    text not null,
  prompt_sha256       text,
  model               text,
  level               text,
  module              text,
  skill_family        text,
  atomic_skills       jsonb not null default '[]'::jsonb,
  method_cues         jsonb not null default '[]'::jsonb,
  strategies          jsonb not null default '[]'::jsonb,
  rpdice              jsonb not null default '{}'::jsonb,   -- primary strategy levels {"R":2,...}
  difficulty_drivers  jsonb not null default '[]'::jsonb,
  possible_errors     jsonb not null default '[]'::jsonb,
  proposed_skills     jsonb not null default '[]'::jsonb,
  proposed_errors     jsonb not null default '[]'::jsonb,
  confidence          numeric,
  issues              jsonb not null default '[]'::jsonb,
  -- Solver / Critic stage: one solution per strategy (strategies[].strategy_id
  -- is what a later student_responses.strategy_id will point at), the
  -- Critic's issues, and which Critic run produced them.
  solutions           jsonb not null default '[]'::jsonb,
  critic_issues       jsonb not null default '[]'::jsonb,
  critic_run_id       text,
  is_current          boolean not null default true,
  created_at          timestamptz not null default now(),
  unique (analysis_run_id, question_key)
);


-- Students and their attempts: the first tables of the student layer. An
-- attempt hangs off question_key, and off strategies[].strategy_id in
-- question_analyses when the working follows a listed strategy.
create table if not exists students (
  student_id     text primary key,
  form           text,
  class_name     text,
  cohort         text,
  created_at     timestamptz not null default now()
);

create table if not exists attempts (
  id                    uuid primary key default gen_random_uuid(),
  student_id            text not null,
  question_key          text not null,
  source_question_id    text not null,
  paper_file_name       text,
  scan_file_name        text,
  scan_sha256           text,
  grader_run_id         text,
  grader_version        text,
  model                 text,
  answer_given          text,
  is_correct            boolean,                 -- null: no reference answer
  strategy_id           text,                    -- question_analyses.strategies[].strategy_id
  strategy_match        text,                    -- listed | new | none
  skills_evidenced      jsonb not null default '[]'::jsonb,
  skills_not_evidenced  jsonb not null default '[]'::jsonb,
  error_ids             jsonb not null default '[]'::jsonb,
  slips                 jsonb not null default '[]'::jsonb,
  misconceptions        jsonb not null default '[]'::jsonb,
  transcription         jsonb not null default '[]'::jsonb,
  confidence            numeric,
  needs_human           boolean not null default false,
  review_reasons        jsonb not null default '[]'::jsonb,
  attempted_at          timestamptz,
  created_at            timestamptz not null default now()
);


-- ------------------------------------------------- tables that already existed
--
-- Brings a table that was made some other way - the Supabase table editor, an
-- earlier version of this file - up to what the pipeline writes, without
-- dropping anything:
--
--   * a missing column is added, always nullable (an existing row cannot
--     satisfy NOT NULL retroactively, and the pipeline writes every column);
--   * a key column the table editor typed as uuid is converted to text, since
--     "na.factor.dos" and "b584940bfebb:4(a)" are not uuids. Existing uuid
--     values survive as strings;
--   * a foreign key that would block such a conversion is dropped, both of its
--     columns are converted, and the constraint is put back;
--   * the two foreign-key columns are typed from the parent table's own id, so
--     a bigint id from the table editor works as well as a uuid one.

create temp table if not exists _mqs_columns
  (table_name text, column_name text, column_type text);
truncate _mqs_columns;

-- What the repair had to change about columns of your own, for the report at
-- the end of this file.
create temp table if not exists _mqs_relaxed
  (table_name text, column_name text, note text);
truncate _mqs_relaxed;
insert into _mqs_columns (table_name, column_name, column_type) values
      ('source_documents', 'sha256',                  'text'),
      ('source_documents', 'file_name',               'text'),
      ('source_documents', 'page_count',              'integer'),
      ('source_documents', 'byte_size',               'bigint'),
      ('source_documents', 'level',                   'text'),
  ('source_documents', 'module',                  'text'),
      ('source_documents', 'year',                    'text'),
      ('source_documents', 'term',                    'text'),
      ('source_documents', 'exam_type',               'text'),
      ('source_documents', 'paper_number',            'integer'),
      ('source_documents', 'school',                  'text'),
      ('source_documents', 'topics',                  'jsonb default ''[]''::jsonb'),
      ('source_documents', 'first_seen_at',           'timestamptz default now()'),
      ('extraction_runs',  'run_id',                  'text'),
      ('extraction_runs',  'source_document_id',      '__doc_id__'),
      ('extraction_runs',  'extracted_at',            'timestamptz'),
      ('extraction_runs',  'extraction_version',      'text'),
      ('extraction_runs',  'question_object_version', 'text'),
      ('extraction_runs',  'model',                   'text'),
      ('extraction_runs',  'prompt_sha256',           'text'),
      ('extraction_runs',  'input_tokens',            'integer'),
      ('extraction_runs',  'output_tokens',           'integer'),
      ('extraction_runs',  'question_count',          'integer'),
      ('extraction_runs',  'issue_count',             'integer'),
      ('extraction_runs',  'blocking',                'boolean default false'),
      ('extraction_runs',  'issues',                  'jsonb default ''[]''::jsonb'),
      ('extraction_runs',  'repairs',                 'jsonb default ''[]''::jsonb'),
      ('extraction_runs',  'marking_scheme_file_name', 'text'),
      ('extraction_runs',  'marking_scheme_sha256',   'text'),
      ('extraction_runs',  'is_current',              'boolean default true'),
      ('extraction_runs',  'created_at',              'timestamptz default now()'),
      ('questions',        'extraction_run_id',       '__run_id__'),
      ('questions',        'source_document_id',      '__doc_id__'),
      ('questions',        'source_question_id',      'text'),
      ('questions',        'question_key',            'text'),
      ('questions',        'depends_on',              'jsonb default ''[]''::jsonb'),
      ('questions',        'level',                   'text'),
  ('questions',        'module',                  'text'),
      ('questions',        'position',                'integer'),
      ('questions',        'question_type',           'text default ''open'''),
      ('questions',        'question_text',           'text'),
      ('questions',        'options',                 'jsonb default ''[]''::jsonb'),
      ('questions',        'marks',                   'numeric'),
      ('questions',        'group_marks',             'numeric'),
      ('questions',        'group_marks_scope',       'text'),
      ('questions',        'answer',                  'text'),
      ('questions',        'answer_source',           'text'),
      ('questions',        'worked_solution',         'text'),
      ('questions',        'page_start',              'integer'),
      ('questions',        'page_end',                'integer'),
      ('questions',        'diagram_required',        'boolean default false'),
      ('questions',        'diagram_region',          'jsonb'),
      ('questions',        'table_regions',           'jsonb default ''[]''::jsonb'),
      ('questions',        'extraction_notes',        'jsonb default ''[]''::jsonb'),
      ('questions',        'images',                  'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'question_key',           'text'),
      ('question_analyses', 'source_sha256',          'text'),
      ('question_analyses', 'source_question_id',     'text'),
      ('question_analyses', 'analysis_run_id',        'text'),
      ('question_analyses', 'analyzer_version',       'text'),
      ('question_analyses', 'prompt_sha256',          'text'),
      ('question_analyses', 'model',                  'text'),
      ('question_analyses', 'level',                  'text'),
  ('question_analyses', 'module',                 'text'),
      ('question_analyses', 'skill_family',           'text'),
      ('question_analyses', 'atomic_skills',          'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'method_cues',            'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'strategies',             'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'rpdice',                 'jsonb default ''{}''::jsonb'),
      ('question_analyses', 'difficulty_drivers',     'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'possible_errors',        'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'proposed_skills',        'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'proposed_errors',        'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'confidence',             'numeric'),
      ('question_analyses', 'issues',                 'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'solutions',              'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'critic_issues',          'jsonb default ''[]''::jsonb'),
      ('question_analyses', 'critic_run_id',          'text'),
      ('students',          'student_id',             'text'),
      ('students',          'form',                   'text'),
      ('students',          'class_name',             'text'),
      ('students',          'cohort',                 'text'),
      ('students',          'created_at',             'timestamptz default now()'),
      ('attempts',          'student_id',             'text'),
      ('attempts',          'question_key',           'text'),
      ('attempts',          'source_question_id',     'text'),
      ('attempts',          'paper_file_name',        'text'),
      ('attempts',          'scan_file_name',         'text'),
      ('attempts',          'scan_sha256',            'text'),
      ('attempts',          'grader_run_id',          'text'),
      ('attempts',          'grader_version',         'text'),
      ('attempts',          'model',                  'text'),
      ('attempts',          'answer_given',           'text'),
      ('attempts',          'is_correct',             'boolean'),
      ('attempts',          'strategy_id',            'text'),
      ('attempts',          'strategy_match',         'text'),
      ('attempts',          'skills_evidenced',       'jsonb default ''[]''::jsonb'),
      ('attempts',          'skills_not_evidenced',   'jsonb default ''[]''::jsonb'),
      ('attempts',          'error_ids',              'jsonb default ''[]''::jsonb'),
      ('attempts',          'slips',                  'jsonb default ''[]''::jsonb'),
      ('attempts',          'misconceptions',         'jsonb default ''[]''::jsonb'),
      ('attempts',          'transcription',          'jsonb default ''[]''::jsonb'),
      ('attempts',          'confidence',             'numeric'),
      ('attempts',          'needs_human',            'boolean default false'),
      ('attempts',          'review_reasons',         'jsonb default ''[]''::jsonb'),
      ('attempts',          'attempted_at',           'timestamptz'),
      ('attempts',          'created_at',             'timestamptz default now()'),
      ('question_analyses', 'is_current',             'boolean default true'),
      ('question_analyses', 'created_at',             'timestamptz default now()'),
      ('skills',           'skill_id',                'text'),
      ('skills',           'strand',                  'text'),
      ('skills',           'unit',                    'text'),
      ('skills',           'name_en',                 'text'),
      ('skills',           'name_zh',                 'text'),
      ('skills',           'form',                    'text'),
      ('skills',           'foundation',              'text'),
      ('skills',           'prerequisites',           'jsonb default ''[]''::jsonb'),
      ('skills',           'guide_ref',               'jsonb default ''[]''::jsonb'),
      ('skills',           'updated_at',              'timestamptz default now()'),
      ('error_patterns',   'error_id',                'text'),
      ('error_patterns',   'name_en',                 'text'),
      ('error_patterns',   'name_zh',                 'text'),
      ('error_patterns',   'skills',                  'jsonb default ''[]''::jsonb'),
      ('error_patterns',   'description',             'text'),
      ('error_patterns',   'updated_at',              'timestamptz default now()');

do $$
declare
  doc_id_type    text;
  run_id_type    text;
  existing_type  text;
  wanted_type    text;
  target         record;
  fk             record;
  convert        text[] := '{}';
  restore        text[] := '{}';
  entry          text;
  parts          text[];
  changed        boolean;
begin
  -- Every row-keyed table needs an id the pipeline can read back after an
  -- insert. skills and error_patterns key on skill_id / error_id instead.
  for target in
    select unnest(array['source_documents', 'extraction_runs', 'questions',
                        'question_analyses', 'attempts']) as name
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

  -- 1. add what is missing, and note every text column that is not text
  for target in select * from _mqs_columns loop
    wanted_type := case target.column_type
                     when '__doc_id__' then doc_id_type
                     when '__run_id__' then run_id_type
                     else target.column_type
                   end;
    execute format('alter table %I add column if not exists %I %s',
                   target.table_name, target.column_name, wanted_type);

    if wanted_type like 'text%' then
      select format_type(atttypid, atttypmod) into existing_type
        from pg_attribute
       where attrelid = target.table_name::regclass and attname = target.column_name
         and attnum > 0 and not attisdropped;
      if existing_type is distinct from 'text' then
        convert := convert || (target.table_name || '|' || target.column_name);
      end if;
    end if;
  end loop;

  -- 2. a foreign key ties two columns together: convert both or neither
  loop
    changed := false;
    for fk in
      select c.conrelid::regclass::text  as child_table,  a.attname::text as child_column,
             c.confrelid::regclass::text as parent_table, b.attname::text as parent_column
        from pg_constraint c
        join pg_attribute a on a.attrelid = c.conrelid  and a.attnum = c.conkey[1]
        join pg_attribute b on b.attrelid = c.confrelid and b.attnum = c.confkey[1]
       where c.contype = 'f' and array_length(c.conkey, 1) = 1
    loop
      if (fk.child_table || '|' || fk.child_column) = any(convert)
         and not ((fk.parent_table || '|' || fk.parent_column) = any(convert)) then
        convert := convert || (fk.parent_table || '|' || fk.parent_column);
        changed := true;
      end if;
      if (fk.parent_table || '|' || fk.parent_column) = any(convert)
         and not ((fk.child_table || '|' || fk.child_column) = any(convert)) then
        convert := convert || (fk.child_table || '|' || fk.child_column);
        changed := true;
      end if;
    end loop;
    exit when not changed;
  end loop;

  -- 3. drop those foreign keys, remembering how to put them back
  for fk in
    select c.conname, c.conrelid::regclass as child_rel, pg_get_constraintdef(c.oid) as def,
           c.conrelid::regclass::text  as child_table,  a.attname::text as child_column,
           c.confrelid::regclass::text as parent_table, b.attname::text as parent_column
      from pg_constraint c
      join pg_attribute a on a.attrelid = c.conrelid  and a.attnum = c.conkey[1]
      join pg_attribute b on b.attrelid = c.confrelid and b.attnum = c.confkey[1]
     where c.contype = 'f' and array_length(c.conkey, 1) = 1
  loop
    if (fk.child_table || '|' || fk.child_column) = any(convert)
       or (fk.parent_table || '|' || fk.parent_column) = any(convert) then
      restore := restore || format('alter table %s add constraint %I %s',
                                   fk.child_rel, fk.conname, fk.def);
      execute format('alter table %s drop constraint %I', fk.child_rel, fk.conname);
    end if;
  end loop;

  -- 4. convert, then put the constraints back
  foreach entry in array convert loop
    parts := string_to_array(entry, '|');
    execute format('alter table %I alter column %I drop default', parts[1], parts[2]);
    execute format('alter table %I alter column %I type text using %I::text',
                   parts[1], parts[2], parts[2]);
  end loop;

  foreach entry in array restore loop
    execute entry;
  end loop;

  -- 5. A column of your own that is NOT NULL with no default blocks every
  --    insert, because the pipeline does not know it exists and cannot fill
  --    it. Relax it: no data is touched, and "alter column ... set not null"
  --    puts it back whenever you are ready to fill it in. A column that
  --    cannot be relaxed - one in a primary key - is reported instead.
  for target in
    select c.table_name::text as table_name, c.column_name::text as column_name
      from information_schema.columns c
     where c.table_schema = 'public'
       and c.table_name in ('source_documents', 'extraction_runs', 'questions',
                            'skills', 'error_patterns', 'question_analyses',
                            'students', 'attempts')
       and c.is_nullable = 'NO'
       and c.column_default is null
       and c.column_name <> 'id'
       and not exists (select 1 from _mqs_columns m
                        where m.table_name = c.table_name
                          and m.column_name = c.column_name)
  loop
    begin
      execute format('alter table %I alter column %I drop not null',
                     target.table_name, target.column_name);
      insert into _mqs_relaxed values (target.table_name, target.column_name,
        'NOT NULL dropped so inserts can leave it empty; set not null to put it back');
    exception when others then
      insert into _mqs_relaxed values (target.table_name, target.column_name,
        'COULD NOT relax (' || sqlerrm || ') - drop this column, or give it a default');
    end;
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
create index if not exists questions_module_idx    on questions (module);
create index if not exists runs_document_idx        on extraction_runs (source_document_id);
create index if not exists runs_current_idx         on extraction_runs (source_document_id) where is_current;

-- The taxonomy upserts conflict on these; the analysis insert is unique per run.
create unique index if not exists skills_skill_id_key         on skills (skill_id);
create unique index if not exists error_patterns_error_id_key on error_patterns (error_id);
create unique index if not exists analyses_run_key            on question_analyses (analysis_run_id, question_key);
create index if not exists analyses_key_idx     on question_analyses (question_key);
create index if not exists analyses_current_idx on question_analyses (question_key) where is_current;

create index if not exists attempts_student_idx  on attempts (student_id);
create index if not exists attempts_question_idx on attempts (question_key);
create index if not exists skills_form_idx   on skills (form);
create index if not exists skills_unit_idx   on skills (unit);


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


-- ------------------------------------------------------------------ report
--
-- Columns of your own that the pipeline does not write, and what was done so
-- they would not block an insert. An empty result means there were none.

select table_name, column_name, note
  from _mqs_relaxed
 order by table_name, column_name;
