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

## 快速開始

```bash
# 1. 安裝
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 設定
cp .env.example .env
#    填返 GEMINI_API_KEY 同 GEMINI_EXTRACTOR_MODEL

# 3. 放 PDF
cp your_paper.pdf inbox/pdf/sample.pdf

# 4. 行
python -m scripts.test_load_pdf     # 淨係測試讀 PDF（唔使 API key）
python -m scripts.ingest_one_pdf    # 處理 inbox/pdf/sample.pdf
python -m scripts.ingest_pdfs       # 批量處理 inbox/pdf/ 所有 PDF
```

輸出：`data/extracted/<file_name>.json`

批量處理時，成功嘅 PDF 會搬去 `processed/pdf/`，失敗嘅去 `failed/pdf/`。

---

## 測試

```bash
pip install pytest
pytest
```

---

## 檔案一覽

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

## Question Object

```json
{
  "source_question_id": "1",
  "page_start": 1,
  "page_end": 1,
  "question_text": "Factorise 1 - 225x².",
  "marks": 2,
  "answer": null,
  "worked_solution": null,
  "diagram_required": false,
  "extraction_notes": []
}
```

---

## 五條規則

1. **Extractor 只抄題** — 唔好解題。
2. **Question Object 是標準表格** — 後面所有人都用它。
3. **Repository 是倉務員** — 所有 database 寫入都集中喺 Repository。
4. **Pipeline 是班長** — 只負責叫人做事，唔自己做事。
5. **原文最重要** — 唔好隨便改 PDF 文字（`1 − 225x²` 唔好變 `1 - 225*x^2`）。

---

## Validation Issue Codes

| Code | Severity |
|---|---|
| `NO_QUESTIONS_FOUND` | critical |
| `EMPTY_QUESTION_TEXT` | critical |
| `PAGE_COUNT_INVALID` | high |
| `PAGE_NUMBER_INVALID` | high |
| `PAGE_RANGE_INVALID` | high |
| `DUPLICATE_QUESTION_ID` | medium |
| `POSSIBLE_BROKEN_POWER` | medium |

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
