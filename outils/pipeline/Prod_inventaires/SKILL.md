---
name: inventaire-samdem
description: Transforme la liste d'inventaire d'un client (texte collé, mail, notes) en PDF « Inventaire de déménagement » Sam'Déménage, à l'identique du modèle maison (logo, tampon, charte, champs modifiables). Déclencher sur : inventaire client, mettre au propre un inventaire, PDF d'inventaire, générer l'inventaire, annexe inventaire du devis.
---

# Inventaire client → PDF Sam'Déménage

## 0. Principe

Le rendu est **figé dans le code** : `template_inventaire.html` (charte, mise en page) +
`generer_inventaire.py` (calculs, PDF, champs modifiables). Référence visuelle :
`exemples/modele_BODARD_Maylis.pdf` (modèle d'origine) et `exemples/reproduction_BODARD_Maylis.pdf`
(sa reproduction par l'outil, avec les deux changements demandés par Samuel le 18/09/2026 :
logo plus grand, tampon sous « L'entreprise »).

**Le modèle ne raisonne pas la mise en page.** Son seul travail : lire la liste de Samuel et
écrire le dossier JSON (section 3). Tout le reste est exécuté par le script, identique à
chaque fois. Ne jamais retoucher le gabarit pour un dossier particulier ; une évolution de la
charte se fait dans `template_inventaire.html`, sur demande de Samuel, et vaut pour tous.

## 1. Déroulé

1. **Lire la liste en entier** (pièces, meubles, quantités, dimensions, remarques).
2. **Réunir les infos du dossier** (Karim, 18/09/2026) : dès qu'elles sont connues, l'adresse de
   départ, l'adresse d'arrivée et la date / le créneau de déménagement **doivent** être
   renseignées dans le JSON — jamais laissées vides si l'information existe. Sources, dans
   l'ordre : le message de Samuel et la conversation ; puis, si le client est nommé, sa fiche
   Notion (le **corps du texte** fait foi, pas les propriétés). Rien de trouvé → champ vide,
   Samuel le remplit dans le PDF.
3. **Écrire le dossier** `donnees/Inventaires\<NOM Prénom>.json` selon la section 3.
4. **Générer** :
   ```
   python "outils/pipeline/Prod_inventaires/generer_inventaire.py" "donnees/Inventaires\<NOM Prénom>.json" --ouvrir
   ```
   Sortie : `donnees/Inventaires\` sous le nom fixé ci-dessous. Un PDF existant
   n'est jamais écrasé (suffixe « (2) ») sauf avec `--remplacer` — à utiliser pendant les
   allers-retours de corrections sur un même dossier.
5. **Relire avant de présenter** : nombre d'articles par pièce = nombre de lignes de la liste,
   aucun meuble oublié ou inventé, volumes cohérents, pas de page quasi vide.
6. **Rendre compte à Samuel** en quelques lignes : chemin du PDF, nombre de pages, volume
   total, et la liste de ce qui reste « à préciser » (n° d'inventaire, adresses, quantités).

Corrections demandées par Samuel → modifier le JSON, relancer avec `--remplacer`.

**Nom du fichier PDF** (Karim, 18/09/2026) — produit par le script, ne pas renommer à la main :
- avec n° d'inventaire : `inventaire <n°> NOM Prénom` — ex. `inventaire 072615092026 BODARD Maylis.pdf` ;
- sans n° : `inventaire NOM Prénom` — ex. `inventaire MASTON Magali.pdf`.

« inventaire » en minuscules, nom de famille en CAPITALES, prénom avec seule l'initiale en
majuscule. Fournir `nom` et `prenom` dans le JSON garantit ce format (le script normalise la
casse). Client inconnu : `inventaire client du JJ-MM-AAAA`, à régénérer dès que le nom est donné.

## 2. Ce que produit le script (ne rien refaire à la main)

- En-tête : logo en haut à gauche (`assets/logo.png`), bloc société à droite.
- Bandeau « INVENTAIRE DE DÉMÉNAGEMENT » + n° d'inventaire/devis + date d'établissement.
- Quatre cartes : dossier client, date de déménagement, adresse de départ, adresse d'arrivée.
- Tableau **Matériel entreprise** : couvertures (barème selon le volume total), penderies
  0 à 10, sangles 10 à 30, film 0 à 5 ; volumes fixes 0,200 / 0,300 / 0,005 / 0,050 m³
  (validés par Samuel le 18/09/2026).
- **Mobilier client par pièce** : encarts sur deux colonnes, compteur « N ARTICLES »,
  pastille rouge FRAGILE, dimensions en gris sous le nom, quantité en gras à droite.
- Récapitulatif des volumes : matériel · mobilier (= total − matériel, préfixé « ≈ ») · total.
- Note légale (annexe au devis, CGV) ; signatures « LE CLIENT » / « L'ENTREPRISE » ;
  **tampon** sous « L'entreprise » (`assets/tampon.png`). Le bloc de fin (récap + note +
  signatures) ne se coupe jamais : il passe entier à la page suivante si besoin.
- Pagination « Page X / Y ».

**Champs modifiables** (par défaut) : n° d'inventaire/devis, date d'établissement, dossier
client, date de déménagement, adresse de départ, adresse d'arrivée — ouvrables et modifiables
dans Acrobat, Edge ou Chrome, police identique au reste (DejaVu Sans). Le n° et la date de la
note légale sont liés à ceux du bandeau : modifier l'un modifie l'autre. `--fige` produit un
PDF sans champs (texte fixe).

## 3. Format du dossier JSON

```json
{
  "numero": "",
  "etabli_le": "18/09/2026",
  "nom": "BODARD",
  "prenom": "Maylis",
  "date_demenagement": "20 octobre 2026 — départ 7h",
  "adresse_depart": "Paris (adresse précise à confirmer)",
  "adresse_arrivee": "Adresse à préciser, 33000 Bordeaux",
  "volume_total": 16,
  "note_maj": false,
  "pieces": [
    {"nom": "Cuisine", "articles": [
      {"nom": "Assiettes", "fragile": true},
      {"nom": "Desserte à roulettes", "dims": "H83 × P51 × L30"},
      {"nom": "Chaises (pliées)", "qte": 2, "dims": "40 × 85"},
      {"nom": "Plantes", "qte": "à préciser", "dims": "nombre non précisé"}
    ]}
  ]
}
```

| Clé | Règle |
|---|---|
| `numero` | **Vide** sauf si Samuel le donne — on ne le devine pas, il le saisit dans le PDF. Format maison : n° de devis (4 chiffres) + date d'établissement JJMMAAAA. |
| `etabli_le` | Omis = date du jour. |
| `nom`, `prenom` | Nom de famille et prénom du client, séparés : le script en tire « NOM Prénom » (carte « Dossier client » et nom du fichier). `client` (chaîne « NOM Prénom » déjà formée) reste accepté. |
| `date_demenagement` | **À renseigner dès que connue**, avec l'heure ou le créneau : `20 octobre 2026 — départ 7h`, `20 octobre 2026 — créneau 8h-11h` (tiret cadratin). Inconnue : vide. |
| `adresse_depart`, `adresse_arrivee` | **À renseigner dès que connues** (voir §1, étape 2), telles que données : n°, rue, CP, ville. Partielle : `Adresse à préciser, 33000 Bordeaux` / `Paris (adresse précise à confirmer)`. Inconnue : vide. |
| `volume_total` | Volume total estimé en m³ (celui du devis). Absent de la liste : le demander à Samuel ou l'estimer avec `/estimer-volume-samdem` (volume **conservateur**). |
| `note_maj` | `true` si l'inventaire remplace une version précédente du même dossier (ajoute la phrase « Cette version met à jour et remplace… »). |
| `note_precisions` | Automatique : la phrase « Les adresses précises… à préciser… » apparaît dès qu'une adresse ou une quantité contient « préciser » / « confirmer ». Forçable à `true`/`false`. |
| `materiel` | Omis = tableau standard ci-dessus. Ne le fournir que sur instruction de Samuel : `[{"nature", "quantite", "volume"}]`. |

**Pièces** : dans l'ordre de la liste de Samuel, nom tel quel (mis en capitales par le gabarit).
Ne créer que les pièces présentes.

**Articles** — une ligne de la liste = un article :
- `nom` : majuscule initiale, formulation du client nettoyée ; état entre parenthèses
  (`Étendoir à linge (plié)`, `Litière (chat)`) ; deux meubles de même nom et de dimensions
  différentes sont numérotés `Table basse (1)`, `Table basse (2)`.
- `qte` : entier, 1 par défaut. Nombre inconnu → `"à préciser"` et, sans dimensions,
  `"dims": "nombre non précisé"`.
- `dims` : celles du client, séparateurs normalisés en ` × ` (signe multiplié), lettres
  L / P / H / Ø conservées quand le client les donne, aucune unité ajoutée.
- `fragile: true` : verres, vaisselle (assiettes, bols, saladiers…), bouteilles, miroirs,
  lampes, vases, cadres et tableaux, écrans — et tout ce que le client signale fragile.
  Pas pour les meubles, lampadaires, plantes.
- Ne rien ajouter qui n'est pas dans la liste ; ne pas regrouper deux lignes en une.

## 3 bis. Mode automatique (chaîne devis)

Depuis le 18/09/2026, la chaîne devis appelle ce skill toute seule : après le message WhatsApp
« Devis prêt à vérifier », `outils/pipeline/inventaire_auto.py` cherche l'inventaire (fiche
Notion puis noCRM), construit le dossier JSON, appelle `generer_inventaire.generer()` et envoie
le PDF sur la conversation « Devis/inventaire ». Les règles de rédaction des articles
ci-dessus (section 3, de « **Pièces** » à la fin) sont **lues telles quelles** par ce script et
transmises au modèle : les modifier ici les modifie aussi là-bas — garder ces titres.
Détail : `outils/pipeline/README.md`, section « Inventaire automatique ».

## 4. Fichiers

```
outils/pipeline/Prod_inventaires/
  SKILL.md                  ce fichier (source de vérité du skill)
  generer_inventaire.py     dossier JSON → PDF (Chrome sans fenêtre + PyMuPDF)
  template_inventaire.html  gabarit Jinja2 : charte, couleurs, mise en page
  assets/fonts/             DejaVu Sans (regular, bold) — police du modèle
  assets/logo.png           logo Sam'Déménage
  assets/tampon.png         tampon, redressé et détouré depuis assets/tampon_source.pdf ;
                            SIRET corrigé en 00049 (le scan portait l'ancien 00015,
                            gardé dans tampon_original_siret00015.png)
  exemples/                 modèle d'origine, sa reproduction, bodard.json
```

Charte (relevée sur le modèle) : bleu marine `#1c3f66`, texte `#1f2d3d`, gris `#46586e`,
libellés `#6f8199`, dimensions `#8797ab`, bordures `#dbe3ec`, fonds d'en-tête `#eef3f9`,
FRAGILE `#c0392b` ; police DejaVu Sans, base 10 pt ; A4, marges 18 / 18 / 20 mm.

Prérequis : Python avec `jinja2`, `pymupdf` (et `fontTools`, facultatif), Chrome ou Edge.

Le skill est déclaré à Claude Code par `.claude/skills/inventaire-samdem/SKILL.md`, qui
renvoie ici.
