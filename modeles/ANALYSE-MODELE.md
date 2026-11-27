# Analyse du modèle de devis reçu — « DEVIS A LA RECHERCHE DE LA BOUM 22_10_26.xlsx »

Fichier original conservé tel quel à côté (`DEVIS A LA RECHERCHE DE LA BOUM 22_10_26.xlsx`, lecture seule).
Analyse faite par lecture directe du XLSX (onglets, cellules, formules) — aucune modification de l'original.

## Onglets (11)
| Onglet | Rôle |
|---|---|
| `Devis` | **Général / récapitulatif** : 9 postes, totaux, frais généraux, imprévus, scénario de réduction |
| `1.Droits artistiques` | détail poste 1 (lignes 11.–19., sous-détails 1411., 1412.) |
| `2.Personnel` | détail poste 2 (21.–29., rubriques 231.–239., fonctions 2311.…, 231Y/231Z = renfort / heures sup) |
| `3.Interpretation` | détail poste 3 « Equipe artistique » (31.–39.) |
| `5.Décors et costumes` | détail poste 5 (51.–59., sous-codes 512.–516., 521.–523., 531.–533.) |
| `6.Transports, défrai., régie` | détail poste 6 (61.–69.) |
| `7. Moyens techniques` | détail poste 7 (71.–76.) |
| `8. Postproduction image et son` | détail poste 8 (81.–89. : 811.–817., 831.–834.) |
| `9. Assurances et divers` | détail poste 9 (91.–94.) |
| `Formulaire Dérogation` | annexe 3, titre II, CCNPC (IDCC 3097) : critères n°1 à 5, ratios 18 % / 80 % |
| `Scénario Live` | copie du général pour tester une hypothèse alternative |

**Remarque :** il n'existe pas d'onglet « 4. » — le poste 4 « Charges sociales » (lignes 41.–47.) est calculé
**directement sur l'onglet général** en % des lignes de personnel (auteurs 20 %, producteurs 64 %,
réalisateur technicien 57 %, équipe technique 57 %, artistes 52 % + BNC 10 %).

## Onglet général (`Devis`) — 3 colonnes monétaires
- **D = « Total dépenses en région »**, **E = « Total dépenses en France (€) »** (hors région),
  **F = « Coût définitif total » = D + E**. Des totaux « à l'étranger » apparaissent aussi (lignes 67 et 115).
- 9 grands postes, puis : **Total partiel → Frais généraux 7 % → Imprévus 3 % → Total hors TVA**.
- Bloc « SCÉNARIO – MARGE DE RÉDUCTION DE LA MASSE SALARIALE » (critère n°2, seuil 18 %, ratio actuel,
  économies CNC 0,58 % + 2 %, etc.).

## Onglet Personnel (`2.Personnel`) — le cœur du modèle
Par fonction (ex. 2336 Scripte) : **3 phases — Préparation / Tournage / Finition**,
chacune avec **Salaire × Jours (ou Semaines) = Total**, et ce **deux fois** : une fois en colonne
« Région » (G–P) et une fois « France » (R–AA). Totaux : P = brut région, AA = brut total, AB = P + AA,
Q/AC = nombre de jours/semaines. Formules du type `=SUM(G7*H7)`, `=SUM(I7+L7+O7)`.

## Fragilités constatées (celles que le logiciel doit éliminer)
- Références inter-onglets en cellules absolues (`='2.Personnel'!P88`) : insérer une ligne casse le récap.
- Soustractions manuelles (`P87-P86`, `P118-P120-P121`) : décaler une colonne rend le récap incohérent.
- Charges sociales en formules « en dur » (`*57%`) sur l'onglet général, non reliées ligne par ligne.
- L'onglet « Scénario Live » duplique tout le général à la main.

## Correspondance proposée avec l'application
- Chaque **onglet de détail = un grand poste** de l'arbre (vue « poste » filtrable dans l'onglet Devis).
- Numérotation et intitulés repris tels quels (11., 21., 231., 2311., 51., 61., 71., 81., 91. …).
- Ventilation à **3 cases** : en région / en France hors région / à l'étranger (le modèle a région + France + étranger).
- « Ajouter un technicien » = ligne fonction avec **3 phases × (salaire, jours/semaine)**,
  exactement comme les colonnes G–P / R–AA du modèle.
- Poste 4 « Charges sociales » : lignes 41.–47. alimentées automatiquement (taux paramétrables par catégorie),
  chaque euro compté une seule fois.
- Lignes « Frais généraux 7 % » et « Imprévus 3 % » calculées sur le total partiel, comme le modèle.
- Le « Scénario Live » = la duplication de projet déjà prévue (dupliquer le film pour une hypothèse).
