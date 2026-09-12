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
#    （可選）SUPABASE_URL + SUPABASE_SECRET_KEY，見下面「Supabase」

# 3. 放 PDF
cp your_paper.pdf inbox/pdf/sample.pdf

# 4. 行
python -m scripts.test_load_pdf              # 淨係讀 PDF（唔使 API key）
python -m scripts.test_load_pdf other.pdf    # 或者指定 file
python -m scripts.ingest_one_pdf             # 處理 inbox/pdf/sample.pdf
python -m scripts.ingest_one_pdf paper.pdf   # 或者指定 file
python -m scripts.ingest_pdfs               # 批量 —— 不論幾多份
```

> **成功抽完，份 PDF 會搬去 `processed/pdf/`。** 所以連續行兩次
> `ingest_one_pdf` 唔加參數，第二次會話你 inbox 已經冇嘢 —— 呢個係正常，唔係壞咗。
> 佢會順手話返你份卷而家喺邊，同埋畀返條重抽嘅命令。

### 檔名點改？

**技術上冇要求** —— 副檔名係 `.pdf` 或者 `.PDF` 就得，其他隨你。抽題同去重都係認
**內容 hash**，唔認檔名，所以改名唔會影響任何嘢。

不過個檔名會變成輸出資料夾名，所以會自動清理:

| 你個檔名 | 輸出 |
|---|---|
| `sample.pdf` | `sample-<sha12>` |
| `2024_mock_paper1.pdf` | `2024_mock_paper1-<sha12>` |
| `數學卷一.pdf` | `數學卷一-<sha12>`（中文照留） |
| `Mock Paper 1.pdf` | `Mock-Paper-1-<sha12>`（空格變 `-`） |
| `Paper (2).pdf` | `Paper-2-<sha12>`（括號剷走） |
| `....pdf` | `document-<sha12>` |

太長會截到 80 字。

**建議噉改**（純粹方便你自己日後搵）:

```text
2024-DSE-M1-paper1.pdf
2023-mock-stpaul-paper2.pdf
P6-uniform-test-2024-03.pdf
```

即係「年份 - 來源 - 卷別」，全部細楷、用 `-` 分隔。噉樣排序自然、shell 唔使 quote、
`analyse_extractions` 出嗰張表亦都對得齊易睇。

想分類就用**子資料夾**，系統會遞歸執，搬去 `processed/` 嗰陣保留返結構:

```text
inbox/pdf/
├── 2024/
│   ├── dse-paper1.pdf
│   └── dse-paper2.pdf
└── mock/
    └── stpaul-paper1.pdf
```

### 批量

`inbox/pdf/` 入面有幾多份都得，**連子資料夾一齊執**:

```bash
python3 -m scripts.ingest_pdfs              # 全部
python3 -m scripts.ingest_pdfs --verbose    # 每條題目都印（同單份一樣）
python3 -m scripts.ingest_pdfs --redo       # 連抽過嘅都重抽
python3 -m scripts.ingest_pdfs --keep       # 唔好郁啲 PDF
python3 -m scripts.ingest_pdfs some/folder  # 第二個 folder
```

```text
Found 47 PDF(s) in inbox/pdf
======================================================================
[12/47] 2024/mock-paper-3.pdf
  ok: 41 questions in 38s
======================================================================
[13/47] 2024/mock-paper-4.pdf
  already ingested (mock-paper-4-a1b2c3d4e5f6.json), skipping - use --redo to force
...
SUMMARY   duplicate: 2   failed: 1   ok: 44
          1,683 questions in 31m12s
  FAILED    scanned-only.pdf  NO_QUESTIONS_FOUND
Report:   data/extracted/batch-20260912T081500Z.md
```

| | |
|---|---|
| **唔會重複燒錢** | 抽過嘅（同 sha256）會跳過，唔會再叫 Gemini。改咗檔名都認得 |
| **Batch 入面有重複** | 同內容嘅第二份標做 `duplicate`，唔會抽兩次 |
| **`.PDF` 大寫** | 執得到（Linux 嘅 `*.pdf` glob 會漏） |
| **子資料夾** | 遞歸執，搬去 `processed/` 嗰陣保留返 folder 結構 |
| **一份炸咗** | 入 `failed/`，其餘照跑 |
| **Ctrl-C** | 得體噉停，已完成嘅照出 report，未做嘅留喺 inbox，exit 130 |
| **Terminal** | 批量模式每份卷一行；`--verbose` 先印全文 |

跑完喺 `data/extracted/batch-<時間>.md` 留低一份總表。有任何 `failed` 就 exit 1。

每次抽完會出三樣嘢:

```text
data/extracted/<name>-<sha12>.json         # 機器讀嘅
data/extracted/<name>-<sha12>.md           # 人讀嘅 report
data/diagrams/<name>-<sha12>/16.png        # 抽到嘅圖同表
data/history/<name>-<sha12>/<run_id>.json  # 每次 run 存返一份，用嚟比較
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
| `app/repository.py` | 🔵 Python | 保存資料（有 Supabase 就寫入，冇就 print） |
| `app/supabase_store.py` | 🔵 Python | Extraction → 三個 table 嘅 rows |
| `docs/supabase_schema.sql` | 🟡 Config | Supabase table 定義 |
| `app/pipeline.py` | 🔵 Python | 串流程 |
| `app/diagram_geometry.py` | 🔵 Python | Crop 座標數學（純函數） |
| `app/diagram_renderer.py` | 🔵 Python | PDF → 圖片 PNG |
| `app/json_exporter.py` | 🔵 Python | 輸出 JSON |
| `app/markdown_exporter.py` | 🔵 Python | 輸出人讀嘅 .md report |
| `app/extraction_diff.py` | 🔵 Python | 比較兩次 run |
| `app/extraction_stats.py` | 🔵 Python | 按題型統計出事率 |
| `prompts/document_extractor_v1.txt` | 🟢 Prompt | Gemini 抽題指令 |
| `scripts/test_load_pdf.py` | 🔴 Test | 測 PDF loader |
| `scripts/ingest_one_pdf.py` | 🔴 Test | 處理一個 PDF |
| `scripts/ingest_pdfs.py` | 🔴 Test | 批量處理 PDF |
| `scripts/show_extraction.py` | 🔴 Test | 查返存低咗嘅結果 |
| `scripts/export_markdown.py` | 🔴 Test | 由 JSON 重新整 .md report |
| `scripts/compare_extractions.py` | 🔴 Test | 比較兩次 run |
| `scripts/analyse_extractions.py` | 🔴 Test | 按題型分析多份卷 |
| `scripts/db_check.py` | 🔴 Test | 驗證 Supabase 連線同 schema |

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

## 睇下抽唔同題目會點

抽咗 20 份卷、800 條題目之後，逐條睇冇意義。你想知嘅係**邊種題型系統做得差**。

```bash
python3 -m scripts.ingest_pdfs          # 掟一批唔同嘅卷落去
python3 -m scripts.analyse_extractions  # 睇 pattern
```

```text
## By what the question contains

| Feature | Questions | Flagged | Rate | Most common issue |
|---|---|---|---|---|
| table          |  8 | 5 | 62% | `MALFORMED_TABLE` (5) |
| sub-question   | 12 | 5 | 42% | `MALFORMED_TABLE` (4) |
| diagram        |  6 | 2 | 33% | `REPEATED_TEXT_IN_QUESTION` (1) |
| prose only     |  3 | 1 | 33% | `POSSIBLE_BROKEN_POWER` (1) |
| group marks    |  3 | 0 |  0% | |
| latex          |  1 | 0 |  0% | |
```

一眼睇到：**有表格嘅題目出事率 62%，純文字得 33%**。噉你就知精力要放邊。

系統會按題目**實際內容**分類，一條題目可以屬於幾類（所以百分比會疊）:

| 類別 | 點判斷 |
|---|---|
| `table` | 題幹有 markdown 表，或者有 `table_regions` |
| `diagram` | `diagram_required=true` |
| `sub-question` | 題號有括號，例如 `2(a)` |
| `spans pages` | `page_end > page_start` |
| `latex` | 題幹有 `\(` |
| `own marks` / `group marks` / `no marks` | 分數嚟自邊 |
| `printed answer` | 卷面已經印咗答案 |
| `prose only` | 冇表、冇圖、冇 LaTeX |

仲會列出**邊份卷最多問題**、**邊幾條題目最多問題**，同埋每份卷嘅 Q/page（抽漏題就
會偏低）。報告會寫入 `data/extracted/analysis-<時間>.md`。

---

## 比較兩次 run — 唯一捉到「作嘢」嘅方法

同一份卷抽咗四次，出過:

```text
表格冇 separator row  →  有
題幹帶住兄弟題目      →  冇  →  又有
減號 U+2212           →  U+2013（肉眼睇唔出）
「B 的底半徑為 18 cm」 →  「B 的底半徑為 B 為 18 cm」
                          仲自己加個 note 話係卷面嘅 typo
```

**最後嗰個冇任何 validator 捉到** — 因為單睇一次 run，佢自己內部完全合理。兩次 run
唔同先係訊號。

每次抽題都會 archive 一份去 `data/history/<卷名>-<sha12>/<run_id>.json`
（主 JSON 照舊覆寫，keep 到 idempotent）。抽多次就可以比:

```bash
python3 -m scripts.ingest_one_pdf          # 抽多一次
python3 -m scripts.compare_extractions     # 比最近兩次
```

```text
Identical : 37
Changed   : 2
Agreement : 95%

======================================================================
20(b)
----------------------------------------------------------------------
  question_text:
    …知 B 的底半徑為 {+B 為 +}18 cm。她宣稱 …
```

兩次一致嘅地方，基本上信得過；唔一致嘅，就係要你揭返卷睇嗰幾條。冇差異 exit 0，
有差異 exit 1。

---

## 自動修正

有啲錯 prompt 講極都唔穩定。同一份 PDF 抽三次，Gemini 曾經**出錯 → 改啱 → 又出錯**
同一個問題：將其中一個小題嘅題目留咗喺兄弟題共用嘅題幹入面，搞到每條小題都帶住
唔屬於自己嘅題目。

所以呢個唔靠 prompt，喺 code 度整返:

```text
Step 1  Extract
Step 2  Repair      ← 新增
Step 3  Validate
```

修正有兩種:

**1. LaTeX backslash 被 JSON 食咗**

```text
模型寫:      "\frac{3}{x-4}"        ← 單 backslash
JSON 解碼:   \x0c + "rac{3}{x-4}"   ← \f 係 form feed
你見到:      " rac{3}{x-4}"          ← \frac 冇咗
```

JSON 只認 `\b \f \n \r \t` 呢五個 escape，所以只有呢五個指令會**靜靜雞**壞。
`\vec`、`\alpha` 呢啲唔係合法 escape，會直接 parse error（反而好，唔會扮冇事）。

五個入面，`\b` 同 `\f` 喺正常文字絕對唔會出現 → **自動修返**（`\frac`、`\beta`
救得返）。`\t` `\n` `\r` 本身係正常空白 → **淨係報，唔亂估**。

**2. 冇包 delimiter 嘅公式**

```text
L = 10 \log \frac{I}{10^{-12}}   →   \( L = 10 \log \frac{I}{10^{-12}} \)
```

只包**成行都係數學**嗰啲（冇中文、未包過、有 LaTeX 指令）。中文夾住嘅 inline
數學唔會自動包 —— 數學喺邊度完結靠估，估錯更差，所以繼續報 `LATEX_NOT_DELIMITED`
等你自己睇。

**3. 共用題幹污染**

修正**故意做得好窄** — 淨係喺「共用題幹最後嗰句，啱啱好等於某個小題嘅全部題目」
嗰陣先郁手。改咗乜一定寫入嗰條題目嘅 `extraction_notes`，`.md` report 亦會有
「Repairs applied」一節，唔會靜靜雞改。

`REPAIR_EXTRACTION=false` 可以熄咗。熄咗之後同一個情況會出
`STEM_CONTAMINATION`（high），而且**三條小題全部報**，唔止自我重複嗰條。

---

## 選擇題

MC 卷嘅選項唔會留喺 `question_text`，會抽做結構:

```json
{
  "source_question_id": "1",
  "question_type": "multiple_choice",
  "question_text": "\\( \\frac{81^{1-n}}{27^{2n}} = \\)",
  "options": ["3^{1-3n}", "\\frac{1}{3^{3n-2}}", "\\frac{1}{3^{5n-2}}", "\\frac{1}{3^{10n-4}}"]
}
```

噉樣之後先做得到打亂選項、對答案、出變化題 —— 選項一旦變咗散文就乜都做唔到。

選項仲留喺 prose 會出 `OPTIONS_NOT_SEPARATED`。偵測要求 A/B/C/D 入面至少三個喺
行首，所以幾何題寫 `A(5, 4) 及 B` 或者 `A、B、D、E 均是圓上的點` 都唔會誤判。

---

## 圖片同表格

凡係 `diagram_required=true` 嘅題目，**同埋每張印出嚟嘅表格**，系統都會由 PDF
render 返張 PNG 出嚟：

```text
data/diagrams/<name>-<sha12>/16.png              # 圖
data/diagrams/<name>-<sha12>/17-a-table-1.png    # 第一張表
data/diagrams/<name>-<sha12>/15-a-table-2.png    # 第二張表
```

### 點解表格文字同圖片兩樣都要？

| | 用嚟做咩 |
|---|---|
| **Markdown 文字** | 機器用 — Analyzer 要 `14, 14, 21, 37, 9, k` 先計到中位數，Question Generator 要啲數值先出到變化題。相係搵唔到、計唔到、比唔到 |
| **圖片** | 人用 — 卷面真正嘅樣，合併格／兩層表頭／並排兩張表全部原汁原味。文字抽錯嗰陣即刻對得返 |

所以 validator 見到表格文字有問題但**已經影咗相**，會將 severity 由 `medium` 降去
`low`，因為你有嘢對返。反過嚟，有表但冇影相會出 `TABLE_NOT_CAPTURED`。

`RENDER_TABLES=false` 可以熄咗表格影相。

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
| `MALFORMED_TABLE` | medium¹ | 表格冇 markdown separator row，render 唔到 |
| `RAGGED_TABLE` | medium¹ | 表格每行格數唔一致，通常係卷面有合併格／兩層表頭 |
| `TABLE_NOT_CAPTURED` | low | 有表格文字但冇影相 |
| `STEM_CONTAMINATION` | high | 共用題幹尾多咗一句係其中一個小題嘅題目 |
| `CONTROL_CHARACTER` | high | LaTeX backslash 俾 JSON escape 食咗，指令爛咗 |
| `OPTIONS_NOT_SEPARATED` | medium | MC 選項留咗喺 question_text |
| `OPTIONS_MISSING` | medium | 標咗 MC 但冇 options |
| `LATEX_NOT_DELIMITED` | medium | LaTeX 冇包喺 `\( \)` 入面，render 唔到 |
| `INCONSISTENT_MINUS_SIGN` | low | 同一份卷用咗幾種唔同減號字元 |
| `REPEATED_TEXT_IN_QUESTION` | medium | 同題內有句子重複，通常係小題題目撈咗入題幹 |
| `MARKS_MISSING` | low | 成份卷有分數，但呢條冇 |

粗體嘅兩個係 **blocking** — 會令 PDF 入 `failed/pdf/`。

¹ 如果嗰條題目已經影咗表格相，會降做 `low`：文字抽錯都有得對返。

---

## 🟣 Supabase

`Repository` 係全系統唯一寫資料嘅地方。`.env` 有 `SUPABASE_URL` 同
`SUPABASE_SECRET_KEY` 就會寫入 Supabase；冇就照舊淨係 print + export JSON，
所以冇 database 嘅電腦一樣行到。

### 三個 table

| Table | 一行係咩 | Key |
|---|---|---|
| `source_documents` | 一份 PDF（按內容 hash） | `sha256` unique |
| `extraction_runs` | 一次抽題 | `run_id` unique；`is_current` 標住最新一次 |
| `questions` | 一條題目（屬於某次 run） | `(extraction_run_id, source_question_id)` unique |

同一份 PDF 再抽一次，**唔會**覆蓋：加一行新 run，舊 run 嘅 `is_current` 變 `false`。
`current_questions` view 就係每份卷最新一次 run 嘅題目。每次 run 嘅 issues、
repairs、圖片路徑都一齊存低（jsonb），所以之後查「呢條題目點解係咁」有得追。

### 點設定

```bash
# 1. Supabase Dashboard → SQL Editor → 貼 docs/supabase_schema.sql 行一次
# 2. Dashboard → Project Settings → API：
#    URL              → SUPABASE_URL
#    service_role key → SUPABASE_SECRET_KEY   （唔係 anon key）
# 3. 驗證連線同 schema
python3 -m scripts.db_check
# 4. 之後每次 ingest 都會自動寫入
python3 -m scripts.ingest_pdfs --redo
```

`db_check` 會逐個 table 讀一次「store 會寫嘅所有 column」，缺一個都會 FAIL 並列出
期望嘅 column。如果你已經有自己嘅 table，column 名唔同，改 `app/supabase_store.py`
入面三個 row builder（`document_row` / `run_row` / `question_rows`）就得，其他嘢
唔使掂。

Supabase REST 冇 transaction。如果 run 已經寫咗但 questions 寫唔入，個 run row 會
即刻刪返，唔會留低一個空 run。

> `SUPABASE_SECRET_KEY` 係 service_role key，可以繞過 RLS。**唔好** commit `.env`，
> 亦唔好放入任何前端。

---

## 下一步（PDF Ingestion 穩定之後先做）

```text
Analyzer → Solver → Critic → Validator → RPDICE → Student Model → Question Generator
```

唔好太早做 — 如果題目抽錯，後面分析一定錯。
