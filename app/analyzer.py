"""Run the RPDICE Analyzer over an extraction.

The Analyzer is the assessor: it reads the questions a paper was extracted
into and says what each demands. It does not touch the question text, does
not see student data, and its output is checked against the taxonomy and the
standard before it is kept.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional
import uuid

from pydantic import BaseModel, Field

from app.config import load_settings
from app.gemini_client import GeminiClient, prompt_sha256
from app.paths import ANALYSES_DIR, PROMPT_ANALYZER_V1, safe_stem
from app.question_key import question_key
from app.rpdice import (AnalysisPayload, QuestionAnalysis, drivers_of, profile_summary,
                        rubric_text, validate_analysis)
from app.schemas import ExtractionResult, ValidationIssue
from app.taxonomy import Taxonomy, load_taxonomy


ANALYZER_VERSION = "RPDICE_v1"


class AnalysisRun(BaseModel):
    run_id: str
    analysed_at: str
    analyzer_version: str
    model: str
    prompt_sha256: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class AnalysisResult(BaseModel):
    """One Analyzer run over one paper."""

    file_name: str
    sha256: str
    extraction_run_id: Optional[str] = None
    level: Optional[str] = None
    run: AnalysisRun
    analyses: list[QuestionAnalysis]
    issues: list[ValidationIssue] = Field(default_factory=list)

    def by_key(self) -> dict[str, QuestionAnalysis]:
        return {question_key(self.sha256, a.source_question_id): a for a in self.analyses}


# --- the prompt ---------------------------------------------------------------

def skills_block(taxonomy: Taxonomy) -> str:
    lines = ["SKILLS (skill_id | unit | form | name)"]
    for s in taxonomy.skills.values():
        lines.append(f"{s.skill_id} | {s.unit} | {s.form} | {s.name_en}")
    return "\n".join(lines)


def errors_block(taxonomy: Taxonomy) -> str:
    lines = ["ERRORS (error_id | skills | name)"]
    for e in taxonomy.errors.values():
        lines.append(f"{e.error_id} | {';'.join(e.skills)} | {e.name_en}")
    return "\n".join(lines)


def questions_block(result: ExtractionResult) -> str:
    rows = []
    for q in result.document.questions:
        rows.append({
            "source_question_id": q.source_question_id,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "options": list(q.options),
            "depends_on": list(q.depends_on),
            "marks": q.marks,
        })
    return "QUESTIONS\n" + json.dumps(rows, ensure_ascii=False, indent=1)


def build_prompt(result: ExtractionResult, taxonomy: Taxonomy,
                 prompt_path: Path = PROMPT_ANALYZER_V1) -> str:
    template = Path(prompt_path).read_text(encoding="utf-8")
    form = (result.document.level or "F4").lstrip("F")
    head = template.replace("{RUBRIC}", rubric_text()).replace("{FORM}", form)
    return "\n\n".join([head, skills_block(taxonomy), errors_block(taxonomy),
                        questions_block(result)])


# --- checking the whole payload against the paper -----------------------------

def check_payload(payload: AnalysisPayload, result: ExtractionResult,
                  taxonomy: Taxonomy) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    texts = {q.source_question_id: q.question_text for q in result.document.questions}
    seen = [a.source_question_id for a in payload.analyses]

    for qid in texts:
        if qid not in seen:
            issues.append(ValidationIssue(issue_code="QUESTION_NOT_ANALYSED", severity="high",
                                          message=f"{qid}: no analysis returned.",
                                          source_question_id=qid))
    for analysis in payload.analyses:
        if analysis.source_question_id not in texts:
            issues.append(ValidationIssue(issue_code="ANALYSIS_FOR_UNKNOWN_QUESTION",
                                          severity="high",
                                          message=f"{analysis.source_question_id}: analysed but "
                                                  f"not in the paper.",
                                          source_question_id=analysis.source_question_id))
            continue
        if seen.count(analysis.source_question_id) > 1:
            issues.append(ValidationIssue(issue_code="DUPLICATE_ANALYSIS", severity="medium",
                                          message=f"{analysis.source_question_id}: analysed "
                                                  f"more than once.",
                                          source_question_id=analysis.source_question_id))
        issues.extend(validate_analysis(analysis, texts[analysis.source_question_id], taxonomy))
    return issues


def repair_drivers(payload: AnalysisPayload) -> int:
    """difficulty_drivers is derivable, so a wrong list is recomputed, not argued about."""
    fixed = 0
    for analysis in payload.analyses:
        primary = analysis.primary()
        if primary is None:
            continue
        expected = drivers_of(primary.rpdice.levels())
        if sorted(analysis.difficulty_drivers) != sorted(expected):
            analysis.difficulty_drivers = expected
            fixed += 1
    return fixed


# --- running it ---------------------------------------------------------------

class RpdiceAnalyzer:
    def __init__(self, gemini=None, taxonomy: Optional[Taxonomy] = None):
        self.settings = load_settings()
        self.gemini = gemini or GeminiClient()
        self.taxonomy = taxonomy or load_taxonomy()

    def analyse(self, result: ExtractionResult) -> AnalysisResult:
        prompt = build_prompt(result, self.taxonomy)
        payload: AnalysisPayload = self.gemini.generate_json(prompt, AnalysisPayload)
        repair_drivers(payload)
        issues = check_payload(payload, result, self.taxonomy)
        usage = getattr(self.gemini, "last_usage", {}) or {}
        return AnalysisResult(
            file_name=result.document.file_name,
            sha256=result.source.sha256 if result.source else "",
            extraction_run_id=result.run.run_id if result.run else None,
            level=result.document.level,
            run=AnalysisRun(
                run_id=uuid.uuid4().hex[:12],
                analysed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                analyzer_version=ANALYZER_VERSION,
                model=self.settings.gemini_extractor_model,
                prompt_sha256=prompt_sha256(PROMPT_ANALYZER_V1),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
            ),
            analyses=list(payload.analyses),
            issues=issues,
        )


# --- saving -------------------------------------------------------------------

def analysis_output_path(result: AnalysisResult) -> Path:
    return ANALYSES_DIR / f"{safe_stem(result.file_name)}-{result.sha256[:12]}.json"


def analysis_history_path(result: AnalysisResult) -> Path:
    stem = analysis_output_path(result).stem
    return ANALYSES_DIR / "history" / stem / f"{result.run.run_id}.json"


def export_analysis_json(result: AnalysisResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_analysis(path: Path) -> AnalysisResult:
    return AnalysisResult.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def render_analysis_markdown(result: AnalysisResult, taxonomy: Taxonomy) -> str:
    lines = [f"# RPDICE — {result.file_name}", "",
             f"Run `{result.run.run_id}` · {result.run.analyzer_version} · {result.run.model} · "
             f"prompt `{result.run.prompt_sha256}` · {len(result.analyses)} questions · "
             f"{len(result.issues)} issues", "",
             "| Q | RPDICE | drivers | skills | conf |", "|---|---|---|---|---|"]
    for a in result.analyses:
        names = ", ".join(taxonomy.skills[s].name_en if s in taxonomy.skills else f"?{s}"
                          for s in a.atomic_skills)
        lines.append(f"| {a.source_question_id} | `{profile_summary(a.levels())}` | "
                     f"{''.join(a.difficulty_drivers)} | {names} | {a.confidence:.1f} |")
    lines.append("")
    for a in result.analyses:
        lines += [f"## {a.source_question_id} — {a.skill_family}", ""]
        for s in a.strategies:
            flag = " (primary)" if s.is_primary else ""
            lines += [f"**{s.strategy_name}{flag}** `{profile_summary(s.rpdice.levels())}`", ""]
            lines += [f"1. {step}" for step in s.steps] + [""]
            for d in ("R", "P", "D", "I", "C", "E"):
                dim = getattr(s.rpdice, d)
                if dim.evidence:
                    lines.append(f"- {d}{dim.level}: " + "; ".join(dim.evidence))
            lines.append("")
        if a.possible_errors:
            lines += ["Errors: " + ", ".join(a.possible_errors), ""]
        if a.method_cues:
            lines += ["Method cues: " + " / ".join(f"“{c}”" for c in a.method_cues), ""]
        for note in a.structural_depth_notes:
            lines += [f"> {note}", ""]
        if a.proposed_skills or a.proposed_errors:
            lines += ["Proposed: " + ", ".join(a.proposed_skills + a.proposed_errors), ""]
    if result.issues:
        lines += ["## Issues", "", "| Severity | Code | Q | Message |", "|---|---|---|---|"]
        for i in result.issues:
            message = i.message.replace("|", "\\|")
            lines.append(f"| {i.severity} | `{i.issue_code}` | {i.source_question_id or ''} | "
                         f"{message} |")
        lines.append("")
    return "\n".join(lines)
