# -*- coding: utf-8 -*-
"""Build the 15-slide Math Question System deck (書面繁中).

Usage: python3 docs/presentation/build/build_deck.py <student_page.jpg> [out_dir]
No third-party packages: pptx_writer.py writes the OOXML directly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from pptx_writer import Deck, write_previews  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STUDENT_JPG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "student_page.jpg")

INK = "1F3A3D"      # dominant dark teal-slate
MID = "5B7A7D"      # muted text
TINT = "E9F1F0"     # light panel
TINT2 = "F4F8F7"    # lighter panel
LINE = "C9D3D2"     # borders
ACC = "D96C2F"      # accent (burnt orange)
ACC_T = "FBE9DD"    # accent tint
ACC_D = "8A2E0A"    # deep accent (level 3)
WHITE = "FFFFFF"
LV = {0: "D5DEDD", 1: "9FB8B5", 2: ACC, 3: ACC_D}  # level colours
LV_TXT = {0: INK, 1: INK, 2: WHITE, 3: WHITE}

TOTAL = 15
deck = Deck()


# ------------------------------------------------------------------ helpers
def B(t, **o):
    o.setdefault("bold", True)
    return (t, o)


def R(t, **o):
    return (t, o)


def P(*runs, **o):
    d = {"runs": list(runs)}
    d.update(o)
    return d


def bullet(*runs, **o):
    d = {"runs": list(runs), "bullet": True, "space_after": o.pop("space_after", 5)}
    d.update(o)
    return d


def frame(s, n, kicker, title, dark=False):
    fg = WHITE if dark else INK
    mute = "B8CCCA" if dark else MID
    s.text(0.6, 0.32, 9.5, 0.3, [P(R(kicker, size=11, color=mute, bold=True))], margin=0)
    s.text(0.6, 0.6, 11.5, 0.7, [P(R(title, size=28, color=fg, bold=True))], margin=0)
    s.text(12.0, 7.02, 0.8, 0.3, [P(R("%d / %d" % (n, TOTAL), size=10, color=mute), align="r")], margin=0)


def chips(s, x, y, profile, size=0.42, gap=0.08, font=14, labels=None):
    """profile: list of (letter, level). Draws coloured level chips."""
    for i, (L, lv) in enumerate(profile):
        cx = x + i * (size + gap)
        s.rect(cx, y, size, size, fill=LV[lv], radius=0.08)
        s.text(cx, y, size, size, [P(R("%s%d" % (L, lv), size=font, color=LV_TXT[lv], bold=True), align="ctr")],
               anchor="m", margin=0)
        if labels:
            s.text(cx - 0.1, y + size + 0.02, size + 0.2, 0.25, [P(R(labels[i], size=8, color=MID), align="ctr")], margin=0)


def card(s, x, y, w, h, fill=TINT2, line=None, radius=0.1, shadow=False):
    s.rect(x, y, w, h, fill=fill, line=line, radius=radius, shadow=shadow)


def source(s, text):
    s.text(0.6, 7.02, 10.5, 0.3, [P(R(text, size=9, color=MID))], margin=0)


# ================================================================== 1 封面
s = deck.add(INK)
s.text(0.8, 1.2, 8, 0.4, [P(R("MATH QUESTION SYSTEM  ·  2026 年 9 月", size=12, color="B8CCCA", bold=True))], margin=0)
s.text(0.8, 1.7, 9, 1.2, [P(R("數學題目系統", size=48, color=WHITE, bold=True))], margin=0)
s.text(0.8, 2.95, 9.6, 1.4, [
    P(R("由試卷 PDF 到學生手寫頁:", size=22, color=WHITE), space_after=4),
    P(R("把每一條題目變成可分析、可比較、可跟進的數據", size=22, color=WHITE)),
], margin=0)
# RPDICE motif
letters = [("R", "Recognition"), ("P", "Procedure"), ("D", "Decision"), ("I", "Integration"), ("C", "Cognitive depth"), ("E", "Error exposure")]
for i, (L, name) in enumerate(letters):
    cx = 0.8 + i * 1.05
    s.rect(cx, 4.7, 0.8, 0.8, fill=ACC if i % 2 == 0 else "2E5457", radius=0.14)
    s.text(cx, 4.7, 0.8, 0.8, [P(R(L, size=26, color=WHITE, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(cx - 0.15, 5.55, 1.1, 0.3, [P(R(name, size=8, color="B8CCCA"), align="ctr")], margin=0)
s.text(0.8, 6.3, 11, 0.5, [P(R("對象:學校數學老師 × 技術同事    ·    20 分鐘", size=13, color="B8CCCA"))], margin=0)
s.text(8.2, 1.2, 4.4, 0.4, [P(R("2526_2nd_S4MATH2 · Q24 · 一張真手寫頁", size=11, color="B8CCCA"), align="r")], margin=0)

# ================================================================== 2 問題
s = deck.add()
frame(s, 2, "01  問題", "分數告訴你答對了多少,卻不告訴你為什麼")
card(s, 0.6, 1.55, 5.9, 3.55, fill=TINT2)
s.text(0.85, 1.7, 5.4, 0.4, [P(B("現況:一份卷改完之後,留下的是", color=MID, size=13))], margin=0)
s.text(0.85, 2.15, 5.5, 2.9, [
    bullet(B("分數和對錯。"), R("「Q24 ✗」——但錯在認不出、算不對,還是接不上?"), space_after=9),
    bullet(B("靠經驗的難度。"), R("這份卷「難」在哪裡,兩位老師未必同意;兩份卷是否同等難度,憑感覺。"), space_after=9),
    bullet(B("用完即棄的題目。"), R("去年那條「考頂點的好題」,今年靠記憶去找。"), space_after=9),
    bullet(B("看不見的過程。"), R("學生的手寫頁只換來一個 ✓ 或 ✗,走了哪條路、哪一步斷了,沒有記錄。")),
], size=14, line_spacing=1.05)
card(s, 6.85, 1.55, 5.9, 3.55, fill=INK)
s.text(7.1, 1.7, 5.4, 0.4, [P(B("目標:每一條題目、每一張答卷,都變成數據", color="B8CCCA", size=13))], margin=0)
s.text(7.1, 2.15, 5.5, 2.9, [
    bullet(B("題目", color=WHITE), R("→ 六個可觀察的難度維度(RPDICE)+ 用到的技能 + 會暴露的錯誤,全部對回課程指引。", color=WHITE), space_after=9, bullet_color=ACC),
    bullet(B("答卷", color=WHITE), R("→ 走了哪條解題路線、哪些技能有紙上證據、錯在哪一類。", color=WHITE), space_after=9, bullet_color=ACC),
    bullet(B("資料庫", color=WHITE), R("→ 可以搜、可以比、可以累積;下一年出卷不用從零開始。", color=WHITE), space_after=9, bullet_color=ACC),
    bullet(B("分工", color=WHITE), R("→ AI 讀,程式判,人核對。每一步有報告,沒有黑箱。", color=WHITE), bullet_color=ACC),
], size=14, line_spacing=1.05)
s.rect(0.6, 5.45, 12.15, 0.8, fill=ACC_T, radius=0.1)
s.text(0.8, 5.45, 11.8, 0.8, [P(R("系統不是取代老師的判斷,而是把判斷寫下來、對得上、存得住。", size=16, color=ACC_D, bold=True), align="ctr")], anchor="m", margin=0)

# ================================================================== 3 全貌
s = deck.add()
frame(s, 3, "02  全貌", "六層流程:每一層都是「AI 讀 → 程式驗 → 人看報告 → 才入庫」")
layers = [
    ("1", "抽題", "Extractor", "試卷 PDF → 結構化題目\n題號、選項、圖、答案、年級", True),
    ("2", "受控詞彙", "Taxonomy", "556 技能 · 139 錯誤模式\n對回 EDB 課程指引", True),
    ("3", "RPDICE 分析", "Analyzer", "每題六個維度 0–3\n解題策略、技能、錯誤", True),
    ("4", "驗證", "Solver / Critic", "照策略真的解一次\n獨立挑錯,定 status", True),
    ("5", "讀答卷", "Grader", "學生手寫頁 → attempt\n路線、技能證據、錯誤", True),
    ("6", "學生模型", "Student model", "技能掌握度、校準\n適性練習、變體生成", False),
]
bx, by, bw, bh, gap = 0.6, 1.7, 1.9, 2.3, 0.15
for i, (n, zh, en, desc, done) in enumerate(layers):
    x = bx + i * (bw + gap)
    fill = TINT if done else WHITE
    s.rect(x, by, bw, bh, fill=fill, line=None if done else LINE, radius=0.12, shadow=done)
    s.rect(x + 0.15, by + 0.15, 0.42, 0.42, fill=INK if done else LINE, radius=0.21)
    s.text(x + 0.15, by + 0.15, 0.42, 0.42, [P(R(n, size=14, color=WHITE if done else INK, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(x + 0.65, by + 0.13, bw - 0.7, 0.5, [P(B(zh, size=15, color=INK if done else MID)), P(R(en, size=9, color=MID))], margin=0)
    s.text(x + 0.15, by + 0.8, bw - 0.3, 1.5, [P(R(ln, size=11, color=INK if done else MID), space_after=3) for ln in desc.split("\n")], margin=0)
    s.text(x + 0.15, by + bh - 0.45, bw - 0.3, 0.35, [P(R("已建" if done else "未做", size=10, color=ACC if done else MID, bold=True))], margin=0)
    if i < len(layers) - 1:
        s.line(x + bw + 0.02, by + bh / 2, x + bw + gap - 0.02, by + bh / 2, color=MID, w=1.5, arrow=True)
# base layer
s.rect(0.6, 4.3, 12.15, 0.75, fill=INK, radius=0.1)
s.text(0.8, 4.3, 11.8, 0.75, [P(B("共同底層:Supabase  ", color=WHITE, size=13), R("papers · questions · skills · error_patterns · guide_objectives · question_analyses · students · attempts", color="B8CCCA", size=12))], anchor="m", margin=0)
s.text(0.6, 5.3, 12.15, 1.6, [
    bullet(B("AI 只做讀和提議:"), R("抽題、評 RPDICE、解題、挑錯、讀手寫,都是 Gemini。"), space_after=5),
    bullet(B("對錯、對照、一致性由程式判:"), R("答案對不對 marking scheme、字母和技能是否自洽、學生路線對回哪個策略,全部是固定規則,不是模型「覺得」。"), space_after=5),
    bullet(B("每一層出一份人讀的 .md 報告,"), R("有問題不會靜靜入庫;兩次 run 可以逐題對比,量得到模型的噪音。")),
], size=13)

# ================================================================== 4 抽題
s = deck.add()
frame(s, 4, "03  第一層 · 抽題", "一條題目入庫時,是一個有身份、有依賴、有出處的物件")
card(s, 0.6, 1.55, 6.0, 5.25, fill=TINT2)
s.text(0.85, 1.68, 5.6, 0.4, [P(B("一條題目(question object)帶着什麼", size=13, color=MID))], margin=0)
fields = [
    ("question_key", "重抽也不會變的 id(卷 + 題號 hash);所有分析、答卷都掛在它上面"),
    ("text / options", "題目原文、四個選項;圖表文字和圖片兩樣都保留"),
    ("diagram", "由 PDF 裁出的 PNG,Solver 和 Grader 都會看到"),
    ("answer", "由 marking scheme(另一份 PDF)配對合併"),
    ("level / module", "中四、S.4、Form 4 → F4;必修 / M1 / M2"),
    ("depends_on", "小題靠哪條小題:(b) 用 (a) 的結果"),
    ("provenance", "頁碼、run id、model、prompt 版本"),
]
y = 2.15
for k, v in fields:
    s.text(0.85, y, 1.75, 0.6, [P(R(k, size=11.5, color=ACC_D, bold=True, font="Consolas"))], margin=0)
    s.text(2.6, y, 3.85, 0.6, [P(R(v, size=11.5))], margin=0)
    y += 0.63
s.text(6.95, 1.6, 5.8, 0.4, [P(B("三道關卡", size=13, color=MID))], margin=0)
steps = [
    ("驗證器", "題號連續、選項齊全、要圖的題有圖、小題依賴不成環。十幾條固定規則,有問題就列出來,不會靜靜入庫。"),
    (".md 報告", "每份卷一份人讀的報告:每題原文、選項、圖、答案、出了什麼問題。老師核對的是報告,不是 JSON。"),
    ("兩次 run 對比", "同一份卷再抽一次,逐題比:哪題文字變了、哪題選項不同。這是捉到模型「作嘢」的唯一方法。"),
]
y = 2.1
for i, (h, d) in enumerate(steps):
    s.rect(6.95, y, 5.8, 1.35, fill=WHITE, line=LINE, radius=0.1)
    s.rect(7.1, y + 0.18, 0.4, 0.4, fill=ACC, radius=0.2)
    s.text(7.1, y + 0.18, 0.4, 0.4, [P(R(str(i + 1), size=13, color=WHITE, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(7.65, y + 0.15, 4.95, 0.4, [P(B(h, size=13))], margin=0)
    s.text(7.65, y + 0.52, 4.95, 0.8, [P(R(d, size=11.5))], margin=0)
    y += 1.5
s.text(6.95, 6.6, 5.8, 0.4, [P(R("支援:MC · 長題 · 小題 · 圖表 · 另一份 marking scheme PDF · M1 / M2 · 批量處理", size=10.5, color=MID))], margin=0)

# ================================================================== 5 受控詞彙
s = deck.add()
frame(s, 5, "04  第二層 · 受控詞彙", "AI 只可以「揀」,不可以「創」:每一粒技能都對回課程指引")
stats = [("556", "atomic skills\n技能"), ("139", "error patterns\n錯誤模式"), ("328", "學習目標\n由指引 PDF 抽出")]
for i, (n, lab) in enumerate(stats):
    x = 0.6 + i * 2.1
    s.rect(x, 1.6, 1.95, 1.45, fill=TINT, radius=0.1)
    s.text(x, 1.62, 1.95, 0.8, [P(R(n, size=34, color=INK, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(x, 2.38, 1.95, 0.6, [P(R(ln, size=9.5, color=MID), align="ctr") for ln in lab.split("\n")], margin=0)
s.text(6.95, 1.6, 5.8, 1.5, [
    bullet(B("來源:"), R("《數學教育學習領域課程指引》(2017)及 KS3 補充文件,兩份官方 PDF 逐條抽出。"), space_after=5),
    bullet(B("基礎 / 非基礎:"), R("由指引的底線標記讀出;M1、M2 與延伸內容另標。"), space_after=5),
    bullet(B("自動檢查:"), R("id 存在、標記與指引一致、先備技能無循環、每條學習目標至少一粒技能覆蓋。")),
], size=12)
s.text(0.6, 3.3, 12, 0.35, [P(B("一粒技能長這樣(taxonomy/skills.csv)", size=12.5, color=MID))], margin=0)
s.table(0.6, 3.7, [2.55, 3.2, 0.7, 0.75, 2.55, 2.4], [
    ["skill_id", "name_zh", "form", "F / N", "prerequisites", "guide_ref"],
    [{"text": "na.func.vertex-form", "font": "Consolas"}, "以配方法求最大 / 最小值", "F4", "N", "na.quad.complete-square", "CP-2.4"],
    [{"text": "na.func.vertex-formula"}, "以 x = −b/2a 求頂點再代回", "F4", "F", "na.func.quadratic-graph;\nna.formula.substitute", "CP-2.3; CP-2.4"],
    [{"text": "na.quad.solve-factor"}, "以因式分解法解二次方程", "F4", "F", "na.factor.complete", "CP-1.1"],
    [{"text": "ms.mensur.rect-tri-area"}, "長方形、三角形、平行四邊形、梯形面積", "F1", "F", "—", "KS2"],
], row_h=0.42, size=10.5, cell_align=["l", "l", "ctr", "ctr", "l", "l"], fills=[WHITE, TINT2],
    row_heights=[0.4, 0.42, 0.6, 0.42, 0.42])
s.text(0.6, 6.05, 12.15, 0.9, [
    bullet(B("錯誤模式也一樣受控:"), R("每個 error 掛在特定技能下(例:err.quad.vertex-sign 掛 vertex-form / vertex-formula),或標為通用。"), space_after=4),
    bullet(B("模型揀不到合適的,"), R("只能放進 proposed_*,由人決定要不要加入詞彙表——詞彙表只會被人改。")),
], size=12)

# ================================================================== 6 RPDICE 是什麼
s = deck.add()
frame(s, 6, "05  第三層 · RPDICE(一)", "RPDICE:一條題目的六個難度維度")
rows = [["", "維度", "問的是什麼", "低 → 高 的例子"]]
dims = [
    ("R", "Recognition 認", "學生要不要先「看出」什麼?", "9a² − 25 一看是平方差(1)  →  方程其實是 log₂x 的二次式(3)"),
    ("P", "Procedure 做", "程序有多長、多容易累積錯?", "一次代入(1)  →  帶參數的多階段代數(3)"),
    ("D", "Decision 揀", "有沒有方法要揀?題目有沒有提示?", "「利用配方法」(0)  →  要自己設 sub-goal、輔助線(3)"),
    ("I", "Integration 連", "要連起多少個單元的知識?", "同一單元幾粒技能(1)  →  三角 + 坐標幾何(2)"),
    ("C", "Cognitive depth 想", "順推,還是要倒推、分情況、驗證?", "順序步驟(1)  →  「你是否同意」要建構論證(3)"),
    ("E", "Error exposure 錯", "這題容易暴露哪一類錯誤?", "符號小失誤(1)  →  錯了得出「看似合理」的答案(3)"),
]
for L, name, q, ex in dims:
    rows.append([{"text": L, "fill": ACC, "color": WHITE, "bold": True, "align": "ctr", "size": 15}, {"text": name, "bold": True}, q, ex])
s.table(0.6, 1.55, [0.55, 1.9, 2.95, 4.9], rows, row_h=0.56, size=11.5, fills=[WHITE, TINT2], row_heights=[0.4] + [0.58] * 6)
s.rect(10.7, 1.55, 2.05, 3.9, fill=INK, radius=0.1)
s.text(10.85, 1.65, 1.8, 3.75, [
    P(B("三個原則", size=13, color="B8CCCA"), space_after=6),
    P(B("1  不加總。", size=11.5, color=WHITE), space_after=2),
    P(R("每個字母 0–3 級,是序數不是分數。一題 = 一個向量 + 哪幾個字母主導(≥ 2)。", size=10.5, color="DCE8E7"), space_after=8),
    P(B("2  只看題目。", size=11.5, color=WHITE), space_after=2),
    P(R("不看分數、題號位置、學生數據。", size=10.5, color="DCE8E7"), space_after=8),
    P(B("3  可觀察。", size=11.5, color=WHITE), space_after=2),
    P(R("每一級是準則,不是形容詞:兩位老師看同一題應落同一數。", size=10.5, color="DCE8E7")),
], margin=0)
s.rect(0.6, 5.7, 12.15, 0.95, fill=ACC_T, radius=0.1)
s.text(0.8, 5.78, 11.8, 0.85, [
    P(B("寫法:", size=12.5, color=ACC_D), R("  R2 P2 D1 I2 C2 E1  ", size=13, color=ACC_D, bold=True, font="Consolas"), R("— 六個數字並列,不是一個總分。「這題難」在系統裡永遠是「這題難在 R 和 C」。", size=12.5, color=INK), space_after=4),
    P(R("每一級都要附 evidence(從題目引證);Analyzer 的 prompt 由程式裡同一份標準生成,人讀的 rubric 與模型讀的是同一份字。", size=11.5, color=INK)),
], margin=0)

# ================================================================== 7 準則
s = deck.add()
frame(s, 7, "05  第三層 · RPDICE(二)", "0 – 3 級的可觀察準則(摘要)")
crit = [
    ("R", "要處理的對象直接寫明", "一個標準形式,符號本身已提示\n9a² − 25", "要先看出隱藏結構或重新解讀\n225x² 看成 (15x)²;「兩相異交點」即 Δ > 0", "認出來是整題關鍵,而且沒有任何提示\n方程其實是 log₂x 的二次式"),
    ("P", "讀個值、講個事實", "一個短的標準程序\n套一個公式、一次代入", "幾個程序串起,或因分數 / 根式 / 參數 / 配方 / 長除法而變複雜", "長鏈,錯誤會累積\n帶參數多階段代數;要分情況的程序"),
    ("D", "題目寫明方法,或只有一個方法\n「利用配方法」「由此」", "課題的標準方法直接用得", "兩個以上可行方法要揀,或次序有影響\n平方差還是先提公因式;代數還是圖像", "要自己設計策略\n設 sub-goal、輔助線、輔助變量"),
    ("I", "一粒 atomic skill", "同一單元幾粒技能\n因式分解再解方程", "兩個不同單元要連起\n三角 + 坐標幾何;百分數 + 對數", "三個以上單元,或要在 representation 之間轉換\n幾何事實 → 代數條件 → 不等式"),
    ("C", "一步直接", "順序步驟,每步由上一步決定,只向前", "由結果倒推條件、分情況、檢驗 / 剔除候選解、「試解釋」要計數比較", "證明、推廣、評估一個宣稱(建構論證或反例)\n「某人宣稱……你是否同意」"),
    ("E", "沒有常見錯誤模式適用", "一個學生自己會發現的小失誤\n符號、算術", "詞彙表裡某個 misconception 直接被觸發,或兩個以上失誤位\n不等式乘負數不變向;對數底錯", "幾個 misconception 同時,或錯了得出「看似合理」的答案\n三角方程漏第二個解"),
]
rows = [["", {"text": "0", "align": "ctr"}, {"text": "1", "align": "ctr"}, {"text": "2", "align": "ctr"}, {"text": "3", "align": "ctr"}]]
for L, *cells in crit:
    row = [{"text": L, "fill": ACC, "color": WHITE, "bold": True, "align": "ctr", "size": 14}]
    for i, c in enumerate(cells):
        lines = c.split("\n")
        ln = [[(lines[0], {})]]
        if len(lines) > 1:
            ln.append([(lines[1], {"color": MID, "size": 8.5, "italic": True})])
        row.append({"lines": ln, "fill": WHITE if i % 2 == 0 else TINT2})
    rows.append(row)
s.table(0.6, 1.5, [0.5, 2.55, 2.85, 3.3, 2.95], rows, row_h=0.72, size=9.5, row_heights=[0.32] + [0.74] * 6, anchor="t")
s.text(0.6, 6.35, 12.15, 0.6, [
    bullet(B("兩條硬規則:"), R("題目印着「利用二次公式」「由此」「利用 (a)」→ D 最多 1;同一程序重複十次,P 不超過 2,I 也不會因重複而升。"), space_after=3),
    bullet(B("完整標準:"), R("docs/rpdice_rubric.md(人讀)與 app/rpdice.py 的 LEVELS(機器讀)是同一份;改標準只改一處,prompt 自動跟。")),
], size=11)

# ================================================================== 8 Q24 實例
s = deck.add()
frame(s, 8, "05  第三層 · RPDICE(三)", "實例:Q24 為什麼是這份卷最難的一題")
card(s, 0.6, 1.5, 5.6, 5.35, fill=TINT2)
s.text(0.8, 1.6, 5.2, 0.35, [P(B("2526 中四下學期 卷二 · Q24(MC)", size=11.5, color=MID))], margin=0)
s.text(0.8, 1.95, 5.2, 1.0, [P(R("曲線 y = −2x² + 28x + 30 與 x 軸相交於 A、B 兩點,P 為曲線上一點。求 △APB 面積的最大值。", size=13.5, color=INK, bold=True))], margin=0)
s.text(0.8, 2.9, 5.2, 0.5, [P(R("A. 128   B. 896   C. 960   D. 1024(平方單位)    答案 D", size=10.5, color=INK, bold=True), space_after=2), P(R("技能:配方法求極值 · 因式分解解二次方程 · 三角形面積", size=10, color=MID))], margin=0)
s.text(0.8, 3.35, 5.2, 0.35, [P(B("主策略:由截距求底,由頂點求高", size=12))], margin=0)
steps = [
    "−2x² + 28x + 30 = 0 ⇒ x² − 14x − 15 = 0 ⇒ (x − 15)(x + 1) = 0",
    "根 −1、15,底 AB = 15 − (−1) = 16",
    "面積最大 ⇔ P 的 y 坐標最大 ⇔ P 是頂點",
    "頂點 x = −28 / (2 × (−2)) = 7",
    "最大 y = −2(7)² + 28(7) + 30 = 128",
    "最大面積 = ½ × 16 × 128 = 1024",
]
s.text(0.8, 3.75, 5.2, 2.4, [P(R("%d  " % (i + 1), size=12, color=ACC, bold=True), R(t, size=12), space_after=7) for i, t in enumerate(steps)], margin=0)
s.text(0.8, 6.2, 5.2, 0.6, [P(R("會暴露的錯誤:err.factor.cross-wrong-pair(十字相乘配錯因子)", size=10, color=MID))], margin=0)
# right: profile
chips(s, 6.6, 1.55, [("R", 2), ("P", 2), ("D", 1), ("I", 2), ("C", 2), ("E", 1)], size=0.55, gap=0.1, font=16)
s.text(10.6, 1.55, 2.2, 0.55, [P(R("主導:R P I C", size=12, color=ACC_D, bold=True))], anchor="m", margin=0)
ev = [
    ("R2", "要認出「面積最大」等於「P 在頂點」——題目沒有說"),
    ("P2", "解二次方程求底、求頂點高、計面積,三個程序串起"),
    ("D1", "底在 x 軸上是固定的,標準方法直接用得"),
    ("I2", "二次函數(頂點)+ 面積,兩個單元要連起"),
    ("C2", "把幾何最優化翻譯成函數的最大值,不是順推"),
    ("E1", "根之差 15 − (−1) = 16,不是 14:一個自己會發現的失誤"),
]
y = 2.3
for k, v in ev:
    s.text(6.6, y, 0.5, 0.36, [P(R(k, size=11, color=ACC_D, bold=True, font="Consolas"))], margin=0)
    s.text(7.1, y, 5.65, 0.36, [P(R(v, size=11))], margin=0)
    y += 0.38
s.rect(6.6, 4.75, 6.15, 2.1, fill=INK, radius=0.1)
s.text(6.8, 4.85, 5.8, 0.35, [P(B("對照 Q17:f(x) = −9 − 4x,求 f(−1)", size=12, color="B8CCCA"))], margin=0)
chips(s, 6.8, 5.25, [("R", 0), ("P", 1), ("D", 0), ("I", 0), ("C", 0), ("E", 1)], size=0.4, gap=0.08, font=12)
s.text(9.8, 5.25, 2.85, 0.4, [P(R("一步代入,只考負負得正", size=11, color=WHITE))], anchor="m", margin=0)
s.text(6.8, 5.85, 5.8, 0.95, [
    P(R("Q24 的難不在「有伏」(E 只有 1),而在結構深:要認、要連、要想。", size=12, color=WHITE, bold=True), space_after=3),
    P(R("這個分別,總分 1 分 / 0 分記不下來;六個字母記得下來。", size=11, color="DCE8E7")),
], margin=0)

# ================================================================== 9 對老師的意義
s = deck.add()
frame(s, 9, "06  RPDICE 對老師的意義", "由「改對錯」變成「知道教什麼」")
s.text(0.6, 1.5, 6.6, 0.35, [P(B("同一條 Q24 答錯,三個學生,三種補救", size=12.5, color=MID))], margin=0)
s.table(0.6, 1.85, [2.35, 1.0, 3.25], [
    ["學生的表現", "維度", "老師的判斷"],
    ["交白卷,或亂算一堆沒有方向", {"text": "R", "align": "ctr", "bold": True, "color": ACC_D}, "不是不會計,是不知道入手點——教「拆題」,不是再操練公式"],
    ["求了根、求了頂點,卻沒有把兩者接起來", {"text": "I / C", "align": "ctr", "bold": True, "color": ACC_D}, "單元內每樣都會,跨單元不會——出綜合題,不是單元練習"],
    ["答 A(128:把最大高當作面積)或 B(896:底當 14)", {"text": "E", "align": "ctr", "bold": True, "color": ACC_D}, "概念全對,只是不小心——提醒即可,不用重教"],
], row_h=0.8, size=10.5, fills=[WHITE, TINT2], row_heights=[0.36, 0.8, 0.8, 0.8], anchor="ctr")
s.text(0.6, 4.75, 6.6, 0.5, [P(R("沒有 RPDICE,三個都是「Q24 錯,再做十條類似題」。", size=11.5, color=ACC_D, bold=True))], margin=0)
cards = [
    ("出卷:控制「難在哪裡」", "這份中四卷 40 題:沒有一題任何維度到 3 級;一半(20 題)六個維度全部 ≤ 1;只有 4 題有四個維度到 2。這是一份測熟練度的卷——是不是你想要的,一眼可判。想加「要思考」的題,加的是 R2 / D2,不是把數字弄複雜(那只是 P)。"),
    ("教學:逐級搭梯", "同一條題每次只動一個字母(下一頁),學生每一步只面對一個新難處。這是「引導」與「派簡單題」的分別。"),
    ("對學生、對家長:講得出的一句話", "「他不是數學差,是三步以上的題接不起來(C);單步的題全對。」比「62 分」有用,學生也聽得明白該練什麼。"),
    ("題庫:判斷可以累積", "每條分析過的題目帶着六個維度、技能、錯誤存進題庫。下一年出卷、下一班補底,按維度和技能搜,不靠記憶。"),
]
y = 1.5
for h, d in cards:
    s.rect(7.5, y, 5.25, 1.25, fill=TINT2, radius=0.1)
    s.text(7.65, y + 0.08, 5.0, 0.32, [P(B(h, size=11.5, color=INK))], margin=0)
    s.text(7.65, y + 0.38, 5.0, 0.85, [P(R(d, size=9.5))], margin=0)
    y += 1.35
s.rect(0.6, 5.4, 6.6, 1.45, fill=INK, radius=0.1)
s.text(0.8, 5.5, 6.2, 1.3, [
    P(B("一句總結", size=12, color="B8CCCA"), space_after=4),
    P(R("RPDICE 把老師本來就有的直覺——「這題難在要先看出來」——變成可以記錄、可以比較、可以跟進的數據。系統不是取代判斷,是把判斷存下來、放大。", size=12.5, color=WHITE)),
], margin=0)

# ================================================================== 10 同一題改一個維度
s = deck.add()
frame(s, 10, "07  同一題,改一個維度", "Q24 的六個變體:每次只動一個字母")
rows = [["改動", "字母", "為什麼"]]
variants = [
    ("加一句「當 P 為頂點時,△APB 面積最大」", "R  2 → 1", "要認的東西已經寫明,剩下的是程序"),
    ("加「利用配方法求頂點的 y 坐標」", "D  1 → 0", "題目印着方法,D 封頂在 0–1"),
    ("改為 y = −3x² + 7x + 6", "P  2 → 3", "根 −⅔ 與 3、頂點 x = 7/6,分數運算貫穿全題,錯誤會累積"),
    ("改為 y = −2x² − 28x + 30", "E  1 → 2", "根 −15 與 1、頂點 x = −7,三個符號位;直接觸發「頂點符號錯」這個 misconception。答案仍是 1024——錯了也可能湊回對答案"),
    ("加問「並求直線 AP 的方程」", "I  2 → 3", "二次函數 + 二次方程 + 面積 + 坐標幾何,四個單元"),
    ("改為「有人宣稱 △APB 的面積可以超過 1000,你是否同意?試解釋。」", "C  2 → 3", "要評估一個宣稱、建構論證,不再是順推到一個數"),
]
for a, b, c in variants:
    lt = b.split()[0]
    rows.append([a, {"text": b, "align": "ctr", "bold": True, "color": ACC_D, "font": "Consolas"}, c])
s.table(0.6, 1.5, [4.3, 1.2, 6.65], rows, row_h=0.7, size=11, fills=[WHITE, TINT2], row_heights=[0.36, 0.62, 0.62, 0.7, 0.9, 0.62, 0.8], anchor="ctr")
s.rect(0.6, 6.25, 12.15, 0.6, fill=ACC_T, radius=0.1)
s.text(0.8, 6.25, 11.8, 0.6, [P(R("每一步只面對一個新難處——這就是將來「出題器」生成變體的原理:不是隨機改數字,而是指定要動哪一個字母。", size=12.5, color=ACC_D, bold=True))], anchor="m", margin=0)

# ================================================================== 11 Solver + Critic
s = deck.add()
frame(s, 11, "08  第四層 · 驗證", "Analyzer 說的策略,不是說了就算:Solver 真的解,Critic 獨立挑錯")
flow = [
    ("Analyzer", "提出策略", "每題一個主策略,\n列出步驟、技能、六個字母"),
    ("Solver", "照步驟解一次", "只准跟策略的步驟走;\n有圖的題連圖一起送"),
    ("程式", "對答案", "對 marking scheme;\n多個策略互相對;不靠模型自評"),
    ("Critic", "獨立挑錯", "另一個 prompt(可另一 model),\n只挑錯,不重寫"),
]
bx, by, bw, bh, gap = 0.6, 1.55, 2.85, 1.75, 0.25
for i, (who, act, desc) in enumerate(flow):
    x = bx + i * (bw + gap)
    s.rect(x, by, bw, bh, fill=TINT if i != 2 else INK, radius=0.12)
    c1 = INK if i != 2 else WHITE
    c2 = MID if i != 2 else "B8CCCA"
    s.text(x + 0.18, by + 0.12, bw - 0.3, 0.7, [P(B(who, size=15, color=c1)), P(R(act, size=11, color=c2, bold=True))], margin=0)
    s.text(x + 0.18, by + 0.8, bw - 0.3, 0.9, [P(R(ln, size=10.5, color=c1), space_after=2) for ln in desc.split("\n")], margin=0)
    if i < 3:
        s.line(x + bw + 0.03, by + bh / 2, x + bw + gap - 0.03, by + bh / 2, color=MID, w=1.5, arrow=True)
s.text(0.6, 3.5, 6, 0.35, [P(B("每個策略的結果:一個 status", size=12.5, color=MID))], margin=0)
st = [
    ("confirmed", ACC, "解到、答案對、Critic 無 high issue"),
    ("proposed", "9FB8B5", "其餘:待人看"),
    ("unverified", LINE, "要看圖而 Solver 收不到圖——不算錯"),
    ("rejected", ACC_D, "照步驟解不到答案:Analyzer 的策略有問題"),
]
y = 3.9
for name, col, d in st:
    s.rect(0.6, y, 1.5, 0.38, fill=col, radius=0.08)
    s.text(0.6, y, 1.5, 0.38, [P(R(name, size=11, color=WHITE if col in (ACC, ACC_D) else INK, bold=True, font="Consolas"), align="ctr")], anchor="m", margin=0)
    s.text(2.25, y, 4.4, 0.38, [P(R(d, size=11))], anchor="m", margin=0)
    y += 0.5
s.text(0.6, 6.0, 6.2, 0.9, [
    P(R("每個策略有穩定的 strategy_id(由名稱 + 技能生成,重跑不變)、source(analyzer / student / teacher)。學生用另一種方法,就以 source: student 加到那題下面。", size=10.5, color=MID)),
], margin=0)
s.rect(7.0, 3.5, 5.75, 3.0, fill=TINT2, radius=0.1)
s.text(7.2, 3.6, 5.4, 0.35, [P(B("這份卷真跑的結果", size=12.5, color=INK))], margin=0)
s.text(7.2, 3.95, 5.4, 2.85, [
    bullet(R("40 個策略全部解過;Critic 報 5 個 issue。"), space_after=6),
    bullet(B("Q38  LEVEL_OVERRATED:"), R("C 評 2,Critic 指全部是順推步驟,按準則應為 1。"), space_after=6),
    bullet(B("Q9  SKILL_IRRELEVANT:"), R("列了「二次公式」,實際是開方直接解。"), space_after=6),
    bullet(B("Q7、Q20  要看圖:"), R("Solver 只有文字時解不到 → 現在連圖送;仍解不到就標 unverified,不當 rejected。"), space_after=6),
    bullet(B("所有 code 都是固定清單;"), R("清單外的一律 CRITIC_OTHER。程式已報過的,Critic 不重複報。")),
], size=11.5)

# ================================================================== 12 Analyzer 會飄
s = deck.add()
frame(s, 12, "09  誠實的一頁 · 模型會飄", "同一份卷、同一 prompt、同一 model、temperature 0,兩天跑兩次")
tiles = [("28 / 40", "題有東西變了"), ("25 / 240", "個字母移了一級(10%)"), ("D", "飄得最多(7 次)"), ("16 題", "技能列表有變"), ("1 題", "主策略換了(Q18)")]
for i, (n, lab) in enumerate(tiles):
    x = 0.6 + i * 2.47
    s.rect(x, 1.55, 2.3, 1.6, fill=TINT, radius=0.1)
    s.text(x, 1.6, 2.3, 0.9, [P(R(n, size=30, color=INK, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(x, 2.5, 2.3, 0.55, [P(R(lab, size=10.5, color=MID), align="ctr")], margin=0)
s.text(0.6, 3.45, 5.9, 0.35, [P(B("這代表什麼", size=12.5, color=MID))], margin=0)
s.text(0.6, 3.8, 5.9, 3.0, [
    bullet(R("大部分是 1 與 2 之間的邊界題;方向不一致,不是系統性偏高或偏低。"), space_after=6),
    bullet(B("這是噪音下限。"), R("任何 prompt 或標準的改動,要贏過這個數才算改進;否則只是換了一種隨機。"), space_after=6),
    bullet(R("技能列表的變動多數是「多列了一粒先備技能」,已由程式用先備關係吸收,不再報錯。")),
], size=12.5)
s.rect(6.85, 3.45, 5.9, 2.55, fill=INK, radius=0.1)
s.text(7.05, 3.55, 5.5, 0.35, [P(B("我們怎樣對付它", size=12.5, color="B8CCCA"))], margin=0)
s.text(7.05, 3.95, 5.5, 2.85, [
    bullet(B("量:", color=WHITE), R("diff_analyses 一條命令,逐題列出哪個字母、哪粒技能、主策略有沒有換。", color=WHITE), space_after=6, bullet_color=ACC),
    bullet(B("錨:", color=WHITE), R("30 條人手評分的黃金集,每次改 prompt 都對回去(每個維度 exact / ±1 / 偏向)。這 30 條需要老師核對。", color=WHITE), space_after=6, bullet_color=ACC),
    bullet(B("驗:", color=WHITE), R("Solver / Critic 是第二層獨立意見,已捉到 Q38 的 C 評高。", color=WHITE), space_after=6, bullet_color=ACC),
    bullet(B("下一步:", color=WHITE), R("同一題跑 N 次取眾數。等多幾份卷的數據再定 N。", color=WHITE), bullet_color=ACC),
], size=12)
s.text(0.6, 6.3, 12.15, 0.4, [P(R("完整逐題差異:docs/deviations_from_guide.md §46;命令:python3 -m scripts.diff_analyses 2526_2nd_S4MATH2", size=10, color=MID))], margin=0)

# ================================================================== 13 Grader
s = deck.add()
frame(s, 13, "10  第五層 · 讀學生手寫頁", "第一張真答卷:Q24,答對,但不是「全對」")
rid = deck.add_media(s, STUDENT_JPG)
s.image(rid, 0.6, 1.5, 3.55, 3.3, crop=(0.05, 0.06, 0.05, 0.36), line=LINE)
s.text(0.6, 4.85, 3.55, 0.25, [P(R("同一頁底部:圈了 D", size=9, color=MID))], margin=0)
s.image(rid, 0.6, 5.1, 3.55, 1.6, crop=(0.05, 0.72, 0.45, 0.12), line=LINE)
s.text(4.35, 1.5, 3.9, 0.32, [P(B("模型逐行照抄(寫錯也照抄,不准修正)", size=11, color=MID))], margin=0)
trans = [
    "頂點的x坐標",
    "x = 28 / 2(−2) = 7",
    "y = 2(7)² + 28(7) + 30",
    "  = −98 + 196 + 30",
    "  = 128",
    "∵ a = −2 < 0",
    "y_max = 128",
    "最大面積 : [ΔAPB]_max = ½ × 16 × 128",
    "  = 8 × 128",
    "  = 1024",
]
s.rect(4.35, 1.85, 3.9, 2.95, fill=TINT2, radius=0.08)
s.text(4.5, 1.95, 3.7, 3.2, [P(R(t, size=10.5, color=INK, font="Consolas"), space_after=2) for t in trans], margin=0)
s.text(4.35, 4.95, 3.9, 1.9, [
    P(R("兩處抄寫失誤(slip)被保留:漏了 −b/2a 的負號、漏了 −2(7)² 的負號——結果卻是對的。", size=10.5, color=MID), space_after=4),
    P(R("模型不會收到標準答案;否則它會「好心」把 2(7)² 讀成 −2(7)²,slip 就消失了。", size=10.5, color=MID)),
], margin=0)
# findings
s.rect(8.5, 1.5, 4.25, 5.35, fill=INK, radius=0.1)
s.text(8.7, 1.6, 3.9, 0.35, [P(B("程式對回題目的分析", size=12.5, color="B8CCCA"))], margin=0)
find = [
    ("對錯", "答對:D(1024)。對照來源:Solver 確認的答案(這份卷沒有 marking scheme)"),
    ("路線", "對回主策略 4d318b39052c:由頂點求高。學生沒有解方程,底 16 直接寫出"),
    ("技能證據", "✓ 三角形面積\n✓ x = −b/2a 求頂點(改用了公式法,不是配方法)\n✗ 因式分解解二次方程:紙上沒有證據"),
    ("錯誤", "2 個 slip(漏負號,結果正確);沒有 misconception"),
    ("信心", "0.95;不需要人手覆核"),
]
y = 2.0
for k, v in find:
    s.text(8.7, y, 0.95, 0.3, [P(R(k, size=10.5, color=ACC, bold=True))], margin=0)
    lines = v.split("\n")
    s.text(9.65, y, 3.0, 0.3 + 0.28 * len(lines), [P(R(ln, size=10, color=WHITE), space_after=1) for ln in lines], margin=0)
    y += 0.36 + 0.27 * len(lines)
s.text(8.7, 6.05, 3.9, 0.75, [P(R("「答對但不是全對」——MC 的 ✓ 記不到,attempt 記得到。", size=11, color=WHITE, bold=True))], margin=0)

# ================================================================== 14 數據模型與未做
s = deck.add()
frame(s, 14, "11  數據模型與下一步", "已建的六張表,和它們要餵的三件未做的事")
s.text(0.6, 1.5, 6.3, 0.35, [P(B("Supabase 裡的表", size=12.5, color=MID))], margin=0)
tbl = [
    ["表", "一行是", "關鍵欄位"],
    ["papers · questions", "一份卷、一條題目", "question_key(穩定 id)、text、options、diagram、answer、level、depends_on"],
    ["skills · error_patterns · guide_objectives", "一粒技能 / 一個錯誤 / 一條學習目標", "guide_ref、foundation、prerequisites;error 掛哪些 skills"],
    ["question_analyses", "一條題目一次 run", "strategies(jsonb:strategy_id、source、status、六個字母 + evidence)、solutions、critic_issues"],
    ["students · attempts", "一個學生一次作答", "strategy_id、skills_evidenced、skills_not_evidenced、errors_observed、verdict、needs_human"],
]
s.table(0.6, 1.85, [1.9, 1.55, 2.85], tbl, row_h=0.8, size=9.5, fills=[WHITE, TINT2], row_heights=[0.34, 0.72, 0.72, 0.9, 0.85], anchor="ctr")
s.text(0.6, 5.55, 6.3, 1.3, [
    P(R("attempts.strategy_id 指回 question_analyses 裡的策略:學生走的路線與題目的分析是同一套 id。學生用了新方法,就以 source: student 加回那條題目。", size=10.5, color=MID)),
], margin=0)
s.text(7.2, 1.5, 5.5, 0.35, [P(B("未做的三件事(按這個次序)", size=12.5, color=MID))], margin=0)
todo = [
    ("學生模型", "由 attempts 聚合出每個學生每粒技能的掌握度(skill_mastery):證據次數、slip 與 misconception 的比例、最近一次。"),
    ("校準", "RPDICE 是「題目應該有多難」,attempts 是「實際有多難」。兩者對回去:E 對真實錯誤率、C 對答錯的分佈,調準標準。"),
    ("適性練習 / 出題器", "按第 10 頁的原理生成變體:指定要動哪個字母,對着哪粒技能,給哪個學生。"),
]
y = 1.9
for i, (h, d) in enumerate(todo):
    s.rect(7.2, y, 5.55, 1.15, fill=WHITE, line=LINE, radius=0.1)
    s.rect(7.35, y + 0.15, 0.4, 0.4, fill=LINE, radius=0.2)
    s.text(7.35, y + 0.15, 0.4, 0.4, [P(R(str(i + 1), size=13, color=INK, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(7.9, y + 0.12, 4.7, 0.35, [P(B(h, size=12))], margin=0)
    s.text(7.9, y + 0.45, 4.7, 0.7, [P(R(d, size=10))], margin=0)
    y += 1.27
s.rect(7.2, 5.75, 5.55, 1.1, fill=ACC_T, radius=0.1)
s.text(7.35, 5.82, 5.3, 1.0, [
    P(B("需要老師的兩件事", size=11.5, color=ACC_D), space_after=3),
    P(R("① 核對 30 條黃金集的 RPDICE 評分(標準的可靠度由此決定)", size=10.5, color=INK), space_after=2),
    P(R("② 更多學生手寫頁:答錯的、用另一路線的、字跡差的", size=10.5, color=INK)),
], margin=0)

# ================================================================== 15 收尾
s = deck.add(INK)
s.text(0.8, 0.9, 11, 0.4, [P(R("收尾", size=12, color="B8CCCA", bold=True))], margin=0)
s.text(0.8, 1.3, 11.5, 1.0, [P(R("三句話", size=40, color=WHITE, bold=True))], margin=0)
msgs = [
    ("題目變成數據。", "六個維度、技能、錯誤,全部對回課程指引;不是一個總分,是一個可以搜、可以比的向量。"),
    ("AI 讀,程式判,人核對。", "每一層有報告、有驗證、有噪音的量度;不合格的不會靜靜入庫。"),
    ("下一步從學生的手寫頁開始。", "第一張真卷已經證明可行;要走到學生模型,需要你們的卷、你們核對的 30 條黃金集。"),
]
y = 2.55
for i, (h, d) in enumerate(msgs):
    s.rect(0.8, y, 0.55, 0.55, fill=ACC, radius=0.12)
    s.text(0.8, y, 0.55, 0.55, [P(R(str(i + 1), size=18, color=WHITE, bold=True), align="ctr")], anchor="m", margin=0)
    s.text(1.55, y - 0.05, 10.8, 0.45, [P(B(h, size=20, color=WHITE))], margin=0)
    s.text(1.55, y + 0.42, 10.8, 0.6, [P(R(d, size=13, color="DCE8E7"))], margin=0)
    y += 1.3
s.text(0.8, 6.5, 11.5, 0.5, [P(R("Q & A", size=16, color="B8CCCA", bold=True))], margin=0)
for i, (L, _) in enumerate(letters):
    cx = 9.4 + i * 0.55
    s.rect(cx, 6.45, 0.45, 0.45, fill=ACC if i % 2 == 0 else "2E5457", radius=0.09)
    s.text(cx, 6.45, 0.45, 0.45, [P(R(L, size=13, color=WHITE, bold=True), align="ctr")], anchor="m", margin=0)

# ------------------------------------------------------------------ output
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..")
os.makedirs(OUT, exist_ok=True)
pptx_path = os.path.join(OUT, "Math_Question_System.pptx")
deck.save(pptx_path, title="數學題目系統")
write_previews(deck, os.path.join(OUT, "preview"))  # HTML previews for screenshot QA
print("wrote", pptx_path, len(deck.slides), "slides")
