"""Guard the minimum Python version.

Python 3.9 (the macOS system interpreter) cannot evaluate `str | Path` at
runtime. Annotations that use it must stay unevaluated, and Pydantic model
fields - which are always resolved - must not use it at all.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import app
from app import config, document_loader, schemas


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("app", "scripts", "tests")


def python_files() -> list[pathlib.Path]:
    return sorted(
        path
        for directory in SOURCE_DIRS
        for path in (PROJECT_ROOT / directory).rglob("*.py")
    )


def _unions(annotation) -> list[ast.BinOp]:
    if annotation is None:
        return []
    return [
        node for node in ast.walk(annotation)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
    ]


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


@pytest.mark.parametrize("path", python_files(), ids=lambda p: p.name)
def test_pep604_unions_are_guarded_by_future_import(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if _has_future_annotations(tree):
        return

    offenders = []
    for node in ast.walk(tree):
        annotation = None
        if isinstance(node, (ast.AnnAssign, ast.arg)):
            annotation = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation = node.returns
        if _unions(annotation):
            offenders.append(node.lineno)

    assert not offenders, (
        f"{path.relative_to(PROJECT_ROOT)} uses 'X | Y' annotations on lines "
        f"{offenders} without 'from __future__ import annotations'. "
        "That raises TypeError on Python 3.9."
    )


@pytest.mark.parametrize("model", [
    schemas.ExtractedQuestion,
    schemas.QuestionExtractionPayload,
    schemas.ExtractedDocument,
    schemas.SourceDocument,
    schemas.ExtractionRun,
    schemas.ValidationIssue,
    schemas.ExtractionResult,
], ids=lambda m: m.__name__)
def test_model_fields_avoid_pep604(model):
    # Pydantic resolves these even when they are strings, so `|` is never safe.
    annotations = vars(model).get("__annotations__", {})
    assert not [name for name, ann in annotations.items() if "|" in str(ann)]


@pytest.mark.parametrize("klass", [document_loader.LoadedDocument, config.Settings],
                         ids=lambda k: k.__name__)
def test_dataclass_fields_avoid_pep604(klass):
    import dataclasses
    assert not [f.name for f in dataclasses.fields(klass) if "|" in str(f.type)]


def test_minimum_python_is_declared():
    assert app.MINIMUM_PYTHON == (3, 9)
