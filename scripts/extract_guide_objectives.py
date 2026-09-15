"""Pull the Learning Objectives out of the two EDB PDFs into taxonomy/guide_objectives.csv.

    python3 -m scripts.extract_guide_objectives

Reads docs/CA_2017_e.pdf (C&A Guide S4-6, 2017: Compulsory Part, M1, M2) and
docs/jsmc2017_e.pdf (KS3 Supplement, 2017). Pure standard library: the PDFs
are Word exports (FlateDecode, WinAnsi and Identity-H fonts with ToUnicode
maps), so a small extractor is enough. Non-foundation objectives are the
underlined ones; Word draws an underline as a 0.6 pt filled rectangle just
below the baseline, while table borders are 0.48 pt, which is how the two are
told apart. Text that the PDFs draw as images (most formulas) is not seen.

The objective tables are read by column position: unit | objective | time |
remarks. Page numbers, table headers and the notes above a table are dropped.
"""

from __future__ import annotations

import csv
from pathlib import Path
import re
import zlib

from app.paths import PROJECT_ROOT


GUIDE_PDF = PROJECT_ROOT / "docs" / "CA_2017_e.pdf"
KS3_PDF = PROJECT_ROOT / "docs" / "jsmc2017_e.pdf"
OUT_CSV = PROJECT_ROOT / "taxonomy" / "guide_objectives.csv"

# PDF pages (1-based) holding each objective table
PAGES = {"CP": (GUIDE_PDF, range(25, 48)), "M1": (GUIDE_PDF, range(53, 68)),
         "M2": (GUIDE_PDF, range(68, 86)), "KS3": (KS3_PDF, range(6, 47))}

def load(path):
    data = open(path, "rb").read()
    objs = {}
    # direct objects
    for m in re.finditer(rb"(?<![0-9])(\d+) 0 obj\s*(.*?)\s*endobj", data, re.S):
        objs[int(m.group(1))] = m.group(2)
    # object streams
    for num, body in list(objs.items()):
        if b"/Type/ObjStm" in body.replace(b" ", b""):
            st = stream(body)
            if st is None: continue
            n = int(re.search(rb"/N\s+(\d+)", body).group(1))
            first = int(re.search(rb"/First\s+(\d+)", body).group(1))
            head = st[:first].split()
            for i in range(n):
                onum, off = int(head[2*i]), int(head[2*i+1])
                end = int(head[2*i+3]) if i+1 < n else len(st) - first
                objs[onum] = st[first+off:first+end]
    return objs

def stream(body):
    m = re.search(rb"stream\r?\n", body)
    if not m: return None
    raw = body[m.end():body.rfind(b"endstream")]
    try: return zlib.decompress(raw)
    except zlib.error:
        try: return zlib.decompressobj().decompress(raw)
        except zlib.error: return None

def balanced(body, start):
    """The dict/array starting at body[start] ('<<' or '['), brackets balanced."""
    opener = body[start:start+2] if body[start:start+2] == b"<<" else body[start:start+1]
    depth = 0; i = start
    while i < len(body):
        if body.startswith(b"<<", i): depth += 1; i += 2; continue
        if body.startswith(b">>", i): depth -= 1; i += 2
        elif body[i:i+1] == b"[": depth += 1; i += 1
        elif body[i:i+1] == b"]": depth -= 1; i += 1
        elif body[i:i+1] == b"(":          # skip strings
            j = i + 1
            while j < len(body) and body[j:j+1] != b")":
                j += 2 if body[j:j+1] == b"\\" else 1
            i = j + 1; continue
        else: i += 1; continue
        if depth == 0: return body[start:i]
    return body[start:]

def ref(objs, body, key):
    m = re.search(rb"/" + key + rb"\s*(\d+) 0 R", body)
    if m: return objs.get(int(m.group(1)))
    m = re.search(rb"/" + key + rb"\s*(?=<<|\[)", body)
    return balanced(body, m.end()) if m else None

def cmap_of(objs, font):
    tu = ref(objs, font, b"ToUnicode")
    table = {}
    if tu is None: return table
    st = stream(tu) or b""
    for m in re.finditer(rb"beginbfchar(.*?)endbfchar", st, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            table[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "replace")
    for m in re.finditer(rb"beginbfrange(.*?)endbfrange", st, re.S):
        for a, b, c in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            lo, hi, base = int(a, 16), int(b, 16), int(c, 16)
            for k in range(lo, hi + 1):
                table[k] = chr(base + k - lo)
    return table

def fonts_of(objs, page):
    res = ref(objs, page, b"Resources") or b""
    fd = ref(objs, res, b"Font") or b""
    fonts = {}
    for name, num in re.findall(rb"/(\w+)\s+(\d+) 0 R", fd):
        f = objs.get(int(num), b"")
        two = b"/Type0" in f
        fonts[name] = (two, cmap_of(objs, f))
    return fonts

def pages_of(objs):
    for num, body in objs.items():
        if re.search(rb"/Type\s*/Page(?![s])", body):
            yield num, body

def decode_str(s, font):
    two, cmap = font
    out = []
    if two:
        for i in range(0, len(s) - 1, 2):
            code = s[i] << 8 | s[i+1]
            out.append(cmap.get(code, ""))
    else:
        for ch in s:
            out.append(cmap.get(ch) or bytes([ch]).decode("cp1252", "replace"))
    return "".join(out)

def unescape(s):
    return re.sub(rb"\\([nrtbf()\\]|[0-7]{1,3})", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}.get(m.group(1), bytes([int(m.group(1), 8)]) if m.group(1)[:1] in b"01234567" else m.group(1)), s)

PIECES = None
TOK = re.compile(rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]<>(]+|[-+.\d]+|[A-Za-z*'\"]+")

def page_text(objs, page):
    fonts = fonts_of(objs, page)
    cont = ref(objs, page, b"Contents")
    if cont is None: return ""
    if cont.startswith(b"["):
        parts = [stream(objs[int(n)]) or b"" for n in re.findall(rb"(\d+) 0 R", cont)]
        st = b"\n".join(parts)
    else:
        st = stream(cont) or b""
    lines = {}   # y -> list of (x, text)
    rules = []   # (x, y, w) thin filled rectangles = underlines
    pieces = []  # (x, y, text, width) for underline matching
    font = (False, {}); size = 1; x = y = 0.0; stack = []
    tm = [1, 0, 0, 1, 0, 0]; tlm = tm[:]
    def add(text):
        px, py = tm[4], tm[5]
        entry = [px, text, size]
        lines.setdefault(round(py), []).append(entry)
        pieces.append((px, py, entry))
    for m in TOK.finditer(st):
        t = m.group(0)
        if t[:1] in b"(<[]" or t[:1] == b"/" or t[:1] in b"-+.0123456789":
            stack.append(t); continue
        op = t
        if op == b"Tf":
            font = fonts.get(stack[-2][1:], (False, {})); size = float(stack[-1])
        elif op == b"Tm":
            tm = [float(v) for v in stack[-6:]]; tlm = tm[:]
        elif op == b"Td" or op == b"TD":
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3], tlm[4] + float(stack[-2]) * tlm[0], tlm[5] + float(stack[-1]) * tlm[3]]; tm = tlm[:]
        elif op == b"re":
            try:
                rx, ry, rw, rh = [float(v) for v in stack[-4:]]
                if 0.55 < abs(rh) < 2.5 and rw > 2: rules.append((rx, ry, rw))   # 0.48 = table border, 0.6+ = underline
            except ValueError: pass
        elif op == b"BT":
            tm = [1, 0, 0, 1, 0, 0]; tlm = tm[:]
        elif op in (b"Tj", b"'", b'"'):
            s = stack[-1]
            text = decode_str(unescape(s[1:-1]) if s[:1] == b"(" else bytes.fromhex(s[1:-1].decode().replace(" ", "")), font)
            add(text); tm[4] += len(text) * size * 0.5
        elif op == b"TJ":
            # tokens between [ and ]
            i = len(stack) - 1
            while i >= 0 and stack[i] != b"[": i -= 1
            buf = []
            for tok in stack[i+1:]:
                if tok[:1] == b"(":
                    buf.append(decode_str(unescape(tok[1:-1]), font))
                elif tok[:1] == b"<":
                    buf.append(decode_str(bytes.fromhex(tok[1:-1].decode().replace(" ", "")), font))
                else:
                    try:
                        if float(tok) < -200: buf.append(" ")
                    except ValueError: pass
            text = "".join(buf)
            add(text); tm[4] += len(text) * size * 0.5
        stack = []
    # mark a text piece as underlined when a rule sits just under its baseline
    for px, py, entry in pieces:
        width = len(entry[1]) * entry[2] * 0.5
        for rx, ry, rw in rules:
            if -4.5 <= ry - py <= 0.5 and rx < px + width and rx + rw > px + 1:
                entry[1] = "_" + entry[1] + "_" if entry[1].strip() else entry[1]
                break
    if PIECES is not None:
        PIECES.append([(round(px, 1), round(py, 1), e[1], e[2]) for px, py, e in pieces if e[1].strip()])
    out = []
    for yk in sorted(lines, reverse=True):
        row = sorted(lines[yk], key=lambda e: e[0])
        s = ""; last = None
        for px, text, size in row:
            if last is not None and px - last > 30 and not s.endswith(" "): s += "  "
            s += text; last = px + len(text) * 5
        out.append(s.rstrip())
    return "\n".join(out)

def extract(path):
    """Positioned text pieces of every page, in page order."""
    global PIECES
    objs = load(path)
    order = []
    for num, body in objs.items():
        if re.search(rb"/Type\s*/Pages", body) and b"/Parent" not in body:
            def walk(n):
                b = objs[n]
                if re.search(rb"/Type\s*/Page(?![s])", b):
                    order.append(n)
                    return
                for k in re.findall(rb"(\d+) 0 R", ref(objs, b, b"Kids") or b""):
                    walk(int(k))
            walk(num)
    if not order:
        order = [n for n, _ in pages_of(objs)]
    PIECES = []
    for n in order:
        page_text(objs, objs[n])
    return PIECES

# --- the objective tables ------------------------------------------------------

def width(text, size):
    w = 0.0
    for ch in text:
        if ch in "iljtfrI.,;:'|!()[] ": w += 0.28
        elif ch.isupper() or ch in "mw": w += 0.72
        else: w += 0.5
    return w * size


def join(pieces):
    """Pieces of one line, a space only where there is a visible gap."""
    s = ""; end = None
    for x, t, size in sorted(pieces):
        if end is not None and x - end > size * 0.22 and not s.endswith(" ") and not t.startswith(" "):
            s += " "
        s += t; end = x + width(t, size)
    return re.sub(r"\s+", " ", s).strip()


def rows_of(pages, page_range, part):
    out = []
    unit_no = strand = ""; name_no = None; pending = None
    names, strand_of = {}, {}
    current = None
    from collections import Counter
    # column positions: objective numbers give the objective column, headers the rest
    xs = Counter(x for pno in page_range for x, y, t, sz in pages[pno - 1] if re.match(r"^\d+\.\d+$", t))
    xo = xs.most_common(1)[0][0]
    xt = Counter(x for pno in page_range for x, y, t, sz in pages[pno - 1] if t == "Time").most_common(1)[0][0]
    xr = Counter(x for pno in page_range for x, y, t, sz in pages[pno - 1] if t == "Remarks").most_common(1)[0][0]
    for pno in page_range:
        pieces = [(x, y, t, sz) for x, y, t, sz in pages[pno - 1]
                  if not re.match(r"^\s*(\d{1,3})\1\s*$", t)              # page number, printed twice
                  and not (y < 110 and re.match(r"^[\d\s]+$", t))]      # page-number footer
        header_y = max([y for x, y, t, sz in pieces if t == "Learning Unit"] or [10**6])
        lines = {}
        for x, y, t, sz in pieces:
            if y < header_y:
                lines.setdefault(round(y), []).append((x, t, sz))
        for yk in sorted(lines, reverse=True):
            row = lines[yk]
            unit_txt = join([p for p in row if p[0] < xo - 2])
            obj_txt = join([p for p in row if xo - 2 <= p[0] < xt - 2])
            time_txt = join([p for p in row if xt - 2 <= p[0] < xr - 2])
            rem_txt = join([p for p in row if p[0] >= xr - 2])
            if unit_txt.startswith("Learning Unit") or obj_txt.startswith("Learning Objective"):
                continue
            unit_txt = re.sub(r"^\d+\s+", "", unit_txt)                  # stray page number
            m = re.match(r"^(\d+)\s*\.\s*(\S.*)$", unit_txt)
            if m:
                name_no = m.group(1); names[name_no] = m.group(2).strip()
                strand_of[name_no] = strand
            elif unit_txt in ("Number and Algebra Strand", "Measures, Shape and Space Strand",
                              "Data Handling Strand", "Further Learning Unit",
                              "Foundation Knowledge", "Calculus", "Statistics", "Algebra"):
                strand = unit_txt
            elif unit_txt and name_no and not re.match(r"^\d+$", unit_txt):
                names[name_no] = (names[name_no] + " " + unit_txt).strip()
            m = re.match(r"^(\d+\.\d+)\s+(.*)$", obj_txt)
            unit_line = re.match(r"^(\d+)\s*\.\s*(\S.*)$", unit_txt)
            if unit_line:
                pending = unit_line.group(1)
            if m:
                unit_no = m.group(1).split(".")[0]; pending = None
                current = dict(part=part, strand="", unit_no=unit_no, unit="",
                               obj=m.group(1), text=m.group(2), nf="N" if "_" in m.group(2) else "",
                               time=time_txt, remarks=rem_txt, page=pno)
                out.append(current)
            elif pending and obj_txt and not (current and current["unit_no"] == pending):
                # Further Learning Unit rows carry one unnumbered objective; kept
                # only if the unit turns out to have no numbered ones
                unit_no = pending; pending = None
                current = dict(part=part, strand="", unit_no=unit_no, unit="",
                               obj=unit_no, text=obj_txt, nf="", time=time_txt, remarks=rem_txt, page=pno)
                out.append(current)
            elif obj_txt and current is not None:
                if obj_txt.lower().startswith("note:") or obj_txt.startswith("Note"):
                    current["remarks"] += " [" + obj_txt + "]"
                else:
                    current["text"] += " " + obj_txt
                    if "_" in obj_txt: current["nf"] = "N"
                if rem_txt: current["remarks"] += " " + rem_txt
            elif rem_txt and current is not None:
                current["remarks"] += " " + rem_txt
            if time_txt and current is not None and not current["time"]:
                current["time"] = time_txt
    numbered = {r["unit_no"] for r in out if "." in r["obj"]}
    out = [r for r in out if "." in r["obj"] or r["unit_no"] not in numbered]
    names = {k: v.replace("Organisationof", "Organisation of") for k, v in names.items()}
    for r in out:
        r["unit"] = names.get(r["unit_no"], "?")
        r["strand"] = strand_of.get(r["unit_no"], "")
    for r in out:
        r["text"] = re.split(r"\s*Subtotal in hours|\s*Grand total", r["text"])[0]
        r["remarks"] = re.split(r"\s*Subtotal in hours|\s*Grand total|\s*Total lesson time", r["remarks"])[0]
        if r["nf"] == "" and r["text"].lstrip("_").startswith("**"):
            r["nf"] = "E"                     # ** = Enrichment Topic (KS3 supplement)
        r["text"] = r["text"].replace("**", "")
        r["text"] = re.sub(r"\s+", " ", r["text"].replace("_", "")).strip()
        r["remarks"] = re.sub(r"\s+", " ", r["remarks"].replace("_", "")).strip()
        r["unit"] = re.sub(r"\s+", " ", r["unit"]).strip()
    return out



HEADER = """# Learning Objectives of the EDB Mathematics C&A Guide (S4-6, 2017): Compulsory Part
# (CP), Module 1 (M1), Module 2 (M2), and of the Supplement on the learning content
# of junior secondary Mathematics (2017; KS3). Extracted from docs/CA_2017_e.pdf and
# docs/jsmc2017_e.pdf by scripts/extract_guide_objectives.py; formulas the PDFs draw
# as images are missing from text and remarks. obj = objective number (a Further
# Learning Unit has one unnumbered objective, given its unit number); nf = blank for
# a Foundation Topic, N = Non-foundation (underlined in the Guide), E = Enrichment
# (** in the KS3 Supplement); time = suggested hours for the unit; page = PDF page.
"""


def main(argv: list[str] | None = None) -> int:
    pieces_by_pdf: dict[Path, list] = {}
    for pdf in {p for p, _ in PAGES.values()}:
        if not pdf.exists():
            print(f"missing {pdf}")
            return 1
        pieces_by_pdf[pdf] = extract(str(pdf))
    rows = []
    for part in ("CP", "M1", "M2", "KS3"):
        pdf, pages = PAGES[part]
        rows.extend(rows_of(pieces_by_pdf[pdf], pages, part))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        fh.write(HEADER)
        writer = csv.DictWriter(fh, fieldnames=["part", "strand", "unit_no", "unit", "obj", "nf",
                                                "time", "text", "remarks", "page"])
        writer.writeheader()
        writer.writerows(rows)
    by_part = {part: sum(1 for r in rows if r["part"] == part) for part in PAGES}
    print(f"{len(rows)} objectives -> {OUT_CSV} {by_part}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
