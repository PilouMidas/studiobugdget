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


class RecetteTest(unittest.TestCase):
    """Scénario de recette de bout en bout, valeurs de démonstration."""

    def setUp(self):
        self.conn, self.tmp = nouveau_contexte()
        self.film_id = db.creer_film(self.conn, "Film test recette", region="Île-de-France", taux_charges=0.40)
        self.fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        self.rub_son = rubrique(self.conn, self.film_id, "Personnel technique", "Son")
        self.rub_cam = rubrique(self.conn, self.film_id, "Moyens techniques", "Caméra")

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
        self.film_id = db.creer_film(self.conn, "Film règles", region="Île-de-France", taux_charges=0.40)
        self.rub_son = rubrique(self.conn, self.film_id, "Personnel technique", "Son")
        self.rub_cam = rubrique(self.conn, self.film_id, "Moyens techniques", "Caméra")

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
        self.conn.execute("UPDATE films SET charges_mode='poste_dedie' WHERE id=?", (self.film_id,))
        self.conn.commit()
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        tid = engine.ajouter_technicien(self.conn, self.film_id, self.rub_son, fonc["id"],
                                        salaire=250.0, unite="jour",
                                        phases=[{"phase": "Tournage", "quantite": 4, "unite": "jour"}])
        calc = engine.compute_film(self.conn, self.film_id)
        self.assertEqual(calc["totaux"]["montant"], 1400.0)  # 1000 brut + 400 charges, comptés une fois
        fiche = engine.fiche_technicien(self.conn, tid)
        self.assertEqual(fiche["brut"], 1000.0)
        self.assertEqual(fiche["charges"], 400.0)
        self.assertEqual(fiche["cout_employeur"], 1400.0)
        # la ligne de charges est reliée à l'engagement et placée dans le poste dédié
        charge = self.conn.execute("SELECT * FROM lignes WHERE type='charge' AND technicien_id=?", (tid,)).fetchone()
        self.assertIsNotNone(charge)
        parent = self.conn.execute("SELECT * FROM lignes WHERE id=?", (charge["parent_id"],)).fetchone()
        self.assertEqual(parent["libelle"], "Charges sociales")

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
        rub_son2 = rubrique(self.conn, self.film_id, "Personnel technique", "Image")
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
        self.film_id = db.creer_film(self.conn, "Film export", region="Île-de-France", taux_charges=0.40)
        fonc = self.conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
        rub_son = rubrique(self.conn, self.film_id, "Personnel technique", "Son")
        rub_cam = rubrique(self.conn, self.film_id, "Moyens techniques", "Caméra")
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
        self.assertEqual(len([n for n in noms if n.startswith("xl/worksheets/sheet")]), 3)
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
        detail = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
        self.assertIn("Location cam", detail)
        self.assertIn("Corps cam", detail)
        self.assertIn("Charges employeur", detail)


def _iter(roots):
    for n in roots:
        yield n
        yield from _iter(n["children"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
