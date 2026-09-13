"""Push the skills and error patterns into Supabase.

    python3 -m scripts.db_push_taxonomy

Upserts on skill_id / error_id, so re-running after an edit updates rows in
place. Rows removed from the CSV are left in the database, deliberately:
an analysis may still reference them.
"""

from __future__ import annotations

from app.config import load_settings
from app.supabase_store import StoreError, connect, key_warning
from app.taxonomy import load_taxonomy

TABLE_SKILLS = "skills"
TABLE_ERRORS = "error_patterns"


def skill_rows(taxonomy) -> list[dict]:
    return [{
        "skill_id": s.skill_id, "strand": s.strand, "unit": s.unit,
        "name_en": s.name_en, "name_zh": s.name_zh, "form": s.form,
        "foundation": s.foundation, "prerequisites": list(s.prerequisites),
    } for s in taxonomy.skills.values()]


def error_rows(taxonomy) -> list[dict]:
    return [{
        "error_id": e.error_id, "name_en": e.name_en, "name_zh": e.name_zh,
        "skills": list(e.skills), "description": e.description,
    } for e in taxonomy.errors.values()]


def main() -> int:
    settings = load_settings()
    url, key = settings.supabase_url, settings.supabase_secret_key
    if not url or not key or url.startswith("put_") or key.startswith("put_"):
        print("SUPABASE_URL / SUPABASE_SECRET_KEY are not set in .env.")
        return 2
    warning = key_warning(key)
    if warning:
        print(f"Warning: {warning}")

    taxonomy = load_taxonomy()            # raises with every problem if invalid
    try:
        client = connect(url, key)
    except StoreError as exc:
        print(exc)
        return 2

    client.table(TABLE_SKILLS).upsert(skill_rows(taxonomy), on_conflict="skill_id").execute()
    client.table(TABLE_ERRORS).upsert(error_rows(taxonomy), on_conflict="error_id").execute()
    print(f"Pushed {len(taxonomy.skills)} skills and {len(taxonomy.errors)} error patterns "
          f"to {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
