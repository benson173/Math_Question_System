# 同 Guide 唔一樣嘅地方

`pdf_ingestion_guide_v1_1.md` 係原本嘅教材。以下係 code 有意偏離 guide 嘅地方，
同埋原因。架構同五條規則（Rule 1-5）冇改。

---

## 1. `run_one_pdf()` return `ExtractionResult`，唔再 return `None`

**Guide**：Lesson 16 嘅 `run_one_pdf()` return `None`。

**問題**：validation issue 只係 print 出嚟，caller 無法知道成功定失敗。Lesson 18
嘅批量 script 於是將**所有**冇拋 exception 嘅 PDF 搬入 `processed/`，包括抽到 0 條
題目嘅。Lesson 03 講明 `failed/pdf = 做失敗的 PDF`，呢個違反咗。

**改法**：`run_one_pdf()` return `ExtractionResult`（Lesson 08 定義咗但原本冇用過）。
批量 script 用 `destination_directory()` 決定去邊：有 `critical` issue 就入 `failed/`。

---

## 2. Gemini 只被要求交 `questions`

**Guide**：Lesson 13 將整個 `ExtractedDocument` 做 `response_schema`，然後
Lesson 13 自己再覆寫 `file_name` 同 `page_count`。

**問題**：`file_name` 同 `page_count` 我們本來就知（loader 讀到）。叫 model 估兩個
已知嘅值，只會浪費 token，估錯仲會令整個 response 廢掉。

**改法**：新增 `QuestionExtractionPayload`（只有 `questions`）做 response schema。
`ExtractedDocument` 由 loader 嘅事實砌出嚟。

---

## 3. `sha256` 會保存落 output

**Guide**：Lesson 09 計 sha256，但之後冇任何一步用過，Lesson 19 嘅 export 都冇。

**問題**：Appendix B 要 `source_documents` table。冇 hash 就做唔到 dedupe。

**改法**：新增 `SourceDocument`（`file_name` / `sha256` / `page_count` /
`byte_size`）同 `ExtractionRun`（`run_id` / `extracted_at` / `extraction_version` /
`question_object_version` / `model`），兩個都寫入 JSON export。`extraction_version`
同 `question_object_version` 原本讀落 `Settings` 之後亦係冇用過。

---

## 4. Output 檔名用 content hash

**Guide**：Lesson 19 輸出 `data/extracted/sample.pdf.json`。

**問題**：兩份唔同嘅卷都叫 `sample.pdf` 就會互相覆寫。

**改法**：`data/extracted/sample-<sha256 前 12 位>.json`。重做同一份卷照樣覆寫自己
上次嘅結果（idempotent），但唔同內容唔會撞。

---

## 5. Gemini 呼叫加了 retry / timeout / 錯誤分類

**Guide**：`requirements.txt` 有 `tenacity`，但由頭到尾冇 import 過。

**改法**：
- `tenacity` retry：429 / 5xx / 網絡錯誤，最多 4 次，exponential backoff
- timeout：`GEMINI_TIMEOUT_SECONDS`（預設 300）
- `MAX_TOKENS` → `TruncatedResponseError`，講清楚要拆細 PDF
  （原本會變成一個睇唔明嘅 Pydantic ValidationError）
- safety block → `ExtractionError`
- 空 response → `EmptyResponseError`（原本會變成 `TypeError`）
- 15MB 以下 PDF 直接 inline 傳，唔使 Files API；大過就 upload 完一定 delete，
  唔會積壓 quota

---

## 6. Validator 加強

`POSSIBLE_BROKEN_POWER` 原本用 `"x2" in text` 加兩個**整條題目**範圍嘅 guard，
結果同題只要有一個正常嘅 `x²`，所有壞嘅都被遮蔽；而且只識字母 `x`。

改成 regex，逐個位置獨立檢查，任何字母都計。`2x2`（尺寸）同 `Q1`（題號）會先遮蔽
避免誤報 — 代價係 `4x²` 壞掉時會漏，同大寫變數 `X2` 會漏，兩者都比誤報罕見。

新增四項：`PAGE_OUT_OF_RANGE`、`MISSING_QUESTION_ID`、`MARKS_INVALID`、
`SUSPICIOUSLY_FEW_QUESTIONS`。

`severity` 由自由 string 改成 `Literal["critical", "high", "medium", "low"]`，
寫錯即刻拋錯。`ValidationIssue` 加 `source_question_id`，方便追去邊條題目。

---

## 7. 其他

| 改動 | 原因 |
|---|---|
| `app/paths.py` — 所有路徑錨住 repo root | 原本 `PROMPT_PATH` 同 `data/extracted` 係相對 cwd，唔喺 repo root 行就炸 |
| `load_settings()` 加 `lru_cache` | 原本 `GeminiClient` 同 `Repository` 各叫一次，`load_dotenv()` 行兩轉 |
| loader 讀 file 一次 | 原本 `PdfReader` 讀一次、`calculate_sha256` 再讀一次；`bytes` 順便重用落 Gemini request |
| loader 拒絕空 file | 0 byte PDF 原本會變成一個奇怪嘅 pypdf error |
| `Repository.save_extracted_document` → `save_extraction_result` | 收 `ExtractionResult`，一個參數包含 document + issues + provenance |
| `PdfIngestionPipeline(extractor=, repository=)` 可注入 | 令 orchestration 可以唔使 API key 測試 |
| script 收 path argument、return exit code | 唔再 hardcode `sample.pdf`；失敗 exit 1，可以放入 shell pipeline |
| 批量 script 有 summary + 唔覆寫同名 file | 原本 `shutil.move` 撞名會靜靜覆寫 |

---

## 8. 圖片抽取（guide v1 完全冇做）

**Guide**：Lesson 20 明寫系統唔做圖，只係喺 `diagram_required` 打個旗。

**改法**：`diagram_required=true` 嘅題目會由 PDF render 返 PNG。

- Gemini 連 `diagram_region` 一齊交（0–1000 頁面座標，
  `[y_min, x_min, y_max, x_max]`，即係 Gemini 自己個 bounding box 慣例）
- `pypdfium2` render 該頁（Apache/BSD licence，pip 直接裝，唔使 brew）
- `Pillow` 照個框 crop，四邊各留 2% padding
- 存去 `data/diagrams/<name>-<sha12>/<題號>.png`，JSON 嘅 `diagrams` 記低路徑、
  頁數、尺寸、同埋 `cropped` 係真定假

**Fallback 係核心**：框唔合理（倒轉、超出頁面、細過頁面 2%）或者根本冇框，就
render 成頁。有張成頁圖總好過乜都冇。呢種情況會出 `DIAGRAM_REGION_UNUSABLE`
（medium，唔算失敗）。

Render 失敗（library 冇裝、PDF 壞）唔會累死成次抽題 — 印個警告，題目照存。

純幾何部分（`app/diagram_geometry.py`）同 render 部分（`app/diagram_renderer.py`）
分開，所以座標數學可以完全唔使 imaging library 就測到。

`DiagramAsset` 刻意唔放入 `ExtractedQuestion` — Question Object 要保持係
Rule 2 講嗰張標準表格，我哋自己整出嚟嘅檔案放喺 `ExtractionResult.diagrams`。
