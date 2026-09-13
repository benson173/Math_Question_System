# Math Question System — 核心定義（Handover / Prompt Spec）

呢份係成個系統嘅定義文件。所有 prompt、schema、database 設計都要對返呢度。
`pdf_ingestion_guide_v1_1.md` 只講地基（PDF → Question Object），呢份講地基之上
要起乜。

---

## 0. 成個系統做乜

唔係將紙版題目變電子咁簡單。三層：

| 層 | 問題 | 靠邊個 |
|---|---|---|
| 1 | 每條題目**要求學生做啲乜** | Analyzer（RPDICE） |
| 2 | 學生**實際錯喺邊** | Student Response + Calibration |
| 3 | 下一題應該**出邊條** | Adaptive System + Question Generator |

第 2 層靠第 1 層準,第 3 層靠頭兩層準。所以 PDF 抽錯,後面全部錯;RPDICE 標錯,
學生分析全部錯。

最終畫面:學生揀咗做邊個課題,系統按佢程度出返相應嘅題目。一個差嘅學生,**唔係**
出晒簡單題俾佢,而係要引導佢行返上去。

---

## 1. RPDICE

RPDICE 係用嚟分析「一條數學題難喺邊」嘅框架。每個字母係一種題目要求學生用到嘅能力。

```text
R = Recognition       睇唔睇得出
P = Procedure         識唔識做步驟
D = Decision          識唔識揀方法
I = Integration       識唔識將幾樣知識連埋
C = Cognitive Depth   推理有幾深
E = Error Exposure    呢題容易暴露咩錯誤
```

### R — Recognition:學生要先「睇得出」啲咩

- 225x² 要睇成 (15x)²
- (2x+1) 要睇成一個整體
- 題目冇講平方差,但要睇得出係平方差
- 圖形入面有隱藏角度關係

### P — Procedure:學生要做咩數學步驟

代入公式、移項、展開括號、因式分解、解方程、化簡分數。

> 步驟多**唔一定** P 高。只係重複計算,未必代表 procedure 深。

### D — Decision:學生要唔要自己揀方法

- 用平方差,定係提出公因式?
- 先化簡,定係先代入?
- 要唔要轉另一個 representation?
- 要點樣 grouping?

> 題目寫咗「Use difference of two squares…」,D 會**降低**,因為方法已經提示咗。
> 所以 method cue 一定要原文保留,Analyzer 先判斷到。

### I — Integration:學生要唔要連接幾個唔同知識點

- 先代入公式,再改 subject
- 先用幾何角度,再解代數方程
- 先用比例,再用百分比
- 先因式分解,再處理 domain restriction

> 同一種技巧重複十次,**唔等於** Integration 高。

### C — Cognitive Depth:推理結構有幾深

直接一步做到 → 要幾步順序做 → 後一步依賴前一步 → 要倒轉諗 → 要分情況 →
要驗證答案 → 要 generalise → 要證明。

> C **唔等於**步驟數。有啲題好短但要逆向思考,C 高;有啲題好長但只係機械計算,C 未必高。

### E — Error Exposure:呢條題容易暴露學生咩錯誤

- 將 a²−b² 錯用成 (a−b)²
- 正負號錯
- 錯誤約分
- 未完成因式分解
- 將 compound expression 拆錯
- 漏 domain restriction

> E 係題目本身「會暴露咩錯誤」,**唔係**話學生一定會錯。

### 正式定義

> RPDICE measures the structural cognitive demand of a question or solution strategy.
> It does not directly measure student ability or empirical item difficulty.
> Empirical difficulty must be calibrated later using student response data.

> RPDICE 量度嘅係「題目本身要求學生做啲咩」,唔係直接量度「學生有幾叻」,亦唔係直接
> 量度「幾多人答啱」。學生實際答對率同真實難度,要等學生作答數據返嚟先可以校準。

### RPDICE 係掛喺 strategy 度,唔係掛喺 question 度

同一條題可以有幾個解法,每個解法嘅 R/P/D/I/C/E 唔同(用平方差 vs 提公因式,D 同 P
唔同)。所以 Analyzer 嘅 output 係 **每個 strategy 一個 RPDICE profile**,題目層面只係
strategies 嘅集合加 summary。

---

## 2. 「深淺」有三種,一定要分開

唔可以將「題目本身有幾深」同「學生實際答得啱唔啱」混埋一齊。

| 名 | 量度乜 | 由邊個決定 | 幾時有 |
|---|---|---|---|
| **Structural Depth** | 題目本身認知結構有幾深 | Analyzer(RPDICE) | 抽完題即刻有 |
| **Empirical Difficulty** | 學生實際答起嚟有幾難 | Student response data | 有學生作答先有 |
| **Calibrated Level** | 結合以上兩樣後嘅 L1–L5 | Calibration system | 有足夠數據先有 |

### Structural Depth(Analyzer)

Analyzer 未睇學生答案之前,只可以分析題目本身:要幾多概念、有冇 hidden structure、有冇
method cue、有冇多個解法、要唔要圖、要唔要先轉 representation、步驟之間有冇依賴、有冇
容易錯嘅位。

Analyzer **唔可以**話「呢題答對率 72%」,因為未有學生數據。

### Empirical Difficulty(Student data)

學生做完題先計得到:答對率、平均分、平均時間、常見錯誤、hint 使用率、first-step
failure、item discrimination、IRT difficulty。

同一條 `Factorise 1 − 225x²`,對熟平方差嘅班答對率可能 90%,對啱啱學因式分解嘅班可能
40%。實際難度受學生群體、課程、教學經驗影響,唔係題目單獨決定。

### Calibrated Level

Structural + Empirical 合埋,放入 L1–L5(或者其他 scale)。**只有** Adaptive System 用
呢個決定下一題。

---

## 3. Analyzer output contract

Analyzer output Structural Analysis,**唔** output empirical difficulty。

```json
{
  "skill_family": "Difference of Two Squares",
  "atomic_skills": [
    "recognise perfect square",
    "recognise difference of two squares",
    "apply DOS identity"
  ],
  "strategies": [
    {
      "strategy_name": "Apply difference of two squares",
      "steps": [
        "Recognise 1 as 1²",
        "Recognise 225x² as (15x)²",
        "Apply a²-b²=(a+b)(a-b)"
      ],
      "rpdice": {
        "R": ["hidden perfect square recognition"],
        "P": ["apply identity"],
        "D": ["method selection if no cue"],
        "I": ["single skill family"],
        "C": ["short sequential reasoning"],
        "E": ["identity confusion", "sign error"]
      }
    }
  ],
  "method_cues": [],
  "representation_features": ["algebraic"],
  "difficulty_drivers": ["recognition"],
  "possible_errors": ["identity confusion", "sign error"],
  "structural_depth_notes": [
    "Difficulty mainly comes from recognition, not procedure."
  ],
  "confidence": 0.8,
  "empirical_difficulty": null
}
```

`empirical_difficulty` 永遠係 `null`,由 Analyzer 寫出嚟。呢個唔係漏,係規則。

---

## 4. Database 一定要分開存

**唔好**得一個欄位叫 `difficulty`。三樣嘢三個地方:

```text
Analyzer output       → structural_difficulty_profile
Student data output   → empirical_item_difficulty
Calibration output    → calibrated_level
```

Question Object 本身(`questions` table)係「印住嘅原文」,**永遠唔改**。所有分析係另外
嘅 table 掛落去,每次分析一個 run,同抽題一樣可以重做、可以比較。

---

## 5. 每一層嘅界線

同 ingestion guide 一樣,每層有嘢**唔可以**做:

| 層 | 可以 | 唔可以 |
|---|---|---|
| Extractor | 抄題、保留原文、標 level | 解題、估深淺、改符號 |
| Analyzer | 由題目本身推 RPDICE、skills、strategies | 睇學生數據、估答對率、改題目 |
| Solver | 用 Analyzer 嘅 strategy 真係解一次 | 標 RPDICE、改題目 |
| Critic | 對 Analyzer 同 Solver 嘅結果挑錯 | 自己重新分析 |
| Validator | 結構檢查(同 extraction validator 一樣角色) | 判斷數學對錯 |
| Student Model | 由作答數據推每個 skill 嘅 mastery | 改 structural profile |
| Calibration | 合 structural + empirical → level | 冇數據就估 |
| Adaptive / Generator | 用 calibrated level 同 skill gap 揀或者生成下一題 | 用未 calibrate 嘅 level |

---

## 6. 呢份 spec 對 Ingestion 嘅要求

因為後面全部靠前面,Extractor 有幾樣嘢**而家唔存,將來補唔返**:

1. **Method cue 原文保留** —— 「Use the difference of two squares」呢句唔可以被「唔好
   改題目」以外嘅任何處理刪走,因為 D 靠佢。
2. **題目要有一個穩定嘅身份** —— 學生作答數據要掛喺題目度,而題目會因為重抽而有新
   run。身份唔可以係 run 嘅 id。
3. **小題之間嘅依賴** —— 1(b) 用 1(a) 嘅答案,係 I 同 C 嘅證據,亦係 Adaptive 唔可以
   單獨出 1(b) 嘅原因。
4. **答案同 marking scheme** —— 有就要存,Solver 同 Critic 要對返。
5. **份卷嘅 metadata** —— 年份、學校、考試類型、Paper 1/2:Empirical difficulty 要按
   群體分,冇 metadata 就分唔到。

呢五樣嘅現況同缺口見 `system_review.md`。
