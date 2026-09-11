# Math Question System v1.1
## PDF Ingestion System 小六學生版

**目標：** 由零開始，做一個可以讀 PDF 數學題，拆成一條條題目的系統。

**今份教材只做 PDF Digest / Ingestion。**  暫時不做解題、RPDICE、難度分析、學生能力分析、自動出題。

---

# 顏色規則

| 標記 | 意思 |
|---|---|
| 🔵 Python | 要建立 / 修改的 Python file |
| 🟢 Prompt | 給 Gemini 的指令文字 |
| 🟡 Config | 設定檔 |
| 🟣 Supabase | Database，暫時你自己做 |
| 🔴 Test | 測試 |
| ⚪ Output | 完成後應該得到甚麼 |

---

# Part 1 — 先認識整個系統

## Lesson 01 — 這個系統做甚麼？

### 🎯 Goal

明白 PDF Ingestion System 的工作。

### 📖 故事

想像你有一本數學練習，入面有 Q1、Q2、Q3。你想電腦幫你把每條題目剪開，再放入不同文件夾。

這就是 PDF Ingestion。

### 系統流程

```text
PDF
 ↓
讀取 PDF
 ↓
逐頁拆開
 ↓
找出每條題目
 ↓
保留數學符號
 ↓
檢查有沒有錯
 ↓
變成 Question Object
```

### 今日不要做

不要做解題、分析難度、分析學生、RPDICE。

### ✔ Check

- [ ] 我知道 PDF Ingestion 是「讀 PDF + 拆題」
- [ ] 我知道它不是解題系統

---

## Lesson 02 — 建立 Project Folder

### 🎯 Goal

建立一個乾淨的 Project。

### 📁 建立 Folder

建立一個 folder，叫：

```text
math-question-system
```

入面建立：

```text
math-question-system/
├── app/
├── prompts/
├── config/
├── scripts/
├── data/
├── inbox/
├── processed/
├── failed/
├── tests/
└── docs/
```

### 每個 folder 做甚麼？

| Folder | 用途 |
|---|---|
| app | 放 Python 工人 |
| prompts | 放 Gemini 指令 |
| config | 放設定 |
| scripts | 放可以執行的入口 |
| data | 放測試題 / JSON 輸出 |
| inbox | 放未處理 PDF |
| processed | 放已成功 PDF |
| failed | 放失敗 PDF |
| tests | 放測試 |
| docs | 放說明 |

### 🔵 Python

今天只建立 folder，不寫 Python。

### 🟢 Prompt

今天只建立 folder，不寫 Prompt。

### ✔ Check

- [ ] `math-question-system/` 已建立
- [ ] `app/` 已建立
- [ ] `prompts/` 已建立
- [ ] `inbox/` 已建立

---

## Lesson 03 — 建立 PDF 收件箱

### 🎯 Goal

建立放 PDF 的地方。

### 📁 Folder

建立：

```text
inbox/pdf/
processed/pdf/
failed/pdf/
```

意思：

```text
inbox/pdf      = 未做的 PDF
processed/pdf  = 做完成功的 PDF
failed/pdf     = 做失敗的 PDF
```

### 📖 故事

好似學校收功課。

```text
未改的功課 → inbox
改好的功課 → processed
有問題的功課 → failed
```

### ✔ Check

- [ ] `inbox/pdf/` 已建立
- [ ] `processed/pdf/` 已建立
- [ ] `failed/pdf/` 已建立

---

# Part 2 — 設定環境

## Lesson 04 — requirements.txt

### 🎯 Goal

告訴 Python 要用甚麼工具。

### 🟡 Config

**File：**

```text
requirements.txt
```

**放入：**

```txt
google-genai
pydantic>=2
python-dotenv
pypdf
tenacity
supabase
```

### 🧠 點解？

Python 好似學生。Package 好似文具。沒有文具，學生做不到功課。

### ✔ Check

- [ ] `requirements.txt` 已建立
- [ ] 入面有 `google-genai`
- [ ] 入面有 `pypdf`

---

## Lesson 05 — .env.example

### 🎯 Goal

建立設定樣板。

### 🟡 Config

**File：**

```text
.env.example
```

**放入：**

```env
GEMINI_API_KEY=put_your_key_here
GEMINI_EXTRACTOR_MODEL=put_model_name_here

SUPABASE_URL=put_supabase_url_here
SUPABASE_SECRET_KEY=put_supabase_secret_key_here

EXTRACTION_VERSION=QEE_v1
QUESTION_OBJECT_VERSION=QOS_v1
```

### 🧠 點解？

`.env` 放秘密。`.env.example` 只係樣板，不能放真正 secret。

### ✔ Check

- [ ] `.env.example` 已建立
- [ ] 沒有真正 secret key

---

## Lesson 06 — app/config.py

### 🎯 Goal

讓 Python 讀取設定。

### 🔵 Python

**File：**

```text
app/config.py
```

**工作：**

- 讀 `.env`
- 拿 Gemini key
- 拿 model name
- 拿 Supabase setting

### 🔵 Code

```python
from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass
class Settings:
    gemini_api_key: str
    gemini_extractor_model: str
    supabase_url: str
    supabase_secret_key: str
    extraction_version: str
    question_object_version: str


def load_settings() -> Settings:
    load_dotenv()

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_extractor_model=os.getenv("GEMINI_EXTRACTOR_MODEL", ""),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY", ""),
        extraction_version=os.getenv("EXTRACTION_VERSION", "QEE_v1"),
        question_object_version=os.getenv("QUESTION_OBJECT_VERSION", "QOS_v1"),
    )
```

### 不負責

`config.py` 不可以讀 PDF、叫 Gemini、寫 database、拆題。

### ✔ Check

- [ ] `app/config.py` 已建立
- [ ] 有 `load_settings()`

---

# Part 3 — Question Object

## Lesson 07 — Question Object 是甚麼？

### 🎯 Goal

明白系統最後要輸出甚麼。

### 📖 故事

一條題目要放入一張表格。表格要有題號、題目、頁數、分數、答案、有沒有圖、有沒有錯。

這張表格就叫 Question Object。

### ⚪ Output Example

```json
{
  "question_number": "1",
  "page_start": 1,
  "page_end": 1,
  "question_text": "Factorise 1 - 225x².",
  "marks": 2,
  "answer": null,
  "worked_solution": null,
  "diagram_required": false
}
```

### ✔ Check

- [ ] 我知道 Question Object 是「一條題目的資料表」
- [ ] 我知道它不是答案分析

---

## Lesson 08 — app/schemas.py

### 🎯 Goal

建立 Question Object 的格式。

### 🔵 Python

**File：**

```text
app/schemas.py
```

**工作：**

規定每個 Question Object 要有甚麼欄位。

### 🔵 Code

```python
from pydantic import BaseModel, Field
from typing import Optional


class ExtractedQuestion(BaseModel):
    source_question_id: str
    page_start: int
    page_end: int
    question_text: str
    marks: Optional[float] = None
    answer: Optional[str] = None
    worked_solution: Optional[str] = None
    diagram_required: bool = False
    extraction_notes: list[str] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    file_name: str
    page_count: int
    questions: list[ExtractedQuestion]


class ValidationIssue(BaseModel):
    issue_code: str
    severity: str
    message: str


class ExtractionResult(BaseModel):
    document: ExtractedDocument
    issues: list[ValidationIssue] = Field(default_factory=list)
```

### 🧠 點解？

如果沒有格式，Gemini 可能每次交不同名字：`question_text`、`text`、`problem`。Database 就會亂。

### 不負責

`schemas.py` 不可以讀 PDF、分析題目、寫 database。

### ✔ Check

- [ ] 有 `ExtractedQuestion`
- [ ] 有 `ExtractedDocument`
- [ ] 有 `ExtractionResult`

---

# Part 4 — 讀 PDF

## Lesson 09 — app/document_loader.py

### 🎯 Goal

讀取 PDF 基本資料。

### 📖 故事

Document Loader 是收件員。他只做：收 PDF、看檔名、數頁數、計 hash。

### 🔵 Python

**File：**

```text
app/document_loader.py
```

### 🔵 Code

```python
from dataclasses import dataclass
from pathlib import Path
import hashlib
from pypdf import PdfReader


@dataclass
class LoadedDocument:
    file_path: Path
    file_name: str
    sha256: str
    page_count: int


def calculate_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_pdf(file_path: str | Path) -> LoadedDocument:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {path}")

    reader = PdfReader(str(path))

    return LoadedDocument(
        file_path=path,
        file_name=path.name,
        sha256=calculate_sha256(path),
        page_count=len(reader.pages),
    )
```

### 不負責

Document Loader 不可以拆題、解題、OCR、改 PDF 文字。

### ⚪ Output

```text
file_name
sha256
page_count
```

### ✔ Check

- [ ] 能讀 PDF
- [ ] 能取得 page count
- [ ] 能計 SHA256

---

## Lesson 10 — scripts/test_load_pdf.py

### 🎯 Goal

測試能否讀 PDF。

### 🔴 Test

**File：**

```text
scripts/test_load_pdf.py
```

### 🔴 Code

```python
from app.document_loader import load_pdf


def main():
    pdf_path = "inbox/pdf/sample.pdf"
    doc = load_pdf(pdf_path)

    print("File:", doc.file_name)
    print("Pages:", doc.page_count)
    print("SHA256:", doc.sha256)


if __name__ == "__main__":
    main()
```

### 做法

1. 放一個 PDF 入：

```text
inbox/pdf/sample.pdf
```

2. 執行：

```bash
python -m scripts.test_load_pdf
```

### ✔ Check

- [ ] Terminal 顯示 File name
- [ ] Terminal 顯示 Pages
- [ ] Terminal 顯示 SHA256

---

# Part 5 — Gemini Prompt

## Lesson 11 — prompts/document_extractor_v1.txt

### 🎯 Goal

寫一張工作紙給 Gemini。

### 🟢 Prompt

**File：**

```text
prompts/document_extractor_v1.txt
```

### 🟢 Content

```text
ROLE
You are a careful mathematics worksheet clerk.

MISSION
Read the supplied PDF and extract the questions faithfully.

INPUT
A mathematics PDF.

OUTPUT
Structured JSON matching the extraction schema.

DO
- Extract each question separately.
- Preserve question numbers.
- Preserve mathematical symbols.
- Preserve fractions, powers, equations and inequalities.
- Preserve marks if printed.
- Preserve answers if printed.
- Preserve worked solutions if printed.
- Mark diagram_required=true if a diagram is needed.

DON'T
- Do not solve questions.
- Do not analyse skills.
- Do not estimate difficulty.
- Do not perform RPDICE.
- Do not rewrite the question in your own style.
- Do not invent missing answers.

QUALITY RULE
If you are unsure, add an extraction note.

RETURN
JSON only.
```

### 🧠 點解？

Gemini 好似一個新同學。你要清楚講：只可以抄題，不可以解題。

### ✔ Check

- [ ] Prompt 已建立
- [ ] 有 DO
- [ ] 有 DON'T
- [ ] 有 JSON only

---

# Part 6 — Gemini Client

## Lesson 12 — app/gemini_client.py

### 🎯 Goal

建立一個負責叫 Gemini 的 file。

### 🔵 Python

**File：**

```text
app/gemini_client.py
```

**工作：**

- 建立 Gemini client
- 讀 prompt
- 傳 PDF 給 Gemini
- 拿 JSON 回來

### 🔵 Code

```python
from pathlib import Path
from google import genai
from google.genai import types

from app.config import load_settings


def read_prompt(prompt_path: str | Path) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


class GeminiClient:
    def __init__(self):
        self.settings = load_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY in .env")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def extract_pdf_json(self, pdf_path: str | Path, prompt_path: str | Path, schema):
        prompt = read_prompt(prompt_path)
        uploaded_file = self.client.files.upload(file=str(pdf_path))

        response = self.client.models.generate_content(
            model=self.settings.gemini_extractor_model,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        if response.parsed is not None:
            return response.parsed

        return schema.model_validate_json(response.text)
```

### 不負責

`gemini_client.py` 不可以決定題目對錯、寫 database、自己改 prompt、分析 difficulty。

### ✔ Check

- [ ] 有 `GeminiClient`
- [ ] 有 `extract_pdf_json`

---

# Part 7 — Document Extractor

## Lesson 13 — app/document_extractor.py

### 🎯 Goal

把 PDF 變成 ExtractedDocument。

### 📖 故事

Document Extractor 是抄題員。他拿 PDF，請 Gemini 幫忙抄題。

### 🔵 Python

**File：**

```text
app/document_extractor.py
```

### 🔵 Code

```python
from pathlib import Path

from app.document_loader import load_pdf
from app.gemini_client import GeminiClient
from app.schemas import ExtractedDocument


PROMPT_PATH = "prompts/document_extractor_v1.txt"


class DocumentExtractor:
    def __init__(self):
        self.gemini = GeminiClient()

    def extract(self, pdf_path: str | Path) -> ExtractedDocument:
        loaded = load_pdf(pdf_path)

        document = self.gemini.extract_pdf_json(
            pdf_path=loaded.file_path,
            prompt_path=PROMPT_PATH,
            schema=ExtractedDocument,
        )

        if document.file_name != loaded.file_name:
            document.file_name = loaded.file_name

        if document.page_count != loaded.page_count:
            document.page_count = loaded.page_count

        return document
```

### 不負責

Document Extractor 不可以解題、RPDICE、Skill analysis、判斷學生能力。

### ⚪ Output

```text
ExtractedDocument
  ├── file_name
  ├── page_count
  └── questions[]
```

### ✔ Check

- [ ] PDF 可以變成 ExtractedDocument
- [ ] 每條題目是獨立 object

---

# Part 8 — Extraction Validation

## Lesson 14 — app/extraction_validator.py

### 🎯 Goal

檢查拆題結果有沒有明顯問題。

### 🔵 Python

**File：**

```text
app/extraction_validator.py
```

### 🔵 Code

```python
from app.schemas import ExtractedDocument, ValidationIssue


def validate_extraction(document: ExtractedDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if document.page_count <= 0:
        issues.append(ValidationIssue(
            issue_code="PAGE_COUNT_INVALID",
            severity="high",
            message="Document page_count is invalid.",
        ))

    if not document.questions:
        issues.append(ValidationIssue(
            issue_code="NO_QUESTIONS_FOUND",
            severity="critical",
            message="No questions were extracted.",
        ))

    seen_ids = set()

    for q in document.questions:
        if not q.question_text.strip():
            issues.append(ValidationIssue(
                issue_code="EMPTY_QUESTION_TEXT",
                severity="critical",
                message=f"Question {q.source_question_id} has empty text.",
            ))

        if q.source_question_id in seen_ids:
            issues.append(ValidationIssue(
                issue_code="DUPLICATE_QUESTION_ID",
                severity="medium",
                message=f"Duplicate question id: {q.source_question_id}",
            ))

        seen_ids.add(q.source_question_id)

        if q.page_start <= 0 or q.page_end <= 0:
            issues.append(ValidationIssue(
                issue_code="PAGE_NUMBER_INVALID",
                severity="high",
                message=f"Question {q.source_question_id} has invalid page number.",
            ))

        if q.page_end < q.page_start:
            issues.append(ValidationIssue(
                issue_code="PAGE_RANGE_INVALID",
                severity="high",
                message=f"Question {q.source_question_id} page_end is before page_start.",
            ))

        if "x2" in q.question_text and "x²" not in q.question_text and "x^2" not in q.question_text:
            issues.append(ValidationIssue(
                issue_code="POSSIBLE_BROKEN_POWER",
                severity="medium",
                message=f"Question {q.source_question_id} may have broken power notation.",
            ))

    return issues
```

### 🧠 點解？

Gemini 可能抄錯。Validator 好似老師檢查：有冇漏題、空題、頁數錯。

### ✔ Check

- [ ] 沒有題目時會報錯
- [ ] 重複題號會報錯
- [ ] 空題會報錯

---

# Part 9 — Repository

## Lesson 15 — app/repository.py

### 🎯 Goal

集中處理保存資料。

### 📖 故事

Repository 是倉務員。所有資料要入倉，都交俾 Repository。其他人不直接寫 Database。

### 🔵 Python

**File：**

```text
app/repository.py
```

### 🔵 Code

```python
from app.config import load_settings
from app.schemas import ExtractedDocument, ValidationIssue


class Repository:
    def __init__(self):
        self.settings = load_settings()

    def save_extracted_document(
        self,
        document: ExtractedDocument,
        issues: list[ValidationIssue],
    ) -> None:
        # Phase 1:
        # Supabase 由你自己做，所以這裏先 print。
        # 之後再改成 supabase.table(...).insert(...)

        print("=== SAVE DOCUMENT ===")
        print("File:", document.file_name)
        print("Pages:", document.page_count)
        print("Questions:", len(document.questions))

        print("=== QUESTIONS ===")
        for q in document.questions:
            print(q.source_question_id, q.question_text[:80])

        print("=== ISSUES ===")
        for issue in issues:
            print(issue.issue_code, issue.severity, issue.message)
```

### 🟣 Supabase

Supabase 你自己做。Python 先預留 `Repository` 位置。

之後要寫入：

```text
source_documents
extraction_runs
questions
```

### 不負責

Repository 不可以解題、拆題、改題目、判斷 difficulty。

### ✔ Check

- [ ] Repository 可以 print document
- [ ] Repository 可以 print questions
- [ ] Repository 可以 print issues

---

# Part 10 — Pipeline

## Lesson 16 — app/pipeline.py

### 🎯 Goal

把所有工人串起來。

### 📖 故事

Pipeline 是班長。班長不做功課，只叫同學順序做事。

### 🔵 Python

**File：**

```text
app/pipeline.py
```

### 🔵 Code

```python
from pathlib import Path

from app.document_extractor import DocumentExtractor
from app.extraction_validator import validate_extraction
from app.repository import Repository


class PdfIngestionPipeline:
    def __init__(self):
        self.extractor = DocumentExtractor()
        self.repository = Repository()

    def run_one_pdf(self, pdf_path: str | Path) -> None:
        print("Step 1: Extract PDF")
        document = self.extractor.extract(pdf_path)

        print("Step 2: Validate extraction")
        issues = validate_extraction(document)

        print("Step 3: Save result")
        self.repository.save_extracted_document(document, issues)

        print("Done.")
```

### 不負責

Pipeline 不可以自己拆題、自己叫 Gemini、自己寫 database、自己分析數學。

### ✔ Check

- [ ] Pipeline 有 3 步：Extract、Validate、Save

---

# Part 11 — 執行第一個 PDF

## Lesson 17 — scripts/ingest_one_pdf.py

### 🎯 Goal

用一個 command 處理一個 PDF。

### 🔴 Test

**File：**

```text
scripts/ingest_one_pdf.py
```

### 🔴 Code

```python
from app.pipeline import PdfIngestionPipeline


def main():
    pdf_path = "inbox/pdf/sample.pdf"
    pipeline = PdfIngestionPipeline()
    pipeline.run_one_pdf(pdf_path)


if __name__ == "__main__":
    main()
```

### 做法

1. 放 PDF：

```text
inbox/pdf/sample.pdf
```

2. 執行：

```bash
python -m scripts.ingest_one_pdf
```

### ✔ Check

- [ ] Terminal 顯示 Step 1
- [ ] Terminal 顯示 Step 2
- [ ] Terminal 顯示 Step 3
- [ ] Terminal 顯示 Done
- [ ] Terminal 顯示題目列表

---

# Part 12 — 批量 PDF

## Lesson 18 — scripts/ingest_pdfs.py

### 🎯 Goal

一次處理 `inbox/pdf/` 入面的所有 PDF。

### 🔴 Test

**File：**

```text
scripts/ingest_pdfs.py
```

### 🔴 Code

```python
from pathlib import Path
import shutil

from app.pipeline import PdfIngestionPipeline


INBOX = Path("inbox/pdf")
PROCESSED = Path("processed/pdf")
FAILED = Path("failed/pdf")


def main():
    pipeline = PdfIngestionPipeline()

    INBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    pdf_files = list(INBOX.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        return

    for pdf_path in pdf_files:
        print("=" * 60)
        print("Processing:", pdf_path.name)

        try:
            pipeline.run_one_pdf(pdf_path)
            shutil.move(str(pdf_path), PROCESSED / pdf_path.name)
            print("Moved to processed.")
        except Exception as e:
            print("Failed:", e)
            shutil.move(str(pdf_path), FAILED / pdf_path.name)
            print("Moved to failed.")


if __name__ == "__main__":
    main()
```

### ✔ Check

- [ ] 成功 PDF 會去 `processed/pdf/`
- [ ] 失敗 PDF 會去 `failed/pdf/`
- [ ] 沒有 PDF 時會顯示 `No PDF files found.`

---

# Part 13 — Question Object 輸出成 JSON

## Lesson 19 — app/json_exporter.py

### 🎯 Goal

把結果存成 JSON file，方便檢查。

### 🔵 Python

**File：**

```text
app/json_exporter.py
```

### 🔵 Code

```python
from pathlib import Path
import json
from app.schemas import ExtractedDocument, ValidationIssue


def export_extraction_json(
    document: ExtractedDocument,
    issues: list[ValidationIssue],
    output_path: str | Path,
) -> None:
    output = {
        "document": document.model_dump(),
        "issues": [issue.model_dump() for issue in issues],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

### 修改 `app/pipeline.py`

加入：

```python
from app.json_exporter import export_extraction_json
```

在 `run_one_pdf()` 最後加入：

```python
output_path = f"data/extracted/{document.file_name}.json"
export_extraction_json(document, issues, output_path)
print("Exported:", output_path)
```

### ⚪ Output

```text
data/extracted/sample.pdf.json
```

### ✔ Check

- [ ] `data/extracted/` 出現 JSON file
- [ ] JSON 入面有 document
- [ ] JSON 入面有 questions
- [ ] JSON 入面有 issues

---

# Part 14 — 最小可用版本完成

## Lesson 20 — MVP Checklist

### 🎯 Goal

確認 PDF Ingestion v1 可以用。

### 完成後你應該有

```text
math-question-system/
├── app/
│   ├── config.py
│   ├── schemas.py
│   ├── gemini_client.py
│   ├── document_loader.py
│   ├── document_extractor.py
│   ├── extraction_validator.py
│   ├── repository.py
│   ├── pipeline.py
│   └── json_exporter.py
├── prompts/
│   └── document_extractor_v1.txt
├── scripts/
│   ├── test_load_pdf.py
│   ├── ingest_one_pdf.py
│   └── ingest_pdfs.py
├── data/
│   └── extracted/
├── inbox/pdf/
├── processed/pdf/
├── failed/pdf/
├── .env.example
└── requirements.txt
```

### 系統現在做到

- [x] 讀 PDF
- [x] 數頁數
- [x] 交給 Gemini 抽題
- [x] 產生 Question Object
- [x] 檢查常見 extraction 問題
- [x] print 結果
- [x] export JSON
- [x] 批量處理 PDF

### 系統現在不做

- [ ] 不解題
- [ ] 不分析 skill
- [ ] 不做 RPDICE
- [ ] 不估 difficulty
- [ ] 不分析學生能力

---

# Part 15 — 小朋友都要記住的規則

## Rule 1

```text
Extractor 只抄題。
```

不要解題。

## Rule 2

```text
Question Object 是標準表格。
```

後面所有人都用它。

## Rule 3

```text
Repository 是倉務員。
```

之後所有 database 寫入都集中在 Repository。

## Rule 4

```text
Pipeline 是班長。
```

只負責叫人做事，不自己做事。

## Rule 5

```text
原文最重要。
```

不要隨便改 PDF 文字。

---

# Part 16 — 下一步才做甚麼？

PDF Ingestion 穩定後，先做：

```text
Analyzer
Solver
Critic
Validator
RPDICE
Student Model
Question Generator
```

不要太早做。

原因：

```text
如果題目抽錯，後面分析一定錯。
```

---

# Appendix A — File 一覽

| File | 類型 | 用途 |
|---|---|---|
| `requirements.txt` | 🟡 Config | Python packages |
| `.env.example` | 🟡 Config | 設定樣板 |
| `app/config.py` | 🔵 Python | 讀設定 |
| `app/schemas.py` | 🔵 Python | 定義資料格式 |
| `app/document_loader.py` | 🔵 Python | 讀 PDF 基本資料 |
| `app/gemini_client.py` | 🔵 Python | 呼叫 Gemini |
| `app/document_extractor.py` | 🔵 Python | PDF → Questions |
| `app/extraction_validator.py` | 🔵 Python | 檢查抽題結果 |
| `app/repository.py` | 🔵 Python | 保存資料 |
| `app/pipeline.py` | 🔵 Python | 串流程 |
| `app/json_exporter.py` | 🔵 Python | 輸出 JSON |
| `prompts/document_extractor_v1.txt` | 🟢 Prompt | Gemini 抽題指令 |
| `scripts/test_load_pdf.py` | 🔴 Test | 測 PDF loader |
| `scripts/ingest_one_pdf.py` | 🔴 Test | 處理一個 PDF |
| `scripts/ingest_pdfs.py` | 🔴 Test | 批量處理 PDF |

---

# Appendix B — Supabase 之後要做

你自己做 Supabase 時，至少要有：

```text
source_documents
extraction_runs
questions
```

暫時 Python 先 print + export JSON。等 PDF Ingestion 穩定後，再接 Supabase。

---

# Appendix C — 常見錯誤

## 錯誤 1：太早做 Analyzer

不要。PDF 未抽準，Analyzer 沒有用。

## 錯誤 2：Extractor 解題

不要。Extractor 只抄題。

## 錯誤 3：改寫數學符號

不要。

例如 PDF 是：

```text
1 − 225x²
```

不要自己改成：

```text
1 - 225*x^2
```

保留原文。

## 錯誤 4：每個 file 都自己寫 database

不要。所有 database 寫入都交給 Repository。

---

# Final Checklist

- [ ] Project folder 建好
- [ ] requirements.txt 建好
- [ ] .env.example 建好
- [ ] Prompt 建好
- [ ] app/config.py 建好
- [ ] app/schemas.py 建好
- [ ] app/document_loader.py 建好
- [ ] app/gemini_client.py 建好
- [ ] app/document_extractor.py 建好
- [ ] app/extraction_validator.py 建好
- [ ] app/repository.py 建好
- [ ] app/pipeline.py 建好
- [ ] app/json_exporter.py 建好
- [ ] scripts/test_load_pdf.py 建好
- [ ] scripts/ingest_one_pdf.py 建好
- [ ] scripts/ingest_pdfs.py 建好
- [ ] sample.pdf 放入 inbox/pdf/
- [ ] 成功 export JSON

---

# 結尾

你現在完成的是：

```text
PDF Question Extraction Engine v1
```

它是整個 Math Question System v1.1 的地基。

地基穩，後面 Analyzer、RPDICE、Student Model 才值得做。
