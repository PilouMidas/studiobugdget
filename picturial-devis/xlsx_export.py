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

    def ligne_detail(n, prof):
        return [n["chemin"], "    " * prof + n["libelle"], n["quantite"], n["unite"],
                n["cout_unitaire"], n["montant"], n["en_region"], n["hors_region"],
                n.get("etranger", 0), n["a_ventiler"],
                "HT" if n["ht"] else ("charges employeur" if n["type"] == "charge" else ""), n["note"]]

    def flatten(roots):
        out = []
        def walk(n, prof):
            out.append((n, prof))
            for c in n["children"]:
                walk(c, prof + 1)
        for r in roots:
            walk(r, 0)
        return out

    # Onglet général (comme l'onglet « Devis » du modèle) : lignes de premier niveau + total
    recap_rows = [["Code", "Poste / ligne", "En région (€)", "France hors région (€)", "Étranger (€)",
                   "À ventiler (€)", "Total (€)"]]
    for p in calc["recap"]:
        recap_rows.append([p["code"], p["libelle"], p["en_region"], p["hors_region"], p.get("etranger", 0),
                           p["a_ventiler"], p["montant"]])
    recap_rows.append(["", "TOTAL HORS TVA (coût définitif total)", t["en_region"], t["hors_region"],
                       t.get("etranger", 0), t["a_ventiler"], t["montant"]])
    recap_rows.append([])
    recap_rows.append(["Film", film["titre"], "", "Région cible", film["region_cible"], "", ""])
    recap_rows.append(["Société", film["societe"], "", "Date réf. barèmes", film["date_ref_baremes"], "", ""])
    recap_rows.append(["Hypothèse charges employeur", film["taux_charges"], "", "Part régionale",
                       f"{t['en_region'] / t['montant'] * 100:.1f} %" if t["montant"] else "", "", ""])

    sheets = [_sheet("Devis (général)", recap_rows, [8, 52, 15, 18, 13, 14, 15])]

    # Un onglet par grand poste (comme les onglets 1. à 9. du modèle)
    for r in calc["arbre"]:
        if r["type"] != "poste":
            continue
        nom = f"{r['code']}. {r['libelle']}"[:31]
        rows = [["Code", "Libellé", "Qté", "Unité", "Coût unit. (€)", "Total (€)", "En région (€)",
                 "France hors région (€)", "Étranger (€)", "À ventiler (€)", "Base", "Note"]]
        for n, prof in flatten([r]):
            rows.append(ligne_detail(n, prof))
        rows.append(["", "TOTAL DU POSTE", None, "", None, r["montant"], r["en_region"], r["hors_region"],
                     r.get("etranger", 0), r["a_ventiler"], "", ""])
        sheets.append(_sheet(nom, rows, [10, 48, 8, 10, 14, 13, 14, 17, 13, 14, 16, 30]))

    # Onglet ventilation territoriale
    region_rows = [["Code", "Ligne", "Total (€)", "En région (€)", "France hors région (€)", "Étranger (€)", "À ventiler (€)"]]
    for p in calc["recap"]:
        region_rows.append([p["code"], p["libelle"], p["montant"], p["en_region"], p["hors_region"],
                            p.get("etranger", 0), p["a_ventiler"]])
    region_rows.append(["", "TOTAL", t["montant"], t["en_region"], t["hors_region"], t.get("etranger", 0), t["a_ventiler"]])
    region_rows.append([])
    region_rows.append([f"Région cible : {film['region_cible']}",
                        f"Part régionale : {t['en_region'] / t['montant'] * 100:.1f} %" if t["montant"] else "",
                        "Contrôle : région + France + étranger + à ventiler =",
                        t["en_region"] + t["hors_region"] + t.get("etranger", 0) + t["a_ventiler"], "", "", ""])
    sheets.append(_sheet("Ventilation territoriale", region_rows, [10, 48, 13, 14, 19, 13, 14]))

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
