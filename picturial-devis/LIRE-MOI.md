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

### Méthode 1 — la plus fiable : lancer via le Terminal (aucun déblocage requis)
1. Ouvrez **Terminal** (Cmd + Espace, tapez « terminal », Entrée).
2. Tapez `bash ` (avec un espace à la fin), puis **faites glisser le fichier
   `Ouvrir le devis.command`** dans la fenêtre du Terminal : son chemin se remplit tout seul.
3. Appuyez sur **Entrée**. Le serveur démarre et le navigateur s'ouvre tout seul.
   (Astuce : vous pouvez faire la même chose en glissant le dossier entier et en tapant
   `bash "picturial-devis/Ouvrir le devis.command"`.)

### Méthode 2 — débloquer le fichier pour le double-clic
1. **Clic droit (ou Ctrl+clic)** sur `Ouvrir le devis.command` → **« Ouvrir »** → cliquez
   « Ouvrir » dans la boîte de dialogue. macOS mémorisera ensuite le déblocage.
   (Sur macOS récent, l'option peut aussi apparaître en bas de
   **Réglages Système → Confidentialité et sécurité → « Ouvrir quand même »**.)
2. **Ou en une commande dans le Terminal** (une seule fois, après décompression) :
   ```
   xattr -dr com.apple.quarantine "/chemin/vers/le/dossier/picturial-devis"
   ```
   (adaptez le chemin — par ex. `~/Téléchargements/picturial-devis` ; gardez les guillemets
   s'il contient des espaces ou des accents).

Sans cette étape, le double-clic affiche uniquement « Placer dans la corbeille » / « Terminé ».

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

## v2 — calquée sur vos documents

- **Nomenclature CNC** reprise de votre modèle « DEVIS A LA RECHERCHE DE LA BOUM 22_10_26.xlsx » :
  9 postes (1. Droits artistiques … 9. Assurances et divers), codes et intitulés du modèle
  (11.–19., 21.–29., 231.–239., 31.–39., 41.–47., 51.–59., 61.–69., 71.–76., 81.–89., 91.–94.),
  **charges sociales en poste 4** (lignes 41.–45. calculées en % : auteurs 20 %, producteurs 64 %,
  réal. technicien 57 %, équipe technique 57 %, artistes 52 % + 10 % BNC), **frais généraux 7 %**
  et **imprévus 3 %** calculés sur le total des postes 1–9 (lignes FG / IMP), total = « Total hors TVA ».
- **Ventilation à 3 cases** comme votre modèle : en région / France (hors région) / à l'étranger,
  avec reliquat « à ventiler » et contrôle d'égalité permanent.
- **Barèmes CCNPC importés du document officiel** « Salaires minimas conventionnels applicables au
  1er juin 2026 » (429 fonctions, statut « VÉRIFIÉ », source = onglet du document) : Annexe 1 (base 39h,
  hebdo), Annexe 2 (équivalence tournage), Annexes 3/3 bis (dérogation, accords 2019/2025), Annexe 4
  (permanents, mensuel), artistes-interprètes (jour/semaine), artistes de complément, réalisateurs.
  Les nouveaux films partent sur la convention **CCNPC (IDCC 3097)**, grille **Annexe 1**, date de
  référence 2026-06-01. Le barème hebdo n'est jamais divisé en jours : unité « semaine » exigée, ou
  « hypothèse manuelle » cochée et signalée.
- **Export Excel fidèle au modèle** : onglet « Devis (général) » (postes + FG + IMP + total hors TVA,
  colonnes région / France / étranger / à ventiler), **un onglet par poste** (1. … 9.), onglet
  « Ventilation territoriale ». Montants en cellules numériques.
- Onglet Devis : **filtre par poste** (sélecteur « Poste : ») pour lire un poste comme un onglet du modèle.
- Les originaux de vos documents sont conservés en lecture seule dans `picturial-devis/modeles/`.
- « Scénario Live » et « Formulaire Dérogation » : non repris en v2 (hors périmètre demandé) ;
  la duplication de projet joue le rôle de « scénario alternatif ».

## Guide rapide — rentrer une ligne de budget

1. Onglet **Devis** → cliquez le bouton jaune **« ＋ Ajouter une ligne »** en haut à droite.
2. Choisissez **où** elle va (poste / rubrique / ligne, ex. `7. Moyens techniques > 71. Matériels prises de vues « cinéma »`).
3. Donnez un **intitulé** (ex. « Location caméra »), puis **quantité × coût unitaire** (ex. 5 jours × 120 €)
   **ou** un **forfait** (ex. 1 000 €). Laissez vide ce qui ne sert pas.
4. Cliquez **« Ajouter la ligne »** : le montant se calcule seul et remonte dans le total général.

Variantes depuis une ligne existante (bouton « ⋯ » à droite de la ligne) :
- **« Ajouter un sous-détail »** : décompose une ligne (ex. Location caméra → Corps caméra 600 € + Optiques 400 €) ;
  si la ligne avait un forfait, on vous demande de le reprendre comme premier sous-détail ou de le remplacer (jamais de double comptage) ;
- **« Ajouter un technicien »** (sur une rubrique, ex. 237. Son) : fonction + salaire (prérempli au minimum CCNPC) + phases prépa/tournage/finissions ;
- « Déplacer vers… », « Dupliquer », « Tout affecter en région / France / étranger », « Supprimer ».

L'arbre est **replié par défaut** : cliquez les ▸/▾ pour déplier/replier, ou « Tout déplier » / « Mode Récapitulatif » en haut.

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

- `python3 -m unittest discover -s tests` : **29 tests OK** (recette v1 + v2 : import des 429 minimas CCNPC vérifiés, nomenclature CNC, charges poste 4 à 57 %, FG 7 % / imprévus 3 %, ventilation étranger, recette complète 1750/700/2450 € → 3800 €), couvrant la recette complète
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
