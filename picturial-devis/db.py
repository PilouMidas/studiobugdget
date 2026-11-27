#!/usr/bin/env python3
# Couche de persistance : schéma SQLite, référentiel (minimas CCNPC importés du document officiel
# + convention de démonstration), nomenclature CNC calquée sur le modèle « Devis À la recherche de la Boum ».
import json
import os
import re
import sqlite3
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

APP_NAME = "picturial-devis"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conventions (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS grilles (
    id TEXT PRIMARY KEY,
    convention_id TEXT NOT NULL REFERENCES conventions(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    date_effet TEXT NOT NULL,
    source TEXT DEFAULT '',
    statut TEXT NOT NULL DEFAULT 'demonstration' CHECK (statut IN ('verifie','demonstration'))
);

CREATE TABLE IF NOT EXISTS fonctions (
    id TEXT PRIMARY KEY,
    convention_id TEXT NOT NULL REFERENCES conventions(id) ON DELETE CASCADE,
    grille_id TEXT NOT NULL REFERENCES grilles(id) ON DELETE CASCADE,
    nom TEXT NOT NULL,
    minimum REAL NOT NULL,
    unite TEXT NOT NULL DEFAULT 'jour',
    valide_du TEXT DEFAULT '',
    valide_au TEXT DEFAULT '',
    source TEXT DEFAULT '',
    statut TEXT NOT NULL DEFAULT 'demonstration' CHECK (statut IN ('verifie','demonstration'))
);

CREATE TABLE IF NOT EXISTS films (
    id TEXT PRIMARY KEY,
    titre TEXT NOT NULL,
    societe TEXT DEFAULT '',
    type_oeuvre TEXT DEFAULT 'Long métrage',
    date_debut TEXT DEFAULT '',
    date_fin TEXT DEFAULT '',
    convention_id TEXT REFERENCES conventions(id),
    grille_id TEXT REFERENCES grilles(id),
    date_ref_baremes TEXT DEFAULT '',
    region_cible TEXT DEFAULT 'Île-de-France',
    taux_charges REAL NOT NULL DEFAULT 0.57,
    charges_mode TEXT NOT NULL DEFAULT 'poste_dedie' CHECK (charges_mode IN ('avec','poste_dedie')),
    rubrique_charges_id TEXT,
    nom_poste_charges TEXT DEFAULT 'Charges sociales',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lignes (
    id TEXT PRIMARY KEY,
    film_id TEXT NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES lignes(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'ligne' CHECK (type IN ('poste','rubrique','ligne','detail','technicien','charge')),
    code TEXT DEFAULT '',
    libelle TEXT NOT NULL,
    quantite REAL,
    unite TEXT DEFAULT 'forfait',
    cout_unitaire REAL,
    montant_forfait REAL,
    note TEXT DEFAULT '',
    ordre REAL NOT NULL DEFAULT 0,
    en_region REAL NOT NULL DEFAULT 0,
    hors_region REAL NOT NULL DEFAULT 0,
    etranger REAL NOT NULL DEFAULT 0,
    ht INTEGER NOT NULL DEFAULT 1,
    phase TEXT DEFAULT '',
    regle TEXT DEFAULT '',
    technicien_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_lignes_film ON lignes(film_id);
CREATE INDEX IF NOT EXISTS idx_lignes_parent ON lignes(parent_id);

CREATE TABLE IF NOT EXISTS techniciens (
    id TEXT PRIMARY KEY,
    film_id TEXT NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    ligne_id TEXT NOT NULL REFERENCES lignes(id) ON DELETE CASCADE,
    fonction_id TEXT REFERENCES fonctions(id),
    nom TEXT DEFAULT '',
    salaire REAL NOT NULL,
    unite TEXT NOT NULL DEFAULT 'jour',
    salaire_perso INTEGER NOT NULL DEFAULT 0,
    hypothese_manuelle INTEGER NOT NULL DEFAULT 0,
    grille_id_snapshot TEXT,
    minimum_snapshot REAL,
    taux_snapshot REAL,
    date_ref_snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_tech_film ON techniciens(film_id);
"""

REGIONS = [
    "Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne", "Centre-Val de Loire",
    "Corse", "Grand Est", "Hauts-de-France", "Île-de-France", "Normandie", "Nouvelle-Aquitaine",
    "Occitanie", "Pays de la Loire", "Provence-Alpes-Côte d'Azur",
    "Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte", "Hors France",
]

UNITES = ["jour", "semaine", "heure", "mois", "forfait", "unité", "kilomètre"]

PHASES = ["Préparation", "Tournage", "Finitions"]

# Nomenclature CNC calquée sur le modèle « DEVIS A LA RECHERCHE DE LA BOUM 22_10_26.xlsx » :
# 9 grands postes, codes et intitulés du modèle, lignes de charges sociales en poste 4 (règles en %),
# frais généraux 7 % et imprévus 3 % en lignes calculées de premier niveau.
# Structure : (type, code, libellé, [enfants] ou regle)
NOMENCLATURE_CNC = [
    ("poste", "1", "Droits artistiques", [
        ("ligne", "11", "Sujet"),
        ("ligne", "12", "Adaptation, dialogues, commentaires"),
        ("ligne", "13", "Droit d'auteur du réalisateur"),
        ("rubrique", "14", "Droits musicaux", [
            ("detail", "1411", "Droits compositeur"),
            ("detail", "1412", "Droits synchro"),
        ]),
        ("ligne", "15", "Droits divers (documents archives)"),
        ("ligne", "16", "Traductions et dactylographie"),
        ("ligne", "17", "Frais sur manuscrits"),
        ("ligne", "18", "Frais préliminaires et frais de reprise d'un projet existant"),
        ("ligne", "19", "Agents littéraires et conseils"),
    ]),
    ("poste", "2", "Personnel", [
        ("rubrique", "21", "Producteurs", [
            ("detail", "211", "Producteurs délégués"),
            ("detail", "212", "Producteurs exécutifs"),
            ("detail", "213", "Producteurs associés"),
        ]),
        ("rubrique", "22", "Réalisateur technicien", [
            ("detail", "221", "Réalisateur"),
        ]),
        ("ligne", "23", "Equipe préparation et tournage", [
            ("rubrique", "231", "Direction - Administration"),
            ("rubrique", "232", "Régie"),
            ("rubrique", "233", "Mise en scène techniciens"),
            ("rubrique", "234", "Conseillers spécialisés"),
            ("rubrique", "235", "Directeur de la photographie"),
            ("rubrique", "236", "Machinerie - Electricité"),
            ("rubrique", "237", "Son"),
            ("rubrique", "238", "Costumes"),
            ("rubrique", "239", "Maquillage - Coiffure"),
        ]),
        ("ligne", "24", "Equipe décoration"),
        ("ligne", "25", "Main d'oeuvre décors"),
        ("ligne", "26", "Montage et finitions"),
        ("ligne", "27", "Personnel affecté aux effets visuels (VFX)"),
        ("ligne", "28", "Divers (prestations personnel tournage et décors)"),
        ("ligne", "29", "Agents artistiques personnel technique"),
    ]),
    ("poste", "3", "Equipe artistique", [
        ("rubrique", "31", "Rôles principaux", [
            ("detail", "31S", "Salaires"),
            ("detail", "31B", "BNC"),
        ]),
        ("rubrique", "32", "Rôles secondaires", [
            ("detail", "32S", "Salaires"),
            ("detail", "32B", "BNC"),
        ]),
        ("ligne", "33", "Petits rôles, doublures, figuration (33 à 35)"),
        ("ligne", "36", "Personnel artistique après tournage"),
        ("ligne", "37", "Personnels musique"),
        ("ligne", "38", "Diverses prestations musiques"),
        ("ligne", "39", "Agents artistiques"),
    ]),
    ("poste", "4", "Charges sociales", [
        ("charge", "41", "Auteurs (20 % des postes 11, 12, 13)", {"regle": [{"source": ["11", "12", "13"], "taux": 0.20}]}),
        ("charge", "42", "Producteurs (64 % du poste 21)", {"regle": [{"source": ["21"], "taux": 0.64}]}),
        ("charge", "43", "Réalisateur technicien (57 % du poste 22)", {"regle": [{"source": ["22"], "taux": 0.57}]}),
        ("charge", "44", "Equipe technique (57 % du poste 2, hors postes 21 et 22)", {"regle": [{"source": ["2"], "exclure": ["21", "22"], "taux": 0.57}]}),
        ("charge", "45", "Artistes (52 % du poste 3 hors agents et BNC ; 10 % sur BNC)", {"regle": [{"source": ["3"], "exclure": ["39", "31B", "32B"], "taux": 0.52}, {"source": ["31B", "32B"], "taux": 0.10}]}),
        ("ligne", "46", "Eléments de salaires annexes"),
        ("ligne", "47", "Impôts et taxes imputés au film"),
    ]),
    ("poste", "5", "Décors et costumes", [
        ("rubrique", "51", "Studios", [
            ("detail", "512", "Plateaux et annexes"),
            ("detail", "513", "Construction"),
            ("detail", "514", "Consommation électrique"),
            ("detail", "515", "Consommations et prestations diverses"),
            ("detail", "516", "Prestations spécifiques"),
        ]),
        ("rubrique", "52", "Décors naturels intérieurs", [
            ("detail", "521", "Locations"),
            ("detail", "522", "Aménagements"),
            ("detail", "523", "Prestations"),
        ]),
        ("rubrique", "53", "Décors naturels extérieurs", [
            ("detail", "531", "Locations"),
            ("detail", "532", "Aménagements"),
            ("detail", "533", "Prestations"),
        ]),
        ("ligne", "54", "Meubles et accessoires"),
        ("ligne", "55", "Animaux"),
        ("ligne", "56", "Moyens de transports jouants"),
        ("ligne", "57", "Effets spéciaux et cascades"),
        ("ligne", "58", "Costumes"),
        ("ligne", "59", "Postiches et maquillage"),
    ]),
    ("poste", "6", "Transports, défraiements, régie", [
        ("ligne", "61", "Déplacements avant tournage"),
        ("ligne", "62", "Tournage"),
        ("ligne", "63", "Défraiements, déplacements après tournage, droits de douane (63 à 67)"),
        ("ligne", "68", "Frais de bureau, régie et divers (68 à 69)"),
    ]),
    ("poste", "7", "Moyens techniques", [
        ("ligne", "71", "Matériels prises de vues « cinéma »"),
        ("ligne", "72", "Matériels additionnels à la prise de vue"),
        ("ligne", "73", "Machineries"),
        ("ligne", "74", "Eclairage"),
        ("ligne", "75", "Son"),
        ("ligne", "76", "Pellicules et supports"),
    ]),
    ("poste", "8", "Postproduction image et son", [
        ("rubrique", "81", "Montage image et son", [
            ("detail", "811", "Montage image"),
            ("detail", "812", "Montage son"),
            ("detail", "813", "Projections"),
            ("detail", "814", "Prestations son"),
            ("detail", "815", "Prestations post-synchro"),
            ("detail", "816", "Auditorium"),
            ("detail", "817", "Postproduction making of"),
        ]),
        ("ligne", "82", "Laboratoire argentique"),
        ("rubrique", "83", "Laboratoire numérique", [
            ("detail", "831", "Travaux avant tournage"),
            ("detail", "832", "Traitement rushes"),
            ("detail", "833", "Travaux après montage"),
            ("detail", "834", "Travaux stéréographie"),
        ]),
        ("ligne", "84", "Effets visuels numériques"),
        ("ligne", "85", "Générique et films annonces"),
        ("ligne", "86", "Eléments de livraison"),
        ("ligne", "87", "Sous-titrages et audiodescription"),
        ("ligne", "88", "Frais photographiques"),
        ("ligne", "89", "Conservations"),
    ]),
    ("poste", "9", "Assurances et divers", [
        ("ligne", "91", "Assurances"),
        ("ligne", "92", "Publicité, promotion et divers"),
        ("ligne", "93", "Frais juridiques, frais divers et certification des comptes"),
        ("ligne", "94", "Frais financiers"),
    ]),
]

FRAIS_GENERAUX = ("charge", "FG", "Frais généraux (7 % du total des postes 1 à 9)",
                  {"regle": [{"source": ["1", "2", "3", "4", "5", "6", "7", "8", "9"], "taux": 0.07}]})
IMPREVUS = ("charge", "IMP", "Imprévus (3 % du total des postes 1 à 9)",
            {"regle": [{"source": ["1", "2", "3", "4", "5", "6", "7", "8", "9"], "taux": 0.03}]})

MINIMAS_FILE = os.path.join(BASE_DIR, "modeles",
                            "PCINE-Salaires-minimas-conventionnels-applicables-au-1er-juin-2026.xlsx")
MINIMAS_SOURCE = "PCINE — Salaires minimas conventionnels applicables au 1er juin 2026.xlsx"


def new_id():
    return uuid.uuid4().hex


def default_data_dir():
    env = os.environ.get("PICTURIAL_DATA_DIR")
    if env:
        return env
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Picturial")
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(xdg, "picturial")


def default_db_path():
    return os.environ.get("PICTURIAL_DB") or os.path.join(default_data_dir(), "devis.db")


def connect(path=None):
    path = path or default_db_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrer(conn)
    return conn


def _migrer(conn):
    """Ajoute les colonnes apparues en v2 (etranger, regle) sur les bases existantes."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(lignes)")}
    if "etranger" not in cols:
        conn.execute("ALTER TABLE lignes ADD COLUMN etranger REAL NOT NULL DEFAULT 0")
    if "regle" not in cols:
        conn.execute("ALTER TABLE lignes ADD COLUMN regle TEXT DEFAULT ''")
    cols_f = {r["name"] for r in conn.execute("PRAGMA table_info(films)")}
    if "taux_charges" not in cols_f:
        conn.execute("ALTER TABLE films ADD COLUMN taux_charges REAL NOT NULL DEFAULT 0.57")
    conn.commit()


def row_to_dict(row):
    return dict(row) if row is not None else None


# ---------------------------------------------------------------- import des minimas CCNPC

def _lire_xlsx(path):
    z = zipfile.ZipFile(path)
    M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    ss = []
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{M}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{M}t")))
    except KeyError:
        pass
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    onglets = {}
    for sh in wb.find(f"{M}sheets"):
        name = sh.get("name")
        rid = sh.get(f"{R}id")
        root = ET.fromstring(z.read("xl/" + relmap[rid].lstrip("/")))
        rows = {}
        for c in root.iter(f"{M}c"):
            ref = c.get("r")
            m = re.match(r"([A-Z]+)(\d+)", ref or "")
            if not m:
                continue
            col, row = m.group(1), int(m.group(2))
            t = c.get("t")
            v = c.find(f"{M}v")
            isel = c.find(f"{M}is")
            val = None
            if t == "s" and v is not None:
                val = ss[int(v.text)]
            elif t == "inlineStr" and isel is not None:
                val = "".join(x.text or "" for x in isel.iter(f"{M}t"))
            elif v is not None:
                val = v.text
            if val not in (None, ""):
                rows.setdefault(row, {})[col] = val
        onglets[name] = rows
    return onglets


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def importer_minimas_ccnpc(conn, path=MINIMAS_FILE):
    """Importe le document officiel des minimas PCINE comme convention + grilles datées.
    Chaque fonction reprend son onglet d'origine en source, statut « vérifié »."""
    if not os.path.isfile(path):
        return None
    if conn.execute("SELECT COUNT(*) AS n FROM conventions WHERE nom LIKE 'CCNPC%'").fetchone()["n"]:
        return conn.execute("SELECT id FROM conventions WHERE nom LIKE 'CCNPC%' LIMIT 1").fetchone()["id"]
    onglets = _lire_xlsx(path)
    conv_id = new_id()
    conn.execute(
        "INSERT INTO conventions (id, nom, description) VALUES (?,?,?)",
        (conv_id, "CCNPC — Convention collective nationale de la production cinématographique (IDCC 3097)",
         "Minimas importés du document officiel « Salaires minimas conventionnels applicables au 1er juin 2026 »."),
    )

    def ajouter_grille(version, onglet, unite, rows_fonctions, date_effet="2026-06-01"):
        gid = new_id()
        conn.execute(
            "INSERT INTO grilles (id, convention_id, version, date_effet, source, statut) VALUES (?,?,?,?,?,?)",
            (gid, conv_id, version, date_effet, f"{MINIMAS_SOURCE}, onglet « {onglet} »", "verifie"),
        )
        n = 0
        for nom, minimum, source_extra in rows_fonctions:
            if not nom or minimum is None:
                continue
            conn.execute(
                "INSERT INTO fonctions (id, convention_id, grille_id, nom, minimum, unite, valide_du, valide_au, source, statut)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id(), conv_id, gid, nom.strip(), minimum, unite, date_effet, "",
                 f"{MINIMAS_SOURCE}, onglet « {onglet} »" + (f" — {source_extra}" if source_extra else ""), "verifie"),
            )
            n += 1
        return gid, n

    # Annexe 1 (base 39h) : salaire minimum garanti hebdomadaire + taux horaire
    rows = []
    for r in sorted(onglets.get("Annexe 1", {})):
        c = onglets["Annexe 1"][r]
        nom, mini, taux = c.get("A"), _num(c.get("B")), c.get("C")
        if nom and mini is not None and r >= 10 and "Fonctions" not in str(nom):
            rows.append((str(nom), mini, f"taux horaire {taux} €/h" if taux else ""))
    g1, _ = ajouter_grille("Annexe 1 — base 39h (minimas au 01/06/2026)", "Annexe 1", "semaine", rows)

    # Annexe 2 (équivalence tournage) : colonne D = salaire minimum garanti hebdo 5 jours
    rows = []
    for r in sorted(onglets.get("Annexe 2", {})):
        c = onglets["Annexe 2"][r]
        nom, mini = c.get("A"), _num(c.get("D"))
        if nom and mini is not None and r >= 11 and "Fonctions" not in str(nom):
            rows.append((str(nom), mini, f"{c.get('B','')}h eff. / {c.get('C','')}h équiv., taux horaire {c.get('E','')} €/h"))
    ajouter_grille("Annexe 2 — équivalence tournage, hebdo 5 jours (01/06/2026)", "Annexe 2", "semaine", rows)

    # Annexe 3 accord 2025 (dérogation, base 39h) : colonne B
    rows = []
    for r in sorted(onglets.get("Annexe 3 - accord 2025", {})):
        c = onglets["Annexe 3 - accord 2025"][r]
        nom, mini = c.get("A"), _num(c.get("B"))
        if nom and mini is not None and r >= 11 and "Fonctions" not in str(nom):
            rows.append((str(nom), mini, f"intéressement {c.get('C','')} €, taux horaire {c.get('D','')} €/h"))
    ajouter_grille("Annexe 3 — accord 2025, dérogation, base 39h (01/06/2026)", "Annexe 3 - accord 2025", "semaine", rows)

    # Annexe 3 bis accord 2025 (équivalence) : colonne D
    rows = []
    for r in sorted(onglets.get("Annexe 3 bis - accord 2025", {})):
        c = onglets["Annexe 3 bis - accord 2025"][r]
        nom, mini = c.get("A"), _num(c.get("D"))
        if nom and mini is not None and r >= 12 and "Fonctions" not in str(nom):
            rows.append((str(nom), mini, f"intéressement {c.get('E','')} €, taux horaire {c.get('F','')} €/h"))
    ajouter_grille("Annexe 3 bis — accord 2025, dérogation, équivalence tournage (01/06/2026)", "Annexe 3 bis - accord 2025", "semaine", rows)

    # Annexe 4 : salaires minima mensuels des permanents (classification)
    rows = []
    for r in sorted(onglets.get("Annexe 4", {})):
        c = onglets["Annexe 4"][r]
        cls, niv, qual, mini = c.get("A"), c.get("B"), c.get("C"), _num(c.get("D"))
        if cls and mini is not None and niv and str(niv) != "" and "Hors niveau" not in str(mini):
            rows.append((f"{cls} — {qual} (niveau {niv})", mini,
                         f"compléments autonomie/technicité/responsabilité 3 % chacun ; annuel base {c.get('E','')} €"))
    ajouter_grille("Annexe 4 — permanents de l'entreprise, salaires mensuels (01/06/2026)", "Annexe 4", "mois", rows)

    # Artistes-interprètes long métrage
    rows = [
        ("Artiste-interprète — journée (8 h)", 418.25, "rémunération L. 212-4 al. 2 : 33 % du minimum (hors HMC 16,73 €/j)"),
        ("Artiste-interprète — semaine 5 jours", 1266.70, "L. 212-4 : 33 % du minimum"),
        ("Artiste-interprète — semaine 6 jours", 1570.23, "L. 212-4 : 33 % du minimum"),
        ("Artiste chorégraphique/lyrique/musicien — service 3 h", 54.37, "répétitions"),
        ("Autre artiste — service 4 h", 54.37, "répétitions"),
        ("Autre artiste — service 2 x 4 h", 98.48, "répétitions"),
    ]
    ajouter_grille("Artistes-interprètes — long métrage (01/06/2026)", "Artistes-interprètes",
                   "jour", [rows[0]])
    g_art, _ = ajouter_grille("Artistes-interprètes — semaines (01/06/2026)", "Artistes-interprètes",
                              "semaine", rows[1:3])
    conn.execute("UPDATE fonctions SET unite='jour' WHERE grille_id=? AND nom LIKE '%service%'",
                 (g_art,))
    ajouter_grille("Artistes-interprètes — répétitions (01/06/2026)", "Artistes-interprètes",
                   "heure", rows[3:])

    # Artistes de complément (figuration) : jour / semaine 5j / semaine 6j
    rows_j, rows_s5, rows_s6 = [], [], []
    for r in sorted(onglets.get("Artistes de complément", {})):
        c = onglets["Artistes de complément"][r]
        nom = c.get("A")
        b, cc, d = _num(c.get("B")), _num(c.get("C")), _num(c.get("D"))
        if nom and (b or cc or d) and r >= 11 and "Emploi" not in str(nom):
            if b:
                rows_j.append((str(nom), b, f"taux horaire {c.get('E','')} €/h"))
            if cc:
                rows_s5.append((str(nom), cc, "semaine 5 jours"))
            if d:
                rows_s6.append((str(nom), d, "semaine 6 jours"))
    ajouter_grille("Artistes de complément — jour (01/06/2026)", "Artistes de complément", "jour", rows_j)
    ajouter_grille("Artistes de complément — semaine 5 jours (01/06/2026)", "Artistes de complément", "semaine", rows_s5)
    ajouter_grille("Artistes de complément — semaine 6 jours (01/06/2026)", "Artistes de complément", "semaine", rows_s6)

    # Réalisateurs
    rows = [
        ("Réalisateur — salaire minimum hebdomadaire (annexe 1, contrat < 5 mois)", 3015.27, "contrat < 5 mois"),
        ("Réalisateur — salaire minimum mensuel (annexe 1, contrat ≥ 5 mois)", 8563.3668, "contrat ≥ 5 mois"),
        ("Réalisateur — hebdomadaire (hors production du film)", 1977.682864, "engagement ≥ 1 semaine"),
        ("Réalisateur — journalier (hors production, < 5 jours)", 494.4207159, ""),
        ("Réalisateur de films publicitaires — hebdomadaire", 3733.93, ""),
        ("Réalisateur de films publicitaires — journalier", 933.4825, "< 5 jours consécutifs"),
    ]
    ajouter_grille("Réalisateurs — minimas au 01/06/2026 (SMIC 12,31 €/h)", "Réalisateurs", "semaine", rows[:1] + rows[2:])
    g_m = ajouter_grille("Réalisateurs — mensuel (01/06/2026)", "Réalisateurs", "mois", rows[1:2])
    conn.commit()
    return conv_id


def seed_referentiel(conn):
    """Convention de démonstration (montants fictifs, v1) + CCNPC importé du document officiel."""
    cur = conn.execute("SELECT COUNT(*) AS n FROM conventions")
    if cur.fetchone()["n"] > 0:
        return
    conv_id = new_id()
    conn.execute(
        "INSERT INTO conventions (id, nom, description) VALUES (?,?,?)",
        (conv_id, "Convention de démonstration (montants fictifs)",
         "Grille fictive pour tester le logiciel — à remplacer par la CCNPC importée ou votre propre convention."),
    )
    grille_id = new_id()
    conn.execute(
        "INSERT INTO grilles (id, convention_id, version, date_effet, source, statut) VALUES (?,?,?,?,?,?)",
        (grille_id, conv_id, "Grille démo 2024-01", "2024-01-01",
         "Montants fictifs créés pour la démonstration — aucune source officielle revendiquée.", "demonstration"),
    )
    fonctions = [
        ("Chef opérateur du son", 250.0, "jour"),
        ("Ingénieur du son", 220.0, "jour"),
        ("Scripte", 180.0, "jour"),
        ("Chef opérateur image", 1300.0, "semaine"),
        ("Réalisateur", 1800.0, "semaine"),
        ("Chef décorateur", 350.0, "jour"),
        ("Monteur", 420.0, "jour"),
        ("Chef costumier", 300.0, "jour"),
    ]
    for nom, minimum, unite in fonctions:
        conn.execute(
            "INSERT INTO fonctions (id, convention_id, grille_id, nom, minimum, unite, valide_du, valide_au, source, statut)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_id(), conv_id, grille_id, nom, minimum, unite, "2024-01-01", "",
             "Montant fictif de démonstration.", "demonstration"),
        )
    conn.commit()
    importer_minimas_ccnpc(conn)


# ---------------------------------------------------------------- nomenclature

def _inserer_noeud(conn, film_id, parent_id, spec, ordre):
    type_, code, libelle = spec[0], spec[1], spec[2]
    enfants = spec[3] if len(spec) > 3 and isinstance(spec[3], list) else None
    regle = spec[3] if len(spec) > 3 and isinstance(spec[3], dict) else None
    lid = new_id()
    conn.execute(
        "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, quantite, unite, cout_unitaire,"
        " montant_forfait, note, ordre, en_region, hors_region, etranger, ht, phase, regle)"
        " VALUES (?,?,?,?,?,?,NULL,'forfait',NULL,NULL,'',?,0,0,0,1,'',?)",
        (lid, film_id, parent_id, type_, code, libelle, ordre, json.dumps(regle, ensure_ascii=False) if regle else ""),
    )
    i = 1
    if enfants:
        for sous in enfants:
            _inserer_noeud(conn, film_id, lid, sous, i)
            i += 1
    return lid


def seed_nomenclature(conn, film_id, frais_generaux=True):
    """Nomenclature CNC (9 postes du modèle) + lignes calculées FG 7 % / imprévus 3 %."""
    ordre = 0
    rubrique_charges_id = None
    for spec in NOMENCLATURE_CNC:
        ordre += 100
        poste_id = _inserer_noeud(conn, film_id, None, spec, ordre)
        if spec[1] == "4":
            rubrique_charges_id = poste_id
    if frais_generaux:
        ordre += 100
        _inserer_noeud(conn, film_id, None, FRAIS_GENERAUX, ordre)
        ordre += 100
        _inserer_noeud(conn, film_id, None, IMPREVUS, ordre)
    return rubrique_charges_id


def creer_film(conn, titre, societe="", type_oeuvre="Long métrage", region="Île-de-France", taux_charges=0.57,
               convention_id=None, grille_id=None, date_ref="", charges_mode="poste_dedie", frais_generaux=True):
    if convention_id is None:
        row = conn.execute("SELECT id FROM conventions WHERE nom LIKE 'CCNPC%' ORDER BY rowid LIMIT 1").fetchone() \
            or conn.execute("SELECT id FROM conventions ORDER BY rowid LIMIT 1").fetchone()
        convention_id = row["id"] if row else None
    if grille_id is None and convention_id:
        row = conn.execute(
            "SELECT id, date_effet FROM grilles WHERE convention_id=? AND version LIKE 'Annexe 1%'"
            " ORDER BY date_effet DESC, rowid DESC LIMIT 1", (convention_id,)).fetchone() \
            or conn.execute(
            "SELECT id, date_effet FROM grilles WHERE convention_id=? ORDER BY date_effet DESC, rowid DESC LIMIT 1",
            (convention_id,)).fetchone()
        if row:
            grille_id = row["id"]
            if not date_ref:
                date_ref = row["date_effet"]
    if not date_ref:
        date_ref = date.today().isoformat()
    film_id = new_id()
    now = date.today().isoformat()
    conn.execute(
        "INSERT INTO films (id, titre, societe, type_oeuvre, date_debut, date_fin, convention_id, grille_id,"
        " date_ref_baremes, region_cible, taux_charges, charges_mode, rubrique_charges_id, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?)",
        (film_id, titre, societe, type_oeuvre, "", "", convention_id, grille_id, date_ref, region,
         taux_charges, charges_mode, now, now),
    )
    rubrique_charges_id = seed_nomenclature(conn, film_id, frais_generaux=frais_generaux)
    conn.execute("UPDATE films SET rubrique_charges_id=? WHERE id=?", (rubrique_charges_id, film_id))
    conn.commit()
    return film_id


def seed_demo(conn):
    """Projet de démonstration « À la recherche de la Boum — démonstration » (montants fictifs)."""
    cur = conn.execute("SELECT COUNT(*) AS n FROM films")
    if cur.fetchone()["n"] > 0:
        return
    import engine
    # le démo reste sur la convention fictive (fonctions en €/jour) pour pouvoir rejouer la recette
    conv = conn.execute("SELECT id FROM conventions WHERE nom LIKE '%démonstration%'").fetchone() \
        or conn.execute("SELECT id FROM conventions ORDER BY rowid LIMIT 1").fetchone()
    grille = conn.execute("SELECT id, date_effet FROM grilles WHERE convention_id=? ORDER BY rowid LIMIT 1", (conv["id"],)).fetchone()
    film_id = creer_film(
        conn, "À la recherche de la Boum — démonstration",
        societe="Picturial (société fictive de démonstration)",
        type_oeuvre="Long métrage",
        region="Île-de-France",
        taux_charges=0.40,
        convention_id=conv["id"],
        grille_id=grille["id"],
        date_ref=grille["date_effet"],
    )
    conn.execute("UPDATE films SET date_debut='2025-03-03', date_fin='2025-04-11', updated_at=? WHERE id=?",
                 (date.today().isoformat(), film_id))
    fonc = conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
    rubrique_son = conn.execute(
        "SELECT l.id FROM lignes l WHERE l.film_id=? AND l.type='rubrique' AND l.code='237'", (film_id,)).fetchone()
    engine.ajouter_technicien(
        conn, film_id, rubrique_son["id"], fonc["id"], nom="(nom à préciser)",
        salaire=250.0, unite="jour",
        phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                {"phase": "Tournage", "quantite": 5, "unite": "jour"}],
    )
    ligne_cam = conn.execute(
        "SELECT l.id FROM lignes l WHERE l.film_id=? AND l.code='71'", (film_id,)).fetchone()
    cam_id = engine.ajouter_ligne(conn, film_id, ligne_cam["id"], type_ligne="ligne",
                                  libelle="Location caméra", unite="forfait", ht=True)
    d1 = engine.ajouter_ligne(conn, film_id, cam_id, type_ligne="detail", libelle="Corps caméra",
                              quantite=5, unite="jour", cout_unitaire=120.0, ht=True)
    d2 = engine.ajouter_ligne(conn, film_id, cam_id, type_ligne="detail", libelle="Série optiques",
                              montant_forfait=400.0, unite="forfait", ht=True)
    engine.set_ventilation(conn, film_id, d1, mode="tout_en")
    engine.set_ventilation(conn, film_id, d2, mode="tout_hors")
    conn.commit()


def initialiser(path=None):
    conn = connect(path)
    seed_referentiel(conn)
    seed_demo(conn)
    return conn
