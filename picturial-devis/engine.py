#!/usr/bin/env python3
# Moteur de calcul unique : partagé par l'écran Devis, la vue Région, l'impression et les exports.
# Règle d'arrondi : au centime, demi au supérieur (ROUND_HALF_UP), propagée des feuilles vers les totaux.
import json
from decimal import Decimal, ROUND_HALF_UP
from xml.sax.saxutils import escape as escape_html

CENT = Decimal("0.01")


class Erreur(Exception):
    def __init__(self, message, status=400, confirmation_requise=False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.confirmation_requise = confirmation_requise


def r2(x):
    if x is None:
        return None
    return float(Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP))


def fmt_fr(x):
    """Format français : 1 750,00 €"""
    if x is None:
        return ""
    d = Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)
    neg = d < 0
    d = abs(d)
    partie_entiere = f"{int(d):,}".replace(",", " ")
    s = f"{partie_entiere},{int((d % 1) * 100):02d} €"
    return ("-" + s) if neg else s


def _film(conn, film_id):
    row = conn.execute("SELECT * FROM films WHERE id=?", (film_id,)).fetchone()
    if not row:
        raise Erreur("Film introuvable.", 404)
    return row


def _ordre_suivant(conn, film_id, parent_id):
    if parent_id is None:
        row = conn.execute("SELECT MAX(ordre) AS m FROM lignes WHERE film_id=? AND parent_id IS NULL", (film_id,)).fetchone()
    else:
        row = conn.execute("SELECT MAX(ordre) AS m FROM lignes WHERE film_id=? AND parent_id=?", (film_id, parent_id)).fetchone()
    m = row["m"]
    return (m or 0) + 1


# ---------------------------------------------------------------- lignes

def ajouter_ligne(conn, film_id, parent_id, type_ligne="ligne", libelle="", quantite=None, unite="forfait",
                  cout_unitaire=None, montant_forfait=None, note="", ht=True, code="", phase=""):
    _film(conn, film_id)
    if parent_id is not None:
        p = conn.execute("SELECT id FROM lignes WHERE id=? AND film_id=?", (parent_id, film_id)).fetchone()
        if not p:
            raise Erreur("Parent introuvable.", 404)
    lid = __import__("db").new_id()
    conn.execute(
        "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
        " montant_forfait, montant_saisi, note, ordre, en_region, hors_region, ht, phase) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)",
        (lid, film_id, parent_id, type_ligne, code, libelle, quantite, unite, cout_unitaire,
         r2(montant_forfait) if montant_forfait is not None else None,
         1 if montant_forfait is not None else 0, note,
         _ordre_suivant(conn, film_id, parent_id), 1 if ht else 0, phase),
    )
    conn.commit()
    return lid


def modifier_ligne(conn, ligne_id, champs):
    row = conn.execute("SELECT * FROM lignes WHERE id=?", (ligne_id,)).fetchone()
    if not row:
        raise Erreur("Ligne introuvable.", 404)
    autorises = {"libelle", "quantite", "unite", "cout_unitaire", "montant_forfait", "note", "ht", "code", "phase"}
    for k, v in champs.items():
        if k not in autorises:
            continue
        if k in ("cout_unitaire", "montant_forfait"):
            v = r2(v) if v not in (None, "") else None
        if k == "montant_forfait":
            # un forfait saisi explicitement devient la source de vérité (non dérivé de la ventilation)
            conn.execute("UPDATE lignes SET montant_saisi=? WHERE id=?", (1 if v is not None else 0, ligne_id))
        if k == "quantite":
            v = None if v in (None, "") else float(v)
        if k == "ht":
            v = 1 if v in (True, 1, "1") else 0
        conn.execute(f"UPDATE lignes SET {k}=? WHERE id=?", (v, ligne_id))
    conn.commit()
    return ligne_id


def _sous_arbre(conn, ligne_id):
    ids = [ligne_id]
    pile = [ligne_id]
    while pile:
        cur = pile.pop()
        for r in conn.execute("SELECT id FROM lignes WHERE parent_id=?", (cur,)).fetchall():
            ids.append(r["id"])
            pile.append(r["id"])
    return ids


def supprimer_ligne(conn, ligne_id):
    if not conn.execute("SELECT id FROM lignes WHERE id=?", (ligne_id,)).fetchone():
        raise Erreur("Ligne introuvable.", 404)
    conn.execute("DELETE FROM lignes WHERE id=?", (ligne_id,))
    conn.commit()


def dupliquer_ligne(conn, ligne_id):
    src = conn.execute("SELECT * FROM lignes WHERE id=?", (ligne_id,)).fetchone()
    if not src:
        raise Erreur("Ligne introuvable.", 404)

    def copie(old_id, new_parent):
        s = dict(conn.execute("SELECT * FROM lignes WHERE id=?", (old_id,)).fetchone())
        nid = __import__("db").new_id()
        conn.execute(
            "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
            " montant_forfait, montant_saisi, note, ordre, en_region, hors_region, etranger, ht, phase, regle, technicien_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nid, s["film_id"], new_parent, s["type"], s["code"], s["libelle"] + " (copie)", s["quantite"],
             s["unite"], s["cout_unitaire"], s["montant_forfait"], s.get("montant_saisi", 0), s["note"],
             _ordre_suivant(conn, s["film_id"], new_parent),
             s["en_region"], s["hors_region"], s.get("etranger", 0), s["ht"], s["phase"], s.get("regle", ""), None),
        )
        for c in conn.execute("SELECT id FROM lignes WHERE parent_id=? ORDER BY ordre", (old_id,)).fetchall():
            copie(c["id"], nid)
        return nid

    new_id = copie(ligne_id, src["parent_id"])
    conn.commit()
    return new_id


def deplacer_ligne(conn, ligne_id, new_parent_id):
    row = conn.execute("SELECT * FROM lignes WHERE id=?", (ligne_id,)).fetchone()
    if not row:
        raise Erreur("Ligne introuvable.", 404)
    if new_parent_id is not None:
        if new_parent_id == ligne_id or new_parent_id in _sous_arbre(conn, ligne_id):
            raise Erreur("Impossible de déplacer une ligne dans l'une de ses propres sous-lignes.")
        p = conn.execute("SELECT id FROM lignes WHERE id=? AND film_id=?", (new_parent_id, row["film_id"])).fetchone()
        if not p:
            raise Erreur("Destination introuvable.", 404)
    conn.execute("UPDATE lignes SET parent_id=?, ordre=? WHERE id=?",
                 (new_parent_id, _ordre_suivant(conn, row["film_id"], new_parent_id), ligne_id))
    conn.commit()


def ajouter_sous_detail(conn, film_id, parent_id, libelle="", quantite=None, unite="forfait",
                        cout_unitaire=None, montant_forfait=None, note="", ht=True, reprendre=None):
    """reprendre : None (demander), True (reprendre l'estimation forfaitaire comme 1er sous-détail),
    False (remplacer l'estimation)."""
    parent = conn.execute("SELECT * FROM lignes WHERE id=? AND film_id=?", (parent_id, film_id)).fetchone()
    if not parent:
        raise Erreur("Ligne parent introuvable.", 404)
    nb_enfants = conn.execute("SELECT COUNT(*) AS n FROM lignes WHERE parent_id=?", (parent_id,)).fetchone()["n"]
    forfait = parent["montant_forfait"]
    if forfait is not None and nb_enfants == 0 and reprendre is not None:
        if reprendre:
            montant_forfait = forfait if montant_forfait is None else montant_forfait
            note = (note + " " if note else "") + f"Estimation initiale de {fmt_fr(forfait)} reprise comme sous-détail."
            conn.execute("UPDATE lignes SET montant_forfait=NULL, montant_saisi=0 WHERE id=?", (parent_id,))
        else:
            conn.execute("UPDATE lignes SET montant_forfait=NULL, montant_saisi=0, note=? WHERE id=?",
                         ((parent["note"] + " " if parent["note"] else "") +
                          f"Estimation initiale de {fmt_fr(forfait)} remplacée par le sous-détail.", parent_id))
    return ajouter_ligne(conn, film_id, parent_id, type_ligne="detail", libelle=libelle, quantite=quantite,
                         unite=unite, cout_unitaire=cout_unitaire, montant_forfait=montant_forfait, note=note, ht=ht)


# ---------------------------------------------------------------- calcul

def _arbre(conn, film_id):
    rows = conn.execute("SELECT * FROM lignes WHERE film_id=? ORDER BY ordre, rowid", (film_id,)).fetchall()
    nodes = {}
    roots = []
    for r in rows:
        n = dict(r)
        n["children"] = []
        nodes[n["id"]] = n
    for n in nodes.values():
        if n["parent_id"] in nodes:
            nodes[n["parent_id"]]["children"].append(n)
        else:
            roots.append(n)
    return roots, nodes


def _montant_feuille(n):
    if n["montant_forfait"] is not None:
        return r2(n["montant_forfait"]), "saisi"
    if n["quantite"] is not None and n["cout_unitaire"] is not None:
        return r2(n["quantite"] * n["cout_unitaire"]), "calcule"
    return 0.0, "calcule"


def compute_film(conn, film_id):
    """Arbre complet avec montants, ventilation et totaux. Source unique de tous les écrans et exports."""
    film = _film(conn, film_id)
    roots, nodes = _arbre(conn, film_id)
    techs = {t["id"]: dict(t) for t in conn.execute("SELECT * FROM techniciens WHERE film_id=?", (film_id,)).fetchall()}
    tech_by_ligne = {t["ligne_id"]: t for t in techs.values()}

    # passe 1 : feuilles hors charges
    for n in nodes.values():
        if not n["children"] and n["type"] != "charge":
            n["montant"], n["statut_montant"] = _montant_feuille(n)
        else:
            n["montant"] = None
            n["statut_montant"] = "calcule"

    # passe 2 : lignes de charges (règle en % sur des codes de postes/lignes, ou brut technicien x taux)
    by_code = {}
    for n in nodes.values():
        if n.get("code"):
            by_code.setdefault(n["code"], n)
    for n in nodes.values():
        if n["type"] == "charge" and not n["children"]:
            regle = None
            try:
                regle = json.loads(n["regle"]) if n.get("regle") else None
            except Exception:
                regle = None
            if not (regle and isinstance(regle, dict) and regle.get("regle")):
                t = techs.get(n["technicien_id"])
                if t is None:
                    n["montant"] = 0.0
                else:
                    brut = 0.0
                    for c in nodes.values():
                        if c["parent_id"] == t["ligne_id"] and c["type"] == "detail":
                            brut += c["montant"] or 0.0
                    n["montant"] = r2(brut * (film["taux_charges"] or 0.0))

    # passe 3 : parents, des feuilles vers la racine (charges à règle comptées à 0 pour l'instant)
    def remonte(n):
        for c in n["children"]:
            remonte(c)
        if n["children"]:
            n["montant"] = r2(sum(c["montant"] or 0.0 for c in n["children"]))
    for r in roots:
        remonte(r)

    # passe 4 : charges à règle, deux passes (FG/imprévus dépendent du poste 4, lui-même règle)
    # En mode « avec », les règles 41-45 du poste 4 sont ignorées (charges déjà comptées par engagement).
    for _passe in range(2):
        for n in nodes.values():
            if n["type"] == "charge" and not n["children"]:
                try:
                    regle = json.loads(n["regle"]) if n.get("regle") else None
                except Exception:
                    regle = None
                if regle and isinstance(regle, dict) and regle.get("regle"):
                    if film["charges_mode"] == "avec" and n.get("code") in ("41", "42", "43", "44", "45"):
                        n["montant"] = 0.0
                        continue
                    total = Decimal("0")
                    for ent in regle["regle"]:
                        src = sum(Decimal(str(by_code[c]["montant"] or 0)) for c in ent.get("source", []) if c in by_code)
                        exc = sum(Decimal(str(by_code[c]["montant"] or 0)) for c in ent.get("exclure", []) if c in by_code)
                        total += Decimal(str(ent.get("taux", 0))) * (src - exc)
                    n["montant"] = r2(total)
        for r in roots:
            remonte(r)

    # ventilation : feuilles = valeurs saisies, parents = somme des enfants
    def ventile(n):
        for c in n["children"]:
            ventile(c)
        if n["children"]:
            n["en_region"] = r2(sum(c["en_region"] for c in n["children"]))
            n["hors_region"] = r2(sum(c["hors_region"] for c in n["children"]))
            n["etranger"] = r2(sum(c.get("etranger", 0) for c in n["children"]))
        n["a_ventiler"] = r2((n["montant"] or 0.0) - n["en_region"] - n["hors_region"] - n.get("etranger", 0))
    for r in roots:
        ventile(r)

    # codes d'affichage et infos techniciens
    def annote(n, prefix, index, parent_path):
        # Seul un code saisi dans la nomenclature est affiché tel quel (11., 1411., 237. comme dans
        # le modèle Excel) : jamais de code inventé (pas de « 1.10 ») pour une ligne sans code.
        n["chemin"] = n["code"] or ""
        t = tech_by_ligne.get(n["id"])
        n["technicien"] = dict(t) if t else None
        if t:
            f = conn.execute("SELECT * FROM fonctions WHERE id=?", (t["fonction_id"],)).fetchone() if t["fonction_id"] else None
            g = conn.execute("SELECT * FROM grilles WHERE id=?", (t["grille_id_snapshot"],)).fetchone() if t["grille_id_snapshot"] else None
            n["tech_info"] = {
                "fonction": dict(f) if f else None,
                "grille_snapshot": dict(g) if g else None,
                "avertissements": avertissements_technicien(conn, film, t, f),
            }
            if t["hypothese_manuelle"]:
                n.setdefault("flags", []).append("hypothèse manuelle")
        i = 1
        for c in n["children"]:
            annote(c, "", i, "")
            i += 1
    i = 1
    for r in roots:
        annote(r, "", i, "")
        i += 1

    totaux = {
        "montant": r2(sum(r["montant"] or 0.0 for r in roots)),
        "en_region": r2(sum(r["en_region"] for r in roots)),
        "hors_region": r2(sum(r["hors_region"] for r in roots)),
        "etranger": r2(sum(r.get("etranger", 0) for r in roots)),
        "a_ventiler": r2(sum(r["a_ventiler"] for r in roots)),
    }
    recap = [{"id": r["id"], "code": r["code"], "libelle": r["libelle"], "montant": r["montant"],
              "en_region": r["en_region"], "hors_region": r["hors_region"], "etranger": r.get("etranger", 0),
              "a_ventiler": r["a_ventiler"]}
             for r in roots]
    return {"film": dict(film), "arbre": roots, "totaux": totaux, "recap": recap}


def avertissements_technicien(conn, film, tech, fonction):
    w = []
    if tech["salaire"] < (tech["minimum_snapshot"] or 0):
        w.append(f"Salaire retenu ({fmt_fr(tech['salaire'])}) inférieur au minimum de la version de barème retenue "
                 f"({fmt_fr(tech['minimum_snapshot'])}).")
    if fonction and tech["salaire"] < fonction["minimum"]:
        w.append(f"Salaire retenu inférieur au minimum actuel de la fonction ({fmt_fr(fonction['minimum'])} {fonction['unite']}).")
    if tech["hypothese_manuelle"]:
        w.append("Unité de rémunération saisie hors barème : hypothèse manuelle explicitement identifiée.")
    return w


# ---------------------------------------------------------------- techniciens

def ajouter_technicien(conn, film_id, parent_id, fonction_id, nom="", salaire=None, unite="jour",
                       phases=None, hypothese_manuelle=False, reprendre=None):
    """reprendre : None (demander), True (reprendre l'estimation de la ligne parent comme sous-détail),
    False (remplacer l'estimation). Évite tout double comptage forfait -> engagement."""
    film = _film(conn, film_id)
    fonc = conn.execute("SELECT * FROM fonctions WHERE id=?", (fonction_id,)).fetchone()
    if not fonc:
        raise Erreur("Fonction introuvable dans les barèmes.", 404)
    parent = None
    if parent_id is not None:
        parent = conn.execute("SELECT * FROM lignes WHERE id=? AND film_id=?", (parent_id, film_id)).fetchone()
        if not parent:
            raise Erreur("Rubrique introuvable.", 404)
    if parent is not None:
        nb_enfants = conn.execute("SELECT COUNT(*) AS n FROM lignes WHERE parent_id=?", (parent_id,)).fetchone()["n"]
        estimation = parent["montant_forfait"]
        if estimation is None and parent["quantite"] is not None and parent["cout_unitaire"] is not None:
            estimation = r2(parent["quantite"] * parent["cout_unitaire"])
        if estimation is not None and nb_enfants == 0:
            if reprendre is None:
                raise Erreur(
                    f"La ligne « {parent['libelle']} » contient déjà une estimation de {fmt_fr(estimation)}. "
                    "Choisissez explicitement de la reprendre comme sous-détail ou de la remplacer.",
                    confirmation_requise=True)
            if reprendre:
                ajouter_ligne(conn, film_id, parent_id, type_ligne="detail",
                              libelle=f"Estimation initiale reprise ({fmt_fr(estimation)})",
                              montant_forfait=r2(estimation), unite="forfait", ht=True)
                conn.execute("UPDATE lignes SET montant_forfait=NULL, montant_saisi=0, quantite=NULL, cout_unitaire=NULL WHERE id=?",
                             (parent_id,))
            else:
                conn.execute("UPDATE lignes SET montant_forfait=NULL, montant_saisi=0, quantite=NULL, cout_unitaire=NULL, note=? WHERE id=?",
                             ((parent["note"] + " " if parent["note"] else "") +
                              f"Estimation initiale de {fmt_fr(estimation)} remplacée par l'engagement.", parent_id))
    unite_ref = fonc["unite"]
    if unite != unite_ref and not hypothese_manuelle:
        raise Erreur(
            f"Le minimum de « {fonc['nom']} » est donné en « {unite_ref} ». Saisissez les périodes en « {unite_ref} », "
            f"ou validez explicitement une hypothèse manuelle (aucune division automatique n'est appliquée).")
    for p in phases or []:
        if p.get("unite", unite) != unite_ref and not hypothese_manuelle:
            raise Erreur(f"La phase « {p.get('phase','')} » doit être saisie en « {unite_ref} » (ou hypothèse manuelle).")
    minimum = r2(fonc["minimum"])
    salaire = r2(salaire) if salaire not in (None, "") else minimum
    import db
    tech_id = db.new_id()
    ligne_id = db.new_id()
    salaire_perso = 1 if salaire != minimum else 0
    libelle = fonc["nom"] + (f" — {nom}" if nom else "")
    conn.execute(
        "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
        " montant_forfait, note, ordre, en_region, hors_region, ht, phase) VALUES (?,?,?,?,?,?,?,?,?,NULL,'',?,0,0,0,?)",
        (ligne_id, film_id, parent_id, "technicien", "", libelle, None, unite, None,
         _ordre_suivant(conn, film_id, parent_id), 0),
    )
    conn.execute(
        "INSERT INTO techniciens (id, film_id, ligne_id, fonction_id, nom, salaire, unite, salaire_perso,"
        " hypothese_manuelle, grille_id_snapshot, minimum_snapshot, taux_snapshot, date_ref_snapshot)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tech_id, film_id, ligne_id, fonction_id, nom, salaire, unite, salaire_perso,
         1 if hypothese_manuelle else 0, fonc["grille_id"], minimum, film["taux_charges"], film["date_ref_baremes"]),
    )
    for p in phases or []:
        q = float(p.get("quantite") or 0)
        if q <= 0:
            continue
        conn.execute(
            "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
            " montant_forfait, note, ordre, en_region, hors_region, ht, phase) VALUES (?,?,?,?,?,?,?,?,?,NULL,'',?,0,0,1,?)",
            (db.new_id(), film_id, ligne_id, "detail", "", p.get("phase", ""), q, p.get("unite", unite), salaire,
             _ordre_suivant(conn, film_id, ligne_id), p.get("phase", "")),
        )
    if film["charges_mode"] == "avec":
        _ajouter_ligne_charges(conn, film, tech_id, ligne_id, fonc["nom"])
    conn.commit()
    return tech_id


def _ajouter_ligne_charges(conn, film, tech_id, ligne_id, fonction_nom):
    import db
    taux = film["taux_charges"] or 0.0
    if film["charges_mode"] == "poste_dedie":
        rub_id = film["rubrique_charges_id"]
        if rub_id is None or not conn.execute("SELECT id FROM lignes WHERE id=? AND film_id=?", (rub_id, film["id"])).fetchone():
            poste = conn.execute("SELECT id FROM lignes WHERE film_id=? AND type='poste' AND libelle='Personnel technique'",
                                 (film["id"],)).fetchone() or conn.execute(
                "SELECT id FROM lignes WHERE film_id=? AND type='poste' ORDER BY ordre LIMIT 1", (film["id"],)).fetchone()
            rub_id = db.new_id()
            conn.execute(
                "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, unite, ordre, ht)"
                " VALUES (?,?,?,?,?,?,?,?,1)",
                (rub_id, film["id"], poste["id"], "rubrique", "3.99", film["nom_poste_charges"] or "Charges sociales",
                 "forfait", _ordre_suivant(conn, film["id"], poste["id"])))
            conn.execute("UPDATE films SET rubrique_charges_id=? WHERE id=?", (rub_id, film["id"]))
        parent = rub_id
        libelle = f"Charges employeur — {fonction_nom} ({taux * 100:g} %)"
    else:
        parent = ligne_id
        libelle = f"Charges employeur ({taux * 100:g} %)"
    conn.execute(
        "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
        " montant_forfait, note, ordre, en_region, hors_region, ht, phase, technicien_id)"
        " VALUES (?,?,?,?,?,?,NULL,'forfait',NULL,NULL,'',?,0,0,?,NULL,?)",
        (db.new_id(), film["id"], parent, "charge", "", libelle, _ordre_suivant(conn, film["id"], parent),
         1 if parent == ligne_id else 0, tech_id),
    )


def modifier_technicien(conn, tech_id, nom=None, salaire=None, unite=None, phases=None, hypothese_manuelle=None):
    t = conn.execute("SELECT * FROM techniciens WHERE id=?", (tech_id,)).fetchone()
    if not t:
        raise Erreur("Engagement introuvable.", 404)
    film = _film(conn, t["film_id"])
    fonc = conn.execute("SELECT * FROM fonctions WHERE id=?", (t["fonction_id"],)).fetchone()
    if unite is not None and unite != t["unite"]:
        # Changement d'unité (jour <-> semaine…) : autorisé, mais hors barème = hypothèse manuelle signalée
        if fonc and unite != fonc["unite"] and not (hypothese_manuelle or t["hypothese_manuelle"]):
            raise Erreur(f"Le barème de « {fonc['nom']} » est en « {fonc['unite']} » : aucune division automatique. "
                          f"Validez une hypothèse manuelle pour saisir en « {unite} ».")
        conn.execute("UPDATE techniciens SET unite=? WHERE id=?", (unite, tech_id))
        conn.execute("UPDATE lignes SET unite=? WHERE parent_id=? AND type='detail'", (unite, t["ligne_id"]))
    if salaire not in (None, ""):
        salaire = r2(salaire)
        conn.execute("UPDATE techniciens SET salaire=?, salaire_perso=? WHERE id=?",
                     (salaire, 1 if fonc and salaire != r2(fonc["minimum"]) else 0, tech_id))
        conn.execute("UPDATE lignes SET cout_unitaire=? WHERE parent_id=? AND type='detail'",
                     (salaire, t["ligne_id"]))
    if nom is not None:
        conn.execute("UPDATE techniciens SET nom=? WHERE id=?", (nom, tech_id))
        libelle = (fonc["nom"] if fonc else "Technicien") + (f" — {nom}" if nom else "")
        conn.execute("UPDATE lignes SET libelle=? WHERE id=?", (libelle, t["ligne_id"]))
    if hypothese_manuelle is not None:
        conn.execute("UPDATE techniciens SET hypothese_manuelle=? WHERE id=?", (1 if hypothese_manuelle else 0, tech_id))
    if phases is not None:
        if fonc and t["unite"] != fonc["unite"] and not (hypothese_manuelle or t["hypothese_manuelle"]):
            raise Erreur(f"Le barème de « {fonc['nom']} » est en « {fonc['unite']} » : aucune division automatique. "
                          "Validez une hypothèse manuelle pour saisir en « {t['unite']} ».")
        conn.execute("DELETE FROM lignes WHERE parent_id=? AND type='detail'", (t["ligne_id"],))
        for p in phases:
            q = float(p.get("quantite") or 0)
            if q <= 0:
                continue
            import db
            salaire_courant = conn.execute("SELECT salaire FROM techniciens WHERE id=?", (tech_id,)).fetchone()["salaire"]
            conn.execute(
                "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
                " montant_forfait, note, ordre, en_region, hors_region, ht, phase) VALUES (?,?,?,?,?,?,?,?,?,NULL,'',?,0,0,1,?)",
                (db.new_id(), t["film_id"], t["ligne_id"], "detail", "", p.get("phase", ""), q, p.get("unite", t["unite"]),
                 salaire_courant, _ordre_suivant(conn, t["film_id"], t["ligne_id"]), p.get("phase", "")),
            )
    conn.commit()


def fiche_technicien(conn, tech_id):
    t = conn.execute("SELECT * FROM techniciens WHERE id=?", (tech_id,)).fetchone()
    if not t:
        raise Erreur("Engagement introuvable.", 404)
    film = _film(conn, t["film_id"])
    calc = compute_film(conn, t["film_id"])
    noeud = None

    def trouve(n):
        nonlocal noeud
        if n["id"] == t["ligne_id"]:
            noeud = n
        for c in n["children"]:
            trouve(c)
    for r in calc["arbre"]:
        trouve(r)
    phases = [dict(c) for c in (noeud["children"] if noeud else []) if c["type"] == "detail"]
    brut = r2(sum(p["montant"] or 0.0 for p in phases))
    charge = None
    for n in _iter_nodes(calc["arbre"]):
        if n["type"] == "charge" and n["technicien_id"] == tech_id:
            charge = n
    charges = charge["montant"] if charge else r2(brut * (film["taux_charges"] or 0.0))
    fonc = conn.execute("SELECT * FROM fonctions WHERE id=?", (t["fonction_id"],)).fetchone() if t["fonction_id"] else None
    return {
        "technicien": dict(t),
        "fonction": dict(fonc) if fonc else None,
        "film": dict(film),
        "phases": phases,
        "brut": brut,
        "taux_charges": film["taux_charges"],
        "charges": charges,
        "cout_employeur": r2(brut + charges),
        "avertissements": avertissements_technicien(conn, film, dict(t), dict(fonc) if fonc else None),
        "ligne_id": t["ligne_id"],
    }


def _iter_nodes(roots):
    for n in roots:
        yield n
        yield from _iter_nodes(n["children"])


# ---------------------------------------------------------------- vue « 2. Personnel » (page 2 du modèle Excel)

def _norm_nom(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if c.isalnum())


def fonction_suggeree(conn, film, libelle):
    """Fonction du référentiel (convention du film) dont le nom correspond au libellé d'une ligne
    du poste 2 — pour pré-remplir le minimum CCNPC lors de l'ajout d'un engagement."""
    if not libelle or not film.get("convention_id"):
        return None
    cible = _norm_nom(libelle)
    if not cible:
        return None
    rows = conn.execute(
        "SELECT f.*, g.version AS grille_version FROM fonctions f JOIN grilles g ON f.grille_id=g.id"
        " WHERE f.convention_id=?", (film["convention_id"],)).fetchall()

    def to_dict(r):
        return {"id": r["id"], "nom": r["nom"], "minimum": r["minimum"], "unite": r["unite"],
                "statut": r["statut"], "grille_version": r["grille_version"], "source": r["source"]}

    exact = [r for r in rows if _norm_nom(r["nom"]) == cible]
    if exact:
        return to_dict(exact[0])
    partiels = [r for r in rows if _norm_nom(r["nom"]) and (_norm_nom(r["nom"]) in cible or cible in _norm_nom(r["nom"]))]
    if partiels:
        # meilleure correspondance : nom qui commence par le libellé, puis écart de longueur minimal
        partiels.sort(key=lambda r: (not _norm_nom(r["nom"]).startswith(cible), abs(len(_norm_nom(r["nom"])) - len(cible))))
        return to_dict(partiels[0])
    return None


def vue_personnel(conn, film_id):
    """Page 2 « Personnel » : sous-arbre du poste 2 avec, pour chaque engagement, ses phases
    (Préparation / Tournage / Finitions) et leur ventilation région / France / étranger,
    plus la fonction de barème suggérée pour chaque ligne fonction. Mêmes totaux que compute_film."""
    calc = compute_film(conn, film_id)
    film = calc["film"]
    poste = next((r for r in calc["arbre"] if r["type"] == "poste" and r["code"] == "2"), None)
    if poste is None:
        raise Erreur("Poste 2 « Personnel » introuvable.", 404)

    def habille(n):
        out = {k: v for k, v in n.items() if k != "children"}
        if n["type"] == "technicien":
            out["phases"] = [
                {"ligne_id": c["id"], "phase": c["phase"], "quantite": c["quantite"], "unite": c["unite"],
                 "salaire": c["cout_unitaire"], "montant": c["montant"],
                 "en_region": c["en_region"], "hors_region": c["hors_region"],
                 "etranger": c.get("etranger", 0), "a_ventiler": c["a_ventiler"]}
                for c in n["children"] if c["type"] == "detail"]
        elif n["type"] != "poste":
            sug = fonction_suggeree(conn, film, n["libelle"])
            if sug:
                out["fonction_suggeree"] = sug
        out["children"] = [habille(c) for c in n["children"]]
        return out

    return {
        "film": film,
        "poste": habille(poste),
        "totaux_poste": {"montant": poste["montant"], "en_region": poste["en_region"],
                         "hors_region": poste["hors_region"], "etranger": poste.get("etranger", 0),
                         "a_ventiler": poste["a_ventiler"]},
        "totaux_film": calc["totaux"],
    }


# ---------------------------------------------------------------- ventilation régionale

def _feuilles(conn, node):
    if not node["children"]:
        return [node]
    out = []
    for c in node["children"]:
        out.extend(_feuilles(conn, c))
    return out


def set_ventilation(conn, film_id, ligne_id, mode="partiel", en_region=None, hors_region=None, etranger=None):
    """Modes : tout_en, tout_hors, partiel. Sur une ligne parent, s'applique à toutes ses feuilles
    (la ligne d'origine est modifiée, aucune copie n'est créée)."""
    calc = compute_film(conn, film_id)
    cible = None

    def trouve(n):
        nonlocal cible
        if n["id"] == ligne_id:
            cible = n
        for c in n["children"]:
            trouve(c)
    for r in calc["arbre"]:
        trouve(r)
    if cible is None:
        raise Erreur("Ligne introuvable.", 404)
    feuilles = _feuilles(conn, cible)
    if mode == "tout_en":
        for f in feuilles:
            conn.execute("UPDATE lignes SET en_region=?, hors_region=0, etranger=0 WHERE id=?", (f["montant"], f["id"]))
    elif mode == "tout_hors":
        for f in feuilles:
            conn.execute("UPDATE lignes SET en_region=0, hors_region=?, etranger=0 WHERE id=?", (f["montant"], f["id"]))
    elif mode == "tout_etranger":
        for f in feuilles:
            conn.execute("UPDATE lignes SET en_region=0, hors_region=0, etranger=? WHERE id=?", (f["montant"], f["id"]))
    else:
        total = r2(sum(f["montant"] or 0.0 for f in feuilles))
        if len(feuilles) == 1:
            f = feuilles[0]
            m = f["montant"] or 0.0
            en = r2(en_region) if en_region is not None else 0.0
            hors = r2(hors_region) if hors_region is not None else 0.0
            et = r2(etranger) if etranger is not None else 0.0
            if en_region is None and hors_region is None and etranger is None:
                hors = r2(m - en - et)
            # Saisie façon modèle Excel (onglets de détail : G = en région, H = France, I = G+H) :
            # sur une ligne sans montant saisi explicitement (ni forfait, ni qté × coût), G/H/étranger
            # sont les inputs et le montant forfaitaire est dérivé de la ventilation (I = G + H).
            sans_source = f["quantite"] is None and not f.get("montant_saisi")
            if en_region is not None or hors_region is not None or etranger is not None:
                if not sans_source and r2(en + hors + et) > r2(m + 0.005):
                    raise Erreur(f"En région + hors région + étranger ({fmt_fr(en + hors + et)}) dépasse le montant de la ligne ({fmt_fr(m)}).")
                if sans_source:
                    conn.execute("UPDATE lignes SET montant_forfait=? WHERE id=?", (r2(en + hors + et), f["id"]))
            conn.execute("UPDATE lignes SET en_region=?, hors_region=?, etranger=? WHERE id=?", (en, hors, et, f["id"]))
        else:
            en_total = r2(en_region) if en_region is not None else 0.0
            if en_total > total:
                raise Erreur(f"Montant en région ({fmt_fr(en_total)}) supérieur au montant de la ligne ({fmt_fr(total)}).")
            if en_region is None and hors_region is None and etranger is None:
                raise Erreur("Précisez au moins un montant (en région, hors région ou étranger).")
            cumul = Decimal("0")
            for i, f in enumerate(feuilles):
                m = Decimal(str(f["montant"] or 0.0))
                if i == len(feuilles) - 1:
                    en = Decimal(str(en_total)) - cumul
                else:
                    en = (Decimal(str(en_total)) * m / Decimal(str(total))).quantize(CENT, rounding=ROUND_HALF_UP) if total else Decimal("0")
                    cumul += en
                conn.execute("UPDATE lignes SET en_region=?, hors_region=? WHERE id=?",
                             (float(en), float(m - en), f["id"]))
    conn.commit()


def vue_region(conn, film_id):
    calc = compute_film(conn, film_id)
    lignes = []
    for n in _iter_nodes(calc["arbre"]):
        if n["type"] in ("ligne", "detail", "technicien", "charge") and (n["montant"] or 0) > 0:
            lignes.append({"id": n["id"], "chemin": n["chemin"], "libelle": n["libelle"], "type": n["type"],
                           "montant": n["montant"], "en_region": n["en_region"], "hors_region": n["hors_region"],
                           "etranger": n.get("etranger", 0), "a_ventiler": n["a_ventiler"]})
    totaux = calc["totaux"]
    part = (totaux["en_region"] / totaux["montant"]) if totaux["montant"] else 0.0
    return {"region": calc["film"]["region_cible"], "totaux": totaux, "part_regionale": part,
            "par_poste": calc["recap"], "lignes": lignes,
            "egalite_ok": r2(totaux["en_region"] + totaux["hors_region"] + totaux.get("etranger", 0) + totaux["a_ventiler"]) == totaux["montant"]}


def changer_region_cible(conn, film_id, nouvelle_region, option=None):
    """option : 'conserver' ou 'reinitialiser'. Sans option et si des dépenses sont déjà ventilées,
    renvoie une demande de confirmation explicite (Erreur confirmation_requise)."""
    film = _film(conn, film_id)
    if nouvelle_region == film["region_cible"]:
        return {"change": False}
    nb_ventilees = conn.execute(
        "SELECT COUNT(*) AS n FROM lignes WHERE film_id=? AND (en_region>0 OR hors_region>0 OR etranger>0)", (film_id,)).fetchone()["n"]
    if nb_ventilees > 0 and option not in ("conserver", "reinitialiser"):
        raise Erreur(
            f"{nb_ventilees} ligne(s) sont déjà ventilées pour « {film['region_cible']} ». "
            "Choisissez : conserver les affectations existantes, ou tout remettre « à ventiler ».",
            status=409, confirmation_requise=True)
    if option == "reinitialiser":
        conn.execute("UPDATE lignes SET en_region=0, hors_region=0, etranger=0 WHERE film_id=?", (film_id,))
    conn.execute("UPDATE films SET region_cible=? WHERE id=?", (nouvelle_region, film_id))
    conn.commit()
    return {"change": True, "region": nouvelle_region, "option": option, "lignes_reinitialisees": nb_ventilees if option == "reinitialiser" else 0}


# ---------------------------------------------------------------- barèmes

def actualiser_baremes(conn, film_id, appliquer=False):
    film = _film(conn, film_id)
    techs = conn.execute("SELECT * FROM techniciens WHERE film_id=?", (film_id,)).fetchall()
    apercu = []
    for t in techs:
        fonc = conn.execute("SELECT * FROM fonctions WHERE id=?", (t["fonction_id"],)).fetchone() if t["fonction_id"] else None
        if not fonc:
            continue
        grille = conn.execute("SELECT * FROM grilles WHERE id=?", (fonc["grille_id"],)).fetchone()
        ancien_min = r2(t["minimum_snapshot"])
        nouveau_min = r2(fonc["minimum"])
        ancien_salaire = r2(t["salaire"])
        if t["salaire_perso"]:
            nouveau_salaire = ancien_salaire
            note = "Salaire négocié conservé."
        else:
            nouveau_salaire = nouveau_min
            note = "Salaire aligné sur le nouveau minimum (il était au minimum)."
        if nouveau_salaire < nouveau_min:
            note += " ⚠ Passe sous le nouveau minimum."
        qte = conn.execute(
            "SELECT COALESCE(SUM(quantite),0) AS q FROM lignes WHERE parent_id=? AND type='detail'", (t["ligne_id"],)).fetchone()["q"]
        apercu.append({
            "technicien_id": t["id"], "ligne_id": t["ligne_id"], "fonction": fonc["nom"],
            "nom": t["nom"], "ancien_minimum": ancien_min, "nouveau_minimum": nouveau_min,
            "ancien_salaire": ancien_salaire, "nouveau_salaire": nouveau_salaire,
            "quantite_totale": qte, "impact_brut": r2((nouveau_salaire - ancien_salaire) * qte),
            "ancienne_grille": t["grille_id_snapshot"], "nouvelle_grille": fonc["grille_id"],
            "version_nouvelle_grille": grille["version"] if grille else "", "note": note,
            "sous_minimum": nouveau_salaire < nouveau_min,
        })
    if appliquer:
        for a in apercu:
            conn.execute(
                "UPDATE techniciens SET salaire=?, minimum_snapshot=?, grille_id_snapshot=?, date_ref_snapshot=? WHERE id=?",
                (a["nouveau_salaire"], a["nouveau_minimum"], a["nouvelle_grille"], film["date_ref_baremes"], a["technicien_id"]))
            conn.execute("UPDATE lignes SET cout_unitaire=? WHERE parent_id=(SELECT ligne_id FROM techniciens WHERE id=?) AND type='detail'",
                         (a["nouveau_salaire"], a["technicien_id"]))
        conn.commit()
    return {"applique": appliquer, "date_ref": film["date_ref_baremes"], "apercu": apercu}


# ---------------------------------------------------------------- projet

def dupliquer_film(conn, film_id):
    import db
    src = _film(conn, film_id)
    nouveau_id = db.creer_film(conn, src["titre"] + " (copie)", societe=src["societe"], type_oeuvre=src["type_oeuvre"],
                                region=src["region_cible"], taux_charges=src["taux_charges"],
                                convention_id=src["convention_id"], grille_id=src["grille_id"],
                                date_ref=src["date_ref_baremes"], charges_mode=src["charges_mode"])
    # supprime la nomenclature auto puis copie l'arbre source
    conn.execute("DELETE FROM lignes WHERE film_id=?", (nouveau_id,))
    ancien = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM lignes WHERE film_id=?", (film_id,)).fetchall()}
    mapping = {}

    def copie(old_id, new_parent):
        s = ancien[old_id]
        nid = db.new_id()
        mapping[old_id] = nid
        conn.execute(
            "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
            " montant_forfait, montant_saisi, note, ordre, en_region, hors_region, etranger, ht, phase, regle, technicien_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (nid, nouveau_id, new_parent, s["type"], s["code"], s["libelle"], s["quantite"], s["unite"],
             s["cout_unitaire"], s["montant_forfait"], s.get("montant_saisi", 0), s["note"], s["ordre"], s["en_region"],
             s["hors_region"], s.get("etranger", 0), s["ht"], s["phase"], s.get("regle", "")))
        for c in conn.execute("SELECT id FROM lignes WHERE film_id=? AND parent_id=? ORDER BY ordre", (film_id, old_id)):
            copie(c["id"], nid)
    for r in conn.execute("SELECT id FROM lignes WHERE film_id=? AND parent_id IS NULL ORDER BY ordre", (film_id,)):
        copie(r["id"], None)
    tech_map = {}
    for t in conn.execute("SELECT * FROM techniciens WHERE film_id=?", (film_id,)).fetchall():
        nid = db.new_id()
        tech_map[t["id"]] = nid
        conn.execute(
            "INSERT INTO techniciens (id, film_id, ligne_id, fonction_id, nom, salaire, unite, salaire_perso,"
            " hypothese_manuelle, grille_id_snapshot, minimum_snapshot, taux_snapshot, date_ref_snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nid, nouveau_id, mapping[t["ligne_id"]], t["fonction_id"], t["nom"], t["salaire"], t["unite"],
             t["salaire_perso"], t["hypothese_manuelle"], t["grille_id_snapshot"], t["minimum_snapshot"],
             t["taux_snapshot"], t["date_ref_snapshot"]))
    for old in ancien.values():
        if old["technicien_id"]:
            conn.execute("UPDATE lignes SET technicien_id=? WHERE id=?",
                         (tech_map.get(old["technicien_id"]), mapping[old["id"]]))
    if src["rubrique_charges_id"] and src["rubrique_charges_id"] in mapping:
        conn.execute("UPDATE films SET rubrique_charges_id=? WHERE id=?", (mapping[src["rubrique_charges_id"]], nouveau_id))
    conn.commit()
    return nouveau_id


def backup_projet(conn, film_id):
    film = _film(conn, film_id)
    return {
        "format": "picturial-devis-backup",
        "version": 1,
        "film": dict(film),
        "lignes": [dict(r) for r in conn.execute("SELECT * FROM lignes WHERE film_id=? ORDER BY ordre", (film_id,)).fetchall()],
        "techniciens": [dict(r) for r in conn.execute("SELECT * FROM techniciens WHERE film_id=?", (film_id,)).fetchall()],
    }


def restaurer_projet(conn, data):
    import db
    if not isinstance(data, dict) or data.get("format") != "picturial-devis-backup":
        raise Erreur("Fichier de sauvegarde non reconnu (format picturial-devis-backup attendu).")
    src = data["film"]
    nouveau_id = db.creer_film(conn, src["titre"] + " (restauré)", societe=src.get("societe", ""),
                                type_oeuvre=src.get("type_oeuvre", "Long métrage"), region=src.get("region_cible", "Île-de-France"),
                                taux_charges=src.get("taux_charges", 0.40), convention_id=src.get("convention_id"),
                                grille_id=src.get("grille_id"), date_ref=src.get("date_ref_baremes", ""),
                                charges_mode=src.get("charges_mode", "avec"))
    conn.execute("DELETE FROM lignes WHERE film_id=?", (nouveau_id,))
    mapping = {}
    lignes = sorted(data.get("lignes", []), key=lambda l: (l.get("parent_id") is not None, l.get("ordre") or 0))
    # insère dans l'ordre topologique
    def insere(l):
        if l["id"] in mapping:
            return
        if l.get("parent_id") and l["parent_id"] not in mapping:
            old_parent = next((x for x in data["lignes"] if x["id"] == l["parent_id"]), None)
            if old_parent:
                insere(old_parent)
        nid = db.new_id()
        mapping[l["id"]] = nid
        conn.execute(
            "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
            " montant_forfait, montant_saisi, note, ordre, en_region, hors_region, etranger, ht, phase, regle, technicien_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nid, nouveau_id, mapping.get(l.get("parent_id")), l["type"], l.get("code", ""), l["libelle"],
             l.get("quantite"), l.get("unite", "forfait"), l.get("cout_unitaire"), l.get("montant_forfait"),
             l.get("montant_saisi", 1 if l.get("montant_forfait") is not None else 0),
             l.get("note", ""), l.get("ordre", 0), l.get("en_region", 0), l.get("hors_region", 0),
             l.get("etranger", 0), l.get("ht", 1), l.get("phase", ""), l.get("regle", ""), None))
    for l in data.get("lignes", []):
        insere(l)
    tech_map = {}
    for t in data.get("techniciens", []):
        nid = db.new_id()
        tech_map[t["id"]] = nid
        conn.execute(
            "INSERT INTO techniciens (id, film_id, ligne_id, fonction_id, nom, salaire, unite, salaire_perso,"
            " hypothese_manuelle, grille_id_snapshot, minimum_snapshot, taux_snapshot, date_ref_snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nid, nouveau_id, mapping[t["ligne_id"]], t.get("fonction_id"), t.get("nom", ""), t["salaire"],
             t.get("unite", "jour"), t.get("salaire_perso", 0), t.get("hypothese_manuelle", 0),
             t.get("grille_id_snapshot"), t.get("minimum_snapshot"), t.get("taux_snapshot"), t.get("date_ref_snapshot")))
    for l in data.get("lignes", []):
        if l.get("technicien_id"):
            conn.execute("UPDATE lignes SET technicien_id=? WHERE id=?", (tech_map.get(l["technicien_id"]), mapping[l["id"]]))
    film_champs = {k: src.get(k) for k in ("date_debut", "date_fin", "region_cible", "taux_charges", "charges_mode",
                                           "convention_id", "grille_id", "date_ref_baremes", "societe", "type_oeuvre", "nom_poste_charges")}
    set_clause = ", ".join(f"{k}=?" for k in film_champs)
    conn.execute(f"UPDATE films SET {set_clause} WHERE id=?", (*film_champs.values(), nouveau_id))
    rub = conn.execute("SELECT id FROM lignes WHERE film_id=? AND type='rubrique' AND libelle=?",
                       (nouveau_id, src.get("nom_poste_charges") or "Charges sociales")).fetchone()
    if rub:
        conn.execute("UPDATE films SET rubrique_charges_id=? WHERE id=?", (rub["id"], nouveau_id))
    conn.commit()
    return nouveau_id
