#!/usr/bin/env python3
# Couche de persistance : schéma SQLite, référentiel de démonstration et nomenclature.
import os
import sqlite3
import sys
import uuid
from datetime import date

APP_NAME = "picturial-devis"

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
    taux_charges REAL NOT NULL DEFAULT 0.40,
    charges_mode TEXT NOT NULL DEFAULT 'avec' CHECK (charges_mode IN ('avec','poste_dedie')),
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
    ht INTEGER NOT NULL DEFAULT 1,
    phase TEXT DEFAULT '',
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

UNITES = ["jour", "semaine", "heure", "forfait", "unité", "kilomètre"]

# Nomenclature provisoire à neuf grands postes (éditable ensuite dans l'interface).
NOMENCLATURE = [
    ("1", "Droits artistiques et scénario", ["Droits d'auteur", "Scénario et adaptation"]),
    ("2", "Rémunérations artistiques", ["Comédiens", "Réalisation"]),
    ("3", "Personnel technique", ["Image", "Son", "Régie technique", "Charges sociales"]),
    ("4", "Régie", ["Régie générale", "Catering"]),
    ("5", "Décors", ["Construction", "Accessoires", "Décors plateau"]),
    ("6", "Costumes, maquillage, coiffure", ["Costumes", "Maquillage", "Coiffure"]),
    ("7", "Moyens techniques", ["Caméra", "Optiques", "Son", "Lumière", "Machinerie"]),
    ("8", "Transports et déplacements", ["Véhicules", "Kilométrage", "Hébergement", "Voyages"]),
    ("9", "Post-production et frais généraux", ["Montage", "Étalonnage", "Mixage", "Frais généraux", "Assurances"]),
]

PHASES = ["Préparation", "Tournage", "Finitions"]


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
    return conn


def row_to_dict(row):
    return dict(row) if row is not None else None


def seed_referentiel(conn):
    """Convention, grille et fonctions de démonstration (montants fictifs, marqués comme tels)."""
    cur = conn.execute("SELECT COUNT(*) AS n FROM conventions")
    if cur.fetchone()["n"] > 0:
        return
    conv_id = new_id()
    conn.execute(
        "INSERT INTO conventions (id, nom, description) VALUES (?,?,?)",
        (conv_id, "Convention collective de la production cinématographique — branche long métrage",
         "Convention de démonstration pour la première version du logiciel."),
    )
    grille_id = new_id()
    conn.execute(
        "INSERT INTO grilles (id, convention_id, version, date_effet, source, statut) VALUES (?,?,?,?,?,?)",
        (grille_id, conv_id, "Grille 2024-01", "2024-01-01",
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


def seed_nomenclature(conn, film_id, nom_poste_charges="Charges sociales"):
    """Crée la trame provisoire à neuf grands postes pour un film."""
    ordre = 0.0
    rubrique_charges_id = None
    for code, libelle, rubriques in NOMENCLATURE:
        ordre += 100
        poste_id = new_id()
        conn.execute(
            "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, unite, ordre, ht) VALUES (?,?,?,?,?,?,?,?,1)",
            (poste_id, film_id, None, "poste", code, libelle, "forfait", ordre),
        )
        r = 0.0
        for rub in rubriques:
            r += 1
            rub_id = new_id()
            if rub == nom_poste_charges:
                rubrique_charges_id = rub_id
            conn.execute(
                "INSERT INTO lignes (id, film_id, parent_id, type, code, libelle, unite, ordre, ht) VALUES (?,?,?,?,?,?,?,?,1)",
                (rub_id, film_id, poste_id, "rubrique", f"{code}.{r}", rub, "forfait", r),
            )
    return rubrique_charges_id


def creer_film(conn, titre, societe="", type_oeuvre="Long métrage", region="Île-de-France", taux_charges=0.40,
               convention_id=None, grille_id=None, date_ref="", charges_mode="avec"):
    if convention_id is None:
        row = conn.execute("SELECT id FROM conventions ORDER BY rowid LIMIT 1").fetchone()
        convention_id = row["id"] if row else None
    if grille_id is None and convention_id:
        row = conn.execute(
            "SELECT id, date_effet FROM grilles WHERE convention_id=? ORDER BY date_effet DESC, rowid DESC LIMIT 1",
            (convention_id,),
        ).fetchone()
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
    rubrique_charges_id = seed_nomenclature(conn, film_id)
    conn.execute("UPDATE films SET rubrique_charges_id=? WHERE id=?", (rubrique_charges_id, film_id))
    conn.commit()
    return film_id


def seed_demo(conn):
    """Projet de démonstration « À la recherche de la Boum — démonstration » (montants fictifs)."""
    cur = conn.execute("SELECT COUNT(*) AS n FROM films")
    if cur.fetchone()["n"] > 0:
        return
    import engine
    film_id = creer_film(
        conn, "À la recherche de la Boum — démonstration",
        societe="Picturial (société fictive de démonstration)",
        type_oeuvre="Long métrage",
        region="Île-de-France",
        taux_charges=0.40,
    )
    conn.execute("UPDATE films SET date_debut='2025-03-03', date_fin='2025-04-11', updated_at=? WHERE id=?",
                 (date.today().isoformat(), film_id))
    # Technicien de démonstration : Chef opérateur du son, 250 €/jour, 2 j prépa + 5 j tournage.
    fonc = conn.execute("SELECT * FROM fonctions WHERE nom='Chef opérateur du son'").fetchone()
    rubrique_son = conn.execute(
        "SELECT l.id FROM lignes l JOIN lignes p ON l.parent_id=p.id WHERE l.film_id=? AND l.type='rubrique'"
        " AND l.libelle='Son' AND p.libelle='Personnel technique'", (film_id,)).fetchone()
    engine.ajouter_technicien(
        conn, film_id, rubrique_son["id"], fonc["id"], nom="(nom à préciser)",
        salaire=250.0, unite="jour",
        phases=[{"phase": "Préparation", "quantite": 2, "unite": "jour"},
                {"phase": "Tournage", "quantite": 5, "unite": "jour"}],
    )
    # Location caméra détaillée en deux sous-détails, ventilée 600 € en région / 400 € hors région.
    rubrique_cam = conn.execute(
        "SELECT l.id FROM lignes l JOIN lignes p ON l.parent_id=p.id WHERE l.film_id=? AND l.type='rubrique'"
        " AND l.libelle='Caméra' AND p.libelle='Moyens techniques'", (film_id,)).fetchone()
    cam_id = engine.ajouter_ligne(conn, film_id, rubrique_cam["id"], type_ligne="ligne",
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
