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

---

## 9. Markdown report（guide 冇）

除咗 JSON，每次抽完會喺隔離寫多份 `.md`：每條題目一個 section、題幹原文照擺（本身
就係 markdown，所以印出嚟嘅表格會 render 返做表格）、圖用**相對路徑**連住、最後一
張 validation issue 表（最嚴重排先）。

相對路徑係刻意嘅：report 喺 `data/extracted/`，圖喺 `data/diagrams/`，連結寫成
`../diagrams/.../16.png`，所以成個 `data/` folder 搬去邊都唔會斷。

`scripts/export_markdown.py` 可以由已存嘅 JSON 重新整份 report，唔使再燒 API。

---

## 10. `group_marks` — 卷面只印一個總分嘅情況

**問題**：好多卷 Q2 印一次「(4 分)」，但 (a)(b)(c) 每個部分喺呢度係獨立一筆。
Gemini 唔亂拆總分係啱嘅，但佢會寫一句英文 note
（`Total marks for Question 2 is 4 marks.`）— 資料困死喺 free text，後面用唔到。
實測一份 39 條嘅卷，**17 條係噉**。

**改法**：`ExtractedQuestion` 加兩個欄位：

```text
marks               呢個部分自己印嘅分（冇就 null）
group_marks         成組共用嘅總分
group_marks_scope   卷面點寫個範圍，例如 "2"、"12(b)-(d)"、"18(a)"
```

Prompt 明確禁止再將分數寫入 `extraction_notes`，亦禁止自己拆總分。

Validator 加 `MARKS_MISSING`（low）— 但**只喺成份卷其他題有分數嘅時候先報**。
成份卷都冇印分數係正常，唔應該嘈。

---

## 11. 表格格式要釘死

**問題**：同一個 prompt 跑兩次，Gemini 出兩種表格格式 —
一次係正常 markdown（`| 球 | 現金獎 |` + `| :---: | :---: |`），
一次係冇 separator row 嘅
（`球 | 現金獎`），後者 render 出嚟係一嚿爛文字，下游亦都 parse 唔到。
Prompt 由頭到尾冇講過表格要咩格式。

**改法**：Prompt 加 `TABLES` 一節，釘死 GitHub-flavoured markdown，明寫 separator
row 唔可以少，空格要留空（畀學生填嘅表），幹葉圖都當表格處理。

Validator 加 `MALFORMED_TABLE`（medium）：搵連續、pipe 數一致嘅行（呢個一致性
就係「表」同「啱好有個 pipe 嘅句子」嘅分別），頭兩行冇 separator 就報。

---

## 12. 數學符號寫法要一致

**問題**：同一份卷 Q1/Q4 嘅分數用 LaTeX `\(\frac{...}{...}\)`，Q9/Q15 又用純
Unicode。Prompt 只講「保留原文符號」，冇講分數呢類結構點寫。

**改法**：Prompt 加 `MATHEMATICAL NOTATION` — Unicode 寫得到嘅就用 Unicode
（`− × ÷ ² ³ ½ π ° θ ∠ △ ≤ ≥ ≠ √`），淨係 Unicode 表達唔到嘅結構（直式分數、
n 次方根、矩陣、求和）先用 LaTeX，而且成份卷要一致。

---

## 13. 同一題入面句子重複

**問題**：實測 Q19 三個小題嘅共用題幹入面，多咗一句其實係 19(c) 嘅題目
（`求 △OAB 的面積。`），所以 19(a)、19(b) 都含住 19(c) 條題，而 19(c) 自己同一
句出現兩次。

**改法**：Prompt 明寫「共用材料去到第一個部分開始為止，唔可以將一個部分嘅題目抄
入另一個部分，同一句唔可以喺一個 question_text 入面出現兩次」。

Validator 加 `REPEATED_TEXT_IN_QUESTION`（medium）：用 `。？！` 同換行斷句，
一句 8 個字以上、唔含 pipe（唔數表格行）、喺同一題出現兩次就報。上面嗰個真實例子
啱啱好就係噉觸發。

---

## 14. 合併格 / 兩層表頭

**問題**：實測有張骰子表，卷面係兩層表頭加合併格（「第二枚」橫跨 6 欄、「第一枚」
直跨 6 行）。Markdown 表格根本冇 merged cell，所以 Gemini 點砌都砌唔正 — 出嚟每行
格數唔一致（7 格 vs 8 格），欄位對唔齊。

**改法**：Prompt 明確講 markdown 表達唔到合併格，要攤平做單層表頭，兩個標籤用斜線
接埋：

```text
| 第一枚勻稱骰子 / 第二枚勻稱骰子 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | (1, 1) | (1, 2) | | | | |
```

Validator 加 `RAGGED_TABLE`（medium）。**同 `MALFORMED_TABLE` 分開係刻意嘅** —
兩者成因唔同，改法亦唔同：一個係冇 separator row，一個係有 separator 但格數唔齊。
報錯要講返真正嘅成因，唔可以兩樣撈埋。

順便重整咗 `_pipe_blocks`：以前用「pipe 數一致」嚟分組，張 ragged 表會被拆成幾嚿，
診斷唔準。而家先按「連續有 pipe 嘅行」分組，再用「有 separator **或者** pipe 數一致」
判斷係咪表格，最後先分辨係 malformed 定 ragged。

---

## 15. Repair step — prompt 講唔掂嘅錯，喺 code 度整返

同一份 PDF 抽三次（temperature=0），Q19 三條小題共用嘅題幹出現咗
**錯 → 啱 → 錯**：其中一個小題（19(c)）嘅題目留咗喺共用題幹入面，搞到 19(a)、
19(b) 都帶住唔屬於自己嘅題目。Prompt 已經明寫「共用材料去到第一個部分為止」，
但模型唔穩定。

**所以加咗第二步**：

```text
Step 1  Extract
Step 2  Repair      ← 新增，app/extraction_repair.py
Step 3  Validate
Step 4  Render diagrams
Step 5  Save
```

觸發條件**故意做得好窄**，寧願漏都唔好亂改:

- 同一個 parent 至少兩條小題（`19(a)`/`19(b)` → parent `19`；
  `18(a)(i)`/`18(a)(ii)` → parent `18(a)`）
- 計所有兄弟嘅最長共同前綴，剪到最後一個句號為止 = 共用題幹
- 題幹**最後嗰句**要啱啱好等於**某一條小題嘅全部剩餘題目**
- 題幹至少兩句（淨係一句就唔敢剪，會剷走成個題幹）
- 嗰句至少 8 個字

改咗乜一定寫入嗰條題目嘅 `extraction_notes`，`ExtractionResult.repairs` 亦會記低，
`.md` report 有「Repairs applied」一節。冇一個改動係靜雞雞。

實測攞 run 3 嘅錯版落去修，出嚟同 run 2 嘅正確版本**逐個字一樣**；而同一份卷其他
六組正常兄弟題（Q2、Q5、Q10、Q11、Q12、Q18(a)）一個都冇被郁過。

`REPAIR_EXTRACTION=false` 可以熄。熄咗之後同一個情況會出 `STEM_CONTAMINATION`
（high）—— 而且**三條小題全部報**。原本個 `REPEATED_TEXT_IN_QUESTION` 淨係捉到
19(c)（因為佢自己同一句出現兩次），19(a) 同 19(b) 完全靜，呢個盲點要兄弟題層面
嘅檢查先補得返。

---

## 16. 並排嘅兩張表唔可以合併

Run 3 將 Q15 卷面並排嘅兩張表（頻數分佈 + 累積頻數分佈）合併成一張四欄表，
run 2 就正確噉分開兩張。合併咗即係話「201–210 對應 210.5」，但卷面冇噉講過 ——
兩張表只係印喺隔離，行與行之間冇定義關係。

Prompt 加咗：並排嘅兩張表係兩張表，要分開出，中間留空行，唔可以併埋一張闊表。

---

## 17. 表格：文字同圖片兩樣都要

三次 run 落嚟，表格係最唔穩定嗰樣 —— 冇 separator row、合併格砌唔正、並排兩張表
被併埋。一個好自然嘅諗法係「不如所有表格都影相算數」。

**但唔可以淨係影相。** Guide Part 16 列明下一步係 Analyzer、Solver、RPDICE、
Student Model、Question Generator，全部都要表格入面嘅**數值**：

```text
Q17  計期望值      →  要 $22 / $10 / $0 同埋每種波嘅數量
Q18  求 k          →  要 14, 14, 21, 37, 9, k
Q15  計平均重量    →  要成張頻數表
```

一張相搵唔到、計唔到、比唔到，Question Generator 亦都出唔到變化題。淨係影相等於
將 parsing problem 推去下一站，仲要再 OCR 一次。

**所以兩樣都保留**：

| | 角色 |
|---|---|
| Markdown 文字（`question_text`） | 機器讀，後面所有階段用 |
| 圖片（`ExtractionResult.tables`） | 人對，卷面真正嘅樣 |

Schema 改動：`DiagramRegion` 改名做 `PageRegion`（佢本來就係「頁面上一個框」，
同圖冇必然關係），`DiagramAsset` 改名做 `RenderedImage` 加 `kind`（diagram/table）
同 `index`。`ExtractedQuestion` 加 `table_regions: list[PageRegion]` —— 用 list
因為一條題目可以有幾張表（Q15 就有兩張）。

Prompt 要求每張印出嚟嘅表都畀一個 region，**同時仍然要 markdown 轉錄**，明寫
「相唔會取代文字」。

Validator 兩個配合改動：

- 表格文字有問題但**已經影咗相** → severity 由 `medium` 降做 `low`，訊息會講明
  有相可以對返。有 fallback 嘅問題冇咁緊要
- 有表格文字但冇 region → `TABLE_NOT_CAPTURED`（low）

Renderer 同一頁只 rasterise 一次再重用：一條題目有圖加兩張表，原本會將同一頁
render 三次。

---

## 18. 比較兩次 run

同一份卷抽咗四次，model 產生過一段**卷面根本冇嘅文字**，仲附上一句 note 聲稱嗰段
係卷面印錯：

```text
run 1-3   嘉欣得知 B 的底半徑為 18 cm。
run 4     嘉欣得知 B 的底半徑為 B 為 18 cm。
          note:「faithfully includes the printed typo ... from the paper」
```

**呢種嘢冇 validator 捉得到。** 單睇一次 run，佢語法啱、表格啱、題號啱、內部完全
自洽。錯嘅係內容同現實唔對應，而 validator 睇唔到現實。仲衰嘅係個 note ——
一段抄錯嘅字，扮成刻意忠於原文。

同類但更隱蔽嘅：run 3 用 `−`(U+2212)，run 4 用 `–`(U+2013)。肉眼一模一樣，但
下游做文字比對就會當成兩個唔同嘅題目。

**唯一可靠訊號係兩次 run 唔同。**

- `data/history/<stem>/<run_id>.json` —— 每次抽題 archive 一份。主 JSON 照舊
  覆寫（保持 idempotent），archive 先係令 model 嘅不穩定變成睇得見
- `app/extraction_diff.py` —— 逐條題目比 `question_text`、`marks`、
  `group_marks`、頁數、`answer`、表格數目；文字差異用 difflib 壓縮成
  `[-舊-]{+新+}` 加前後文，唔會 print 兩條長題目
- `scripts/compare_extractions.py` —— 冇參數就比最近兩次。冇差異 exit 0，
  有差異 exit 1，可以放入 script

`agreement`（一致嘅題目比例）係最直接嘅信心指標。兩次一致嘅地方基本信得過；
唔一致嗰幾條，先值得你揭返卷。

---

## 19. 批量真係跑 50 份卷

Lesson 18 個批量 script 邏輯啱，但係為咗示範寫，真係掟幾十份卷落去會撞到幾樣嘢 ——
其中最大鑊嗰個仲要係前面自己整返出嚟嘅。

| 問題 | 點解 | 改法 |
|---|---|---|
| Terminal 爆炸 | 第 (§ 上面) 次修好「印全文」之後，一份卷 39 條題目就幾百行，50 份 = 過萬行，個 summary 完全搵唔到 | `Repository(verbose=False)`，批量模式每份卷印一行，詳情留返畀每份卷自己嘅 `.md` |
| 重複燒錢 | `sha256` 由 Lesson 09 開始就計，但從來冇用嚟做 dedupe。重跑一個 batch = 全部重新叫一次 Gemini | 跑之前先 hash，`data/extracted/*-<sha12>.json` 已經有就跳過。改咗檔名都認得，因為認內容唔認名 |
| `.PDF` 大寫執唔到 | `glob("*.pdf")` 喺 Linux 係 case-sensitive，靜靜雞漏咗 | 改用 `rglob("*")` 再比較 `suffix.lower()` |
| 子資料夾執唔到 | `glob` 唔遞歸，`inbox/pdf/2024/x.pdf` 完全唔處理 | `rglob`，搬去 `processed/` 嗰陣保留返 folder 結構，空 folder 清埋 |
| 睇唔到進度 | 50 份卷跑 30 分鐘，唔知做到邊 | `[12/47]` + 每份幾秒 + 總時間 |
| Ctrl-C 拋 traceback | 中途想停，唔知做咗幾多 | 接住 `KeyboardInterrupt`，照出 report，exit 130 |
| Batch 內有重複卷 | 同內容第二份會覆寫第一份個 JSON（同 hash 同名），冇人出聲 | 記住呢次 run 見過嘅 hash，標做 `duplicate` |
| 冇留低嘅總結 | 得 terminal output | `data/extracted/batch-<時間>.md`，逐份卷列狀態／題數／用時 |

Pipeline 喺**任何 file 搬動之前**就起好 —— 冇 API key 就即刻炸，唔會半個 inbox
搬晒先發現。

---

## 20. 按題型分析（guide 冇）

抽一份卷，你睇得晒 39 條。抽 20 份卷 800 條，逐條睇冇意義 —— 而你真正想知嘅唔係
「呢條啱唔啱」，係「**邊種題型系統做得差**」。

`app/extraction_stats.py` 按題目**實際內容**分類（有表、有圖、有小題、跨頁、
有 LaTeX、分數嚟自邊、卷面有冇印答案、純文字），然後 cross-tab 每類嘅 issue 出事率。

一條題目可以同時屬於幾類，所以啲百分比係**故意重疊**嘅 —— 重點係比較
「有表格」對「純文字」，唔係要分割成互斥嘅類別。

仲會出：邊份卷最多問題、邊幾條題目最多問題、每份卷嘅 questions-per-page
（抽漏題就會偏低）。

`scripts/analyse_extractions.py` 讀晒 `data/extracted/*.json` 出報告，
亦都寫入 `analysis-<時間>.md`。

Document 層面嘅 issue（例如 `SUSPICIOUSLY_FEW_QUESTIONS`，冇
`source_question_id`）會計入總數，但**唔會賴落任何題型**，否則會冤枉咗啲題目。

---

## 21. PDF 檔名會流入輸出路徑

`extraction_output_path` 用 `Path(file_name).stem` 砌輸出名，而 `diagram_output_dir`
又用嗰個 stem 做資料夾名，最後 `.md` report 又用嗰個資料夾名砌圖片連結。即係話
**PDF 個檔名會直接變成 markdown 連結嘅一部分**。

實測：

```text
Mock Paper 1.pdf  ->  ![16](../diagrams/Mock Paper 1-abc123/16.png)   ← 空格，連結斷
Paper (2).pdf     ->  ![16](../diagrams/Paper (2)-abc123/16.png)      ← 括號提早收掣
```

兩個都令張圖 render 唔到。

**兩重修法**:

1. `paths.safe_stem()` —— 空格變 `-`，剷走會搞亂路徑或連結嘅符號
   （`/ \ : * ? " < > | ( ) [ ] { } # % & ...`），保留任何文字系統嘅字母數字
   （所以中文檔名照樣睇得明），收窄連續 `-`，截到 80 字，全部剷淨就用 `document`
2. Markdown 連結 percent-encode —— 就算路徑真係有特殊字元都唔會斷。中文資料夾
   喺磁碟上保持中文，淨係連結入面先編碼

去重一路以嚟都係認 sha256 唔認檔名，所以改名、複製都唔會令同一份卷抽兩次 ——
呢點冇變。

---

## 22. LaTeX backslash 俾 JSON escape 食咗

實測三份中學卷，S5 第 2 題出咗:

```text
化簡 \(\frac{6}{2x+5} - rac{3}{x-4}\)。
                          ^^^^ \frac 冇咗個 \f
```

同一份卷第 1 題嘅 `\frac` 完全正常 —— 即係模型**唔穩定噉**漏咗 escape 個 backslash。

成因：JSON 字串入面個 backslash 要寫兩個。模型寫咗 `"\frac"`，JSON 解碼器見到
`\f` 就當係 form feed (U+000C)，剩返 `rac`。

JSON 只定義咗 `\b \f \n \r \t`（連同 `\" \\ \/ \uXXXX`）。所以:

| 指令 | 結果 |
|---|---|
| `\frac` `\forall` | FF + 文字 —— **靜靜雞壞** |
| `\beta` `\binom` | BS + 文字 —— **靜靜雞壞** |
| `\times` `\theta` | TAB + 文字 —— 壞，但 TAB 係正常空白 |
| `\neq` `\rho` | LF / CR + 文字 —— 同上 |
| `\vec` `\alpha` `\sum` | **唔係合法 escape → 成個 response parse 唔到** |

最後嗰行其實係好消息：唔合法嘅會即刻炸，唔會扮冇事。

**修法**:
- Prompt 加 `JSON ESCAPING` 一節，明寫每個 backslash 要寫兩次，同埋
  `question_text` 唔可以有控制字元
- `repair_control_characters()` 自動修 BS 同 FF —— 呢兩個喺數學題文字入面
  **絕對唔會**合法出現，所以零風險
- TAB / LF / CR **唔會自動改**（佢哋係正常空白），只出 `CONTROL_CHARACTER`（high）
- 每個修正都寫入 `extraction_notes`

---

## 23. 選擇題

S6 係一份 45 條全 MC 嘅卷。系統當時將成段嘢（題幹 + A/B/C/D 四個選項）塞晒入
`question_text`。

噉樣後面做唔到：打亂選項、對答案、由選項出變化題、統計邊個 distractor 最多人揀。

**改法**：`ExtractedQuestion` 加 `question_type`（`open` / `multiple_choice`）同
`options: list[str]`（按印刷次序，唔要 A/B/C/D 標籤）。Prompt 要求 `question_text`
淨係放題幹，唔可以重複啲選項。

Validator 加 `OPTIONS_NOT_SEPARATED`（選項仲喺 prose）同 `OPTIONS_MISSING`
（標咗 MC 但 options 空）。

偵測用「A/B/C/D 至少三個出現喺行首，後面跟 `.` `)` `、` 加空白」。用三份卷嘅真實
文字試過，幾何題寫 `A(5, 4) 及 B`、`A、B、D、E 和 F 均是圓上的點` 都唔會誤判。

---

## 24. LaTeX 冇包 delimiter

再試三份卷，S4 第二份出咗:

```text
Q18(a)   L = 10 \log \frac{I}{10^{-12}}      ← 冇 \( \) 包住
Q19      把 y = \log_a bx 的圖像記為 G。         ← 同上
Q15      簡化 i^{1029} - i^{1026} + ...        ← 上標都係
```

而同一份卷嘅 Q9 就完全正確：`\(\frac{\tan \theta - \sin \theta}{...}\)`。
即係話 backslash 冇爛（同 §22 嗰個唔同），純粹係漏咗 delimiter，所以去到邊都
render 唔到。

**偵測**：先剷走所有 `\( ... \)`、`$...$`、`$$...$$` 區段，剩低嘅再搵
`\command` 或者 `^{...}` / `_{...}`。噉樣寫得啱嘅數學永遠唔會被誤報 —— 用三份卷
嘅真實文字試過，包括 `\begin{cases}`、Unicode 上標 `x⁵`、`√137`、markdown 表格
同純中文，全部唔報。

Prompt 加咗規則，連埋獨立成行嘅公式都要包。

---

## 25. 同一份卷入面幾種減號

S4 第一份第二次 run，**一份卷用咗三個唔同字元**做減號:

```text
Q10     x - 6x² - 4 = 0        U+002D  hyphen
Q12     kx² – kx + k – 2 = 0   U+2013  en dash
Q19     2x² + 8x − 3 = 0       U+2212  minus
```

卷面只印一個字元。下游做文字比對、去重、搵題，呢三個會當成唔同嘢。

`INCONSISTENT_MINUS_SIGN`（low）—— 每種用夠三次先報，所以一兩個連字號唔會嘈。
Prompt 釘死用 U+2212。

**唔會自動改**：我哋唔知卷面實際印邊個，改咗就係作嘢，違反 Rule 5。報出嚟等你
決定。

---

## 26. 選擇題結構成功

S6 第二份 45 條全部抽做 `MC, 4 options`，題幹同選項完全分開:

```text
question_text  \(\frac{(81^{2n})(3^{-n})}{9^{2n}}=\)
options        ["81ⁿ。", "27ⁿ。", "3²ⁿ。", "\(\frac{1}{3^n}\)。"]
```

I/II/III 嗰種題（Q14、Q17、Q20、Q25、Q30、Q37、Q45）亦都啱 —— I/II/III 留喺題幹
（佢哋本身係題目一部分），A/B/C/D 抽做 options。

---

## 27. 自動包返冇 delimiter 嘅公式

§24 偵測到 LaTeX 冇包 `\( \)`，但淨係報。實測結果：報咗都冇用 —— 條式喺 `.md`
report、web viewer、同任何你 copy 去嘅地方都 render 唔到，用家要自己 copy 去第二個
工具先睇得明條式係咩。

Prompt 講咗兩次都仲係噉，所以同 §15 一樣，落 code 修。

**只包「成行都係數學」嗰啲**：

```text
L = 10 \log \frac{I}{10^{-12}}        →  \( L = 10 \log \frac{I}{10^{-12}} \)
```

條件（缺一不可）:

- 成行冇中日韓文字
- 未有 `\(` / `$` 包住
- 至少有一個 `\command` 或者 `^{...}` / `_{...}`

**中文夾住嘅 inline 數學唔會自動包**，例如
`把 y = \log_a bx 的圖像記為 G。` —— 數學喺邊度完全靠估，估錯比生 markup 更差。
呢種繼續出 `LATEX_NOT_DELIMITED` 等人手處理。

---

## 28. Unicode 上標放唔落小數指數

同一條題目，卷面印 `10⁻⁷·²`（即 10 的 −7.2 次方），抽出嚟係
`10⁻⁷·²` —— 用咗個間隔號 `·` 扮小數點，因為 Unicode **根本冇上標小數點**。

Prompt 加咗：Unicode 上標淨係載得起單一整數指數；小數、分數、或者式做指數
一律要用 LaTeX（`\( 10^{-7.2} \)`）。

---

## 29. 減號檢查要分「散文」同「LaTeX」

§25 個 `INCONSISTENT_MINUS_SIGN` 上線之後，三份本來乾淨嘅卷全部報咗一個 low：

```text
S4-2nd   hyphen x4   minus x20
S5       hyphen x8   minus x26
S6-2nd   hyphen x5   minus x39
```

逐個 hyphen 追返，**14 個全部喺 `\( \)` 入面**：`\frac{6}{2x + 5} - \frac{3}{x - 4}`、
`10^{-12}`、`\begin{cases} ... y \ge x - 10`。

LaTeX 入面 ASCII `-` 就係正確嘅減號，用 U+2212 反而唔標準。所以「散文用 −、公式
用 -」係一致，唔係撈亂。個 check 而家先剷走 `\( \)` 區段再數。Prompt 亦改成兩條
規則：散文 U+2212，公式內 ASCII hyphen。

好處係呢三份卷而家係**真正零 issue**，而唔係一個要人手排除嘅誤報。

## 30. Supabase：先做 row builder，再做 store

Guide 話 Repository 係「唯一寫資料嘅地方」，之後接 Supabase。接嘅時候分咗兩層：

- `document_row` / `run_row` / `question_rows` 係純函數：`ExtractionResult` 入，
  plain dict 出。寫入嘅每個 column 都可以用 fake client 測，唔使有 database。
- `SupabaseStore.save` 得三十行：upsert document → insert run → insert questions
  → 將舊 run 嘅 `is_current` 改做 false。

同 guide 唔同嘅地方：

1. **每次 run 都留低，唔覆蓋。** Guide 只講三個 table。實際跑落嚟，同一份卷會抽好幾
   次（prompt 改咗、model 改咗、想比較），而 §18–§20 嘅 run-to-run diff 正正需要舊
   run 仲喺度。所以 `extraction_runs` 加 `is_current`，`questions` 掛喺 run 而唔係
   直接掛喺 document。
2. **`source_documents` 用 sha256 做 unique key。** 同一份 PDF 改咗檔名再放入
   inbox，仍然係同一個 document，只係多一個 run。
3. **冇 transaction 就自己收拾。** Supabase REST 一次一個 request。Run row 寫咗但
   questions 寫唔入，會即刻刪返個 run row，寧願重跑都唔好留低空 run。
4. **冇 `.env` 就唔連。** `Repository()` 見 `SUPABASE_URL` 空或者仲係 `put_...`
   就當冇 database，行為同 v1.1 之前一模一樣。Batch、單份、test 都唔會因為冇
   Supabase 而壞。
5. **`scripts/db_check.py` 先行一次。** 佢會逐個 table select 齊 store 會寫嘅
   column。Column 名對唔上會喺 ingest 之前爆，而唔係抽完題目先發現寫唔入。

未驗證：呢個環境連唔到 PyPI 同 Supabase，`supabase-py` 嘅 `upsert(on_conflict=)`、
`update().eq().neq()`、`select(count="exact")` 係按官方文件寫，第一次真接
Supabase 請先行 `db_check`。


## 31. 級別 F1–F6：兩個來源，一個碼

Guide 由頭到尾寫住「Primary 6 level」，即係成個 system 淨係一級，所以 Question
Object 冇級別呢個欄。實際上收返嚟嘅係中四、中五、中六嘅卷，冇級別就分唔到題庫。

加咗 `app/level.py`，做一件事：將人寫級別嘅所有寫法，變做一個碼。

```text
S4   S.4   s4   F4   F.4   F 4   Form 4   Secondary 4   Sec 4   中四   中五級   Grade 10
```

全部 → `F4` / `F5`。碼只有 `F1`–`F6`。

### 點解唔淨係信份卷

Prompt 加咗一個 `level_text`，叫 Gemini **照抄**封面印住嘅字（「中四」），唔好解讀。
解讀係 code 做，因為：

1. **抄字係確定性嘅，解讀唔係。** §22、§27 已經證咗 prompt 叫佢做判斷會時好時壞。
   「中四」呢兩個字抄出嚟，之後每次 parse 都一定係 `F4`。
2. **檔名優先。** 檔名係你自己改，錯就 rename，即刻改到；份卷印咩字係 model 讀一次
   封面。所以 `S5-mock.pdf` 入面印住「中四」，用 `F5`，同時報 `LEVEL_MISMATCH`
   叫你睇返。兩個來源唔同 **一定要有人知**，唔可以靜靜雞揀一個。
3. **估唔到就唔估。** 「中一至中三」搵到兩個級別，`parse_level` 返 `None` 而唔係揀
   第一個；「其中一個」入面嘅「中一」有 negative lookbehind 擋住。寧願 `LEVEL_MISSING`
   （low，唔 blocking）都好過寫錯級別入 database —— 錯級別會靜靜雞污染成個題庫。

### 邊度用得著

`questions.level` 係 denormalise 出嚟嘅（document 已經有一份）。多存一欄嘅原因係
最常問嗰句 SQL：

```sql
select * from current_questions where level = 'F4' and question_type = 'open';
```

唔使 join 就出到「中四所有非選擇題」。

### 冇級別唔會擋住抽題

`LEVEL_MISSING` 係 low，唔係 blocking。冇級別嘅卷照抽、照存，只係之後篩唔到。呢個
係刻意嘅：抽題目同分類係兩件事，一件失敗唔應該拖冧另一件。

## 32. Schema 檔要補得返，唔可以淨係「開新 table」

第一次真連 Supabase，`db_check` 三個 table 全部 FAIL：

```text
FAIL source_documents   APIError: column source_documents.sha256 does not exist  (42703)
FAIL extraction_runs    APIError: column extraction_runs.run_id does not exist
FAIL questions          APIError: column questions.extraction_run_id does not exist
```

`42703` 係 **undefined_column**，唔係 undefined_table —— 即係三個 table 都喺度，
但入面乜 column 都冇。用 Supabase table editor 開一個 table 就係噉：得
`id bigint identity` 同 `created_at`。

原本份 `supabase_schema.sql` 全部係 `create table if not exists`，遇到呢個情況乜都
唔做（table 「已經存在」），於是永遠 FAIL 落去。改成三段：

1. `create table if not exists` —— 全新 project 一步搞掂。
2. 一個 `do $$` block，逐隻 column `add column if not exists`。補出嚟嘅 column
   **一律 nullable**，因為已經存在嘅 row 冇可能追溯滿足 NOT NULL；pipeline 每次都
   寫齊所有欄，所以冇損失。
3. Unique index（`sha256`、`run_id`、`(extraction_run_id, source_question_id)`）。
   `sha256` 嗰個唔係裝飾 —— 冇佢 `upsert(on_conflict="sha256")` 根本做唔到，同一份
   PDF 就會變幾行。

兩個 foreign key column 嘅型別係由 parent 個 `id` **讀返嚟**再 `format()` 出去，
所以 table editor 嗰個 `bigint` id 同全新 schema 嘅 `uuid` id 都接得上。Table 連
`id` 都冇嘅話，會補一個 `uuid default gen_random_uuid()`；`gen_random_uuid()` 係
volatile，Postgres 會逐行計一次，所以舊 row 唔會攞到同一個 id。

### 真係跑過先算

呢啲嘢估唔得，所以喺本機開咗個 Postgres 16 測四種情況，每種都行埋 store 嗰串
寫入（upsert document → insert run → insert questions → 舊 run 轉 `is_current=false`）：

| 情況 | 結果 |
|---|---|
| 全新空 database | 建齊，寫入正常 |
| 再行多次 | 冇變化，寫入正常 |
| Table editor 開嘅 table（bigint id，已有 row） | 補齊 column，FK 變 bigint，舊 row 留住 |
| 手開、冇 `id`、已有三行 | 補 uuid id，三行三個唔同 id |

四種都係 `documents = 1, runs = 2, current run = run-b, questions = 3`。

### `db_check` 要講得出邊隻 column

之前佢一次 select 晒所有 column，PostgREST 只報第一隻唔見嘅，於是你要「補一隻、行
一次、再補一隻」。而家逐隻 column 試一次（三個 table 加埋四十個 request，一次過嘅
嘢，唔緊要），一次過列晒。同時分開兩種情況：`select *` 都失敗 = table 唔存在；
`select *` 得、逐隻 column 失敗 = column 對唔上 —— 兩種嘅下一步唔同。
