#!/usr/bin/env python3
# Test d'intégration HTTP : on démarre le vrai serveur sur un port éphémère avec une base temporaire
# et on déroule la recette via l'API JSON (mêmes routes que l'interface web).
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp(prefix="picturial-api-")
os.environ["PICTURIAL_DB"] = os.path.join(TMP, "devis.db")
os.environ["PICTURIAL_DATA_DIR"] = TMP

import server  # noqa: E402  (initialise CONN sur la base temporaire)


def call(method, path, body=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = res.read()
            ct = res.headers.get("Content-Type", "")
            return res.status, (json.loads(raw) if "json" in ct else raw), ct
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), ""


httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.films = call("GET", "/api/films")[1]
        cls.demo = next(f for f in cls.films if "démonstration" in f["titre"])
        cls.film_id = call("POST", "/api/films", {"titre": "Film API", "societe": "Test", "frais_generaux": False, "taux_charges": 0.40, "charges_mode": "avec"})[1]["id"]
        ref = call("GET", "/api/referentiel")[1]
        cls.fonc_id = ref["conventions"][0]["grilles"][0]["fonctions"][0]["id"]
        cls.fonc_son = next(f["id"] for f in ref["conventions"][0]["grilles"][0]["fonctions"]
                            if f["nom"] == "Chef opérateur du son")
        cls.ref = ref

    def test_00b_referentiel_ccnpc(self):
        ccnpc = next(c for c in self.ref["conventions"] if c["nom"].startswith("CCNPC"))
        total = sum(len(g["fonctions"]) for g in ccnpc["grilles"])
        self.assertGreater(total, 150)
        f = next(f for g in ccnpc["grilles"] if g["version"].startswith("Annexe 1") for f in g["fonctions"] if f["nom"] == "Chef opérateur du son cinéma")
        self.assertAlmostEqual(f["minimum"], 1930.05755, places=4)
        self.assertEqual(f["unite"], "semaine")
        self.assertEqual(f["statut"], "verifie")

    def test_00_health_et_statique(self):
        status, body, _ = call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10) as r:
            html = r.read().decode()
        self.assertIn("Picturial", html)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/static/app.js", timeout=10) as r:
            js = r.read().decode()
        self.assertIn("renderDevis", js)

    def test_01_projet_demo_prempli(self):
        status, devis, _ = call("GET", f"/api/films/{self.demo['id']}/devis")
        self.assertEqual(status, 200)
        # 1750 brut technicien + 997,50 charges (poste 4, règle 57 %) + 1000 caméra
        # + FG 7 % (262,33) + imprévus 3 % (112,43) = 4 122,26
        self.assertEqual(devis["totaux"]["montant"], 4122.26)
        self.assertEqual(devis["totaux"]["en_region"], 600.0)
        self.assertEqual(devis["totaux"]["hors_region"], 400.0)
        self.assertEqual(devis["totaux"].get("etranger", 0), 0.0)
        self.assertEqual(devis["totaux"]["a_ventiler"], 3122.26)
        self.assertEqual(len([r for r in devis["recap"] if r["code"].isdigit()]), 9)  # neuf grands postes

    def test_02_recette_via_api(self):
        fid = self.film_id
        devis = call("GET", f"/api/films/{fid}/devis")[1]
        rub_son = next(n for p in devis["arbre"] if p["code"] == "2"
                       for n in p["children"] if n["code"] == "23"
                       for n2 in n["children"] if n2["code"] == "237")["id"]
        rub_cam = next(n for p in devis["arbre"] if p["code"] == "7"
                       for n in p["children"] if n["code"] == "71")["id"]
        # 1. technicien 250 €/jour, 2 j prépa + 5 j tournage
        status, r, _ = call("POST", f"/api/films/{fid}/techniciens", {
            "parent_id": rub_son, "fonction_id": self.fonc_son, "salaire": 250.0, "unite": "jour",
            "phases": [{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                       {"phase": "Tournage", "quantite": 5, "unite": "jour"}]})
        self.assertEqual(status, 201)
        fiche = r["fiche"]
        self.assertEqual((fiche["brut"], fiche["charges"], fiche["cout_employeur"]), (1750.0, 700.0, 2450.0))
        tech_id = r["id"]
        # 2. tournage 5 -> 6 jours
        call("PUT", f"/api/techniciens/{tech_id}", {
            "phases": [{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                       {"phase": "Tournage", "quantite": 6, "unite": "jour"}]})
        fiche = call("GET", f"/api/techniciens/{tech_id}")[1]
        self.assertEqual((fiche["brut"], fiche["charges"], fiche["cout_employeur"]), (2000.0, 800.0, 2800.0))
        total_avant = call("GET", f"/api/films/{fid}/devis")[1]["totaux"]["montant"]
        # 3. location caméra 600 + 400
        status, r, _ = call("POST", f"/api/films/{fid}/lignes", {
            "parent_id": rub_cam, "type": "ligne", "libelle": "Location caméra", "unite": "forfait"})
        cam = r["id"]
        d1 = call("POST", f"/api/films/{fid}/lignes", {
            "sous_detail": True, "parent_id": cam, "libelle": "Corps caméra",
            "quantite": 5, "unite": "jour", "cout_unitaire": 120.0})[1]["id"]
        d2 = call("POST", f"/api/films/{fid}/lignes", {
            "sous_detail": True, "parent_id": cam, "libelle": "Série optiques",
            "montant_forfait": 400.0, "unite": "forfait"})[1]["id"]
        tot = call("GET", f"/api/films/{fid}/devis")[1]["totaux"]
        self.assertEqual(tot["montant"], 3800.0)
        self.assertAlmostEqual(tot["montant"] - total_avant, 1000.0)
        # 4. ventilation 600 en région / 400 hors région, personnel à ventiler
        call("POST", f"/api/lignes/{d1}/ventilation", {"mode": "tout_en"})
        call("POST", f"/api/lignes/{d2}/ventilation", {"mode": "tout_hors"})
        v = call("GET", f"/api/films/{fid}/region")[1]
        self.assertEqual((v["totaux"]["en_region"], v["totaux"]["hors_region"], v["totaux"].get("etranger", 0), v["totaux"]["a_ventiler"],
                          v["totaux"]["montant"]), (600.0, 400.0, 0.0, 2800.0, 3800.0))
        self.assertTrue(v["egalite_ok"])
        # bascule des 400 € en région depuis la vue Région
        call("POST", f"/api/lignes/{d2}/ventilation", {"mode": "tout_en"})
        v = call("GET", f"/api/films/{fid}/region")[1]
        self.assertEqual((v["totaux"]["en_region"], v["totaux"]["montant"]), (1000.0, 3800.0))
        # 5. barème commun 250 -> 260 : devis inchangé, aperçu, puis application
        call("PUT", f"/api/fonctions/{self.fonc_son}", {"minimum": 260})
        self.assertEqual(call("GET", f"/api/films/{fid}/devis")[1]["totaux"]["montant"], 3800.0)
        preview = call("POST", f"/api/films/{fid}/baremes/actualiser", {"appliquer": False})[1]
        self.assertEqual(preview["apercu"][0]["nouveau_minimum"], 260.0)
        self.assertEqual(call("GET", f"/api/films/{fid}/devis")[1]["totaux"]["montant"], 3800.0)
        call("POST", f"/api/films/{fid}/baremes/actualiser", {"appliquer": True})
        fiche = call("GET", f"/api/techniciens/{tech_id}")[1]
        self.assertEqual((fiche["brut"], fiche["charges"], fiche["cout_employeur"]), (2080.0, 832.0, 2912.0))
        self.assertEqual(call("GET", f"/api/films/{fid}/devis")[1]["totaux"]["montant"], 3912.0)

    def test_03_export_xlsx_backup_restore_via_api(self):
        fid = self.film_id
        status, blob, ct = call("GET", f"/api/films/{fid}/export.xlsx")
        self.assertEqual(status, 200)
        self.assertIn("spreadsheetml", ct)
        import io, zipfile
        z = zipfile.ZipFile(io.BytesIO(blob))
        self.assertIn("xl/workbook.xml", z.namelist())
        status, backup, _ = call("GET", f"/api/films/{fid}/backup")
        self.assertEqual(status, 200)
        self.assertEqual(backup["format"], "picturial-devis-backup")
        status, r, _ = call("POST", "/api/restaurer", backup)
        self.assertEqual(status, 201)
        t1 = call("GET", f"/api/films/{fid}/devis")[1]["totaux"]
        t2 = call("GET", f"/api/films/{r['id']}/devis")[1]["totaux"]
        self.assertEqual(t1, t2)
        # vue imprimable
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/print/{fid}", timeout=10) as resp:
            html = resp.read().decode()
        self.assertIn("Récapitulatif", html)
        self.assertIn("TOTAL GÉNÉRAL", html)

    def test_04_dupliquer_supprimer_film(self):
        fid = self.film_id
        nid = call("POST", f"/api/films/{fid}/dupliquer")[1]["id"]
        self.assertEqual(call("GET", f"/api/films/{nid}/devis")[1]["totaux"],
                         call("GET", f"/api/films/{fid}/devis")[1]["totaux"])
        status, _, _ = call("DELETE", f"/api/films/{nid}")
        self.assertEqual(status, 200)
        status, body, _ = call("GET", f"/api/films/{nid}/devis")
        self.assertEqual(status, 404)

    def test_05_changement_region_avec_confirmation(self):
        fid = self.film_id
        status, body, _ = call("PUT", f"/api/films/{fid}", {"region_cible": "Bretagne"})
        self.assertEqual(status, 409)
        self.assertTrue(body["confirmation_requise"])
        status, body, _ = call("PUT", f"/api/films/{fid}",
                               {"region_cible": "Bretagne", "option_ventilation": "conserver"})
        self.assertEqual(status, 200)
        self.assertEqual(body["region"], "Bretagne")

    def test_06_unite_incompatible_refusee(self):
        fid = self.film_id
        devis = call("GET", f"/api/films/{fid}/devis")[1]
        rub_son = next(n for p in devis["arbre"] if p["code"] == "2"
                       for n in p["children"] if n["code"] == "23"
                       for n2 in n["children"] if n2["code"] == "237")["id"]
        fonc_sem = next(f["id"] for g in self.ref["conventions"][0]["grilles"] for f in g["fonctions"]
                        if f["unite"] == "semaine")
        status, body, _ = call("POST", f"/api/films/{fid}/techniciens", {
            "parent_id": rub_son, "fonction_id": fonc_sem, "salaire": 1300.0, "unite": "jour",
            "phases": [{"phase": "Tournage", "quantite": 5, "unite": "jour"}]})
        self.assertEqual(status, 400)
        self.assertIn("semaine", body["erreur"])

    def test_07_personnel_page2(self):
        fid = self.film_id
        status, v, _ = call("GET", f"/api/films/{fid}/personnel")
        self.assertEqual(status, 200)
        self.assertEqual(v["poste"]["code"], "2")
        codes = set()
        def walk(nodes):
            for n in nodes:
                if n.get("code"):
                    codes.add(n["code"])
                walk(n.get("children", []))
        walk(v["poste"]["children"])
        self.assertIn("2336", codes)
        self.assertIn("237", codes)

        def trouve(nodes, code):
            for n in nodes:
                if n.get("code") == code:
                    return n
                x = trouve(n.get("children", []), code)
                if x:
                    return x
            return None

        # engagement sur la fonction 2336 (Scripte) du poste 2
        devis = call("GET", f"/api/films/{fid}/devis")[1]
        id_2336 = trouve(devis["arbre"], "2336")["id"]
        status, r, _ = call("POST", f"/api/films/{fid}/techniciens", {
            "parent_id": id_2336, "fonction_id": self.fonc_son, "salaire": 250.0, "unite": "jour",
            "phases": [{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                       {"phase": "Tournage", "quantite": 5, "unite": "jour"}]})
        self.assertEqual(status, 201)
        v = call("GET", f"/api/films/{fid}/personnel")[1]
        f2336 = trouve(v["poste"]["children"], "2336")
        tech = next(c for c in f2336["children"] if c["type"] == "technicien")
        self.assertEqual(len(tech["phases"]), 2)
        ph = next(p for p in tech["phases"] if p["phase"] == "Tournage")
        self.assertEqual(ph["montant"], 1250.0)  # 5 j x 250 €
        # ventilation de la phase en région via l'API, comme dans la vue
        call("POST", f"/api/lignes/{ph['ligne_id']}/ventilation", {"mode": "tout_en"})
        v = call("GET", f"/api/films/{fid}/personnel")[1]
        f2336 = trouve(v["poste"]["children"], "2336")
        tech = next(c for c in f2336["children"] if c["type"] == "technicien")
        ph = next(p for p in tech["phases"] if p["phase"] == "Tournage")
        self.assertEqual(ph["en_region"], 1250.0)
        self.assertEqual(v["totaux_poste"]["en_region"], 1250.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
