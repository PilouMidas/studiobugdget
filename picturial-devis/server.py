#!/usr/bin/env python3
# Serveur applicatif local : API JSON + interface web + exports. Bibliothèque standard uniquement.
# Usage : python3 server.py [--port 8765] [--host 127.0.0.1]
import argparse
import json
import os
import re
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import db
import engine
from xlsx_export import export_xlsx_bytes

DB_PATH = os.environ.get("PICTURIAL_DB") or db.default_db_path()
CONN = db.initialiser(DB_PATH)
LOCK = threading.RLock()


def repondre(handler, status, donnees, content_type="application/json; charset=utf-8", headers=None):
    if isinstance(donnees, (dict, list)):
        body = json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8")
    elif isinstance(donnees, str):
        body = donnees.encode("utf-8")
    else:
        body = donnees
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def lignes_publiques(node):
    n = {k: v for k, v in node.items() if k != "children"}
    n["children"] = [lignes_publiques(c) for c in node["children"]]
    return n


def referentiel(conn):
    out = []
    for c in conn.execute("SELECT * FROM conventions ORDER BY rowid").fetchall():
        grilles = []
        for g in conn.execute("SELECT * FROM grilles WHERE convention_id=? ORDER BY date_effet DESC, rowid DESC", (c["id"],)).fetchall():
            fonctions = [dict(f) for f in conn.execute(
                "SELECT * FROM fonctions WHERE grille_id=? ORDER BY nom", (g["id"],)).fetchall()]
            grilles.append({**dict(g), "fonctions": fonctions})
        out.append({**dict(c), "grilles": grilles})
    return out


def print_html(conn, film_id):
    calc = engine.compute_film(conn, film_id)
    f = calc["film"]
    t = calc["totaux"]

    def ligne_html(n, prof):
        ind = "&nbsp;" * 4 * prof
        cls = {"saisi": "saisi", "calcule": "calcule"}.get(n.get("statut_montant"), "")
        return ("<tr>"
                f"<td class='code'>{n['chemin']}</td>"
                f"<td>{ind}{engine.escape_html(n['libelle'])}</td>"
                f"<td class='num'>{n['quantite'] if n['quantite'] is not None else ''}</td>"
                f"<td>{n['unite'] or ''}</td>"
                f"<td class='num'>{engine.fmt_fr(n['cout_unitaire'])}</td>"
                f"<td class='num {cls}'>{engine.fmt_fr(n['montant'])}</td>"
                f"<td class='num'>{engine.fmt_fr(n['en_region'])}</td>"
                f"<td class='num'>{engine.fmt_fr(n['hors_region'])}</td>"
                f"<td class='num'>{engine.fmt_fr(n.get('etranger', 0))}</td>"
                f"<td class='num'>{engine.fmt_fr(n['a_ventiler'])}</td>"
                "</tr>" + "".join(ligne_html(c, prof + 1) for c in n["children"]))

    recap_rows = "".join(
        f"<tr><td class='code'>{p['code']}</td><td>{engine.escape_html(p['libelle'])}</td>"
        f"<td class='num'>{engine.fmt_fr(p['montant'])}</td><td class='num'>{engine.fmt_fr(p['en_region'])}</td>"
        f"<td class='num'>{engine.fmt_fr(p['hors_region'])}</td><td class='num'>{engine.fmt_fr(p.get('etranger', 0))}</td>"
        f"<td class='num'>{engine.fmt_fr(p['a_ventiler'])}</td></tr>"
        for p in calc["recap"])
    detail_rows = "".join(ligne_html(r, 0) for r in calc["arbre"])
    part = f"{t['en_region'] / t['montant'] * 100:.1f} %" if t["montant"] else "—"
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Devis — {engine.escape_html(f['titre'])}</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 32px; color:#111; font-size: 13px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 15px; margin: 24px 0 8px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 4px 8px; text-align: left; }}
th {{ border-bottom: 2px solid #111; }} td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.code {{ color:#666; white-space: nowrap; }} .total td {{ font-weight: 700; border-top: 2px solid #111; }}
.meta {{ color:#444; margin-bottom: 16px; }} .saisi {{ font-weight: 600; }}
@media print {{ .noprint {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<h1>Devis de production — {engine.escape_html(f['titre'])}</h1>
<div class="meta">{engine.escape_html(f['societe'])} — {engine.escape_html(f['type_oeuvre'])} —
Région cible : <strong>{engine.escape_html(f['region_cible'])}</strong> —
Convention : {engine.escape_html(f['convention_id'] and (CONN.execute('SELECT nom FROM conventions WHERE id=?',(f['convention_id'],)).fetchone() or [''])[0] or '—')} —
Date de référence des barèmes : {f['date_ref_baremes']} — Hypothèse de charges employeur : {f['taux_charges']*100:g} %<br>
Édité le {date.today().isoformat()} — montants fictifs de démonstration si le barème est marqué « Démonstration ».</div>
<button class="noprint" onclick="window.print()">Imprimer / enregistrer en PDF</button>
<h2>Récapitulatif</h2>
<table><tr><th>Code</th><th>Grand poste</th><th>Montant</th><th>En région</th><th>France (hors région)</th><th>Étranger</th><th>À ventiler</th></tr>
{recap_rows}
<tr class="total"><td></td><td>TOTAL GÉNÉRAL</td><td class="num">{engine.fmt_fr(t['montant'])}</td>
<td class="num">{engine.fmt_fr(t['en_region'])}</td><td class="num">{engine.fmt_fr(t['hors_region'])}</td>
<td class="num">{engine.fmt_fr(t.get('etranger', 0))}</td>
<td class="num">{engine.fmt_fr(t['a_ventiler'])}</td></tr></table>
<div class="meta">Part régionale du budget : <strong>{part}</strong> — contrôle : en région + France hors région + étranger + à ventiler = {engine.fmt_fr(engine.r2(t['en_region']+t['hors_region']+t.get('etranger',0)+t['a_ventiler']))}</div>
<h2>Détail du devis</h2>
<table><tr><th>Code</th><th>Libellé</th><th>Qté</th><th>Unité</th><th>Coût unit.</th><th>Montant</th><th>En région</th><th>France (hors région)</th><th>Étranger</th><th>À ventiler</th></tr>
{detail_rows}
<tr class="total"><td></td><td>TOTAL GÉNÉRAL</td><td></td><td></td><td></td><td class="num">{engine.fmt_fr(t['montant'])}</td>
<td class="num">{engine.fmt_fr(t['en_region'])}</td><td class="num">{engine.fmt_fr(t['hors_region'])}</td>
<td class="num">{engine.fmt_fr(t.get('etranger', 0))}</td><td class="num">{engine.fmt_fr(t['a_ventiler'])}</td></tr>
</table></body></html>"""


ROUTES = []


def route(method, pattern):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


@route("GET", r"/api/health")
def health(h, m, q, body):
    return {"ok": True, "app": db.APP_NAME, "db": os.path.abspath(DB_PATH)}


@route("GET", r"/api/films")
def films_liste(h, m, q, body):
    rows = CONN.execute("SELECT id, titre, societe, type_oeuvre, region_cible, updated_at FROM films ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


@route("POST", r"/api/films")
def films_creer(h, m, q, body):
    titre = (body.get("titre") or "").strip() or "Nouveau film"
    with LOCK:
        fid = db.creer_film(CONN, titre, societe=body.get("societe", ""), type_oeuvre=body.get("type_oeuvre", "Long métrage"),
                            region=body.get("region", "Île-de-France"),
                            taux_charges=float(body.get("taux_charges", 0.57) or 0.57),
                            convention_id=body.get("convention_id"), grille_id=body.get("grille_id"),
                            charges_mode=body.get("charges_mode", "poste_dedie"),
                            frais_generaux=bool(body.get("frais_generaux", True)))
    return {"id": fid}, 201


@route("GET", r"/api/films/([0-9a-f]+)")
def film_get(h, m, q, body):
    return dict(engine._film(CONN, m.group(1)))


@route("PUT", r"/api/films/([0-9a-f]+)")
def film_put(h, m, q, body):
    fid = m.group(1)
    film = dict(engine._film(CONN, fid))
    if "region_cible" in body and body["region_cible"] != film["region_cible"]:
        with LOCK:
            res = engine.changer_region_cible(CONN, fid, body["region_cible"], option=body.get("option_ventilation"))
        return res
    champs = {k: body[k] for k in ("titre", "societe", "type_oeuvre", "date_debut", "date_fin", "convention_id",
                                   "grille_id", "date_ref_baremes", "taux_charges", "charges_mode", "nom_poste_charges") if k in body}
    if "taux_charges" in champs:
        champs["taux_charges"] = float(champs["taux_charges"])
    with LOCK:
        if champs:
            set_clause = ", ".join(f"{k}=?" for k in champs)
            CONN.execute(f"UPDATE films SET {set_clause}, updated_at=? WHERE id=?", (*champs.values(), date.today().isoformat(), fid))
            CONN.commit()
    return dict(engine._film(CONN, fid))


@route("POST", r"/api/films/([0-9a-f]+)/dupliquer")
def film_dupliquer(h, m, q, body):
    with LOCK:
        nid = engine.dupliquer_film(CONN, m.group(1))
    return {"id": nid}, 201


@route("DELETE", r"/api/films/([0-9a-f]+)")
def film_supprimer(h, m, q, body):
    with LOCK:
        CONN.execute("DELETE FROM films WHERE id=?", (m.group(1),))
        CONN.commit()
    return {"ok": True}


@route("GET", r"/api/referentiel")
def ref_get(h, m, q, body):
    return {"conventions": referentiel(CONN), "regions": db.REGIONS, "unites": db.UNITES, "phases": db.PHASES}


@route("POST", r"/api/conventions")
def conv_creer(h, m, q, body):
    with LOCK:
        cid = db.new_id()
        CONN.execute("INSERT INTO conventions (id, nom, description) VALUES (?,?,?)", (cid, body.get("nom", "Nouvelle convention"), body.get("description", "")))
        CONN.commit()
    return {"id": cid}, 201


@route("PUT", r"/api/conventions/([0-9a-f]+)")
def conv_modifier(h, m, q, body):
    with LOCK:
        CONN.execute("UPDATE conventions SET nom=COALESCE(?, nom), description=COALESCE(?, description) WHERE id=?",
                     (body.get("nom"), body.get("description"), m.group(1)))
        CONN.commit()
    return {"ok": True}


@route("POST", r"/api/conventions/([0-9a-f]+)/grilles")
def grille_creer(h, m, q, body):
    with LOCK:
        gid = db.new_id()
        CONN.execute("INSERT INTO grilles (id, convention_id, version, date_effet, source, statut) VALUES (?,?,?,?,?,?)",
                     (gid, m.group(1), body.get("version", "Nouvelle version"), body.get("date_effet", date.today().isoformat()),
                      body.get("source", ""), body.get("statut", "demonstration")))
        CONN.commit()
    return {"id": gid}, 201


@route("PUT", r"/api/grilles/([0-9a-f]+)")
def grille_modifier(h, m, q, body):
    with LOCK:
        champs = {k: body[k] for k in ("version", "date_effet", "source", "statut") if k in body}
        if champs:
            CONN.execute("UPDATE grilles SET " + ", ".join(f"{k}=?" for k in champs) + " WHERE id=?", (*champs.values(), m.group(1)))
            CONN.commit()
    return {"ok": True}


@route("POST", r"/api/grilles/([0-9a-f]+)/fonctions")
def fonction_creer(h, m, q, body):
    with LOCK:
        fid = db.new_id()
        grille = CONN.execute("SELECT * FROM grilles WHERE id=?", (m.group(1),)).fetchone()
        CONN.execute(
            "INSERT INTO fonctions (id, convention_id, grille_id, nom, minimum, unite, valide_du, valide_au, source, statut)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (fid, grille["convention_id"], m.group(1), body.get("nom", "Nouvelle fonction"), float(body.get("minimum", 0)),
             body.get("unite", "jour"), body.get("valide_du", ""), body.get("valide_au", ""),
             body.get("source", ""), body.get("statut", "demonstration")))
        CONN.commit()
    return {"id": fid}, 201


@route("PUT", r"/api/fonctions/([0-9a-f]+)")
def fonction_modifier(h, m, q, body):
    with LOCK:
        champs = {}
        for k in ("nom", "unite", "valide_du", "valide_au", "source", "statut", "grille_id"):
            if k in body:
                champs[k] = body[k]
        if "minimum" in body:
            champs["minimum"] = float(body["minimum"])
        if champs:
            CONN.execute("UPDATE fonctions SET " + ", ".join(f"{k}=?" for k in champs) + " WHERE id=?", (*champs.values(), m.group(1)))
            CONN.commit()
    return {"ok": True}


@route("GET", r"/api/films/([0-9a-f]+)/devis")
def devis_get(h, m, q, body):
    calc = engine.compute_film(CONN, m.group(1))
    return {"film": calc["film"], "arbre": [lignes_publiques(r) for r in calc["arbre"]],
            "totaux": calc["totaux"], "recap": calc["recap"]}


@route("POST", r"/api/films/([0-9a-f]+)/lignes")
def ligne_creer(h, m, q, body):
    with LOCK:
        if body.get("sous_detail"):
            lid = engine.ajouter_sous_detail(CONN, m.group(1), body.get("parent_id"), libelle=body.get("libelle", ""),
                                             quantite=body.get("quantite"), unite=body.get("unite", "forfait"),
                                             cout_unitaire=body.get("cout_unitaire"), montant_forfait=body.get("montant_forfait"),
                                             note=body.get("note", ""), ht=bool(body.get("ht", True)),
                                             reprendre=body.get("reprendre"))
        else:
            lid = engine.ajouter_ligne(CONN, m.group(1), body.get("parent_id"), type_ligne=body.get("type", "ligne"),
                                       libelle=body.get("libelle", ""), quantite=body.get("quantite"), unite=body.get("unite", "forfait"),
                                       cout_unitaire=body.get("cout_unitaire"), montant_forfait=body.get("montant_forfait"),
                                       note=body.get("note", ""), ht=bool(body.get("ht", True)), code=body.get("code", ""))
    return {"id": lid}, 201


@route("PUT", r"/api/lignes/([0-9a-f]+)")
def ligne_modifier(h, m, q, body):
    with LOCK:
        engine.modifier_ligne(CONN, m.group(1), body)
    return {"ok": True}


@route("DELETE", r"/api/lignes/([0-9a-f]+)")
def ligne_supprimer(h, m, q, body):
    with LOCK:
        ids = engine._sous_arbre(CONN, m.group(1))
        engine.supprimer_ligne(CONN, m.group(1))
    return {"ok": True, "supprimees": len(ids)}


@route("POST", r"/api/lignes/([0-9a-f]+)/dupliquer")
def ligne_dupliquer(h, m, q, body):
    with LOCK:
        nid = engine.dupliquer_ligne(CONN, m.group(1))
    return {"id": nid}, 201


@route("POST", r"/api/lignes/([0-9a-f]+)/deplacer")
def ligne_deplacer(h, m, q, body):
    with LOCK:
        engine.deplacer_ligne(CONN, m.group(1), body.get("parent_id"))
    return {"ok": True}


@route("POST", r"/api/lignes/([0-9a-f]+)/ventilation")
def ligne_ventilation(h, m, q, body):
    film_id = CONN.execute("SELECT film_id FROM lignes WHERE id=?", (m.group(1),)).fetchone()["film_id"]
    with LOCK:
        engine.set_ventilation(CONN, film_id, m.group(1), mode=body.get("mode", "partiel"),
                               en_region=body.get("en_region"), hors_region=body.get("hors_region"),
                               etranger=body.get("etranger"))
    return engine.vue_region(CONN, film_id)


@route("POST", r"/api/films/([0-9a-f]+)/techniciens")
def tech_creer(h, m, q, body):
    with LOCK:
        tid = engine.ajouter_technicien(CONN, m.group(1), body.get("parent_id"), body.get("fonction_id"),
                                        nom=body.get("nom", ""), salaire=body.get("salaire"), unite=body.get("unite", "jour"),
                                        phases=body.get("phases", []), hypothese_manuelle=bool(body.get("hypothese_manuelle")))
        fiche = engine.fiche_technicien(CONN, tid)
    return {"id": tid, "fiche": fiche}, 201


@route("GET", r"/api/techniciens/([0-9a-f]+)")
def tech_get(h, m, q, body):
    return engine.fiche_technicien(CONN, m.group(1))


@route("PUT", r"/api/techniciens/([0-9a-f]+)")
def tech_modifier(h, m, q, body):
    with LOCK:
        engine.modifier_technicien(CONN, m.group(1), nom=body.get("nom"), salaire=body.get("salaire"),
                                   phases=body.get("phases"), hypothese_manuelle=body.get("hypothese_manuelle"))
        fiche = engine.fiche_technicien(CONN, m.group(1))
    return {"ok": True, "fiche": fiche}


@route("GET", r"/api/films/([0-9a-f]+)/region")
def region_get(h, m, q, body):
    return engine.vue_region(CONN, m.group(1))


@route("POST", r"/api/films/([0-9a-f]+)/baremes/actualiser")
def baremes_actualiser(h, m, q, body):
    with LOCK:
        return engine.actualiser_baremes(CONN, m.group(1), appliquer=bool(body.get("appliquer")))


@route("GET", r"/api/films/([0-9a-f]+)/export\.xlsx")
def export_xlsx(h, m, q, body):
    data, nom = export_xlsx_bytes(CONN, m.group(1))
    h.send_response(200)
    h.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    h.send_header("Content-Disposition", f'attachment; filename="{nom}"')
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)
    return None


@route("GET", r"/api/films/([0-9a-f]+)/backup")
def backup(h, m, q, body):
    data = json.dumps(engine.backup_projet(CONN, m.group(1)), ensure_ascii=False, indent=1).encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Disposition", f'attachment; filename="sauvegarde-{m.group(1)[:8]}.json"')
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)
    return None


@route("POST", r"/api/restaurer")
def restaurer(h, m, q, body):
    with LOCK:
        nid = engine.restaurer_projet(CONN, body)
    return {"id": nid}, 201


@route("GET", r"/print/([0-9a-f]+)")
def print_route(h, m, q, body):
    return None  # géré plus bas (HTML)


CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                 ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PicturialDevis/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[picturial] " + (fmt % args) + "\n")

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise engine.Erreur("Corps JSON illisible.", 400)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if method == "GET" and path.startswith("/print/"):
            m = re.match(r"^/print/([0-9a-f]+)$", path)
            if m:
                try:
                    return repondre(self, 200, print_html(CONN, m.group(1)), "text/html; charset=utf-8")
                except engine.Erreur as e:
                    return repondre(self, e.status, {"erreur": e.message})
        if method == "GET" and (path == "/" or path == "/index.html"):
            return self._static("index.html")
        if method == "GET" and path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        try:
            body = self._json_body() if method in ("POST", "PUT") else {}
        except engine.Erreur as e:
            return repondre(self, e.status, {"erreur": e.message})
        for meth, rx, fn in ROUTES:
            if meth != method:
                continue
            m = rx.match(path)
            if m:
                try:
                    with LOCK:
                        result = fn(self, m, query, body)
                    if result is None:
                        return
                    data, status = (result if isinstance(result, tuple) else (result, 200))
                    return repondre(self, status, data)
                except engine.Erreur as e:
                    payload = {"erreur": e.message}
                    if e.confirmation_requise:
                        payload["confirmation_requise"] = True
                    return repondre(self, e.status, payload)
                except Exception as e:
                    return repondre(self, 500, {"erreur": f"Erreur interne : {e}"})
        return repondre(self, 404, {"erreur": f"Route introuvable : {method} {path}"})

    def _static(self, rel):
        rel = os.path.normpath(rel).lstrip("/")
        full = os.path.join(BASE_DIR, "static", rel)
        if not full.startswith(os.path.join(BASE_DIR, "static")) or not os.path.isfile(full):
            return repondre(self, 404, {"erreur": "Fichier statique introuvable."})
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            data = f.read()
        return repondre(self, 200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def ecrire_lock(port):
    try:
        data_dir = os.path.dirname(os.path.abspath(DB_PATH))
        with open(os.path.join(data_dir, "serveur.json"), "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": os.getpid()}, f)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PICTURIAL_PORT", "8765")))
    parser.add_argument("--host", default=os.environ.get("PICTURIAL_HOST", "127.0.0.1"))
    args = parser.parse_args()
    ecrire_lock(args.port)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Picturial — serveur de devis prêt sur http://{args.host}:{args.port}/", flush=True)
    print(f"Base de données : {os.path.abspath(DB_PATH)}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "serveur.json"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
