# Teacher Workbench v1: architecture and contracts

Owner: Architect. Readers: the Frontend and Backend chats. This file is the contract they work
from. Once the backend runs, `GET /api/openapi.json` is the machine-readable copy; if the two
disagree, fix whichever one is wrong in the same PR.

**Why this milestone.** No feature was named, so this picks the next step the repo points at.
Every layer up to the Grader works, but only from the CLI, and the two things the system needs
next both need teachers: confirming the 30-question gold set, and reviewing Grader attempts
flagged `needs_human`. Teachers will not run `python -m scripts.*`. Student Model, Calibration
and Adaptive come after this, and they need the reviewed attempts it produces
(`system_spec.md` §5: Adaptive must not use uncalibrated levels).

---

## 1. Goals

A teacher, in a browser, can:

1. **Upload a paper** (PDF, optional marking scheme, optional metadata), get it ingested and see
   its questions.
2. **Run the Analyzer** (with Solver + Critic) on a paper and read each question's RPDICE profile,
   strategies, evidence and Critic status.
3. **Grade a student's page**: upload one scan for one question and one student, and get an
   attempt back.
4. **Review attempts** the Grader flagged `needs_human`, and record a correction without
   overwriting what the Grader produced.
5. **Rate the gold set** without seeing the answers first (blind), so two teachers' ratings can be
   compared with each other and with the Analyzer.

### Non-goals (v1)

- Student Model (`skill_mastery`), Calibration, Adaptive practice, Question Generator.
- Student logins or any page for students.
- Editing question text or analyses. Questions are what was printed, and analyses are model
  runs; both are immutable. You correct them by running again, or through the gold set.
- Editing the taxonomy. `taxonomy/*.csv` + git + `check_taxonomy` stays the only way in;
  `proposed_skills` / `proposed_errors` are shown but read-only.
- Adding a strategy a student found to the question (`source: student`, §45). The review only
  records a note.
- Multi-page or multi-question scans. The Grader handles one page for one question.
- More than one school, or any role besides "teacher".
- WebSockets/SSE, Redis/Celery, Analyzer N-run majority vote, or a run-diff view (the
  `diff_analyses` CLI covers that).

### Defaults assumed (change any of them and tell the Architect)

| Topic | Default |
|---|---|
| UI language | Written Traditional Chinese (書面繁中); skill/error names use `name_zh` |
| Users | Teachers at one school, authenticated individually |
| Auth | Supabase Auth email magic link, with an allowlist (`teachers` table) |
| Hosting | One container on one host with a **persistent** disk |
| Student identity | A code the school issues (`student_id`). The system never stores names |

---

## 2. Design

```text
 Browser (web/, React + Vite + TS)
   │  supabase-js used ONLY to sign in → access token
   │  all data: fetch /api/*  with  Authorization: Bearer <token>
   ▼
 FastAPI (server/)  ── one process, serves /api/* and the built web/dist
   ├─ auth dependency: verify Supabase JWT → email must be in teachers
   ├─ read routes ──────────────► Supabase Postgres (secret key, server-side only)
   ├─ write routes ─► jobs row ─► in-process worker (1 thread)
   │                                └─ app/workflows.py ─► existing app.* classes ─► Gemini
   │                                     writes JSON/PNG to data/  +  rows to Supabase
   └─ /api/blobs/* ─────────────► data/diagrams, data/attempts (on the persistent disk)
```

### Decisions and tradeoffs

1. **One API; the browser never holds a database key.** Student scans and attempts are personal
   data, so every read goes through the backend's auth check. The other option, supabase-js
   plus RLS policies, would split the contract in two and put access rules in SQL that nobody
   reviews. RLS is still turned **on, with no policies**, on every table, so the publishable key
   reads nothing.
2. **Supabase is the system of record for anything you query; disk holds the blobs.** Rows
   (papers, questions, analyses, attempts, reviews, gold labels, jobs) live in Postgres. PDFs,
   PNGs, scans and the full `ExtractionResult` / `AnalysisResult` JSON stay on disk where the
   pipeline already writes them, because the Solver, Critic and Grader need whole objects and
   already load them from there. The web path makes Supabase **required**: a job whose DB push
   fails is marked **failed** (the CLI only warns), and `scripts.db_push` re-syncs.
   `ponytail: blobs on local disk → single host. Move data/ to Supabase Storage when there is a
   second instance or the host's disk is ephemeral.`
3. **The CLI and the web call the same functions.** The body of each script
   (`ingest_one_pdf`, `ingest_pdfs` scheme pairing, `attach_marking_scheme`, `analyse_rpdice`,
   `grade_answer` + `locate`) moves into `app/workflows.py`, and both the scripts and the job
   worker call it. Otherwise the two paths drift apart within a month.
4. **Jobs: one Postgres table and one worker thread.** Ingesting a paper takes about 40 s;
   Analyzer + Critic takes minutes. That is short enough to poll every 2 s and long enough that
   it cannot run inside a request. With concurrency 1 there is no Gemini rate-limit storm and no
   cost surprise. A partial unique index stops a double-click from starting the same job twice.
   On startup, any `running` job is marked `failed / INTERRUPTED`.
   `ponytail: in-process worker → one API process. Move to a separate worker using
   SELECT … FOR UPDATE SKIP LOCKED when you need a second process.`
5. **Human corrections are appended, never overwritten.** This is the same rule as
   `questions` and `is_current` runs. `attempt_reviews` rows sit next to `attempts`; the view
   `attempts_effective` returns the latest review where there is one and the Grader's value
   otherwise. The Student Model will read that view.
6. **Gold labels go in a table, and an export writes the existing CSV format**, so
   `score_rpdice` keeps working unchanged. The queue is the `question_key`s in
   `taxonomy/golden/rpdice_gold.csv`, so there is no `gold_items` table.
7. **Types are generated, not written by hand.** The backend's pydantic response models produce
   OpenAPI, and the frontend runs `openapi-typescript` to get `web/src/api.d.ts`. The TS below
   is the target; the generated file wins.

---

## 3. Interfaces and contracts

### 3.1 Conventions

- Base path `/api`. JSON in and out, except uploads, which are `multipart/form-data`.
- Every route except `GET /api/health` requires `Authorization: Bearer <supabase access token>`.
  401 if the token is missing or invalid; 403 if the email is not in `teachers`.
- `question_key` is `<sha12>:<source_question_id>` and contains `:` and `(` `)`, for example
  `b584940bfebb:17(a)`. The frontend **must** `encodeURIComponent` it in paths.
- A paper is addressed by `sha12`, the first 12 hex characters of the PDF's sha256 (the same
  prefix `question_key` uses).
- Lists use `?limit=` (default 50, max 200) and `?cursor=` (opaque), and return
  `{ items: T[], next_cursor: string | null }`.
- Timestamps are ISO-8601 UTC strings.
- Errors return the matching HTTP status with this body:

```ts
interface ApiError { error: { code: ErrorCode; message: string; details?: unknown } }
type ErrorCode =
  | 'UNAUTHORIZED' | 'FORBIDDEN' | 'NOT_FOUND' | 'VALIDATION'
  | 'ANALYSIS_REQUIRED'     // 409: grading needs a current analysis of the question
  | 'UNSUPPORTED_FILE'      // 415: wrong type, or over the size limit
  | 'JOB_ALREADY_RUNNING'   // 409: details.job_id is the running job
  | 'ALREADY_EXISTS';       // 409: e.g. POST /students with an existing student_id
```

Upload limits: paper or marking scheme PDF ≤ 30 MB; scans (`.pdf .png .jpg .jpeg .webp`, the
Grader's `MIME` table) ≤ 15 MB.

### 3.2 Shared types

```ts
type Level = 'F1' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6';
type Module = 'compulsory' | 'M1' | 'M2';
type Letter = 'R' | 'P' | 'D' | 'I' | 'C' | 'E';
type Severity = 'low' | 'medium' | 'high' | 'critical';
type StrategyStatus = 'proposed' | 'confirmed' | 'rejected' | 'unverified';

interface Issue { issue_code: string; severity: Severity; message: string; source_question_id: string | null }

interface PaperMeta {
  year: string | null; term: string | null; exam_type: string | null;
  paper_number: number | null; school: string | null; topics: string[];
}

interface PaperSummary extends PaperMeta {
  sha12: string; file_name: string; page_count: number;
  level: Level | null; module: Module | null;
  question_count: number; issue_count: number; blocking: boolean;
  extracted_at: string; has_marking_scheme: boolean;
  analysis: { analysis_run_id: string; analysed_at: string; critic_ran: boolean } | null;
}

interface PaperDetail extends PaperSummary {
  run: { run_id: string; model: string; extraction_version: string; prompt_sha256: string | null;
         input_tokens: number | null; output_tokens: number | null;
         marking_scheme_file_name: string | null };
  issues: Issue[];
  questions: QuestionSummary[];          // in paper order (position)
}

interface QuestionSummary {
  question_key: string; source_question_id: string; position: number;
  question_type: 'open' | 'multiple_choice'; marks: number | null;
  level: Level | null; module: Module | null;
  has_answer: boolean; answer_source: 'paper' | 'marking_scheme' | null;
  diagram_required: boolean; depends_on: string[];   // source_question_ids
  rpdice: Record<Letter, number> | null;              // primary strategy; null = not analysed
  difficulty_drivers: Letter[];
  skill_family: string | null;
  primary_status: StrategyStatus | null;
  attempt_count: number;
}

interface Image { kind: 'diagram' | 'table'; page: number; url: string; width: number; height: number }

interface QuestionDetail extends QuestionSummary {
  paper: { sha12: string; file_name: string };
  question_text: string;                 // Markdown + LaTeX in \( \); see 3.6
  options: string[];                     // MC only
  group_marks: number | null; group_marks_scope: string | null;
  answer: string | null; worked_solution: string | null;
  images: Image[];
  extraction_notes: string[];
  analysis: Analysis | null;
}

interface Analysis {
  analysis_run_id: string; analyzer_version: string; model: string | null; analysed_at: string;
  skill_family: string;
  atomic_skills: string[];               // skill_ids; names come from GET /api/taxonomy
  method_cues: string[];                 // verbatim quotes from question_text
  representation_features: string[];
  strategies: Strategy[];
  possible_errors: string[];             // error_ids
  difficulty_drivers: Letter[];
  structural_depth_notes: string[];
  proposed_skills: string[]; proposed_errors: string[];   // free text, read-only
  confidence: number;
  issues: Issue[]; critic_issues: Issue[];
}

interface Strategy {
  strategy_id: string; strategy_name: string; steps: string[]; skills: string[];
  rpdice: Record<Letter, { level: 0 | 1 | 2 | 3; evidence: string[] }>;
  is_primary: boolean; source: 'analyzer' | 'student' | 'teacher'; status: StrategyStatus;
  solution: {
    final_answer: string | null; worked_steps: string[]; reached_answer: boolean;
    deviations: string[]; pitfalls_met: string[]; notes: string | null;
  } | null;
}

interface Student { student_id: string; form: Level | null; class_name: string | null; cohort: string | null }

interface AttemptSummary {
  id: string; student_id: string; question_key: string; source_question_id: string;
  attempted_at: string | null; created_at: string;
  is_correct: boolean | null;            // effective value (the review wins)
  strategy_match: 'listed' | 'new' | 'none';
  needs_human: boolean; reviewed: boolean;
}

interface AttemptDetail extends AttemptSummary {
  scan_url: string; scan_mime: string;
  grader: {                              // the Grader's output, as stored, never changed
    run_id: string; version: string; model: string;
    transcription: string[]; answer_given: string | null;
    is_correct: boolean | null; reference_answer: string | null;
    reference_source: 'marking_scheme' | 'solver' | null;
    strategy_id: string | null; strategy_match: 'listed' | 'new' | 'none';
    skills_evidenced: string[]; skills_not_evidenced: string[];
    error_ids: string[]; slips: string[]; misconceptions: string[];
    confidence: number | null; review_reasons: string[];
    analysis_run_id: string | null;      // the analysis the strategy_id belongs to (new column)
  };
  reviews: AttemptReview[];              // newest first
  effective: { is_correct: boolean | null; strategy_id: string | null;
               strategy_match: 'listed' | 'new' | 'none';
               error_ids: string[]; skills_evidenced: string[] };
}

interface AttemptReview {
  id: string; reviewer: string; created_at: string; note: string | null;
  // null = "agree with the Grader" for that field
  is_correct: boolean | null; strategy_id: string | null;
  strategy_match: 'listed' | 'new' | 'none' | null;
  error_ids: string[] | null; skills_evidenced: string[] | null;
}

interface GoldLabel {
  question_key: string; rater: string; created_at: string;
  levels: Record<Letter, 0 | 1 | 2 | 3>; skills: string[]; errors: string[]; notes: string | null;
}

type JobKind = 'ingest' | 'attach_scheme' | 'analyse' | 'grade';
type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';
interface Job {
  id: string; kind: JobKind; status: JobStatus; target: string;
  created_by: string; created_at: string; started_at: string | null; finished_at: string | null;
  result: JobResult | null;
  error: { code: string; message: string } | null;   // code is a pipeline issue_code where one exists
}
type JobResult =
  | { kind: 'ingest'; sha12: string; question_count: number; issue_count: number; blocking: boolean;
      input_tokens: number | null; output_tokens: number | null }
  | { kind: 'attach_scheme'; sha12: string; matched: number; unmatched: number }
  | { kind: 'analyse'; sha12: string; analysis_run_id: string; analysed: number;
      issue_count: number; high_or_critical: number; critic_ran: boolean;
      input_tokens: number | null; output_tokens: number | null }
  | { kind: 'grade'; attempt_id: string; is_correct: boolean | null; needs_human: boolean };
```

### 3.3 Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | none (no auth) | `{ ok: true, db: boolean, gemini_configured: boolean }` |
| GET | `/api/me` | none | `{ email, display_name }` |
| GET | `/api/taxonomy` | none (send `ETag` / honour `If-None-Match`) | `{ skills: {skill_id, strand, unit, name_en, name_zh, form, foundation}[], errors: {error_id, name_en, name_zh, skills}[], rubric: Record<Letter, {name: string, levels: Record<0\|1\|2\|3, string>}> }` (rubric comes from `rpdice.LEVELS` + `DIMENSION_NAMES`) |
| GET | `/api/papers` | `?level&module&year&exam_type&q` (q matches file_name) | `Page<PaperSummary>`, newest first |
| POST | `/api/papers` | multipart: `pdf` (required), `marking_scheme` (pdf, optional), `meta` (JSON string of `Partial<PaperMeta> & {form?: Level}`), `redo` (bool, default false) | 202 `{ job: Job, sha12, duplicate: false }`, or 200 `{ job: null, sha12, duplicate: true }` when the sha256 is already ingested and `redo` is false |
| GET | `/api/papers/{sha12}` | none | `PaperDetail` |
| POST | `/api/papers/{sha12}/marking-scheme` | multipart: `pdf` | 202 `{ job: Job }` |
| POST | `/api/papers/{sha12}/analyses` | `{ skip_critique?: boolean }` | 202 `{ job: Job }` |
| GET | `/api/questions` | `?paper=<sha12>&level&module&skill=<skill_id>&error=<error_id>&driver=<Letter>` | `Page<QuestionSummary>` |
| GET | `/api/questions/{question_key}` | none | `QuestionDetail` |
| GET | `/api/students` | `?q` (matches student_id or class_name) | `Page<Student>` |
| POST | `/api/students` | `Student` | 201 `Student`; 409 `ALREADY_EXISTS` |
| POST | `/api/attempts` | multipart: `scan`, `student_id`, `question_key` | 202 `{ job: Job }`; 409 `ANALYSIS_REQUIRED`; 404 if the student or question does not exist |
| GET | `/api/attempts` | `?student_id&question_key&needs_review=true` (needs_review = `needs_human` and no review yet) | `Page<AttemptSummary>`, newest first |
| GET | `/api/attempts/{id}` | none | `AttemptDetail` |
| POST | `/api/attempts/{id}/reviews` | `Omit<AttemptReview, 'id'\|'reviewer'\|'created_at'>` | 201 `AttemptReview`. Checks error_ids/skills against the taxonomy and strategy_id against the analysis (422 `VALIDATION`) |
| GET | `/api/gold` | none | `{ items: { question_key, source_question_id, paper_file_name, rated_by_me: boolean, rater_count: number }[] }` |
| GET | `/api/gold/{question_key}` | none | Before the caller rates: `{ question: QuestionDetail with analysis, rpdice, difficulty_drivers, skill_family, primary_status all null, mine: null }`. After: `{ question: QuestionDetail, mine: GoldLabel, others: GoldLabel[], draft: GoldLabel \| null }` (blind until you submit) |
| PUT | `/api/gold/{question_key}` | `{ levels, skills, errors, notes }` | 200 `GoldLabel` (one per rater per question; PUT replaces yours) |
| GET | `/api/gold/agreement` | none | `{ pairs: { a: string, b: string, n: number, exact: Record<Letter, number>, within_one: Record<Letter, number> }[], vs_analyzer: { rater: string, n: number, exact: Record<Letter, number>, within_one: Record<Letter, number> }[] }` |
| GET | `/api/jobs` | `?status&kind&mine=true` | `Page<Job>`, newest first |
| GET | `/api/jobs/{id}` | none | `Job` (the frontend polls every 2 s while `queued` or `running`) |
| GET | `/api/blobs/{path}` | none | The file. `path` must resolve inside `data/diagrams/` or `data/attempts/`; otherwise 404 (no traversal) |

### 3.4 Jobs: what each handler does

All four go through `app/workflows.py` and write disk and Supabase. `target` is the dedup key.

| kind | target | Steps | Fails with |
|---|---|---|---|
| `ingest` | `sha256` | Save the upload as `inbox/web/<safe_name>.pdf` and the meta as a `.meta.txt` sidecar (reuse `paper_meta`); save the scheme as `<safe_name>-ms.pdf`; `PdfIngestionPipeline.run_one_pdf(pdf, marking_scheme_path)`; file away to `processed/pdf/` or `failed/pdf/` exactly as `ingest_pdfs` does | `NO_QUESTIONS_FOUND`, `EMPTY_QUESTION_TEXT`, `PDF_UNREADABLE`, `MODEL_ERROR`, `DB_WRITE_FAILED` |
| `attach_scheme` | `sha12` | `pipeline.attach_marking_scheme(load_extraction(...), path)` → new run | `MARKING_SCHEME_UNUSED`, `MODEL_ERROR`, `DB_WRITE_FAILED` |
| `analyse` | `sha12` | What `analyse_rpdice.main` does for one path, with `skip_critique`; a Critic failure does **not** fail the job (`critic_ran: false`) | `MODEL_ERROR`, `DB_WRITE_FAILED` |
| `grade` | `question_key\|student_id\|scan_sha256` | `locate` → `Grader.grade` → `export_attempt` + copy the scan → `push_attempt` (adding `analysis_run_id`) | `ANALYSIS_REQUIRED`, `MODEL_ERROR`, `DB_WRITE_FAILED` |

### 3.5 Database additions (append to `docs/supabase_schema.sql`)

The file's rules still hold: it can be re-run, it adds and never drops, and it uses the
existing repair block for hand-made tables. Sketch:

```sql
create table if not exists teachers (
  email        text primary key,
  display_name text,
  created_at   timestamptz not null default now()
);

create table if not exists jobs (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null check (kind in ('ingest','attach_scheme','analyse','grade')),
  target      text not null,
  status      text not null default 'queued' check (status in ('queued','running','succeeded','failed')),
  input       jsonb not null default '{}'::jsonb,
  result      jsonb,
  error       jsonb,
  created_by  text not null,
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz
);
create unique index if not exists jobs_one_active
  on jobs (kind, target) where status in ('queued','running');

alter table attempts add column if not exists analysis_run_id text;

create table if not exists attempt_reviews (
  id               uuid primary key default gen_random_uuid(),
  attempt_id       uuid not null,          -- same type as attempts.id (repair block if not uuid)
  reviewer         text not null,
  is_correct       boolean,
  strategy_id      text,
  strategy_match   text check (strategy_match in ('listed','new','none')),
  error_ids        jsonb,
  skills_evidenced jsonb,
  note             text,
  created_at       timestamptz not null default now()
);

create table if not exists gold_labels (
  question_key text not null,
  rater        text not null,
  levels       jsonb not null,              -- {"R":0..3,...}; all six required (app check)
  skills       jsonb not null default '[]'::jsonb,
  errors       jsonb not null default '[]'::jsonb,
  notes        text,
  created_at   timestamptz not null default now(),
  primary key (question_key, rater)
);

drop view if exists current_analyses;
create view current_analyses as select * from question_analyses where is_current;

drop view if exists attempts_effective;
create view attempts_effective as
  select a.*,
         r.id is not null                                as reviewed,
         coalesce(r.is_correct, a.is_correct)             as eff_is_correct,
         coalesce(r.strategy_id, a.strategy_id)           as eff_strategy_id,
         coalesce(r.strategy_match, a.strategy_match)     as eff_strategy_match,
         coalesce(r.error_ids, a.error_ids)               as eff_error_ids,
         coalesce(r.skills_evidenced, a.skills_evidenced) as eff_skills_evidenced
    from attempts a
    left join lateral (select * from attempt_reviews x where x.attempt_id = a.id
                        order by x.created_at desc limit 1) r on true;

-- Every table: RLS on, no policies. Only the backend's secret key reads.
alter table source_documents  enable row level security;   -- … and the same for every table above
```

A known limitation of the view: `coalesce` cannot express "the reviewer set `is_correct` back to
null". That is acceptable for v1.

### 3.6 Rendering contract (frontend)

- `question_text`, `options`, `worked_solution`, `steps` and `evidence` are Markdown (with GFM
  tables), and **all** LaTeX is inside `\( … \)` (the extractor prompt enforces this; there is
  no `$` and no `\[`).
- **Gotcha:** CommonMark treats `\(` as an escaped `(` and silently drops the backslash. Split
  the math out **before** the Markdown pass: turn each `\(…\)` into `katex.renderToString`
  output behind a placeholder, render the rest as Markdown, then put the math back. Write one
  `<MathText>` component and use it everywhere.
- Skill and error ids are never shown raw. Look them up in `/api/taxonomy` and show `name_zh`,
  with `name_en` and the id in a tooltip. Unknown ids show the id in a warning style.
- RPDICE is shown as six cells, one per letter, coloured 0–3, with no total, ever (spec §1:
  "不加總"). Label it as a model estimate with the run id and date. Show the Critic status badge
  next to the primary strategy.
- A `strategy_id` that does not appear in the current analysis is shown as "strategy from an
  earlier analysis run", not as an error (see risk 2).
- Scans: `<img>` for images, `<iframe>` or `<object>` for PDF. Both need the auth header, so
  fetch the file as a blob, then use `URL.createObjectURL`.

---

## 4. Tasks

### Backend (`server/`, `app/workflows.py`, `docs/supabase_schema.sql`)

Phase order. Every phase keeps `pytest` green; none needs network access.

- **B0 Schema.** Append section 3.5 to `docs/supabase_schema.sql` (follow the repair-block
  pattern and add the new columns and tables to `db_check`'s readiness list). Add
  `analysis_run_id` to `attempt_row`. Turn on RLS for every table.
- **B1 Workflows.** Move the script bodies into `app/workflows.py`:
  `ingest(pdf, scheme=None, meta=None, redo=False)`, `attach_scheme(sha12, pdf)`,
  `analyse(sha12, skip_critique=False)`, `grade(scan, student_id, question_key)`,
  `locate(question_key)`. Each returns a result object and **raises** on DB failure when
  `require_db=True`. The scripts call these functions and keep their printing; their existing
  tests must pass unchanged.
- **B2 Read API.** FastAPI app with an auth dependency (verify the Supabase JWT against the
  project's JWKS or JWT secret, then look up `teachers`), the `ApiError` handler, and these
  routes: `health`, `me`, `taxonomy`, `papers` (list and detail), `questions` (list and
  detail), `students`, `attempts` (list and detail), `blobs` (with the path-traversal guard and
  its test). Read from `current_questions`, `current_analyses` and `attempts_effective`.
- **B3 Jobs.** The `jobs` table, a worker thread with concurrency 1, the startup sweep
  (`running` → `failed/INTERRUPTED`), and the four handlers from section 3.4. Wire up
  `POST /papers`, `/marking-scheme`, `/analyses` and `/attempts`, plus `GET /jobs`. Turn
  `jobs_one_active` violations into `409 JOB_ALREADY_RUNNING`. Enforce upload size and MIME
  limits.
- **B4 Review + gold.** `POST /attempts/{id}/reviews` (validated against the taxonomy and the
  analysis), the `gold` routes with blind reveal, `agreement`, and
  `scripts/export_gold.py --rater <email>`, which writes a CSV that `rpdice.read_gold` and
  `validate_gold` accept (one rater per file, `status=confirmed`).
- **B5 Ship.** Serve `web/dist` from the same app (no CORS). Write a Dockerfile, and document
  the persistent volume for `data/ inbox/ processed/ failed/`. New env: `SUPABASE_JWT_SECRET`
  (or the JWKS URL). New deps: `fastapi`, `uvicorn`, `python-multipart`, `pyjwt`. Python 3.9
  must still work.

### Frontend (`web/`)

Stack: React + Vite + TypeScript, react-router, `@supabase/supabase-js` (sign-in only),
`katex`, one Markdown library (`marked` or `markdown-it`). Use plain `fetch` through one
`api()` helper that adds the token and parses `ApiError`; add a query library only if caching
actually hurts. Types come from `openapi-typescript`. Until B2 lands, work against fixtures
built from section 3.2.

- **F0 Shell.** Login (magic link), an auth guard, the `api()` helper, a taxonomy cache
  (loaded once, keyed by ETag), the `<MathText>` from section 3.6, and an `<Rpdice>` 6-cell
  strip with evidence on hover.
- **F1 Browse (read-only).** `/papers` (filters, table); `/papers/:sha12` (meta, run and token
  info, issues, the question table with RPDICE strips, drivers and status); `/questions/:key`
  (text, images, options, links to `depends_on`, a tab per strategy with steps, skills, all six
  letters with evidence, the solution and status, possible errors, Critic issues, and the
  attempts list).
- **F2 Actions + jobs.** The upload dialog (PDF, optional scheme, meta form; show the
  `duplicate: true` case clearly), attach scheme, run/re-run analysis (confirm first, and say
  it costs model calls and may change letters), `/attempts/new?question=` (student picker with
  inline create, scan upload), and a jobs drawer that polls active jobs and links to the result.
- **F3 Review.** `/review` (queue = `needs_review=true`); `/attempts/:id` with the scan and the
  transcription side by side, the Grader's verdict, strategy, skills shown and not shown, and
  slips versus misconceptions, plus an override form where each field defaults to "agree with
  the Grader" and errors and skills are pickers limited to the taxonomy.
- **F4 Gold.** `/gold` queue (yours versus everyone's); `/gold/:key` with a blind form (six
  0–3 radios, each showing its rubric sentence from `/api/taxonomy` `rubric`, plus skills and
  errors pickers); after you submit, show the Analyzer, the draft and the other raters side by
  side; `/gold/agreement` table.

Who owns what at the seams: **Backend** owns every correctness rule (taxonomy membership,
strategy existence, blind reveal, dedup, path guard). **Frontend** owns presentation only, and
must never compute a verdict, an "effective" value or a level.

---

## 5. Rollout

| Phase | Ships | Exit check |
|---|---|---|
| P0 | B0 + `db_push` / `db_push_taxonomy` backfill of the existing JSON | `db_check` green, `current_analyses` has rows |
| P1 | B1, B2 + F0, F1 | A teacher opens Q24 of `2526_2nd_S4MATH2` and sees R2 with its evidence. No Gemini spend |
| P2 | B3 + F2 | Upload a paper → analysed → grade one page, all in the browser; CLI tests still pass |
| P3 | B4 + F3, F4 | Two teachers rate the 30 gold items; `export_gold` → `score_rpdice` runs |
| P4 | B5 | Deployed on a host with a persistent volume; a restart loses nothing but in-flight jobs |

Each phase can be released on its own. Before P2 the UI hides the write buttons and the backend
returns 404 for write routes.

---

## 6. Open risks

1. **The disk and Supabase can diverge.** A job writes the JSON and then the DB push fails.
   Mitigation: the job fails loudly, and `db_push` re-syncs. Ceiling: one host. Most PaaS disks
   are ephemeral, so a persistent volume is mandatory; otherwise move to Supabase Storage first.
2. **Strategy ids drift.** `strategy_id = hash(name, skills)`, so a re-analysis that adds one
   skill to a strategy gives it a new id, and old attempts point at an id the current analysis
   no longer has. Mitigation: store `analysis_run_id` on new attempts (B0) and show unresolved
   ids softly. The real fix (carrying ids across runs) belongs to the Analyzer and is out of
   scope here.
3. **Analyzer noise.** About 10% of letters move one level between identical runs (`deviations_from_guide.md` §46).
   Teachers will see letters change after a re-run. Mitigation: show the run id and date
   everywhere and confirm before a re-run. There is no diff UI in v1.
4. **Gemini cost.** Any teacher can trigger spend. Mitigation: sha dedup,
   `jobs_one_active`, concurrency 1, and tokens recorded in the job result. There is **no
   budget cap** in v1.
5. **Privacy (HK PDPO).** Scans are personal data. Every route, blobs included, is behind auth;
   there are no names; RLS is on. **Not in v1:** deleting an attempt or student, and a retention
   policy. Agree these with the school before real student pages go in.
6. **Math rendering.** The `\(` escape described in section 3.6. If `<MathText>` is wrong, every
   formula breaks silently.
7. **Schema drift in hand-made tables.** The user's tables were created by hand with their own
   id types. `attempt_reviews.attempt_id` must match `attempts.id`; use the repair block and do
   not assume uuid.
8. **One worker.** Twenty papers uploaded at once take about 15 minutes to drain. That is
   acceptable for one school; the upgrade path is in decision 4.
