"""Minimal PPTX writer (no third-party packages): rectangles, text boxes, images, tables."""
from __future__ import annotations

import zipfile
from xml.sax.saxutils import escape

EMU = 914400
SLIDE_W, SLIDE_H = 13.333, 7.5

LATIN = "Calibri"
EA = "Microsoft JhengHei"


def emu(v):
    return int(round(v * EMU))


class Slide:
    def __init__(self, bg="FFFFFF"):
        self.bg = bg
        self.shapes = []
        self.rels = []  # (rId, type, target)
        self._id = 2
        self.ops = []
        self.media_paths = {}

    def nid(self):
        self._id += 1
        return self._id

    # ---- shapes -------------------------------------------------------
    def rect(self, x, y, w, h, fill=None, line=None, line_w=0.75, radius=None, prst=None, shadow=False):
        self.ops.append(("rect", dict(x=x, y=y, w=w, h=h, fill=fill, line=line, line_w=line_w, radius=radius, prst=prst, shadow=shadow)))
        prst = prst or ("roundRect" if radius is not None else "rect")
        adj = ""
        if radius is not None and prst == "roundRect":
            # adj is 1/100000 of min(w,h)... roughly: 50000 = fully round. radius in inches
            a = int(min(50000, radius / min(w, h) * 100000))
            adj = '<a:avLst><a:gd name="adj" fmla="val %d"/></a:avLst>' % a
        fill_xml = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % fill if fill else "<a:noFill/>"
        if line:
            line_xml = '<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln>' % (int(line_w * 12700), line)
        else:
            line_xml = "<a:ln><a:noFill/></a:ln>"
        eff = ""
        if shadow:
            eff = ('<a:effectLst><a:outerShdw blurRad="50800" dist="25400" dir="5400000" algn="t" rotWithShape="0">'
                   '<a:srgbClr val="000000"><a:alpha val="18000"/></a:srgbClr></a:outerShdw></a:effectLst>')
        i = self.nid()
        self.shapes.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Shape %d"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="%s">%s</a:prstGeom>%s%s%s</p:spPr>'
            '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="zh-TW"/></a:p></p:txBody></p:sp>'
            % (i, i, emu(x), emu(y), emu(w), emu(h), prst, adj, fill_xml, line_xml, eff)
        )

    def text(self, x, y, w, h, paras, size=14, color="1F3A3D", bold=False, align="l", anchor="t",
             margin=0.05, font=None, line_spacing=None, autofit=False, wrap=True):
        """paras: list of paragraphs. A paragraph is a str, or a dict with keys:
        runs: list of (text, opts) or str; align; bullet (bool or char); space_after (pt); level; size; color; bold
        """
        if isinstance(paras, str):
            paras = [paras]
        self.ops.append(("text", dict(x=x, y=y, w=w, h=h, paras=paras, size=size, color=color, bold=bold, align=align, anchor=anchor, margin=margin, font=font, line_spacing=line_spacing, wrap=wrap)))
        body = []
        for p in paras:
            if isinstance(p, str):
                p = {"runs": [p]}
            al = p.get("align", align)
            ppr = ['<a:pPr algn="%s"' % al]
            lvl = p.get("level", 0)
            if lvl:
                ppr.append(' lvl="%d"' % lvl)
            bullet = p.get("bullet")
            indent = p.get("indent")
            if bullet:
                ind = indent if indent is not None else 0.22
                ppr.append(' marL="%d" indent="-%d"' % (emu(ind * (lvl + 1)), emu(ind)))
            elif indent:
                ppr.append(' marL="%d" indent="0"' % emu(indent))
            ppr.append(">")
            ls = p.get("line_spacing", line_spacing)
            if ls:
                ppr.append('<a:lnSpc><a:spcPct val="%d"/></a:lnSpc>' % int(ls * 100000))
            sb = p.get("space_before")
            if sb:
                ppr.append('<a:spcBef><a:spcPts val="%d"/></a:spcBef>' % int(sb * 100))
            sa = p.get("space_after")
            if sa:
                ppr.append('<a:spcAft><a:spcPts val="%d"/></a:spcAft>' % int(sa * 100))
            if bullet:
                ch = bullet if isinstance(bullet, str) else "•"
                bc = p.get("bullet_color")
                if bc:
                    ppr.append('<a:buClr><a:srgbClr val="%s"/></a:buClr>' % bc)
                ppr.append('<a:buFont typeface="Arial"/><a:buChar char="%s"/>' % escape(ch))
            else:
                ppr.append("<a:buNone/>")
            ppr.append("</a:pPr>")
            runs = []
            for r in p.get("runs", []):
                if isinstance(r, str):
                    r = (r, {})
                t, o = r
                sz = o.get("size", p.get("size", size))
                col = o.get("color", p.get("color", color))
                b = o.get("bold", p.get("bold", bold))
                it = o.get("italic", False)
                fn = o.get("font", font)
                lat = fn or LATIN
                ea = fn or EA
                rpr = '<a:rPr lang="zh-TW" altLang="en-US" sz="%d" b="%d" i="%d" dirty="0">' % (int(sz * 100), 1 if b else 0, 1 if it else 0)
                rpr += '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % col
                rpr += '<a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface="%s"/></a:rPr>' % (lat, ea, ea)
                runs.append('<a:r>%s<a:t>%s</a:t></a:r>' % (rpr, escape(t)))
            if not runs:
                runs.append('<a:endParaRPr lang="zh-TW" sz="%d"/>' % int(p.get("size", size) * 100))
            body.append("<a:p>%s%s</a:p>" % ("".join(ppr), "".join(runs)))
        anchor_map = {"t": "t", "m": "ctr", "b": "b"}
        m = emu(margin)
        bodypr = '<a:bodyPr wrap="%s" lIns="%d" tIns="%d" rIns="%d" bIns="%d" anchor="%s" rtlCol="0">%s</a:bodyPr>' % (
            "square" if wrap else "none", m, m, m, m, anchor_map[anchor],
            '<a:normAutofit/>' if autofit else '')
        i = self.nid()
        self.shapes.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="TextBox %d"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            '<p:txBody>%s<a:lstStyle/>%s</p:txBody></p:sp>'
            % (i, i, emu(x), emu(y), emu(w), emu(h), bodypr, "".join(body))
        )

    def image(self, rid, x, y, w, h, crop=None, line=None):
        """crop = (l, t, r, b) fractions 0-1 to crop off each side."""
        self.ops.append(("image", dict(rid=rid, x=x, y=y, w=w, h=h, crop=crop, line=line)))
        src = ""
        if crop:
            src = '<a:srcRect l="%d" t="%d" r="%d" b="%d"/>' % tuple(int(c * 100000) for c in crop)
        ln = ('<a:ln w="9525"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln>' % line) if line else ""
        i = self.nid()
        self.shapes.append(
            '<p:pic><p:nvPicPr><p:cNvPr id="%d" name="Picture %d"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            '<p:blipFill><a:blip r:embed="%s"/>%s<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>%s</p:spPr></p:pic>'
            % (i, i, rid, src, emu(x), emu(y), emu(w), emu(h), ln)
        )

    def table(self, x, y, col_w, rows, row_h=0.4, size=12, header=True, head_fill="1F3A3D", head_color="FFFFFF",
              fills=None, border="C9D3D2", color="1F3A3D", first_col_bold=False, cell_align=None, anchor="ctr",
              margin=0.06, row_heights=None):
        """rows: list of rows; each cell is str or dict(runs/text, fill, color, bold, align, size)."""
        self.ops.append(("table", dict(x=x, y=y, col_w=col_w, rows=rows, row_h=row_h, size=size, header=header, head_fill=head_fill, head_color=head_color, fills=fills, border=border, color=color, first_col_bold=first_col_bold, cell_align=cell_align, margin=margin, row_heights=row_heights)))
        i = self.nid()
        total_w = sum(col_w)
        grid = "".join('<a:gridCol w="%d"/>' % emu(w) for w in col_w)
        trs = []
        for ri, row in enumerate(rows):
            rh = (row_heights[ri] if row_heights else row_h)
            tcs = []
            for ci, cell in enumerate(row):
                if not isinstance(cell, dict):
                    cell = {"text": cell}
                is_head = header and ri == 0
                fill = cell.get("fill") or (head_fill if is_head else (fills[ri % len(fills)] if fills else "FFFFFF"))
                col = cell.get("color") or (head_color if is_head else color)
                b = cell.get("bold", is_head or (first_col_bold and ci == 0))
                sz = cell.get("size", size)
                al = cell.get("align") or (cell_align[ci] if cell_align else "l")
                runs = cell.get("runs")
                paras_xml = []
                lines = cell.get("lines")
                if lines is None:
                    lines = [runs if runs else cell.get("text", "")]
                for ln in lines:
                    if isinstance(ln, str):
                        ln = [(ln, {})]
                    rx = []
                    for r in ln:
                        if isinstance(r, str):
                            r = (r, {})
                        t, o = r
                        rsz = o.get("size", sz); rcol = o.get("color", col); rb = o.get("bold", b)
                        fn = o.get("font") or cell.get("font")
                        rx.append('<a:r><a:rPr lang="zh-TW" altLang="en-US" sz="%d" b="%d" i="%d" dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                                  '<a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface="%s"/></a:rPr><a:t>%s</a:t></a:r>'
                                  % (int(rsz * 100), 1 if rb else 0, 1 if o.get("italic") else 0, rcol, fn or LATIN, fn or EA, fn or EA, escape(t)))
                    if not rx:
                        rx.append('<a:endParaRPr lang="zh-TW" sz="%d"/>' % int(sz * 100))
                    paras_xml.append('<a:p><a:pPr algn="%s"/>%s</a:p>' % (al, "".join(rx)))
                m = emu(margin)
                bord = ""
                for side in ("lnL", "lnR", "lnT", "lnB"):
                    bord += '<a:%s w="6350"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:%s>' % (side, border, side)
                tcpr = '<a:tcPr marL="%d" marR="%d" marT="%d" marB="%d" anchor="%s">%s<a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:tcPr>' % (
                    m, m, emu(0.04), emu(0.04), anchor, bord, fill)
                tcs.append('<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>%s</a:txBody>%s</a:tc>' % ("".join(paras_xml), tcpr))
            trs.append('<a:tr h="%d">%s</a:tr>' % (emu(rh), "".join(tcs)))
        total_h = sum(row_heights) if row_heights else row_h * len(rows)
        self.shapes.append(
            '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="%d" name="Table %d"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
            '<p:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></p:xfrm>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            '<a:tbl><a:tblPr firstRow="0" bandRow="0"/><a:tblGrid>%s</a:tblGrid>%s</a:tbl>'
            '</a:graphicData></a:graphic></p:graphicFrame>'
            % (i, i, emu(x), emu(y), emu(total_w), emu(total_h), grid, "".join(trs))
        )

    def line(self, x1, y1, x2, y2, color="C9D3D2", w=1.0, arrow=False, dash=False):
        self.ops.append(("line", dict(x1=x1, y1=y1, x2=x2, y2=y2, color=color, w=w, arrow=arrow, dash=dash)))
        i = self.nid()
        x, y = min(x1, x2), min(y1, y2)
        cx, cy = abs(x2 - x1), abs(y2 - y1)
        flip = ' flipV="1"' if (y2 < y1) != (x2 < x1) and cy and cx else ""
        head = '<a:tailEnd type="triangle" w="med" len="med"/>' if arrow else ""
        dsh = '<a:prstDash val="dash"/>' if dash else ""
        self.shapes.append(
            '<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="%d" name="Line %d"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
            '<p:spPr><a:xfrm%s><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
            '<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>%s%s</a:ln></p:spPr></p:cxnSp>'
            % (i, i, flip, emu(x), emu(y), emu(cx), emu(cy), int(w * 12700), color, dsh, head)
        )

    def xml(self, layout_rid="rId1"):
        bg = ('<p:bg><p:bgPr><a:solidFill><a:srgbClr val="%s"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>' % self.bg)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld>%s<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
            % (bg, "".join(self.shapes))
        )


class Deck:
    def __init__(self):
        self.slides = []
        self.media = []  # (name, bytes)

    def add(self, bg="FFFFFF"):
        s = Slide(bg)
        self.slides.append(s)
        return s

    def add_media(self, slide, path):
        data = open(path, "rb").read()
        ext = path.rsplit(".", 1)[-1].lower()
        name = "image%d.%s" % (len(self.media) + 1, ext)
        self.media.append((name, data, ext))
        rid = "rId%d" % (len(slide.rels) + 2)
        slide.media_paths[rid] = path
        slide.rels.append((rid, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", "../media/" + name))
        return rid

    def save(self, path, title="Presentation"):
        z = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
        n = len(self.slides)
        exts = sorted({m[2] for m in self.media})
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>']
        for e in exts:
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}[e]
            ct.append('<Default Extension="%s" ContentType="%s"/>' % (e, mime))
        ct.append('<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
                  '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
                  '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
                  '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
                  '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>'
                  '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>'
                  '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>'
                  '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                  '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>')
        for i in range(1, n + 1):
            ct.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % i)
        ct.append("</Types>")
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                   '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                   '</Relationships>')
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                   'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                   '<dc:title>%s</dc:title><dc:creator></dc:creator></cp:coreProperties>' % escape(title))
        z.writestr("docProps/app.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
                   'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Office PowerPoint</Application>'
                   '<Slides>%d</Slides></Properties>' % n)
        sld_ids = "".join('<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, 10 + i) for i in range(1, n + 1))
        z.writestr("ppt/presentation.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                   'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
                   '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                   '<p:sldIdLst>%s</p:sldIdLst>'
                   '<p:sldSz cx="%d" cy="%d"/><p:notesSz cx="6858000" cy="9144000"/>'
                   '<p:defaultTextStyle><a:defPPr><a:defRPr lang="zh-TW"/></a:defPPr></p:defaultTextStyle>'
                   '</p:presentation>' % (sld_ids, emu(SLIDE_W), emu(SLIDE_H)))
        prels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
                 '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>'
                 '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>'
                 '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>']
        for i in range(1, n + 1):
            prels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide%d.xml"/>' % (10 + i, i))
        prels.append("</Relationships>")
        z.writestr("ppt/_rels/presentation.xml.rels", "".join(prels))
        z.writestr("ppt/presProps.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>')
        z.writestr("ppt/viewProps.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr><p:gridSpacing cx="72008" cy="72008"/></p:viewPr>')
        z.writestr("ppt/tableStyles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>')
        z.writestr("ppt/theme/theme1.xml", THEME)
        z.writestr("ppt/slideMasters/slideMaster1.xml", MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
                   '</Relationships>')
        z.writestr("ppt/slideLayouts/slideLayout1.xml", LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
                   '</Relationships>')
        for i, s in enumerate(self.slides, 1):
            z.writestr("ppt/slides/slide%d.xml" % i, s.xml())
            rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>']
            for rid, typ, tgt in s.rels:
                rels.append('<Relationship Id="%s" Type="%s" Target="%s"/>' % (rid, typ, tgt))
            rels.append("</Relationships>")
            z.writestr("ppt/slides/_rels/slide%d.xml.rels" % i, "".join(rels))
        for name, data, _ in self.media:
            z.writestr("ppt/media/" + name, data)
        z.close()


_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')

_TXSTYLE = ('<a:defPPr><a:defRPr lang="zh-TW"/></a:defPPr>'
            '<a:lvl1pPr><a:defRPr sz="1400"><a:latin typeface="%s"/><a:ea typeface="%s"/></a:defRPr></a:lvl1pPr>' % (LATIN, EA))

MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster %s><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    '</p:spTree></p:cSld>'
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    '<p:txStyles><p:titleStyle>%s</p:titleStyle><p:bodyStyle>%s</p:bodyStyle><p:otherStyle>%s</p:otherStyle></p:txStyles>'
    '</p:sldMaster>' % (_NS, _TXSTYLE, _TXSTYLE, _TXSTYLE)
)

LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout %s type="blank" preserve="1"><p:cSld name="Blank">'
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>' % _NS
)

THEME = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="MQS">'
    '<a:themeElements><a:clrScheme name="MQS">'
    '<a:dk1><a:srgbClr val="1F3A3D"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="5B7A7D"/></a:dk2><a:lt2><a:srgbClr val="E9F1F0"/></a:lt2>'
    '<a:accent1><a:srgbClr val="D96C2F"/></a:accent1><a:accent2><a:srgbClr val="5B7A7D"/></a:accent2>'
    '<a:accent3><a:srgbClr val="9FB8B5"/></a:accent3><a:accent4><a:srgbClr val="F3D9C8"/></a:accent4>'
    '<a:accent5><a:srgbClr val="8A2E0A"/></a:accent5><a:accent6><a:srgbClr val="C9D3D2"/></a:accent6>'
    '<a:hlink><a:srgbClr val="D96C2F"/></a:hlink><a:folHlink><a:srgbClr val="5B7A7D"/></a:folHlink>'
    '</a:clrScheme>'
    '<a:fontScheme name="MQS"><a:majorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
    '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
    '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
    '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
    '</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>' % (LATIN, EA, LATIN, EA)
)


# ---------------------------------------------------------------- HTML preview
import os as _os

PX = 100.0  # px per inch


def _px(v):
    return "%.1fpx" % (v * PX)


def _pt(pt):
    return "%.1fpx" % (pt * PX / 72.0)


def _runs_html(runs, size, color, bold, font=None):
    out = []
    for r in runs:
        if isinstance(r, str):
            r = (r, {})
        t, o = r
        st = "font-size:%s;color:#%s;font-weight:%s;%s" % (
            _pt(o.get("size", size)), o.get("color", color), "700" if o.get("bold", bold) else "400",
            "font-style:italic;" if o.get("italic") else "")
        if o.get("font") or font:
            st += "font-family:'%s',monospace;" % (o.get("font") or font)
        out.append('<span style="%s">%s</span>' % (st, escape(t).replace("\n", "<br>")))
    return "".join(out)


def slide_html(slide, title=""):
    parts = ['<html><head><meta charset="utf-8"><style>'
             'body{margin:0;background:#888;font-family:"Carlito","Calibri","WenQuanYi Zen Hei",sans-serif;}'
             '.sl{position:relative;width:%s;height:%s;background:#%s;overflow:hidden;}'
             '.ab{position:absolute;box-sizing:border-box;}'
             'p{margin:0;line-height:1.2;} table{border-collapse:collapse;table-layout:fixed;} td{vertical-align:middle;line-height:1.2;}'
             '</style></head><body><div class="sl">' % (_px(SLIDE_W), _px(SLIDE_H), slide.bg)]
    for kind, o in slide.ops:
        if kind == "rect":
            st = "left:%s;top:%s;width:%s;height:%s;" % (_px(o["x"]), _px(o["y"]), _px(o["w"]), _px(o["h"]))
            if o["fill"]:
                st += "background:#%s;" % o["fill"]
            if o["line"]:
                st += "border:%.1fpx solid #%s;" % (o["line_w"] * PX / 72, o["line"])
            if o["radius"] is not None:
                st += "border-radius:%s;" % _px(o["radius"])
            if o["prst"] == "ellipse":
                st += "border-radius:50%;"
            if o["shadow"]:
                st += "box-shadow:0 2px 5px rgba(0,0,0,.18);"
            parts.append('<div class="ab" style="%s"></div>' % st)
        elif kind == "text":
            m = o["margin"]
            st = "left:%s;top:%s;width:%s;height:%s;padding:%s;display:flex;flex-direction:column;justify-content:%s;" % (
                _px(o["x"]), _px(o["y"]), _px(o["w"]), _px(o["h"]), _px(m),
                {"t": "flex-start", "m": "center", "b": "flex-end"}[o["anchor"]])
            if not o["wrap"]:
                st += "white-space:nowrap;"
            ps = []
            for p in o["paras"]:
                if isinstance(p, str):
                    p = {"runs": [p]}
                al = {"l": "left", "ctr": "center", "r": "right"}[p.get("align", o["align"])]
                pst = "text-align:%s;" % al
                ls = p.get("line_spacing", o["line_spacing"])
                if ls:
                    pst += "line-height:%.2f;" % (1.2 * ls)
                if p.get("space_before"):
                    pst += "margin-top:%s;" % _pt(p["space_before"])
                if p.get("space_after"):
                    pst += "margin-bottom:%s;" % _pt(p["space_after"])
                lvl = p.get("level", 0)
                ind = p.get("indent")
                if p.get("bullet"):
                    ind = ind if ind is not None else 0.22
                    pst += "padding-left:%s;text-indent:-%s;" % (_px(ind * (lvl + 1)), _px(ind))
                    ch = p["bullet"] if isinstance(p["bullet"], str) else "•"
                    bc = p.get("bullet_color", p.get("color", o["color"]))
                    bullet = '<span style="display:inline-block;width:%s;text-indent:0;color:#%s;font-size:%s">%s</span>' % (
                        _px(ind), bc, _pt(p.get("size", o["size"])), ch)
                else:
                    bullet = ""
                    if ind:
                        pst += "padding-left:%s;" % _px(ind)
                sz = p.get("size", o["size"])
                inner = _runs_html(p.get("runs", []), sz, p.get("color", o["color"]), p.get("bold", o["bold"]), o["font"])
                if not inner:
                    inner = '<span style="font-size:%s">&nbsp;</span>' % _pt(sz)
                ps.append('<p style="%s">%s%s</p>' % (pst, bullet, inner))
            parts.append('<div class="ab" style="%s">%s</div>' % (st, "".join(ps)))
        elif kind == "image":
            path = slide.media_paths[o["rid"]]
            crop = o["crop"] or (0, 0, 0, 0)
            l, t, r, b = crop
            iw = o["w"] / (1 - l - r)
            ih = o["h"] / (1 - t - b)
            st = "left:%s;top:%s;width:%s;height:%s;overflow:hidden;%s" % (
                _px(o["x"]), _px(o["y"]), _px(o["w"]), _px(o["h"]),
                ("border:1px solid #%s;" % o["line"]) if o["line"] else "")
            parts.append('<div class="ab" style="%s"><img src="file://%s" style="position:absolute;left:%s;top:%s;width:%s;height:%s"></div>' % (
                st, _os.path.abspath(path), _px(-l * iw), _px(-t * ih), _px(iw), _px(ih)))
        elif kind == "table":
            rows = o["rows"]
            cols = "".join('<col style="width:%s">' % _px(w) for w in o["col_w"])
            trs = []
            for ri, row in enumerate(rows):
                rh = o["row_heights"][ri] if o["row_heights"] else o["row_h"]
                tds = []
                for ci, cell in enumerate(row):
                    if not isinstance(cell, dict):
                        cell = {"text": cell}
                    is_head = o["header"] and ri == 0
                    fill = cell.get("fill") or (o["head_fill"] if is_head else (o["fills"][ri % len(o["fills"])] if o["fills"] else "FFFFFF"))
                    col = cell.get("color") or (o["head_color"] if is_head else o["color"])
                    b = cell.get("bold", is_head or (o["first_col_bold"] and ci == 0))
                    sz = cell.get("size", o["size"])
                    al = cell.get("align") or (o["cell_align"][ci] if o["cell_align"] else "l")
                    lines = cell.get("lines")
                    if lines is None:
                        lines = [cell.get("runs") or cell.get("text", "")]
                    ps = []
                    for ln in lines:
                        if isinstance(ln, str):
                            ln = [(ln, {})]
                        ps.append('<p style="text-align:%s">%s</p>' % ({"l": "left", "ctr": "center", "r": "right"}[al], _runs_html(ln, sz, col, b, cell.get("font")) or "&nbsp;"))
                    tds.append('<td style="background:#%s;border:0.5px solid #%s;padding:%s %s;height:%s">%s</td>' % (
                        fill, o["border"], _px(0.04), _px(o["margin"]), _px(rh), "".join(ps)))
                trs.append("<tr>%s</tr>" % "".join(tds))
            parts.append('<table class="ab" style="left:%s;top:%s;width:%s"><colgroup>%s</colgroup>%s</table>' % (
                _px(o["x"]), _px(o["y"]), _px(sum(o["col_w"])), cols, "".join(trs)))
        elif kind == "line":
            import math
            x1, y1, x2, y2 = o["x1"], o["y1"], o["x2"], o["y2"]
            L = math.hypot(x2 - x1, y2 - y1)
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            st = "left:%s;top:%s;width:%s;height:0;border-top:%.1fpx %s #%s;transform-origin:0 0;transform:rotate(%.1fdeg);" % (
                _px(x1), _px(y1), _px(L), o["w"] * PX / 72, "dashed" if o["dash"] else "solid", o["color"], ang)
            head = ""
            if o["arrow"]:
                head = '<div style="position:absolute;right:-2px;top:-6px;width:0;height:0;border-left:10px solid #%s;border-top:5px solid transparent;border-bottom:5px solid transparent"></div>' % o["color"]
            parts.append('<div class="ab" style="%s">%s</div>' % (st, head))
    parts.append("</div></body></html>")
    return "".join(parts)


def write_previews(deck, out_dir):
    _os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, s in enumerate(deck.slides, 1):
        p = _os.path.join(out_dir, "slide%02d.html" % i)
        open(p, "w", encoding="utf-8").write(slide_html(s))
        paths.append(p)
    return paths
