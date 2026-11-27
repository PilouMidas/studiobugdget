#!/usr/bin/env python3
# Export Excel .xlsx sans dépendance : un XLSX est un ZIP de fichiers XML.
# Onglets : Récapitulatif (9 postes + total), Détail du devis, Ventilation régionale.
# Les montants sont écrits comme des nombres (cellules numériques exploitables).
import io
import zipfile
from xml.sax.saxutils import escape

import engine


def _col_letter(idx):
    s = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, value, style=0):
    if value is None or value == "":
        return f'<c r="{ref}" s="{style}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{value!r}</v></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def _sheet(name, rows, widths=None, style_header=True):
    """rows : liste de listes (valeurs str/int/float/None). style 1 = en-tête gras."""
    ncols = max((len(r) for r in rows), default=1)
    xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if widths:
        xml.append("<cols>" + "".join(
            f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)) + "</cols>")
    xml.append('<sheetData>')
    for ri, row in enumerate(rows, start=1):
        xml.append(f'<row r="{ri}">')
        for ci, val in enumerate(row, start=1):
            style = 1 if (style_header and ri == 1) else 0
            xml.append(_cell(f"{_col_letter(ci)}{ri}", val, style))
        xml.append("</row>")
    xml.append("</sheetData></worksheet>")
    return name, "".join(xml)


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
          '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
          '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
          '<borders count="1"><border/></borders>'
          '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
          '<cellXfs count="2"><xf/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>')


def _flatten(roots):
    out = []

    def walk(n, profondeur):
        out.append((n, profondeur))
        for c in n["children"]:
            walk(c, profondeur + 1)
    for r in roots:
        walk(r, 0)
    return out


def export_xlsx_bytes(conn, film_id):
    calc = engine.compute_film(conn, film_id)
    film = calc["film"]
    t = calc["totaux"]
    buf = io.BytesIO()
    titre = f"Devis — {film['titre']}"

    recap_rows = [["Code", "Grand poste", "Montant (€)", "En région (€)", "Hors région (€)", "À ventiler (€)"]]
    for p in calc["recap"]:
        recap_rows.append([p["code"], p["libelle"], p["montant"], p["en_region"], p["hors_region"], p["a_ventiler"]])
    recap_rows.append(["", "TOTAL GÉNÉRAL", t["montant"], t["en_region"], t["hors_region"], t["a_ventiler"]])
    recap_rows.append([])
    recap_rows.append(["Film", film["titre"], "", "Région cible", calc["film"]["region_cible"], ""])
    recap_rows.append(["Société", film["societe"], "", "Date réf. barèmes", film["date_ref_baremes"], ""])
    recap_rows.append(["Taux de charges employeur (hypothèse)", film["taux_charges"], "", "Part régionale", f"{t['en_region'] / t['montant'] * 100:.1f} %" if t["montant"] else "", ""])

    detail_rows = [["Code", "Libellé", "Qté", "Unité", "Coût unitaire (€)", "Montant (€)", "En région (€)", "Hors région (€)", "À ventiler (€)", "Base", "Note"]]
    for n, prof in _flatten(calc["arbre"]):
        base = "HT" if n["ht"] else ("brut + charges" if n["type"] in ("technicien", "charge") else "")
        if n["type"] == "charge":
            base = "charges employeur"
        detail_rows.append([n["chemin"], "    " * prof + n["libelle"], n["quantite"], n["unite"],
                            n["cout_unitaire"], n["montant"], n["en_region"], n["hors_region"], n["a_ventiler"],
                            base, n["note"]])
    detail_rows.append(["", "TOTAL GÉNÉRAL", None, "", None, t["montant"], t["en_region"], t["hors_region"], t["a_ventiler"], "", ""])

    region_rows = [["Code", "Ligne", "Montant (€)", "En région (€)", "Hors région (€)", "À ventiler (€)"]]
    for p in calc["recap"]:
        region_rows.append([p["code"], p["libelle"], p["montant"], p["en_region"], p["hors_region"], p["a_ventiler"]])
    region_rows.append(["", "TOTAL", t["montant"], t["en_region"], t["hors_region"], t["a_ventiler"]])
    region_rows.append([])
    region_rows.append([f"Région cible : {film['region_cible']}",
                        f"Part régionale : {t['en_region'] / t['montant'] * 100:.1f} %" if t["montant"] else "",
                        "Contrôle : en région + hors région + à ventiler =", t["en_region"] + t["hors_region"] + t["a_ventiler"], "", ""])

    sheets = [
        _sheet("Récapitulatif", recap_rows, [8, 42, 14, 14, 14, 14]),
        _sheet("Détail du devis", detail_rows, [10, 46, 8, 10, 16, 14, 14, 14, 14, 16, 30]),
        _sheet("Ventilation régionale", region_rows, [10, 46, 14, 14, 14, 14]),
    ]

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets)))
                   + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   "<sheets>" + "".join(
                       f'<sheet name="{escape(name)}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i, (name, _) in enumerate(sheets))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", STYLES)
        for i, (_, xml) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", xml)
    return buf.getvalue(), f"devis-{film_id[:8]}.xlsx"
