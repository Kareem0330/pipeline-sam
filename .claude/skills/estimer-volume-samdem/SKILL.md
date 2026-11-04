---
name: estimer-volume-samdem
description: Estime le volume en m³ d'un déménagement à partir d'un inventaire client (texte libre, mail, PDF, photos, manuscrit). Déclencher sur : estimer un volume, cubage, inventaire à chiffrer, fiche client sans volume mais avec inventaire.
---

# Estimation de volume — Sam'Déménage

**Journal (Karim, 04/11/2026)** : `../calcul-devis-samdem/JOURNAL.md`, à alimenter sans attendre qu'on le demande dès qu'une règle d'estimation change.

## 0. Principe

**Prompt de référence : `references/prompt-projet.md`** — les instructions du projet Claude de
Samuel, recopiées mot pour mot (16/09/2026). **Le lire avant chaque estimation.** Il prime sur
ce fichier et sur `volume.py` : ce skill n'en est que la mise en œuvre (JSON + script). Toute
règle ci-dessous qui s'en écarterait est une erreur à corriger ici, pas une variante.


Deux étapes séparées, et cette séparation n'est pas négociable :

1. **Toi** : identifier les objets dans l'inventaire et les décrire en JSON. C'est le travail
   qui demande du jugement — reconnaître un objet, deviner s'il est démonté, repérer une
   formulation conditionnelle.
2. **Le script `outils/pipeline/volume.py`** : appliquer les coefficients et faire les
   sommes. **Ne jamais calculer un volume à la main** : l'arithmétique est codée, elle est
   reproductible et vérifiable, et la refaire de tête introduit des erreurs invisibles.

**Le volume retenu pour le devis est le CONSERVATEUR** (décision Karim 08/09/2026). Le
standard et le longue distance sont calculés, mais ne servent que de comparaison — ne jamais
reporter le standard dans une fiche ou un devis.

## 1. Lecture de l'inventaire

- **Fichiers HEIC** : convertir en JPEG avant analyse (`pillow-heif`). Ne jamais analyser un
  HEIC brut.
- **Liste + photos fournies ensemble** : croiser systématiquement les deux — objets visibles
  sur photo mais absents de la liste, doublons probables (même objet sous plusieurs angles),
  types ou quantités incertains.
- **Manuscrit / PDF scanné** : ne retenir que les lignes manuscrites ou numérotées ; ignorer
  les lignes pré-imprimées du formulaire type, sauf demande explicite.
- **Inventaire finissant par « etc. », « et d'autres choses », « … »** : le traiter comme
  **structurellement incomplet**, le signaler dans la section incertitude quel que soit le
  détail du reste, et **ne jamais extrapoler** ce que masque le « etc. ».

## 2. Produire le JSON

Un objet par ligne d'inventaire. Écrire le fichier dans le scratchpad, pas dans le vault.

```json
{
  "client": "NOM Prénom",
  "objets": [
    {"nom": "Canapé 3 places", "qte": 1, "dims_cm": [200, 90, 80]},
    {"nom": "Armoire 3 portes", "qte": 1, "ref": "armoire_3p", "tags": ["demonte"]},
    {"nom": "Cartons standards", "qte": 25, "ref": "carton_standard"},
    {"nom": "Vélos", "qte": 2, "ref": "velo", "tags": ["irregulier"]},
    {"nom": "Olivier en pot", "qte": 1, "colonne_cm": [150, 150, 250]},
    {"nom": "Buffet ancien vitré", "qte": 1, "ref": "buffet", "tags": ["pro"], "incertain": true}
  ]
}
```

| Champ | Quand l'utiliser |
|---|---|
| `dims_cm: [L, l, h]` | Dimensions fournies par le client, ou mesurables de façon fiable sur photo |
| `ref: "<clé>"` | Aucune dimension → volume moyen de référence. Clés : `python outils/pipeline/volume.py --references` |
| `colonne_cm: [L, l, h]` | **Arbre, grand arbuste, pot ≥ 40 cm** — voir §3 |
| `tags` | `demonte`, `irregulier`, `pro` — cumulables |
| `incertain: true` | Formulation conditionnelle ou quantité imprécise — voir §4 |

Si un objet n'a ni dimensions ni référence connue, le script s'arrête avec une erreur claire
plutôt que d'inventer un volume. Dans ce cas : trouver la bonne `ref`, fournir des `dims_cm`
plausibles à la hausse, ou demander la dimension au client.

## 3. ⚠ Règle de la colonne neutralisée — non négociable

**S'applique aux arbres, grands arbustes en pot, et tout pot de diamètre ≥ 40 cm.**

Un coefficient d'irrégularité appliqué au volume du **pot** est massivement faux et ne doit
jamais être utilisé seul : dans un camion, rien ne s'empile autour d'un arbre. C'est
**l'emprise verticale totale de chargement** qui compte.

Renseigner `colonne_cm` avec :
1. l'emprise au sol du **branchage/feuillage** (largeur × profondeur de la couronne, pas
   celle du pot),
2. la **hauteur totale**, du sol du pot au sommet du feuillage.

Le script applique ensuite ×1,3 / ×1,5 sur ce volume de colonne. Ne pas ajouter le tag
`irregulier` : la colonne le porte déjà.

*Exemple validé : olivier, couronne 150 × 150 cm, hauteur 250 cm → 5,625 m³ bruts → 7,31 m³
standard / 8,44 m³ conservateur. L'ancienne méthode donnait ~0,4 m³.*

## 4. Classer les objets

**`demonte`** — un meuble démonté prend moins de volume théorique mais plus de place réelle
(panneaux à plat, emballage, quincaillerie).

**`irregulier`** — vélos, plantes en pot (< 40 cm), tapis roulés, lampadaires, chaises
empilables, barbecues, poussettes, matériel sur pied, enseignes, miroirs sur pied.

**`pro`** — matériel de métier (coiffure, médical, artistique, artisanal), objets hors
catalogue, et **pièces anciennes / fragiles / design** : miroirs dorés, bibliothèques vitrées,
meubles sculptés, secrétaires anciens, tapisseries encadrées grand format.
→ Pour ces pièces, évaluer si un **calage ou une caisse sur mesure** serait nécessaire. Si
oui, le signaler en fin de rapport comme point à confirmer : impact volume et coût non chiffré
dans l'estimation.

**`incertain: true`** — « peut-être », « je réfléchis », « à confirmer », ou quantité vague
(« plusieurs », « quelques »). L'objet est inclus dans les deux estimations ; le script ajoute
+20 % sur lui en conservateur uniquement.

⚠ **`incertain` n'est PAS une étiquette de prudence** (erreur BODARD, 15/09/2026). Il ne se
pose que sur les critères du prompt : formulation conditionnelle du **client** ou quantité
vague. Un libellé générique (« Meuble », « Table »), un qualificatif de taille (« petit »,
« medium ») ou un libellé mal saisi par l'outil d'inventaire ne sont **pas** incertains : ils se
traitent en choisissant la référence la plus plausible, à la hausse. Poser `incertain` sur la
moitié de l'inventaire gonfle le conservateur de plusieurs m³.

**Objet ambigu ou inhabituel** : toujours arrondir à la hausse. Ne jamais sous-estimer — c'est
le choix de la référence qui porte cette prudence, pas une surcote.

**Taille indiquée → référence de cette taille.** « Étagère petite », « Buffet petit »,
« Étagère grande » : utiliser `etagere_petite`, `buffet_petit`, `etagere_grande`… (voir
`--references`). Jamais la référence générique d'un meuble dont la taille est donnée : un
« buffet petit » compté comme un buffet ordinaire vaut +0,4 m³, répété sur tout l'inventaire.

## 5. Lancer le calcul

```bash
python "outils/pipeline/volume.py" <inventaire.json>
python "outils/pipeline/volume.py" <inventaire.json> --detail   # ligne par ligne
python "outils/pipeline/volume.py" <inventaire.json> --json     # pour chaîner
```

Le script rend le rapport au format attendu : volumes standard / conservateur / longue
distance, analyse de palier camion, écart, niveau d'incertitude, éléments à confirmer.
**Restituer ce rapport tel quel**, sans le recalculer ni le reformuler.

## 6. Saturation de palier

Le script gère seul deux situations, à ne pas passer sous silence dans ta réponse :

- **Changement de palier** : standard et conservateur de part et d'autre d'un seuil
  (15/20/30 m³). C'est un risque logistique, pas un détail numérique.
- **Saturation** : le conservateur atteint la capacité nominale du palier. Le remplissage
  réel n'égale jamais la capacité théorique (colis non cubiques, espaces perdus, arrimage) →
  le script recommande le palier supérieur.

## 7. Après l'estimation

- Reporter le **volume conservateur** sur la ligne `Volume de meuble : … m3 | source : …` de la fiche (note
  « Fiche client » de la transaction HubSpot), avec pour source « estimation Sam'Déménage sur inventaire client
  (conservateur) ». Une correction de fiche modifie la note : `fiche_hubspot.py --lire
  <transaction>`, corriger la ligne dans un fichier, puis `fiche_hubspot.py --creer <fichier>` avec les options
  de la création (`calcul-devis-samdem`, § 1).
- Cocher `- [x] Inventaire : Oui`.
- Enchaîner sur `/calcul-devis-samdem` si le reste de la fiche est complet.

## 8. Style de réponse

Concis et ciblé. Pas de cadrage méthodologique, pas de reformulation de la demande. Le détail
ligne par ligne seulement s'il est demandé (`--detail`). Si seule une liste d'éléments est
demandée sans chiffrage, rendre une liste numérotée propre, sans chiffres.

## ⚠ Table des volumes de référence — à valider

Les volumes moyens utilisés quand un objet n'a pas de dimensions sont dans `REFERENCES`
(`volume.py`). Seuls les trois cartons viennent du prompt de référence ; **le reste est une
proposition non validée par Samuel**. Ces valeurs pilotent le volume, donc le prix : le
signaler quand une estimation repose largement sur des objets sans dimensions.
