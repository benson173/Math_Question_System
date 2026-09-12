# Math Question System v1.1 — PDF Ingestion

讀 PDF 數學題，拆成一條條題目（Question Object）。

**呢個階段只做 PDF Digest / Ingestion。** 不做解題、RPDICE、難度分析、學生能力分析、自動出題。

完整教材：[`docs/pdf_ingestion_guide_v1_1.md`](docs/pdf_ingestion_guide_v1_1.md)

---

## 流程

```text
PDF → 讀取 → 逐頁拆開 → 找出每條題目 → 保留數學符號 → 檢查有冇錯 → Question Object
```

三步 Pipeline：**Extract → Validate → Save**

---

## 需要

**Python 3.9 或以上。**

macOS 內置嘅 `python3` 通常係 3.9，啱啱夠用。如果 `python3 --version` 顯示 3.8 或
更舊，就要裝新啲嘅:

```bash
python3 --version          # 睇吓係邊個版本
python3.11 -m venv .venv   # 或者用你裝咗嘅新版本
```

3.9 已經過咗官方支援期，得閒可以升去 3.11+，但而家唔升都行。

---

## 快速開始

```bash
# 1. 安裝
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 設定
cp .env.example .env
#    填返 GEMINI_API_KEY 同 GEMINI_EXTRACTOR_MODEL

# 3. 放 PDF
cp your_paper.pdf inbox/pdf/sample.pdf

# 4. 行
python -m scripts.test_load_pdf              # 淨係讀 PDF（唔使 API key）
python -m scripts.test_load_pdf other.pdf    # 或者指定 file
python -m scripts.ingest_one_pdf             # 處理 inbox/pdf/sample.pdf
python -m scripts.ingest_one_pdf paper.pdf   # 或者指定 file
python -m scripts.ingest_pdfs                # 批量處理 inbox/pdf/ 所有 PDF
```

每次抽完會出三樣嘢:

```text
data/extracted/<name>-<sha12>.json    # 機器讀嘅
data/extracted/<name>-<sha12>.md      # 人讀嘅 report
data/diagrams/<name>-<sha12>/16.png   # 抽到嘅圖
```

用 hash 命名，所以兩份都叫 `sample.pdf` 嘅唔同卷唔會互相覆寫，而重做同一份卷就會
覆寫自己上次嘅結果。

### `.md` report

睇得明、可以直接 upload 出去嘅版本 — 每條題目一個 section，題幹嘅 markdown 表格會
正常 render，圖用**相對路徑**連住（所以成個 `data/` folder 搬去邊都唔會斷），最後有
張 validation issue 表。

想由舊 JSON 重新整返個 report（唔使再叫 Gemini）:

```bash
python3 -m scripts.export_markdown              # 最新嗰份
python3 -m scripts.export_markdown path/x.json  # 指定
```

所有 script 喺任何 directory 行都可以（path 由 `app/paths.py` 錨住 repo root）。

### 成功同失敗點分？

| 情況 | 去邊 | exit code |
|---|---|---|
| 正常抽到題目 | `processed/pdf/` | 0 |
| 抽到 0 條題目（`NO_QUESTIONS_FOUND`） | `failed/pdf/` | 1 |
| 有題目空白（`EMPTY_QUESTION_TEXT`） | `failed/pdf/` | 1 |
| 讀唔到 PDF / Gemini 出錯 | `failed/pdf/` | 1 |
| 只有 `medium` / `high` 警告（例如懷疑符號壞） | `processed/pdf/` | 0 |

**只有 `critical` severity 會當失敗**，因為咁代表根本冇可用題目。其餘警告一樣會寫入
JSON，等你自己覆核。失敗嘅 PDF 都會 export JSON，方便你查係咩事。

---

## 測試

```bash
pip install pytest
pytest
```

全部測試都唔使 API key、唔使上網。

---

## 檔案一覽

| File | 類型 | 用途 |
|---|---|---|
| `requirements.txt` | 🟡 Config | Python packages |
| `.env.example` | 🟡 Config | 設定樣板 |
| `app/config.py` | 🔵 Python | 讀設定（有 cache） |
| `app/paths.py` | 🔵 Python | 所有路徑錨住 repo root |
| `app/errors.py` | 🔵 Python | 錯誤類型 |
| `app/schemas.py` | 🔵 Python | 定義資料格式 |
| `app/document_loader.py` | 🔵 Python | 讀 PDF 基本資料 |
| `app/gemini_client.py` | 🔵 Python | 呼叫 Gemini |
| `app/document_extractor.py` | 🔵 Python | PDF → Questions |
| `app/extraction_validator.py` | 🔵 Python | 檢查抽題結果 |
| `app/repository.py` | 🔵 Python | 保存資料 |
| `app/pipeline.py` | 🔵 Python | 串流程 |
| `app/diagram_geometry.py` | 🔵 Python | Crop 座標數學（純函數） |
| `app/diagram_renderer.py` | 🔵 Python | PDF → 圖片 PNG |
| `app/json_exporter.py` | 🔵 Python | 輸出 JSON |
| `app/markdown_exporter.py` | 🔵 Python | 輸出人讀嘅 .md report |
| `prompts/document_extractor_v1.txt` | 🟢 Prompt | Gemini 抽題指令 |
| `scripts/test_load_pdf.py` | 🔴 Test | 測 PDF loader |
| `scripts/ingest_one_pdf.py` | 🔴 Test | 處理一個 PDF |
| `scripts/ingest_pdfs.py` | 🔴 Test | 批量處理 PDF |
| `scripts/show_extraction.py` | 🔴 Test | 查返存低咗嘅結果 |
| `scripts/export_markdown.py` | 🔴 Test | 由 JSON 重新整 .md report |

---

## Question Object

```json
{
  "source_question_id": "1(a)",
  "page_start": 1,
  "page_end": 1,
  "question_text": "Factorise 1 - 225x².",
  "marks": 2,
  "group_marks": null,
  "group_marks_scope": null,
  "answer": null,
  "worked_solution": null,
  "diagram_required": false,
  "extraction_notes": []
}
```

### Sub-question 編號

用 **`1(a)`** — parent number 加圓括號，中間冇空格。

```text
1          冇分小題
1(a)       小題
1(a)(i)    再分一層
```

**每一個要答嘅部分自己一筆**。Q1 有 (a) (b) 就出 `1(a)` 同 `1(b)`，唔會再出一筆
叫 `1`。共用嘅表格 / 故事 / 圖會喺每個小題嘅 `question_text` 重複一次，令每條題目
獨立睇得明。

### Provenance

每份 export 除咗 `document` 同 `issues`，仲有：

```json
{
  "source": { "file_name": "...", "sha256": "...", "page_count": 8, "byte_size": 204813 },
  "run":    { "run_id": "...", "extracted_at": "...", "extraction_version": "QEE_v1",
              "question_object_version": "QOS_v1", "model": "..." }
}
```

`sha256` 係之後 Supabase `source_documents` 做 dedupe 嘅 key。

---

## 圖片

凡係 `diagram_required=true` 嘅題目，系統會由 PDF render 返張 PNG 出嚟：

```text
data/diagrams/<name>-<sha12>/17-a.png
```

Gemini 會連埋 `diagram_region` 一齊交返（0–1000 座標，`[y_min, x_min, y_max, x_max]`），
系統就照住個框 crop。**框唔合理或者冇框，就 render 成頁**，唔會乜都冇 —
會出 `DIAGRAM_REGION_UNUSABLE` 警告（唔算失敗）。

JSON 入面:

```json
"diagrams": [
  { "source_question_id": "16", "page": 8, "image_path": "data/diagrams/.../16.png",
    "cropped": true, "width": 840, "height": 610 }
]
```

唔想 render 就喺 `.env` 設 `RENDER_DIAGRAMS=false`。解像度用 `DIAGRAM_DPI`（預設 200）。

render 失敗（library 冇裝、PDF 壞）**唔會累死成次抽題** — 只會印個警告，題目照樣存低。

---

## 五條規則

1. **Extractor 只抄題** — 唔好解題。
2. **Question Object 是標準表格** — 後面所有人都用它。
3. **Repository 是倉務員** — 所有 database 寫入都集中喺 Repository。
4. **Pipeline 是班長** — 只負責叫人做事，唔自己做事。
5. **原文最重要** — 唔好隨便改 PDF 文字（`1 − 225x²` 唔好變 `1 - 225*x^2`）。

---

## Validation Issue Codes

| Code | Severity | 意思 |
|---|---|---|
| `NO_QUESTIONS_FOUND` | **critical** | 一條題目都抽唔到 |
| `EMPTY_QUESTION_TEXT` | **critical** | 有題目係空白 |
| `PAGE_COUNT_INVALID` | high | `page_count` 唔合理 |
| `PAGE_NUMBER_INVALID` | high | 頁數 ≤ 0 |
| `PAGE_RANGE_INVALID` | high | `page_end` 早過 `page_start` |
| `PAGE_OUT_OF_RANGE` | high | 頁數超出 PDF 總頁數 |
| `MISSING_QUESTION_ID` | high | 冇題號 |
| `DUPLICATE_QUESTION_ID` | medium | 題號重複 |
| `POSSIBLE_BROKEN_POWER` | medium | 疑似 `x²` 被壓成 `x2` |
| `MARKS_INVALID` | medium | 負分數 |
| `SUSPICIOUSLY_FEW_QUESTIONS` | medium | 頁數多但題目少，可能抽漏 |
| `DIAGRAM_REGION_UNUSABLE` | medium | 要圖但冇合理座標，會 render 成頁 |
| `MALFORMED_TABLE` | medium | 表格冇 markdown separator row，render 唔到 |
| `REPEATED_TEXT_IN_QUESTION` | medium | 同題內有句子重複，通常係小題題目撈咗入題幹 |
| `MARKS_MISSING` | low | 成份卷有分數，但呢條冇 |

粗體嘅兩個係 **blocking** — 會令 PDF 入 `failed/pdf/`。

---

## 🟣 Supabase（之後做）

而家 `Repository` 淨係 print + export JSON。之後至少要有以下 table：

```text
source_documents
extraction_runs
questions
```

---

## 下一步（PDF Ingestion 穩定之後先做）

```text
Analyzer → Solver → Critic → Validator → RPDICE → Student Model → Question Generator
```

唔好太早做 — 如果題目抽錯，後面分析一定錯。
