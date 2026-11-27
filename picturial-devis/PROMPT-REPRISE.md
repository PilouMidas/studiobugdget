# PROMPT DE REPRISE — Logiciel de devis Picturial (à copier dans Vibe Studio Code)

Tu es une nouvelle instance travaillant sur le logiciel de devis de production de **Picturial**.
L'utilisateur a une version locale ancienne : **ne travaille PAS depuis cette copie locale**. Récupère
toujours la version à jour d'abord :

```
git clone https://github.com/PilouMidas/studiobugdget.git
cd studiobugdget
git checkout vibe/devis-production-v1-eb55c7     # branche de travail, PR #1
```

Le ZIP livrable est `picturial-devis.zip` à la racine de la branche ; le code est dans `picturial-devis/`.
**Les données de l'utilisateur (films) sont dans sa base SQLite séparée** (`~/Library/Application Support/Picturial/devis.db`
sur Mac) : remplacer le dossier de l'application ne fait perdre aucun film. Ne jamais toucher à cette base autrement
que via l'application.

## Ce qui existe déjà (v2, testée, 29 tests OK)
- Application web **100 % Python 3 standard** (aucune dépendance) : `server.py` (API JSON + statique),
  `engine.py` (moteur de calcul unique : arbre hiérarchique, arrondi au centime, propagation immédiate),
  `db.py` (schéma SQLite + seeds), `static/` (UI vanilla JS), `xlsx_export.py`, `tests/` (29 tests).
- Lancement Mac : décompresser le ZIP, puis `Ouvrir le devis.command` (Gatekeeper : au premier lancement,
  soit clic droit → « Ouvrir », soit dans le Terminal `bash ` + glisser-déposer le fichier, soit
  `xattr -dr com.apple.quarantine "/chemin/picturial-devis"`). Le serveur écoute sur `127.0.0.1` (port libre auto),
  le navigateur s'ouvre tout seul.
- **Nomenclature CNC calquée sur le modèle Excel de l'utilisateur** (« DEVIS A LA RECHERCHE DE LA BOUM 22_10_26.xlsx",
  conservé en lecture seule dans `modeles/` et embarqué dans `picturial-devis/modeles/`) : 9 postes, codes 11.–94.,
  charges sociales en poste 4 (règles en % : 20/64/57/57/52+10), frais généraux 7 % et imprévus 3 % (lignes FG/IMP),
  total = « Total hors TVA ».
- **Minimas CCNPC importés du document officiel** (`modeles/PCINE-Salaires-minimas-...xlsx`) : 429 fonctions,
  statut « VÉRIFIÉ », grilles Annexe 1/2/3/3bis/4, artistes, réalisateurs, date réf. 2026-06-01.
- Ventilation **3 cases** : en région / France (hors région) / à l'étranger + à ventiler, éditable directement
  dans les lignes du tableau Devis, contrôle d'égalité permanent.
- « Ajouter un technicien » : fonction (minimum CCNPC prérempli, salaire négociable avec avertissement sous le minimum),
  3 phases (préparation/tournage/finissions) × salaire × jours/semaines ; barème hebdo jamais divisé (hypothèse manuelle signalée) ;
  poste 4 calcule les charges automatiquement (chaque euro une seule fois) ; actualisation volontaire des barèmes avec aperçu.
- Exports : Excel multi-onglets (général + un onglet par poste + ventilation), vue imprimable PDF, sauvegarde/restauration JSON.
- Projet de démonstration « À la recherche de la Boum — démonstration » pré-rempli.

## Méthode de travail demandée par l'utilisateur : PAGE PAR PAGE
On calque l'application sur le tableur Excel de l'utilisateur **onglet par onglet**, en commençant par le plus simple.
- ✅ Page 1 « 1. Droits artistiques » : faite (codes 11.–19. + 1411./1412., ventilation directe dans les colonnes).
- ⏭️ **Page 2 « 2. Personnel » : À FAIRE EN PRIORITÉ** — reproduire fidèlement l'onglet Excel `2.Personnel` :
  par fonction (2311., 2321., … sous les rubriques 231.–239.), 3 phases Préparation/Tournage/Finition,
  chacune avec Salaire × Jours (prépa/finition) ou Semaines (tournage), éclaté en deux blocs « Région » (colonnes G–P)
  et « France » (R–AA), totaux P (brut région), AA (brut total), AB (P+AA), Q/AC (nb jours/semaines).
  L'app a déjà le modèle « technicien = 3 phases » ; il faut vérifier que la vue poste 2 affiche ça de façon lisible
  (tableau phases × région/France) et que la saisie colle à l'Excel.
- Puis pages 3 (Interprétation), 5 (Décors et costumes), 6, 7, 8, 9.
- Hors périmètre v2 (à prévoir plus tard, l'utilisateur l'a dit) : onglets « Scénario Live » et « Formulaire Dérogation »
  (critères n°1–5, ratios 18 %/80 %) du modèle.

## Boucle de livraison (rapide, l'utilisateur veut des retours fréquents)
1. Modifier le code dans `picturial-devis/`.
2. Tester : `cd picturial-devis && python3 -m unittest discover -s tests` (doit rester OK) + test manuel via
   `python3 server.py --port 8765` puis navigateur sur `http://127.0.0.1:8765/`.
3. Régénérer le ZIP : `cd .. && rm -f picturial-devis.zip && zip -r picturial-devis.zip picturial-devis`.
4. Commit + push sur `vibe/devis-production-v1-eb55c7` et commenter la PR #1 avec ce qui a changé :
   `gh pr comment 1 --repo PilouMidas/studiobugdget --body-file /tmp/comment.md`.
5. L'utilisateur re-télécharge `picturial-devis.zip` sur la PR, teste sur son Mac, donne son retour ici ou sur la PR.

## Règles importantes
- Français partout (UI, messages, commits). Arrondi au centime, format français, un seul moteur de calcul (`engine.py`)
  pour écran Devis, vue Région, impression et exports — ne jamais dupliquer la logique de calcul.
- Jamais de double comptage (forfait → sous-détail avec choix explicite « reprendre/remplacer » ; charges comptées une fois).
- Ne jamais choisir silencieusement entre deux grilles compatibles ; barème hebdo non divisé automatiquement.
- Pas de dépendance externe, pas de service cloud, pas d'exposition réseau (serveur en loopback uniquement).
- Ne pas exposer de secrets ; ne pas modifier les fichiers originaux dans `modeles/` (lecture seule).
- Ne jamais pousser sur `main` directement : branche de travail + PR #1 uniquement.

## Points à vérifier sur le Mac de l'utilisateur (non testables ici, Linux)
- Ouverture auto du navigateur via `open` (le lanceur a un repli `xdg-open`/URL affichée).
- Comportement Gatekeeper au premier lancement (procédure documentée dans `LIRE-MOI.md`).

## Questions ouvertes pour l'utilisateur (à lui poser si bloquant)
- Page 2 Personnel : la vue par fonction avec phases × région/France suffit-elle, ou faut-il un tableau strictement
  identique aux colonnes G–P / R–AA ?
- Faut-il reprendre le bloc « scénario de réduction de la masse salariale » et le formulaire de dérogation dans une v3 ?
