# Picturial — Devis de production (v1 locale)

Logiciel de devis pour la production cinéma et audiovisuelle. Aucune installation d'outil
de développement : il suffit de **décompresser le ZIP** et de **double-cliquer sur
« Ouvrir le devis.command »**. L'application s'ouvre dans votre navigateur sur
`http://127.0.0.1:<port>/`.

## ⚠️ Premier lancement sur Mac : débloquer le Gatekeeper

Le ZIP téléchargé depuis GitHub porte l'attribut de « quarantaine » d'Apple : au premier
double-clic, macOS peut afficher « Ouvrir le devis.command n'a pas pu être ouvert car Apple
n'a pas pu confirmer qu'il ne contient pas de logiciel malveillant ». **C'est normal pour
tout logiciel non signé Apple.** Deux solutions, au choix :

1. **Clic droit (ou Ctrl+clic)** sur `Ouvrir le devis.command` → **« Ouvrir »** → cliquez
   « Ouvrir » dans la boîte de dialogue. macOS mémorisera ensuite le déblocage.
2. **Ou en une commande dans le Terminal** (une seule fois, après décompression) :
   ```
   xattr -dr com.apple.quarantine "/chemin/vers/le/dossier/picturial-devis"
   ```
   (adaptez le chemin ; gardez les guillemets s'il contient des espaces ou des accents).

Sans cette étape, macOS propose uniquement « Placer dans la corbeille » / « Terminé ».

## Ouvrir le logiciel (Mac)

1. Décompressez le ZIP (le dossier peut s'appeler comme vous voulez, espaces et accents acceptés).
2. Double-cliquez sur **`Ouvrir le devis.command`**.
3. Le lanceur démarre le serveur local, attend qu'il soit prêt, puis ouvre votre navigateur
   par défaut. S'il tourne déjà, le lanceur rouvre simplement l'instance existante.
   En cas de problème, un message en français s'affiche (journal : `serveur.log` à côté des données).

**Seul prérequis non embarqué :** Python 3, présent sur macOS. Si une fenêtre système vous
propose d'installer les « Command Line Developer Tools », acceptez (ou exécutez
`xcode-select --install` dans le Terminal), puis relancez le `.command`. Le lanceur détecte
l'absence de Python 3 et affiche la marche à suivre.

## Où sont vos données

Vos films sont enregistrés dans une base SQLite **hors du dossier de l'application**, donc
conservés si vous remplacez le dossier par une nouvelle version :

- **Mac :** `~/Library/Application Support/Picturial/devis.db`
- **Linux :** `~/.local/share/picturial/devis.db`
- (surcharge possible via la variable d'environnement `PICTURIAL_DATA_DIR`)

Fermez le navigateur, éteignez le Mac, relancez le lendemain : le devis est identique.

## Premiers pas

- Ouvrez le projet de démonstration **« À la recherche de la Boum — démonstration »**
  (montants fictifs) ou créez un **Nouveau film** (projet vierge).
- Quatre onglets : **Paramètres du film** (convention, grille, date de référence des barèmes,
  région cible, taux de charges employeur), **Devis** (tableau hiérarchique à neuf grands
  postes, provisoire et éditable), **Région** (ventilation en région / hors région),
  **Barèmes** (conventions, versions de grilles datées, fonctions avec minimum, unité, source
  et statut « VÉRIFIÉ » / « DÉMONSTRATION »).
- Depuis une ligne du devis, le menu « ⋯ » propose : **Ajouter un sous-détail**,
  **Ajouter un technicien**, dupliquer, **Déplacer vers…**, ventiler, supprimer.
- Exports dans la barre du haut : **Excel** (.xlsx : récapitulatif + détail + ventilation
  régionale, montants en cellules numériques), **Imprimer** (vue propre, enregistrer en PDF),
  **Sauvegarder / Restaurer** (sauvegarde complète du projet en JSON).

## Règles de calcul

- Un seul moteur de calcul partagé par l'écran Devis, la vue Région, l'impression et l'export Excel.
- Arrondi au centime (demi au supérieur), nombres au format français, propagation immédiate
  des sous-détails jusqu'au total général.
- Ligne détaillée = somme de ses sous-détails. Passer d'un forfait à un détail demande
  explicitement de reprendre l'estimation comme premier sous-détail ou de la remplacer :
  aucun montant n'est compté deux fois ni perdu.
- « Ajouter un technicien » : fonction recherchée dans le barème du film, salaire prérempli
  au minimum (remplaçable, avertissement si inférieur), périodes par phase (préparation /
  tournage / finitions), aperçu brut + charges + coût employeur avant validation, puis
  engagement rouvrable et modifiable. Un barème hebdomadaire n'est jamais divisé
  automatiquement en jours : unité compatible exigée, ou « hypothèse manuelle » cochée et
  signalée. Le devis conserve la version de barème utilisée au chiffrage ;
  « Actualiser les barèmes du devis » (onglet Paramètres) montre les écarts avant validation,
  préserve les salaires négociés et signale ceux passant sous le nouveau minimum.
- Ventilation : chaque ligne peut être affectée en région, hors région, ou répartie ;
  « en région + hors région + à ventiler = devis général » est vérifié en permanence.
  Changer de région cible avec des dépenses déjà ventilées demande une confirmation explicite.

## Tests exécutés (dans l'environnement de développement, Linux + Python 3.12)

- `python3 -m unittest discover -s tests` : **25 tests OK**, couvrant la recette complète
  (technicien 250 €/jour × 2 j prépa + 5 j tournage → 1 750 € brut, 700 € charges, 2 450 € ;
  passage à 6 j → 2 000 € / 800 € / 2 800 €, hausse du total exactement 350 € ; location
  caméra 600 + 400 → 1 000 €, film 3 800 € ; ventilation 600/400 avec 2 800 € à ventiler,
  colonnes qui retombent sur 3 800 € ; barème 250 → 260 € sans changement du devis jusqu'à
  l'actualisation volontaire, aperçu des écarts, puis application), les règles métier
  (pas de double comptage forfait → sous-détail, barème hebdomadaire non divisé, salaire
  sous minimum signalé, charges en poste dédié comptées une seule fois, salaire négocié
  préservé, confirmation de changement de région, déplacement/suppression), la persistance
  (fermeture/réouverture de la base), la sauvegarde/restauration (mêmes totaux), la
  duplication de film et la relecture du fichier .xlsx produit (totaux en cellules numériques).
- Test d'intégration HTTP : le vrai serveur est démarré sur un port éphémère et toute la
  recette est rejouée via les mêmes routes JSON que l'interface web, plus export .xlsx,
  sauvegarde/restauration, vue imprimable, duplication/suppression de film.
- Le lanceur `.command` a été testé sous Linux (démarrage du serveur, attente de disponibilité,
  réouverture si déjà lancé, choix d'un port libre) dans un chemin contenant espaces et accents.

## Limites connues de cette v1

- **À vérifier sur votre Mac** : l'ouverture automatique du navigateur utilise la commande
  `open` de macOS (non testable depuis cet environnement Linux) ; le ZIP préserve bien le
  droit d'exécution du lanceur (vérifié avec `zipinfo`).
- La nomenclature à neuf postes est **provisoire** et éditable ; aucun modèle de devis CNC
  officiel n'était disponible dans l'espace de travail, donc tous les montants de barèmes
  sont marqués « DÉMONSTRATION » avec leur source fictive indiquée.
- L'export Excel est un .xlsx valide en lecture seule (pas de formules Excel internes :
  les totaux y sont des valeurs numériques, cohérents avec l'écran).
- Un seul utilisateur à la fois (application locale mono-poste).
- Hébergement en ligne : non livré dans cette version. L'architecture est prête
  (interface web + serveur applicatif + SQLite + moteur de calcul séparé) : il suffira
  de changer la configuration (hôte/port) et éventuellement de remplacer la couche SQLite
  par une base distante.

## Arborescence

```
picturial-devis/
├── Ouvrir le devis.command   # lanceur (double-clic)
├── server.py                 # serveur applicatif : API JSON + statique + exports
├── engine.py                 # moteur de calcul unique (devis, région, exports)
├── db.py                     # schéma SQLite + référentiel et projet de démonstration
├── xlsx_export.py            # export Excel .xlsx (bibliothèque standard uniquement)
├── static/                   # interface web (index.html, app.js, styles.css)
├── tests/                    # tests automatisés (moteur + API HTTP)
└── LIRE-MOI.md
```
