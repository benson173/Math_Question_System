# RPDICE 評分標準(v1)

自動化 RPDICE 嘅唯一方法係:標準寫到兩個人(或者一個人同一個 model)對住同一條題目、同一個
解法,會落同一個數。所以每個字母每一級都係**可觀察**嘅準則,唔係形容詞。

機器讀嘅版本喺 `app/rpdice.py` 嘅 `LEVELS`,Analyzer prompt 由佢生成,呢份文件係人讀嘅
解釋加 anchor 例子。**改標準改 `LEVELS`**,唔好淨係改呢份文件。

## 原則

1. **每個 strategy 一個 profile。** 同一條題兩個解法,R/P/D 唔同。題目層面用 primary
   strategy(中四 / 中五學生預期用嗰個)。
2. **0–3 係序數,唔係分數,永遠唔加埋。** 一條題目係一個 vector 加「邊啲維度主導」
   (`difficulty_drivers` = 去到 2 或以上嘅字母)。
3. **只睇題目同解法。** 唔睇分數、唔睇題號位置、唔睇學生數據。`empirical_difficulty`
   永遠係 null。
4. **Method cue 決定 D 嘅上限。** 題目印住「利用二次公式」「利用配方法」「Hence」「由此」
   「利用 (a)」,D 最多係 1。Cue 要**原文照抄**入 `method_cues`,validator 會查佢真係喺
   題目度。
5. **靠前面小題嘅部分,只評佢自己嗰步。** (a) 嘅結果當已知;evidence 要講明。
6. **Skill 同 error 只可以揀,唔可以創。** 搵唔到就放 `proposed_*`。

## 六個維度

### R — Recognition(睇唔睇得出)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 冇嘢要認:要處理嘅對象直接寫明 | 解 2x + 3 = 7 |
| 1 | 一個標準形式,符號本身已經提示 | 9a² − 25 一睇就係 a² − b²;直角三角形俾兩邊 |
| 2 | 要先睇出隱藏結構或者重新解讀 | 225x² 要睇成 (15x)²;(2x+1) 當一個整體;重疊圖形入面認相似三角形;「兩相異交點」即係 Δ > 0 |
| 3 | 認出嚟係成條題嘅關鍵,而且冇任何提示 | 方程其實係 log₂x 嘅二次式;坐標題入面藏住幾何事實;輪流擲骰係無限等比 |

### P — Procedure(識唔識做步驟)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 讀個值、講個事實 | 寫出 x 截距 |
| 1 | 一個標準程序,短 | 套一個恆等式、一個公式、一次代入 |
| 2 | 幾個程序串埋,或者一個程序因分數 / 根式 / 參數 / 配方 / 長除法而變複雜 | ¾k² − 2k + 1 = 0 用公式;配方法求頂點 |
| 3 | 長鏈,錯誤會累積 | 帶參數多階段代數;三維圖形幾個三角形;要分情況嘅程序 |

> 重複同一個程序十次,P 唔會超過 2。

### D — Decision(識唔識揀方法)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 題目寫明方法,或者只有一個方法 | 「利用二次公式」「利用配方法」「Hence」 |
| 1 | 課題嘅標準方法直接用得 | 因式分解一節入面見到 a² − b² |
| 2 | 兩個以上可行方法要揀,或者次序有影響,或者要揀 representation | 平方差定提公因式先;先化簡定先代入;代數定圖像 |
| 3 | 要自己設計策略 | 冇標準方法直接套;要設 sub-goal、輔助線、輔助變量;要決定重用邊個前面結果 |

### I — Integration(識唔識將幾樣知識連埋)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 一個 atomic skill | |
| 1 | 同一 unit 入面幾個 skill | 因式分解再解方程 |
| 2 | 兩個唔同 unit 要連埋 | 三角 + 坐標幾何;百分數 + 對數 |
| 3 | 三個以上 unit,或者要喺 representation 之間轉換 | 幾何事實 → 代數條件 → 不等式 |

> 同一技巧重複十次唔係 integration。Validator 會對返 `atomic_skills` 嘅 unit 數目。

### C — Cognitive Depth(推理有幾深)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 一步直接 | |
| 1 | 順序步驟,每步由上一步決定,只向前 | |
| 2 | 以下其一:由結果倒推條件、分情況、檢驗 / 剔除候選解、「試解釋」要計數比較 | 兩位數應用題要剔除不合理根;(3x−10)² > 0 嘅等號情況 |
| 3 | 證明、推廣、評估一個宣稱(要建構論證或反例);或者後面小題用前面結果嘅方式唔明顯 | 「某人宣稱……你是否同意」;內心 → 證明圓內接四邊形 |

> C 唔等於步驟數。一條短題要逆向思考,C 可以係 3;一條長題只係機械計算,C 可以係 1。

### E — Error Exposure(呢題容易暴露咩錯誤)

| 級 | 準則 | Anchor |
|---|---|---|
| 0 | 冇常見錯誤模式適用 | |
| 1 | 一個學生自己會發現嘅小失誤 | 符號、算術 |
| 2 | `error_patterns` 入面某個 misconception 直接被觸發,或者兩個以上失誤位 | 不等式乘負數唔變向;增根;對數底錯 |
| 3 | 幾個 misconception 同時,或者錯咗會得出一個「睇落合理」嘅答案,冇得自我檢查 | 三角方程漏第二個解;非獨立事件當獨立相乘 |

> E 係題目「會暴露乜」,唔係「學生一定錯」。每個 E 都要列 `error_id`。

## 一致性規則(validator 會查)

| Code | 意思 |
|---|---|
| `RPDICE_LEVEL_OUT_OF_RANGE` | 唔係 0–3 |
| `RPDICE_EVIDENCE_MISSING` | 級數 > 0 但冇 evidence |
| `SKILL_UNKNOWN` / `ERROR_UNKNOWN` | 唔喺 taxonomy;應該放 `proposed_*`(只係 strand 前綴錯、其餘部分獨一無二嘅 id,runner 會先自動改正並記喺 `repairs`) |
| `ERROR_NOT_OF_SKILL` | error 唔屬於任何一個列出嘅 skill,亦唔屬於佢哋嘅 prerequisite(`*` / `ms.*` 嗰啲通用 error 唔會報) |
| `METHOD_CUE_NOT_IN_TEXT` | cue 唔係原文 |
| `DECISION_IGNORES_CUE` | 題目有 cue 但 D > 1 |
| `DRIVERS_MISMATCH` | drivers 同 levels 對唔上(runner 會自動重算) |
| `INTEGRATION_INCONSISTENT` | I 同 skill 嘅 unit 數目對唔上 |
| `PRIMARY_STRATEGY_COUNT` | 唔係恰好一個 primary |
| `EMPIRICAL_NOT_NULL` | Analyzer 估咗答對率 |
| `DUPLICATE_STRATEGY` | 兩個 strategy 同名同 skills(同一個 `strategy_id`) |
| `STRATEGY_FIELDS_INVALID` | `source` / `status` 唔係認可值 |

## Solver / Critic 會報嘅(`critic_issues`)

| Code | 邊個報 | 意思 |
|---|---|---|
| `STRATEGY_DOES_NOT_SOLVE` | code / Critic | 照 steps 行解唔到答案 → strategy `rejected` |
| `ANSWER_MISMATCH` | code | Solver 答案同 marking scheme 唔同 |
| `STRATEGIES_DISAGREE` | code | 同一題唔同 strategy 解出唔同答案 |
| `SOLUTION_MISSING` | code | Solver 冇交某個 strategy 嘅解 |
| `SOLUTION_NEEDS_DIAGRAM` | code | 題目要睇圖而 Solver 冇圖 → strategy `unverified`,唔算 rejected |
| `STRATEGY_STEPS_WRONG` / `STRATEGY_MISSING` / `PRIMARY_NOT_TYPICAL` | Critic | steps 數學上錯 / 漏咗明顯方法 / primary 揀錯 |
| `LEVEL_OVERRATED` / `LEVEL_UNDERRATED` | Critic | 某個字母唔跟 rubric(message 講邊個 strategy、邊個字母、應該幾多) |
| `EVIDENCE_NOT_IN_QUESTION` | Critic | evidence 講嘅嘢題目冇 |
| `SKILL_MISSING` / `SKILL_IRRELEVANT` | Critic | 漏 skill / 列咗冇用嘅 skill |
| `ERROR_NOT_TRIGGERED` / `ERROR_MISSING` | Critic | 列咗唔會發生嘅 error / 漏咗明顯陷阱 |
| `CRITIC_OTHER` | — | Critic 用咗清單外嘅 code |
| `QUESTION_NOT_ANALYSED` / `ANALYSIS_FOR_UNKNOWN_QUESTION` / `DUPLICATE_ANALYSIS` | 同份卷對唔上 |

## 黃金集同計分

`taxonomy/golden/rpdice_gold.csv`:每條題目人手一行(question_key、skills、R–E、errors、
rater、status)。而家 30 條係我起草嘅 `draft`,你核對後改 `confirmed`。

```bash
python3 -m scripts.score_rpdice --check      # 驗黃金集
python3 -m scripts.analyse_rpdice            # 跑 Analyzer(要 Gemini)
python3 -m scripts.score_rpdice              # 對比:每個維度 exact / within-1 / bias
```

改 prompt 之後睇嘅係:每個維度嘅 exact agreement 有冇跌、bias 有冇偏(Analyzer 系統性
評高定評低)、最大分歧嗰幾條係咩。Skill overlap 同 error overlap 用 Jaccard。

## 呢個標準未解決嘅嘢

- 同一條題目兩個人評,agreement 有幾高?要你同另一個老師各評 30 條先知。標準嘅可靠度
  係由呢個數決定,唔係由文字幾靚決定。
- 某啲題目(尤其 MC)嘅 primary strategy 唔明顯,D 會浮動。
- E 而家係「暴露乜」;學生數據返嚟之後,E 應該同真實錯誤率對返(`error_patterns` 就係
  呢個接口)。
