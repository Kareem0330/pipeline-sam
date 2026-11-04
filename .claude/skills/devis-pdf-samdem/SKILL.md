---
name: devis-pdf-samdem
description: Produit le PDF du devis Sam'Déménage à envoyer au client (en-tête société, forfaits transport et manutention, formule, frais, totaux, acompte, engagements, signature), à la mise en page des devis envoyés. Choisit seul entre la version « inventaire court » (inventaire listé dans le devis) et la version normale (« Voir inventaire » + inventaire séparé). Déclencher sur : produire le devis PDF, faire le devis de X, devis à envoyer, sortir le PDF du devis, production du devis.
---

# Devis PDF Sam'Déménage

Le chiffrage est fait en amont (skill `calcul-devis-samdem`, export du calculateur). Ce skill
ne recalcule rien : il met en page un devis déjà chiffré. Le PDF est produit par
`outils/pipeline/devis-pdf/generer_devis_pdf.py` ; ne jamais refaire la mise en page à la main.
Référence visuelle : devis MARSALLON 080726102026 du 26/10/2026.

**Depuis le 02/11/2026, chaque export produit le PDF seul** (`outils/pipeline/devis_auto.py`) et,
depuis le 03/11/2026, le garde en local : Samuel le relit et le valide (`calcul-devis-samdem`, § 13 bis), il
rejoint alors HubSpot, puis Sandrine l'envoie depuis son adresse (§ 7 sur demande seulement). Ce skill sert aux cas que la chaîne laisse à la main (motif
dans le message : relivraison, étape, chargement seul, accès à confirmer…). Les notes de la fiche
sont internes et ne vont jamais sur le devis (Karim, 02/11/2026). Voir `outils/pipeline/README.md`.

**Références (Karim, 04/11/2026)** : avant d'écrire la spec d'un cas particulier, lire `outils/pipeline/références/README.md`
et reprendre le format du cas le plus proche : sa présentation, jamais ses montants. Une fois un devis particulier validé,
sans attendre qu'on le demande, le ranger **anonymisé** par `python "outils/pipeline/reference_devis.py" "<spec>" "<Formule + particularité>"`
(jamais par une copie), ajouter sa ligne au README, puis le dire à Samuel. Un cas déjà couvert n'en crée pas de nouveau.

## 1. Réunir les données

- **Montants** : le dernier export du client dans `donnees/Devis générés/exports/` (`AAAAMMJJ-HHMMSS NOM Prénom.json`,
  le plus récent). Prendre `champs_fiche` : `manut_ht`, `deplacement_ht`, `dossier_ht`,
  `materiel_ht`, `formule_ht`, et `total_ttc`. Le transport est recalculé par le script.
- **Client et accès** : fiche client, note « Fiche client » de la transaction HubSpot (`fiche.page_id` de
  l'export est l'identifiant de transaction ; `python "outils/pipeline/fiche_hubspot.py" --lire <id>`). La vérité
  est dans le **corps de la fiche**, pas dans les propriétés : adresses, téléphone, e-mail, dates (tous les
  créneaux), type de logement, étages, ascenseur, portage entrée et intérieur, intervenants,
  section Inventaire, Notes.
- **Écart fiche / export** (ex. frais de dossier) : l'export fait foi s'il retombe sur le total ;
  le signaler à Samuel pour corriger la fiche (note modifiée, `calcul-devis-samdem` § 1).
- **Fiche marquée « indicatif »** : le dire à Samuel avant de produire ; un indicatif n'a ni
  acompte ni RIB.

## 2. Numéro et date

Format `NNNN` + `JJMMAAAA` (ex. `080828102026` = n° 0808 du 28/10/2026). Partir du dernier
numéro connu (devis fourni par Samuel, `donnees/Devis SamDem\`, Téléchargements) + 1.
Si le dernier numéro n'est pas certain, le dire à Samuel : c'est une supposition.

## 3. Écrire la spec

`donnees/Devis SamDem\specs\<numéro> NOM Prénom.json` (exemple complet :
`080828102026 SUNGU Gracia.json`) :

```json
{
  "numero": "080828102026", "date": "28/10/2026", "volume": 6, "formule": "Standard",
  "total_ttc": 400,
  "client": {"nom": "NOM Prénom", "adresse_depart": "...", "adresse_arrivee": "...",
             "date_demenagement": "entre le 03/11/2026 et le 11/11/2026",
             "telephone": "06.78.10.89.23", "email": "..."},
  "depart":  {"logement": "Maison", "etage_sans_ascenseur": "RDC",
              "portage_entree": "< 10 mètres", "portage_interieur": "< 10 mètres", "intervenants": 1},
  "arrivee": {"logement": "Appartement", "etage_ascenseur": 4, ...},
  "notes_manutention": ["Une personne au minimum doit être présente sur place ..."],
  "inventaire": ["Cartons standards : 25", "Matelas 140 cm : 1"],
  "lignes": [
    {"type": "transport", "montant": 0, "ajuste": true},
    {"type": "manutention", "montant": 128.80},
    {"type": "formule", "montant": 0},
    {"type": "autre", "libelle": "Frais de déplacement", "montant": 43.00},
    {"type": "autre", "libelle": "Frais de dossier", "montant": 34.00}
  ],
  "annulation": "J-14 avant la date du déménagement.",
  "conditions": []
}
```

- Étage : `etage_ascenseur` **ou** `etage_sans_ascenseur` selon la fiche.
- Téléphone au format `06.xx.xx.xx.xx`.
- Matériel facturé : une ligne `{"type": "autre", "libelle": "Matériel", "detail": [...], "montant": x}`.
- `conditions` : phrases propres au dossier, placées avant « Règlement par virement »
  (ex. « Réservation des places de stationnement effectuée par la cliente auprès de la mairie. »).
- `notes_manutention` : consignes dites par Samuel ou notées dans la fiche (aide du client, etc.), seulement si elles
  s'adressent au client. **Aucun détail logistique ni mention interne sur un document client** (Karim, 04/11/2026) :
  ni valeur d'un objet, ni kraft ou couverture, ni « à protéger », ni ordre de tournée, ni consigne d'équipe.
- **Stockage dans notre local** (Karim, 04/11/2026, 1er cas LE TRIVIDIC) : le calculateur ne le chiffre pas. Écrire
  `client.adresse_stockage` (147 route des Valentons, 33450 Saint-Loubès, affichée entre départ et arrivée) et une ligne
  `{"type": "autre", "libelle": "Stockage en garde-meuble du JJ/MM/AAAA au JJ/MM/AAAA", "montant": x}`. Le prix dépend du
  dossier : le demander à Samuel, sans le déduire de la grille. **Offert** : `"detail": ["Offert"]`, `montant` 0, le TTC
  de l'export ne bouge pas. **Facturé** : monter `total_ttc` de x × 1,2, `--ajouter-pdf` avec ce TTC, puis, après
  validation, le reporter sur la transaction et la fiche, qui gardent celui de l'export. Un nouvel export repart sans ce supplément.
- **Fourchette** (Karim, 28/10/2026, 1er cas RIBEZZI) : un seul devis, `volume` + `volume_max`,
  `total_ttc` + `total_ttc_max` (les TTC des deux exports), `montant_max` sur chaque ligne qui
  varie ; le PDF affiche « x à y ». Le transport reste la ligne `ajuste` aux deux bornes.
- **Indicatif** : `"indicatif": true` retire acompte et solde et ajoute la mention « devis
  indicatif » ; mail d'envoi = modèle Gmail « Modèle devis indicatif », sans RIB.
- **Chargement seul** : `"arrivee": null`. `note_transport` (liste de phrases) remplace
  « Voir inventaire » quand il n'y a pas d'inventaire.
- **Sections par trajet** (Karim, 28/10/2026, 1er cas SAINT-MLEUX, format validé) : `"sections": [{"titre",
  "detail", "lignes"}]` à la place de `lignes`, un sous-total HT par section, un seul total.
  Titres au format `Trajet 1 : Cogolin - Saint-Loubès`, `Trajet 2 : Saint-Loubès - Paris, en
  groupage` : villes séparées par un **tiret simple « - », jamais de flèche « → »** (Samuel : ça fait
  trop IA ; le script refuse une spec qui en contient). Avec
  une relivraison, la section 2 reprend les postes « Relivraison · » de l'export plus sa part de
  transport (`relivraison.montant_ht` − ses postes) ; la section 1 garde le reste, transport `ajuste`.
  Le calculateur ne chiffre pas de relivraison en groupage : en parler à Samuel avant de produire.
- **Formule Confort / Premium** : options choisies dans `formule_incluses_plus`, et ce qu'elles
  couvrent dans `formule_non_incluses_retirer` (ex. « Tarif préférentiel (groupage). » si un trajet
  part en groupage). Repère : devis CHAUVEAU 067024082026. **Jamais de durée** dans le libellé
  d'une option (« Mise en carton de la vaisselle. », pas « … (2h00). ») : le temps d'options est
  interne, il ne s'écrit nulle part dans le devis (Karim, 28/10/2026 ; le script refuse une option
  qui porte une durée).
- **Aucune trace de préparation sur un document client** (Karim, 03/11/2026) : ni pastille 🟡 ni
  autre émoji, ni « temps à chiffrer », ni nom de variante, ni temps d'options, sous aucune forme. Une
  option s'écrit comme un client la lirait (« Mise en carton de la vaisselle. »). Le client ne doit
  jamais pouvoir deviner qu'une IA a préparé le devis. Le script refuse une spec qui en contient.
- `inventaire` : une ligne par article, `Article, précision utile : quantité`, rédigée pour le
  client (pas de note interne du type « Samuel n'en note qu'un »). Quantité ambiguë dans la
  fiche : poser la question à Samuel.

## 4. Version inventaire court ou normale (codé dans le script)

| Inventaire | Résultat |
|---|---|
| 10 lignes ou moins, devis de 3 pages ou moins | **Inventaire court** : liste sous « Forfait transport » |
| Plus de 10 lignes, ou devis qui dépasserait 3 pages | **Normale** : « Voir inventaire <n°> » |

Mettre toujours l'inventaire dans la spec : le script tranche et affiche la version retenue.
S'il affiche `INVENTAIRE SÉPARÉ À PRODUIRE`, enchaîner avec le skill `inventaire-samdem`,
**même numéro** que le devis.

## 5. Produire

```bash
python -I outils/pipeline/devis-pdf/generer_devis_pdf.py "donnees/Devis SamDem/specs/<numéro> NOM Prénom.json"
```

Sortie : `donnees/Devis SamDem\Devis <numéro> NOM.pdf` (remplace la version précédente).

## 6. Relire avant de livrer (obligatoire)

Jamais le premier jet. Rendre chaque page en image (pymupdf, 110 dpi), la regarder, et
contrôler point par point :
- chaque valeur du PDF contre la fiche et l'export : nom, adresses, dates, téléphone, e-mail,
  volume, logements, étages, portage, intervenants, montants ;
- HT + TVA = TTC au centime, acompte = 30 % du TTC, solde = TTC − acompte ;
- texte fixe identique à la référence (formule, engagements, renvois ¹ ² *) ;
- mise en page : police Inter, logo, aucune ligne coupée entre deux pages, en-têtes de
  colonnes seulement en page 1.

Une fois relu, le remettre dans la relecture de Samuel, qui reste la même que pour un PDF automatique
(`calcul-devis-samdem`, § 13 bis, étapes 3 à 7) : sélection, puis import sur HubSpot.

```bash
python outils/pipeline/validation_devis.py --ajouter-pdf "<pdf>" --page-id <fiche.page_id> --ttc <TTC> [--variante "X"]
```

## 7. Brouillon d'envoi (codé dans le script), sur demande seulement

**Optionnel (Karim, 03/11/2026)** : le plus souvent, Sandrine envoie le devis depuis son adresse. Ne préparer
ce brouillon que si Samuel le demande explicitement, et ne pas le proposer de soi-même.

Les modèles de mail sont dans le Vault : `outils/pipeline/devis-pdf/modeles-mail/` (`devis-ferme.html`,
`devis-indicatif.html`, `signataires.json`). Ne plus aller les chercher dans Gmail.

```bash
python outils/pipeline/devis-pdf/brouillon_envoi.py "donnees/Devis SamDem/specs/<numéro> NOM Prénom.json" --signataire samuel
```

Le modèle suit `indicatif` dans la spec ; les balises (prénom, montant ou fourchette, acompte,
solde, signature) sont remplies depuis la spec. Le script écrit
`outils/pipeline/livrables/pj-envoi/<numéro>/brouillon.json` (à, objet, html, texte) et y copie le PDF et les
documents de `donnees/Docs Devis SamDem` (RIB seulement pour un ferme). `--prenom` corrige un
prénom mal déduit.

**Pas de CLI Google** (Karim, 28/10/2026 : il ne veut pas connecter gws au compte Sam'Déménage).
Le brouillon se fait en deux temps, jamais d'envoi :
1. Connecteur Gmail `create_draft` avec `to`, **`cc`**, `subject`, `htmlBody` et `body` de `brouillon.json`.
   **Copie systématique** (Karim, 28/10/2026) : Sandrine `secretariat@samdemenage.fr` et l'e-mail
   contact `contact@samdemenage.fr` en Cc de chaque mail d'envoi de devis, ferme ou indicatif
   (constante `COPIE` du script)
   (sans pièces jointes : le connecteur les veut en base64, trop lourd pour ~1,5 Mo).
2. Chrome : ouvrir le brouillon (`viewUrl`), `find` le champ « Joindre des fichiers »,
   `file_upload` avec les chemins de `pieces_jointes` (seuls les fichiers du Vault sont acceptés,
   d'où la copie dans `pj-envoi/`), vérifier les quatre ou cinq pastilles de pièces jointes.
   Fermer ensuite par le bouton « Enregistrer et fermer » trouvé avec `find`, jamais par un clic à
   coordonnées fixes (il a réduit la fenêtre au lieu de la fermer, PJ non enregistrées). Contrôle :
   `list_drafts` doit montrer un nouveau `messageId` pour ce brouillon.
3. `python outils/pipeline/devis-pdf/brouillon_envoi.py --nettoyer <numéro>` une fois le brouillon enregistré.

**Documents d'envoi en deux exemplaires** : `donnees/Docs Devis SamDem` (lu par le script) et
le dossier Drive « Docs Devis SamDem », synchronisé sur `G:\Mon Drive\Infos Partagés Sam'Déménage\Docs Devis SamDem`.
Un document qui change (ex. nouveau RIB Themis Banque, 29/10/2026) se remplace **aux deux endroits**,
sous le même nom de fichier.

**Toujours envoyer le PDF à Samuel** (Karim, 28/10/2026) : dès le brouillon prêt, `SendUserFile`
avec le PDF du devis (et l'inventaire séparé s'il y en a un), `display: "render"`, pour qu'il le
vérifie avant de valider le brouillon. Ne pas se contenter du chemin dans le texte.

Livrer le PDF à Samuel avec la liste de ce qui reste à confirmer (numéro supposé, écarts
fiche/export, quantités ambiguës, indicatif ou non). Les pièces jointes d'envoi (CGV,
déclaration de valeur, grille de vétusté, RIB) sont dans `donnees/Docs Devis SamDem`.
