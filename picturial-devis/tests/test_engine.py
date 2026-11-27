#!/usr/bin/env python3
# Tests du moteur de calcul : recette complète, double comptage, persistance, sauvegarde, export.
import json
import os
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import engine
from xlsx_export import export_xlsx_bytes


def nouveau_contexte():
    tmp = tempfile.mkdtemp(prefix="picturial-test-")
    conn = db.initialiser(os.path.join(tmp, "devis.db"))
    return conn, tmp


def trouver_ligne(conn, film_id, libelle, type_ligne=None):
    q = "SELECT * FROM lignes WHERE film_id=? AND libelle LIKE ?"
    args = [film_id, "%" + libelle + "%"]
    if type_ligne:
        q += " AND type=?"
        args.append(type_ligne)
    rows = conn.execute(q, args).fetchall()
    assert rows, f"ligne '{libelle}' introuvable"
    return rows[0]


def rubrique(conn, film_id, poste_lib, rub_lib):
    return conn.execute(
        "SELECT l.id FROM lignes l JOIN lignes p ON l.parent_id=p.id WHERE l.film_id=? AND l.type='rubrique'"
        " AND l.libelle=? AND p.libelle=?", (film_id, rub_lib, poste_lib)).fetchone()["id"]


def ligne_par_code(conn, film_id, code):
    return conn.execute("SELECT id FROM lignes WHERE film_id=? AND code=?", (film_id, code)).fetchone()["id"]


class RecetteTest(unittest.TestCase):
    """Scénario de recette de bout en bout, valeurs de démonstration."""

    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        self.film_id = db.creer_film(self.conn, "Film test recette", region="Île-de-France", taux_charges=0.40, frais_generaux=False, charges_mode="avec")
        self.fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        self.rub_son = ligne_par_code(self.conn, self.film_id, "237")
        self.rub_cam = ligne_par_code(self.conn, self.film_id, "71")

    def test_01_technicien_250e_2j_5j(self):
        tech_id = engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], nom="",
            salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 5, "unite": "jour"}])
        fiche = engine.fiche_technicien(self.conn, tech_id)
        self.assertEqual(fiche["brut"], 1750.00)
        self.assertEqual(fiche["charges"], 700.00)
        self.assertEqual(fiche["cout_employeur"], 2450.00)
        self.assertEqual(engine.compute_film(self.conn, self.film_id)["totaux"]["montant"], 2450.00)

    def test_02_tournage_6_jours_delta_350(self):
        tech_id = engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 5, "unite": "jour"}])
        avant = engine.compute_film(self.conn, self.film_id)["totaux"]["montant"]
        engine.modifier_technicien(self.conn, tech_id, phases=[
            {"phase": "Préparation", "quantite": 2, "unite": "jour"},
            {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        fiche = engine.fiche_technicien(self.conn, tech_id)
        self.assertEqual(fiche["brut"], 2000.00)
        self.assertEqual(fiche["charges"], 800.00)
        self.assertEqual(fiche["cout_employeur"], 2800.00)
        apres = engine.compute_film(self.conn, self.film_id)["totaux"]["montant"]
        self.assertEqual(apres - avant, 350.00)

    def test_03_location_camera_600_400(self):
        tech_id = engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait")
        d1 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                        quantite=5, unite="jour", cout_unitaire=120.0, reprendre=None)
        d2 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Série optiques",
                                        montant_forfait=400.0, unite="forfait", reprendre=None)
        calc = engine.compute_film(self.conn, self.film_id)
        self.assertEqual(calc["totaux"]["montant"], 3800.00)
        cam_node = next(n for n in _iter(calc["arbre"]) if n["id"] == cam)
        self.assertEqual(cam_node["montant"], 1000.00)
        self.assertEqual(cam_node["statut_montant"], "calcule")

    def test_04_ventilation_600_en_400_hors(self):
        tech_id = engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait")
        d1 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                        quantite=5, unite="jour", cout_unitaire=120.0, reprendre=None)
        d2 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Série optiques",
                                        montant_forfait=400.0, unite="forfait", reprendre=None)
        engine.set_ventilation(self.conn, self.film_id, d1, mode="tout_en")
        engine.set_ventilation(self.conn, self.film_id, d2, mode="tout_hors")
        v = engine.vue_region(self.conn, self.film_id)
        self.assertEqual(v["totaux"]["en_region"], 600.00)
        self.assertEqual(v["totaux"]["hors_region"], 400.00)
        self.assertEqual(v["totaux"]["a_ventiler"], 2800.00)
        self.assertEqual(engine.r2(v["totaux"]["en_region"] + v["totaux"]["hors_region"] + v["totaux"]["a_ventiler"]),
                         v["totaux"]["montant"])
        self.assertEqual(v["totaux"]["montant"], 3800.00)
        self.assertTrue(v["egalite_ok"])
        # bascule des 400 € en région depuis la vue Région : total inchangé
        engine.set_ventilation(self.conn, self.film_id, d2, mode="tout_en")
        v2 = engine.vue_region(self.conn, self.film_id)
        self.assertEqual(v2["totaux"]["en_region"], 1000.00)
        self.assertEqual(v2["totaux"]["hors_region"], 0.00)
        self.assertEqual(v2["totaux"]["a_ventiler"], 2800.00)
        self.assertEqual(v2["totaux"]["montant"], 3800.00)

    def test_05_bareme_250_260_devis_inchange_sans_actualisation(self):
        tech_id = engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait")
        engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                   quantite=5, unite="jour", cout_unitaire=120.0, reprendre=None)
        engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Série optiques",
                                   montant_forfait=400.0, unite="forfait", reprendre=None)
        self.conn.execute("UPDATE fonctions SET minimum=260 WHERE id=?", (self.fonc["id"],))
        self.conn.commit()
        # le devis garde ses chiffres tant que l'actualisation n'est pas validée
        self.assertEqual(engine.compute_film(self.conn, self.film_id)["totaux"]["montant"], 3800.00)
        preview = engine.actualiser_baremes(self.conn, self.film_id, appliquer=False)
        self.assertFalse(preview["applique"])
        self.assertEqual(len(preview["apercu"]), 1)
        a = preview["apercu"][0]
        self.assertEqual(a["ancien_minimum"], 250.0)
        self.assertEqual(a["nouveau_minimum"], 260.0)
        self.assertEqual(a["nouveau_salaire"], 260.0)
        self.assertEqual(a["impact_brut"], 80.0)  # 8 jours x 10 €
        # toujours inchangé après l'aperçu
        self.assertEqual(engine.compute_film(self.conn, self.film_id)["totaux"]["montant"], 3800.00)
        res = engine.actualiser_baremes(self.conn, self.film_id, appliquer=True)
        self.assertTrue(res["applique"])
        fiche = engine.fiche_technicien(self.conn, tech_id)
        self.assertEqual(fiche["brut"], 2080.00)   # 8 x 260
        self.assertEqual(fiche["charges"], 832.00)
        self.assertEqual(fiche["cout_employeur"], 2912.00)
        self.assertEqual(engine.compute_film(self.conn, self.film_id)["totaux"]["montant"], 3912.00)

    def test_06_persistance_fermeture_reouverture(self):
        engine.ajouter_technicien(
            self.conn, self.film_id, self.rub_son, self.fonc["id"], salaire=250.0, unite="jour",
            phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                    {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        self.conn.close()
        conn2 = db.connect(os.path.join(self.tmp, "devis.db"))
        calc = engine.compute_film(conn2, self.film_id)
        self.assertEqual(calc["totaux"]["montant"], 2800.00)
        self.conn = conn2


class ReglesMetierTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        self.film_id = db.creer_film(self.conn, "Film règles", region="Île-de-France", taux_charges=0.40, frais_generaux=False)  # mode poste_dedie par défaut
        self.rub_son = ligne_par_code(self.conn, self.film_id, "237")
        self.rub_cam = ligne_par_code(self.conn, self.film_id, "71")

    def test_forfait_detail_reprendre_pas_de_double_comptage(self):
        # estimation forfaitaire de 2000 €, puis sous-détail en reprenant l'estimation
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait", montant_forfait=2000.0)
        d1 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                        montant_forfait=2000.0, unite="forfait", reprendre=True)
        calc = engine.compute_film(self.conn, self.film_id)
        node = next(n for n in _iter(calc["arbre"]) if n["id"] == cam)
        self.assertEqual(node["montant"], 2000.0)  # pas 4000
        # ajouter un second sous-détail : le total suit les enfants
        engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Optiques", montant_forfait=500.0, unite="forfait")
        calc = engine.compute_film(self.conn, self.film_id)
        node = next(n for n in _iter(calc["arbre"]) if n["id"] == cam)
        self.assertEqual(node["montant"], 2500.0)
        self.assertEqual(calc["totaux"]["montant"], 2500.0)

    def test_forfait_detail_remplacer(self):
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait", montant_forfait=2000.0)
        engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                   montant_forfait=600.0, unite="forfait", reprendre=False)
        calc = engine.compute_film(self.conn, self.film_id)
        self.assertEqual(calc["totaux"]["montant"], 600.0)  # l'estimation est remplacée, pas additionnée

    def test_bareme_hebdomadaire_pas_de_division_auto(self):
        fonc_sem = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur image'").fetchone()
        with self.assertRaises(engine.Erreur) as ctx:
            engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc_sem["id"],
                                      salaire=fonc_sem["minimum"], unite="jour",
                                      phases=[{"phase": "Tournage", "quantite": 5, "unite": "jour"}])
        self.assertIn("semaine", str(ctx.exception))
        # avec hypothèse manuelle explicite, c'est accepté et signalé
        tid = engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc_sem["id"],
                                        salaire=fonc_sem["minimum"], unite="jour", hypothese_manuelle=True,
                                        phases=[{"phase": "Tournage", "quantite": 5, "unite": "jour"}])
        fiche = engine.fiche_technicien(self.conn, tid)
        self.assertTrue(fiche["avertissements"])
        self.assertTrue(any("hypothèse manuelle" in w for w in fiche["avertissements"]))

    def test_salaire_inferieur_minimum_avertissement(self):
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        tid = engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc["id"],
                                        salaire=200.0, unite="jour",
                                        phases=[{"phase": "Tournage", "quantite": 3, "unite": "jour"}])
        fiche = engine.fiche_technicien(self.conn, tid)
        self.assertEqual(fiche["brut"], 600.0)
        self.assertTrue(any("inférieur au minimum" in w for w in fiche["avertissements"]))

    def test_charges_poste_dedie_chaque_euro_une_fois(self):
        # mode par défaut v2 : poste_dedie -> aucune ligne de charges par technicien,
        # le poste 4 (ligne 44) calcule 57 % de l'équipe technique ; chaque euro compté une fois.
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        tid = engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc["id"],
                                        salaire=250.0, unite="jour",
                                        phases=[{"phase": "Tournage", "quantite": 4, "unite": "jour"}])
        self.assertIsNone(self.conn.execute(
            "SELECT id FROM lignes WHERE type='charge' AND technicien_id=?", (tid,)).fetchone())
        calc = engine.compute_film(self.conn, self.film_id)
        by_code = {n["code"]: n for n in _iter(calc["arbre"])}
        self.assertEqual(by_code["237"]["montant"], 1000.0)   # brut
        self.assertEqual(by_code["44"]["montant"], 570.0)      # 57 % de l'équipe technique
        self.assertEqual(calc["totaux"]["montant"], 1570.0)    # 1000 + 570, une seule fois
        fiche = engine.fiche_technicien(self.conn, tid)
        self.assertEqual(fiche["brut"], 1000.0)
        self.assertEqual(fiche["charges"], 400.0)              # estimation au taux du film (40 %)
        self.assertEqual(fiche["cout_employeur"], 1400.0)

    def test_salaire_negocie_preserve_a_actualisation(self):
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        tid = engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc["id"],
                                        salaire=300.0, unite="jour",  # négocié au-dessus du minimum 250
                                        phases=[{"phase": "Tournage", "quantite": 2, "unite": "jour"}])
        self.conn.execute("UPDATE fonctions SET minimum=400 WHERE id=?", (fonc["id"],))
        self.conn.commit()
        preview = engine.actualiser_baremes(self.conn, self.film_id, appliquer=True)
        a = preview["apercu"][0]
        self.assertEqual(a["nouveau_salaire"], 300.0)  # négocié conservé
        self.assertTrue(a["sous_minimum"])             # mais signalé sous le nouveau minimum
        fiche = engine.fiche_technicien(self.conn, tid)
        self.assertEqual(fiche["brut"], 600.0)
        self.assertTrue(any("minimum actuel" in w for w in fiche["avertissements"]))

    def test_changement_region_confirmation_requise(self):
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait", montant_forfait=1000.0)
        engine.set_ventilation(self.conn, self.film_id, cam, mode="tout_en")
        with self.assertRaises(engine.Erreur) as ctx:
            engine.changer_region_cible(self.conn, self.film_id, "Bretagne")
        self.assertTrue(ctx.exception.confirmation_requise)
        res = engine.changer_region_cible(self.conn, self.film_id, "Bretagne", option="reinitialiser")
        self.assertEqual(res["region"], "Bretagne")
        v = engine.vue_region(self.conn, self.film_id)
        self.assertEqual(v["totaux"]["en_region"], 0.0)
        self.assertEqual(v["totaux"]["a_ventiler"], 1000.0)
        res = engine.changer_region_cible(self.conn, self.film_id, "Occitanie", option="conserver")
        self.assertEqual(res["change"], True)

    def test_deplacer_et_supprimer(self):
        cam = engine.ajouter_ligne(self.conn, self.film_id, self.rub_cam, type_ligne="ligne",
                                   libelle="Caméra", unite="forfait", montant_forfait=100.0)
        rub_son2 = ligne_par_code(self.conn, self.film_id, "235")
        engine.deplacer_ligne(self.conn, cam, rub_son2)
        row = self.conn.execute("SELECT parent_id FROM lignes WHERE id=?", (cam,)).fetchone()
        self.assertEqual(row["parent_id"], rub_son2)
        with self.assertRaises(engine.Erreur):
            engine.deplacer_ligne(self.conn, rub_son2, cam)  # dans son propre descendant
        engine.supprimer_ligne(self.conn, cam)
        self.assertIsNone(self.conn.execute("SELECT id FROM lignes WHERE id=?", (cam,)).fetchone())

    def test_arrondi_centime(self):
        self.assertEqual(engine.r2(10.005), 10.01)   # demi au supérieur
        self.assertEqual(engine.r2(2.675), 2.68)
        self.assertEqual(engine.fmt_fr(1750), "1 750,00 €")


class SauvegardeExportTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        self.film_id = db.creer_film(self.conn, "Film export", region="Île-de-France", taux_charges=0.40, frais_generaux=False, charges_mode="avec")
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        rub_son = ligne_par_code(self.conn, self.film_id, "237")
        rub_cam = ligne_par_code(self.conn, self.film_id, "71")
        engine.ajouter_technicien(self.conn, self.film_id, rub_son, fonc["id"], salaire=250.0, unite="jour",
                                  phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                                          {"phase": "Tournage", "quantite": 6, "unite": "jour"}])
        cam = engine.ajouter_ligne(self.conn, self.film_id, rub_cam, type_ligne="ligne",
                                   libelle="Location caméra", unite="forfait")
        d1 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                        quantite=5, unite="jour", cout_unitaire=120.0, reprendre=None)
        d2 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Série optiques",
                                        montant_forfait=400.0, unite="forfait", reprendre=None)
        engine.set_ventilation(self.conn, self.film_id, d1, mode="tout_en")
        engine.set_ventilation(self.conn, self.film_id, d2, mode="tout_hors")

    def test_backup_restore_memes_totaux(self):
        data = engine.backup_projet(self.conn, self.film_id)
        json.dumps(data)  # sérialisable
        nouveau = engine.restaurer_projet(self.conn, data)
        c1 = engine.compute_film(self.conn, self.film_id)["totaux"]
        c2 = engine.compute_film(self.conn, nouveau)["totaux"]
        self.assertEqual(c1, c2)
        self.assertEqual(c1["montant"], 3800.0)
        v1 = engine.vue_region(self.conn, self.film_id)
        v2 = engine.vue_region(self.conn, nouveau)
        self.assertEqual(v1["totaux"], v2["totaux"])
        # snapshot de barème conservé dans la restauration
        t1 = self.conn.execute("SELECT * FROM techniciens WHERE film_id=?", (self.film_id,)).fetchone()
        t2 = self.conn.execute("SELECT * FROM techniciens WHERE film_id=?", (nouveau,)).fetchone()
        self.assertEqual(t1["minimum_snapshot"], t2["minimum_snapshot"])
        self.assertEqual(t1["salaire"], t2["salaire"])

    def test_dupliquer_film(self):
        nid = engine.dupliquer_film(self.conn, self.film_id)
        c1 = engine.compute_film(self.conn, self.film_id)["totaux"]
        c2 = engine.compute_film(self.conn, nid)["totaux"]
        self.assertEqual(c1, c2)
        titre = self.conn.execute("SELECT titre FROM films WHERE id=?", (nid,)).fetchone()["titre"]
        self.assertIn("(copie)", titre)

    def test_export_xlsx_relecture(self):
        data, nom = export_xlsx_bytes(self.conn, self.film_id)
        self.assertTrue(nom.endswith(".xlsx"))
        z = zipfile.ZipFile(__import__("io").BytesIO(data))
        noms = z.namelist()
        self.assertIn("xl/workbook.xml", noms)
        self.assertGreaterEqual(len([n for n in noms if n.startswith("xl/worksheets/sheet")]), 4)
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        # onglet Récapitulatif : total général en cellule numérique
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        valeurs = {}
        for c in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
            ref = c.get("r")
            v = c.find("m:v", ns)
            t = c.get("t")
            if v is not None:
                valeurs[ref] = (t, v.text)
        nums = {r: float(v) for r, (t, v) in valeurs.items() if t is None}
        self.assertIn(3800.0, nums.values())      # total général numérique
        self.assertIn(600.0, nums.values())        # en région
        self.assertIn(400.0, nums.values())        # hors région
        self.assertIn(2800.0, nums.values())       # à ventiler
        # onglet Détail : contient les intitulés
        tout = " ".join(z.read(n).decode("utf-8") for n in noms if n.startswith("xl/worksheets/sheet"))
        self.assertIn("Location cam", tout)
        self.assertIn("Corps cam", tout)
        self.assertIn("Charges employeur", tout)
        wb = z.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("Devis (g", wb)                 # onglet général
        self.assertIn("2. Personnel", wb)             # un onglet par poste, comme le modèle
        self.assertIn("Ventilation territoriale", wb)


def _iter(roots):
    for n in roots:
        yield n
        yield from _iter(n["children"])


class V2CncTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()

    def test_minimas_ccnpc_importes(self):
        conv = self.conn.execute("SELECT * FROM conventions WHERE nom LIKE 'CCNPC%'").fetchone()
        self.assertIsNotNone(conv)
        grille = self.conn.execute("SELECT * FROM grilles WHERE convention_id=? AND version LIKE 'Annexe 1%'", (conv["id"],)).fetchone()
        self.assertIsNotNone(grille)
        self.assertEqual(grille["statut"], "verifie")
        self.assertIn("PCINE", grille["source"])
        self.assertEqual(grille["date_effet"], "2026-06-01")
        f = self.conn.execute("SELECT * FROM fonctions WHERE grille_id=? AND nom='Chef opérateur du son cinéma'", (grille["id"],)).fetchone()
        self.assertIsNotNone(f)
        self.assertAlmostEqual(f["minimum"], 1930.05755, places=4)
        self.assertEqual(f["unite"], "semaine")
        self.assertEqual(f["statut"], "verifie")
        nb = self.conn.execute("SELECT COUNT(*) AS n FROM fonctions WHERE convention_id=?", (conv["id"],)).fetchone()["n"]
        self.assertGreater(nb, 150)

    def test_vieille_base_recoit_la_ccnpc_au_demarrage(self):
        # base v1 (convention démo seule) : initialiser() doit importer la CCNPC quand même
        import sqlite3
        tmp2 = tempfile.mkdtemp(prefix="picturial-old-")
        conn2 = sqlite3.connect(os.path.join(tmp2, "old.db"))
        conn2.row_factory = sqlite3.Row
        conn2.executescript(db.SCHEMA)
        conn2.execute("INSERT INTO conventions (id, nom, description) VALUES ('c1', 'Convention de démonstration (montants fictifs)', '')")
        conn2.commit()
        conn2.close()
        conn2 = db.connect(os.path.join(tmp2, "old.db"))
        db.seed_referentiel(conn2)
        conv = conn2.execute("SELECT * FROM conventions WHERE nom LIKE 'CCNPC%'").fetchone()
        self.assertIsNotNone(conv)
        nb = conn2.execute("SELECT COUNT(*) AS n FROM fonctions WHERE convention_id=?", (conv["id"],)).fetchone()["n"]
        self.assertGreater(nb, 150)
        conn2.close()

    def test_nomenclature_cnc_et_charges_poste4(self):
        film_id = db.creer_film(self.conn, "Film CNC", taux_charges=0.57)
        calc = engine.compute_film(self.conn, film_id)
        codes = [r["code"] for r in calc["recap"]]
        self.assertEqual([c for c in codes if c.isdigit()], ["1","2","3","4","5","6","7","8","9"])
        self.assertIn("FG", codes); self.assertIn("IMP", codes)
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        engine.ajouter_technicien(self.conn, film_id, ligne_par_code(self.conn, film_id, "237"), fonc["id"],
                                  salaire=1000.0, unite="jour",
                                  phases=[{"phase": "Tournage", "quantite": 4, "unite": "jour"}])
        calc = engine.compute_film(self.conn, film_id)
        by_code = {}
        for n in _iter(calc["arbre"]):
            by_code[n["code"]] = n
        self.assertEqual(by_code["237"]["montant"], 4000.0)      # 4 j x 1000 €
        self.assertEqual(by_code["44"]["montant"], 2280.0)       # 57 % de l'équipe technique (poste 2 hors 21/22)
        postes_1_9 = sum(by_code[str(i)]["montant"] for i in range(1, 10))
        self.assertEqual(postes_1_9, 6280.0)
        self.assertEqual(by_code["FG"]["montant"], engine.r2(0.07 * 6280.0))   # 439,60
        self.assertEqual(by_code["IMP"]["montant"], engine.r2(0.03 * 6280.0))  # 188,40
        self.assertEqual(calc["totaux"]["montant"], engine.r2(6280.0 + 439.60 + 188.40))  # 6 908,00

    def test_ventilation_etranger(self):
        film_id = db.creer_film(self.conn, "Film étranger", frais_generaux=False)
        cam = engine.ajouter_ligne(self.conn, film_id, ligne_par_code(self.conn, film_id, "71"),
                                   type_ligne="ligne", libelle="Location caméra", unite="forfait", montant_forfait=1000.0)
        engine.set_ventilation(self.conn, film_id, cam, mode="tout_en", en_region=600.0)
        # mode partiel multi-feuilles impossible ici (1 feuille) : on pose 600 en région, 400 étranger
        engine.set_ventilation(self.conn, film_id, cam, mode="partiel", en_region=600.0, etranger=400.0)
        v = engine.vue_region(self.conn, film_id)
        self.assertEqual(v["totaux"]["en_region"], 600.0)
        self.assertEqual(v["totaux"]["hors_region"], 0.0)
        self.assertEqual(v["totaux"]["etranger"], 400.0)
        self.assertEqual(v["totaux"]["a_ventiler"], 0.0)
        self.assertTrue(v["egalite_ok"])
        engine.set_ventilation(self.conn, film_id, cam, mode="tout_etranger")
        v = engine.vue_region(self.conn, film_id)
        self.assertEqual((v["totaux"]["etranger"], v["totaux"]["montant"]), (1000.0, 1000.0))
        self.assertTrue(v["egalite_ok"])


class Page2PersonnelTest(unittest.TestCase):
    """Page 2 « Personnel » : nomenclature fidèle à l'onglet Excel 2.Personnel + vue phases × région/France."""

    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        conv = self.conn.execute("SELECT id FROM conventions WHERE nom LIKE '%démonstration%'").fetchone()
        grille = self.conn.execute("SELECT id, date_effet FROM grilles WHERE convention_id=? ORDER BY rowid LIMIT 1",
                                   (conv["id"],)).fetchone()
        self.film_id = db.creer_film(self.conn, "Film page 2", convention_id=conv["id"], grille_id=grille["id"],
                                      date_ref=grille["date_effet"], taux_charges=0.40, frais_generaux=False)

    def _poste2(self):
        calc = engine.compute_film(self.conn, self.film_id)
        return next(r for r in calc["arbre"] if r["code"] == "2")

    @staticmethod
    def _trouve(nodes, code):
        for n in nodes:
            if n.get("code") == code:
                return n
            r = Page2PersonnelTest._trouve(n.get("children", []), code)
            if r:
                return r
        return None

    def test_nomenclature_poste2_fidele_au_modele(self):
        poste = self._poste2()
        codes = {n["code"] for n in _iter([poste])}
        for c in ["21", "22", "23", "24", "25", "26", "27", "28", "29",
                  "211", "221", "231", "2311", "2336", "2391", "241", "2411",
                  "251", "2511", "261", "2621", "271", "2711", "281", "291"]:
            self.assertIn(c, codes)
        nb_details = sum(1 for n in _iter([poste]) if n["type"] == "detail")
        self.assertGreaterEqual(nb_details, 190)
        by_code = {n["code"]: n for n in _iter([poste])}
        self.assertEqual(by_code["235"]["libelle"], "Prise de vues")
        self.assertEqual(by_code["2336"]["libelle"], "Scripte")

    def test_vue_personnel_phases_ventilation_et_suggestion(self):
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Scripte'").fetchone()
        id_2336 = ligne_par_code(self.conn, self.film_id, "2336")
        engine.ajouter_technicien(self.conn, self.film_id, id_2336, fonc["id"],
                                  salaire=180.0, unite="jour",
                                  phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                                          {"phase": "Tournage", "quantite": 5, "unite": "jour"},
                                          {"phase": "Finitions", "quantite": 1, "unite": "jour"}])
        v = engine.vue_personnel(self.conn, self.film_id)
        self.assertEqual(v["poste"]["code"], "2")
        f2336 = self._trouve(v["poste"]["children"], "2336")
        self.assertIsNotNone(f2336)
        self.assertIsNotNone(f2336.get("fonction_suggeree"))
        self.assertEqual(f2336["fonction_suggeree"]["nom"], "Scripte")
        tech = next(c for c in f2336["children"] if c["type"] == "technicien")
        self.assertEqual(len(tech["phases"]), 3)
        ph_tournage = next(p for p in tech["phases"] if p["phase"] == "Tournage")
        self.assertEqual(ph_tournage["montant"], 900.0)  # 5 j x 180 €
        # ventilation de la phase « Tournage » en région (colonne « En région » = bloc G–P du modèle)
        engine.set_ventilation(self.conn, self.film_id, ph_tournage["ligne_id"], mode="tout_en")
        v = engine.vue_personnel(self.conn, self.film_id)
        f2336 = self._trouve(v["poste"]["children"], "2336")
        tech = next(c for c in f2336["children"] if c["type"] == "technicien")
        ph = next(p for p in tech["phases"] if p["phase"] == "Tournage")
        self.assertEqual((ph["en_region"], ph["hors_region"], ph["a_ventiler"]), (900.0, 0.0, 0.0))
        # totaux du poste 2 identiques au moteur unique
        poste = self._poste2()
        self.assertEqual(v["totaux_poste"]["montant"], poste["montant"])
        self.assertEqual(v["totaux_poste"]["montant"], 1440.0)  # 8 j x 180 €
        self.assertEqual(v["totaux_poste"]["en_region"], 900.0)

    def test_technicien_sur_fonction_avec_estimation_reprendre_remplacer(self):
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Scripte'").fetchone()
        id_2336 = ligne_par_code(self.conn, self.film_id, "2336")
        engine.modifier_ligne(self.conn, id_2336, {"montant_forfait": 1000.0})
        # sans choix explicite -> refus avec demande de confirmation
        with self.assertRaises(engine.Erreur) as ctx:
            engine.ajouter_technicien(self.conn, self.film_id, id_2336, fonc["id"], salaire=180.0, unite="jour",
                                      phases=[{"phase": "Tournage", "quantite": 5, "unite": "jour"}])
        self.assertTrue(ctx.exception.confirmation_requise)
        # « remplacer » : l'estimation disparaît, aucun double comptage
        engine.ajouter_technicien(self.conn, self.film_id, id_2336, fonc["id"], salaire=180.0, unite="jour",
                                  phases=[{"phase": "Tournage", "quantite": 5, "unite": "jour"}], reprendre=False)
        self.assertEqual(self._poste2()["montant"], 900.0)
        # « reprendre » sur une autre fonction : l'estimation est conservée comme sous-détail + l'engagement
        id_2337 = ligne_par_code(self.conn, self.film_id, "2337")
        engine.modifier_ligne(self.conn, id_2337, {"montant_forfait": 500.0})
        engine.ajouter_technicien(self.conn, self.film_id, id_2337, fonc["id"], salaire=180.0, unite="jour",
                                  phases=[{"phase": "Tournage", "quantite": 2, "unite": "jour"}], reprendre=True)
        self.assertEqual(self._poste2()["montant"], 900.0 + 500.0 + 360.0)


class Page1DroitsTest(unittest.TestCase):
    """Page 1 « Droits artistiques » : saisie façon onglet Excel (G/H en inputs, I = G+H dérivé)."""

    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        self.film_id = db.creer_film(self.conn, "Film page 1", frais_generaux=False)

    def test_ventilation_derive_le_total_quand_ligne_vide(self):
        id_11 = ligne_par_code(self.conn, self.film_id, "11")
        # ligne vide : saisir H = 80 000 € (colonne H du modèle) -> le total I se calcule tout seul
        engine.set_ventilation(self.conn, self.film_id, id_11, mode="partiel", hors_region=80000.0)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["code"] == "11")
        self.assertEqual(n["montant"], 80000.0)
        self.assertEqual((n["en_region"], n["hors_region"], n["a_ventiler"]), (0.0, 80000.0, 0.0))
        # puis G = 20 000 € en plus -> total 100 000 € (I = G + H à chaque saisie)
        engine.set_ventilation(self.conn, self.film_id, id_11, mode="partiel", en_region=20000.0, hors_region=80000.0)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["code"] == "11")
        self.assertEqual(n["montant"], 100000.0)
        self.assertEqual((n["en_region"], n["hors_region"]), (20000.0, 80000.0))

    def test_total_saisi_explicitement_borne_la_ventilation(self):
        id_12 = ligne_par_code(self.conn, self.film_id, "12")
        engine.modifier_ligne(self.conn, id_12, {"montant_forfait": 60000.0})
        engine.set_ventilation(self.conn, self.film_id, id_12, mode="partiel", hors_region=60000.0)
        # une fois le total saisi, G + H + étranger ne doit pas le dépasser
        with self.assertRaises(engine.Erreur):
            engine.set_ventilation(self.conn, self.film_id, id_12, mode="partiel", en_region=1000.0, hors_region=60000.0)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["code"] == "12")
        self.assertEqual((n["montant"], n["hors_region"], n["a_ventiler"]), (60000.0, 60000.0, 0.0))
        # effacer le total -> retour en mode dérivé
        engine.modifier_ligne(self.conn, id_12, {"montant_forfait": None})
        engine.set_ventilation(self.conn, self.film_id, id_12, mode="partiel", en_region=10000.0, hors_region=60000.0)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["code"] == "12")
        self.assertEqual(n["montant"], 70000.0)

    def test_ligne_qte_cout_jamais_derivee(self):
        id_71 = ligne_par_code(self.conn, self.film_id, "71")
        cam = engine.ajouter_ligne(self.conn, self.film_id, id_71, type_ligne="ligne", libelle="Location caméra", unite="forfait")
        d1 = engine.ajouter_sous_detail(self.conn, self.film_id, cam, libelle="Corps caméra",
                                        quantite=5, unite="jour", cout_unitaire=120.0, reprendre=None)
        engine.set_ventilation(self.conn, self.film_id, d1, mode="partiel", en_region=600.0)
        with self.assertRaises(engine.Erreur):
            engine.set_ventilation(self.conn, self.film_id, d1, mode="partiel", en_region=700.0)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["id"] == d1)
        self.assertEqual((n["montant"], n["en_region"]), (600.0, 600.0))

    def test_aucun_code_invente_pour_ligne_sans_code(self):
        id_14 = ligne_par_code(self.conn, self.film_id, "14")
        d = engine.ajouter_sous_detail(self.conn, self.film_id, id_14,
                                      libelle="Droits Vladimir Cosma — musique originale",
                                      montant_forfait=15000.0, unite="forfait", reprendre=None)
        calc = engine.compute_film(self.conn, self.film_id)
        n = next(x for x in _iter(calc["arbre"]) if x["id"] == d)
        self.assertEqual(n["chemin"], "")   # pas de « 1.41 » / « 1.10 » inventé
        self.assertEqual(n["code"], "")
        self.assertEqual(n["montant"], 15000.0)
        rub = next(x for x in _iter(calc["arbre"]) if x["code"] == "14")
        self.assertEqual(rub["montant"], 15000.0)  # le total de la rubrique suit

    def test_dupliquer_ligne_repare(self):
        # régression : dupliquer_ligne plantait (sqlite3.Row sans .get)
        id_11 = ligne_par_code(self.conn, self.film_id, "11")
        engine.modifier_ligne(self.conn, id_11, {"montant_forfait": 100.0})
        nid = engine.dupliquer_ligne(self.conn, id_11)
        row = self.conn.execute("SELECT * FROM lignes WHERE id=?", (nid,)).fetchone()
        self.assertEqual(row["montant_forfait"], 100.0)
        self.assertEqual(row["montant_saisi"], 1)
        self.assertIn("(copie)", row["libelle"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
