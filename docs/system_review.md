# 成個系統嘅複查（2026-09-13）

> **狀態(2026-09-15)**:「而家要做嘅」1–8 全部做咗(§34–§37 deviations),Analyzer 嘅
> prompt / schema / validator / 黃金集起咗(§37),taxonomy 逐條對咗 C&A Guide(§44),
> 第 2 層 Solver / Critic 起咗,strategy 有穩定 id(§45)。第 3 層開咗頭:Grader 讀單頁手寫,
> `students` / `attempts` table(§47)。未做:Student Model(skill_mastery)、Calibration、Adaptive。

對住 `system_spec.md` 逐層睇:而家有乜、缺乜、邊啲而家唔做將來補唔返。
Ingestion 嗰層嘅 15 個 bug(pipeline 次序、blocking run 蓋過好 run 等)已經另外列咗,
呢度唔重複,只講**成個系統**嘅設計。

---

## 一句總結

而家嘅 Question Object 係「一份卷、一次抽、一批題」。後面每一層需要嘅係「**一條題目
一個穩定身份**,任何分析、任何學生作答都掛落去」。呢個身份而家冇。其他所有缺口都係
呢個問題嘅分支。

---

## 第 0 層:Ingestion(而家有嘅)

| 後面要嘅 | 現況 | 缺口 |
|---|---|---|
| 原文唔改 | ✅ prompt 明令、validator 驗 | — |
| Method cue 原文保留 | ✅ 因為原文唔改 | 冇標記邊句係 cue(Analyzer 做,唔係 Extractor) |
| Level F1–F6 | ✅ 剛加 | — |
| 答案 / worked solution | ✅ 有欄,印咗就抄 | 冇「marking scheme」欄:HKDSE 卷嘅 marking scheme 係另一份 PDF,而家冇路配對返 |
| 題目穩定身份 | ❌ `questions.id` 每次 run 都新 | **最大缺口**,見下 |
| 小題依賴 | ❌ 只係重複 shared stem | 1(b) 靠 1(a) 嘅答案,冇記錄 |
| 份卷 metadata | ❌ 只有 file_name + level | 年份、學校、考試類型、Paper 1/2、課題範圍全部冇 |
| 題目喺卷入面嘅位置 | ✅ `position` | 可以做 structural depth 嘅弱 prior(卷尾通常深) |
| 分數 | ✅ marks / group_marks | 同上,係 prior |
| 圖 | ✅ crop 咗 PNG,path 存低 | path 係絕對路徑(已列);圖本身冇上 Supabase |

### 0.1 題目身份(canonical question id)

重抽同一份卷 → 新 run → 新 `questions.id`。學生作答數據如果掛喺舊 id,重抽之後全部變
孤兒。Analyzer 嘅結果同樣。

建議:加一個 `question_bank` 概念,身份 = `sha256(卷) + source_question_id`,即係
「呢份 PDF 嘅第 17(a) 條」,不論抽幾多次都係同一個。

```text
question_key = <source sha256 前 12 位>:<source_question_id>      例  b584940bfebb:17(a)
```

- `questions` 每行加 `question_key`(可以由現有欄計出嚟,唔使改 prompt)
- 之後 `question_analyses`、`student_responses`、`item_statistics` 全部掛 `question_key`,
  唔掛 `questions.id`
- 重抽之後 current run 嘅題目自動接返所有舊分析同作答數據

呢個係**而家就要做**嘅,因為越遲做,越多嘢掛錯 id。

### 0.2 小題依賴

Extractor 可以喺唔解題嘅前提下做到一樣嘢:標記「呢條小題有冇引用前面小題嘅結果」。
例如「利用 (a) 嘅結果」、「Hence」、「由此」呢啲字係原文就有。加一個 `depends_on:
["17(a)"]`,由 prompt 抄返(唔係推理),validator 驗 id 存在。

用途:I 同 C 嘅證據;Adaptive 唔可以單獨出 17(b);Generator 生成變體時要連 (a) 一齊。

### 0.3 份卷 metadata

Empirical difficulty 要按群體分(F4 上學期 vs DSE mock 唔同班)。建議一個
`paper_meta`,可以由檔名 convention 讀(同 level 一樣嘅做法),或者一個 sidecar
`inbox/pdf/<name>.yaml`:

```yaml
year: 2025
school: ABC College
exam: 1st term test      # test | exam | mock | dse | homework
paper: 1
topics: [factorisation, quadratic]
```

檔名讀唔到就 null,唔會擋住抽題。

### 0.4 Marking scheme 配對

HKDSE 同好多校內卷,題目卷同 marking scheme 係兩份 PDF。而家 `answer` /
`worked_solution` 只係「同一份 PDF 印咗就抄」。要一個配對機制:同一 sha 前綴、或者
檔名 `<name>-ms.pdf`,抽出嚟嘅 answer 掛返去 `question_key`。Solver 同 Critic 冇
marking scheme 就冇「標準答案」可以對。

---

## 第 1 層:Analyzer(RPDICE)

未做。但 schema 而家要諗定,因為 Analyzer 嘅 output 係後面所有層嘅 input。

### 1.1 Skill 要用受控詞彙,唔可以 free text

Analyzer 如果每次自由寫 `"recognise perfect square"` / `"recognize perfect squares"` /
`"perfect square recognition"`,Student Model 計 mastery 嗰陣會當三個 skill。

建議 `skills` table:`skill_id`、`skill_family`、`name_en`、`name_zh`、`form`(F1–F6
邊級教)、`prerequisites`。Analyzer 嘅 prompt 俾佢個 list 揀,揀唔到先可以 propose 新
skill(另一個 table `skill_proposals`,人手 review 先入正式表)。

呢個 taxonomy 係成個系統最貴、最難改嘅資產,越早定越好。建議由 HK 課程大綱起,
唔好由 Gemini 自由生成。

### 1.2 RPDICE 掛 strategy,一題多 strategy

Spec §1 講咗。Schema:

```text
question_analyses     一次分析(掛 question_key,記 analyzer_version、prompt_sha、model)
  └ strategies        每個 strategy 一行(name、steps、rpdice jsonb、is_primary)
  └ analysis_skills   多對多,掛 skills.skill_id
  └ analysis_errors   掛 error_patterns.error_id(E 嘅受控詞彙,同 skill 一樣道理)
```

`question_analyses` 同 `extraction_runs` 一樣有 `is_current`,可以重跑、可以 diff。

### 1.3 RPDICE 要有 scale,唔止 evidence list

Spec 嘅 JSON 每個字母係 evidence 嘅 list。呢個啱,但 Calibration 要數字。建議每個
字母加一個 0–3 嘅 ordinal(0 無、1 低、2 中、3 高),evidence 解釋點解。Ordinal 唔係
「難度」,係「呢個維度嘅要求有幾強」。

### 1.4 Analyzer 要有自己嘅 validator 同 diff

同 extraction 一樣,Gemini 做 RPDICE 會時好時壞(§18–20 已經證咗抽題係咁)。要:
- 結構 validator:每個 strategy 有 steps、skills 喺受控表、E 有至少一個
- run-to-run diff:同一題兩次分析 RPDICE 差幾遠 —— 差得遠即係 prompt 未穩
- 黃金集:人手標 30–50 題做 baseline,每次改 prompt 對返

### 1.5 D 靠 method cue,Analyzer 要 output 佢搵到嘅 cue 原句

`method_cues: ["Use the difference of two squares"]`,原文摘錄。Critic 可以驗:句子真係
喺題目度。Generator 想降 D 就加 cue,想升 D 就刪 cue —— 呢個係最平嘅變體生成。

---

## 第 2 層:Solver + Critic + Validator

### 2.1 Solver 係 Analyzer 嘅驗證,唔係獨立功能

Solver 用 Analyzer 列出嘅 strategy 真係解一次。目的唔係「俾答案」,係驗證:
- strategy 嘅 steps 真係行得通
- 解出嚟同 marking scheme(如果有)一致
- 過程中真係會經過 E 列出嘅易錯位

Solver 解唔到 / 解錯 = Analyzer 嘅 strategy 有問題,唔係 Solver 有問題。

### 2.2 Critic 要獨立,唔可以同一個 prompt

Critic 攞 Analyzer output + Solver output + 原題,只做一件事:挑錯。用另一個 prompt
(最好另一個 model)。Critic 嘅 output 係 issues,同 extraction validator 一樣格式
(`issue_code`, `severity`, `message`),入 `question_analyses.issues`。

### 2.3 Validator = 結構檢查,同而家嘅 extraction_validator 一樣角色

唔判斷數學,只驗:skill id 存在、RPDICE 六個字母齊、confidence 喺 0–1、
`empirical_difficulty` 真係 null。可以直接 code 寫,唔使 LLM。

---

## 第 3 層:Student Model + Empirical Difficulty

未有學生,但 schema 而家定:

```text
students              student_id、form、class、cohort(邊班、邊年)
attempts              一次作答:student_id、question_key、answer_given、is_correct、
                      score、time_seconds、hints_used、first_step_correct、
                      error_ids[](對返 error_patterns)、attempted_at
item_statistics       每條題每個 cohort:n、p_correct、mean_score、mean_time、
                      discrimination、irt_b、updated_at
skill_mastery         每個學生每個 skill:估計值、信心、最後更新
```

要點:
- `attempts` 掛 `question_key`,唔掛 `questions.id`(0.1)
- `error_ids` 對返 Analyzer 嘅 E:呢個係「Analyzer 話會暴露乜錯」同「學生真係錯乜」
  嘅接口。兩邊對唔上 = Analyzer 嘅 E 標錯,係最有價值嘅 feedback loop
- `item_statistics` 按 cohort 分,唔好全校一個數(spec §2:實際難度受群體影響)
- Student Model 由 attempts 推 skill_mastery,唔係由題目對錯直接推 —— 一條題錯,
  要經 Analyzer 嘅 atomic_skills 先知邊個 skill 弱

---

## 第 4 層:Calibration

Structural(Analyzer)+ Empirical(item_statistics)→ `calibrated_level`。

- 冇 empirical 數據嗰陣,`calibrated_level` = null,**唔好**用 structural 頂住當 level。
  Adaptive 可以退而用 structural,但要知道自己用緊嘅係未校準嘅嘢
- 有 n ≥ 某個門檻(例如 30 次作答)先 calibrate
- 記低 calibration 用咗邊個版本嘅 analysis、幾多 attempts,可以重算

Schema:`calibrations`:question_key、cohort、level(L1–L5)、structural_version、
n_attempts、calibrated_at、`is_current`。

---

## 第 5 層:Adaptive + Question Generator

Spec §0 嘅最終畫面:差嘅學生唔係出晒簡單題,係引導。呢個意味住:

### 5.1 揀題唔係「揀 level 啱嘅」,係「揀 skill gap 啱嘅」

Adaptive 嘅 input 係 `skill_mastery`(邊個 skill 弱)+ `question_analyses`(邊條題考
邊個 skill、RPDICE 邊個維度重)。「差」嘅學生通常唔係全部弱,係某個 R 或者某個 D 弱。
出一條 R 低 D 低但 P 一樣嘅題,佢做到,先慢慢加返 R。

### 5.2 Generator 生成嘅係「沿 RPDICE 某個軸移動嘅變體」,唔係「相似題」

由 1.5:加 / 刪 method cue 改 D;拆一條 I 高嘅題做兩條 I 低嘅;改數字唔改結構(最平,
用嚟練 P)。每個變體都要行返 Analyzer → Critic,確認真係移咗預期嘅軸,先可以入題庫。
生成嘅題掛 `derived_from: question_key`,永遠追得返源頭。

### 5.3 Generator 出嚟嘅題,一定要標 `source: generated`

同 extracted 嘅分開存或者分開標。Empirical 數據返嚟,可以對比「生成題 vs 真卷題」嘅
calibration 有冇偏,呢個係 Generator 準唔準嘅唯一量度。

---

## 而家要做嘅(未有 Analyzer 都要做)

| # | 嘢 | 點解而家 |
|---|---|---|
| 1 | `question_key` 加入 `questions`,所有將來 table 掛佢 | 越遲越多嘢掛錯 id |
| 2 | `depends_on` 加入 Question Object,prompt 抄返「利用 (a) 嘅結果 / Hence」 | 原文有,而家唔抄將來要重抽 |
| 3 | `paper_meta`(年份 / 學校 / 考試類型 / paper)由檔名或 sidecar 讀 | Empirical 按群體分靠佢 |
| 4 | `skills` taxonomy 由 HK 課程起稿(人手,唔用 LLM) | 成個系統最難改嘅資產 |
| 5 | `error_patterns` 受控表(同 skills 一樣) | E 同學生錯誤嘅接口 |
| 6 | Marking scheme 配對機制(`<name>-ms.pdf`) | Solver / Critic 冇標準答案就冇得驗 |
| 7 | `extraction_runs` 記 `prompt_sha256` + token usage | Analyzer runs 會照抄呢個 pattern |
| 8 | Ingestion 嗰 15 個 bug | 地基 |

## 之後先做(要 1–5 先)

- Analyzer prompt + schema + validator + 黃金集(30–50 題人手標)
- Solver / Critic
- `attempts` / `item_statistics` / `skill_mastery`(schema 可以而家開,有學生先有數據)
- Calibration
- Adaptive / Generator

## 唔好做嘅

- 唔好喺 `questions` 加 `difficulty` 一欄(spec §4)
- 唔好俾 Extractor 標 skill 或 RPDICE(guide 同 spec 都禁)
- 唔好用 Gemini 自由生成 skill 名(1.1)
- 唔好用 structural 頂替 calibrated level 而唔標明(第 4 層)
