---
name: creer-fiche-client-samdem
description: Crée la fiche d'un client déménagement sur HubSpot pour Sam'Déménage, dans une note « Fiche client » de sa transaction. Déclencher sur : créer une fiche, nouveau client, prise de contact, informations sur un client à déménager, ou fiche absente au moment d'un devis.
---

Ce skill pilote la création de la fiche client. **Depuis le 03/11/2026 (Samuel), elle vit sur la transaction
HubSpot** : une seule note « Fiche client », créée si elle manque, modifiée sinon (Karim, 04/11/2026). Plus aucune fiche créée dans Notion.

**Aucune question posée à Samuel sur les éléments manquants** : tout est signalé par 🟡 dans la
fiche, le workflow reste autonome de bout en bout.

---

## Références

- `references/modele-fiche.md` : la trame de la fiche, sections et cases à cocher, à reproduire telle quelle.
- `references/regles-remplissage.md` : les règles détaillées.

Format de la note, relu par `outils/pipeline/fiche_notion.py` : `### Titre` pour un titre, `- [x] Libellé` et
`- [ ] Libellé` pour une case, `- Libellé` pour une puce, le reste en lignes libres. Une valeur par ligne.

---

## ÉTAPE 0 — La source

- Informations collées par Samuel, transcript, formulaire : la source est la conversation.
- **Fiche absente au moment d'un devis** (`pipeline.py --fiche` rend `FICHE_A_CREER`) : la
  source est la transaction, lue par `python "outils/pipeline/hubspot_crm.py" --description "NOM Prénom"`. La fiche est
  créée avant tout chiffrage (décision Karim 11/09/2026).
- Inventaire sans volume : estimer avec `/estimer-volume-samdem` et reporter le volume
  **conservateur**, source « estimation Sam'Déménage sur inventaire client (conservateur) ».
- ⛔ **Visite de Christophe → aucun inventaire recopié du formulaire/CRM** (Karim, 13/10/2026).
  Christophe fait lui-même l'inventaire pendant la visite ; celui du client peut en différer.
  Ni section « Inventaire (repris du CRM) », ni débranchement ou autre ligne tirée de
  l'inventaire client. L'inventaire du client reste joint en PDF à la transaction : sans
  section Inventaire dans la fiche, `inventaire_auto.py` le prend dans la note formulaire
  HubSpot (conservée, jamais écrasée). La règle ci-dessous ne vaut que sans visite de Christophe.
- ⚠ **Inventaire présent sur la transaction → recopié en entier dans la fiche** (Karim, 16/09/2026). Section
  dédiée, placée juste **avant** `### Itinéraires :` (titre hors trame du parseur, sans effet sur le chiffrage) :
  ```
  ### Inventaire (repris du CRM) :
  Salon : Canapé 3 places x1 · Table + 2 chaises x1 · Meuble TV x1
  Chambre 1 : Lit double x1 · Armoire 2 portes x1
  Cartons : Carton standard x14 · Carton livres x20
  ```
  Une ligne par pièce, **chaque objet repris avec son libellé et sa quantité d'origine** —
  aucun objet omis, regroupé ou renommé, dimensions et commentaires conservés. Rien à
  recopier si la transaction ne porte pas d'inventaire.

---

## ÉTAPE 1 — Lire les règles

Lire `references/regles-remplissage.md` **avant toute autre action**. Exceptions arbitrées après sa rédaction, qui
priment : l'itinéraire (étape 6, Karim 08/09/2026) et le barème monte-charge (300 € HT (2 h) / 360 € HT (demi-journée) par
côté : Karim 08/09/2026, palier à 180 € retiré le 05/10/2026).

---

## ÉTAPE 2 — Préparer le corps

Copier `references/modele-fiche.md` dans un fichier du scratchpad de la session. On y écrit la fiche : jamais de
format libre ni de section inventée.

---

## ÉTAPE 4 — Remplir la fiche

Voir `references/regles-remplissage.md` pour l'ensemble des règles détaillées.

### Résumé des règles critiques

**Formule :**
- ☑ Standard = aucune option (penderie incluse)
- ☑ Confort = mise en carton partielle, protection fragile, OU démontage/remontage
- ☑ Premium = mise en carton complète ET démontage/remontage
- Ne cocher une option que si explicitement mentionnée — jamais déduite

**Étages :**
- Maison → R+1, R+2, etc. (plain-pied : `R+0 (plain-pied)`)
- Appartement → 1, 2, 3, etc. (jamais R+X)
- Duplex avec ascenseur → Étage avec ascenseur = étage d'accès, Étage sans ascenseur = 1, ajouter "(duplex)"
- **Rdc** coché en plus du type de logement dès que l'accès est au rez-de-chaussée

**Ascenseur :**
- Sans ascenseur → supprimer : "Étage avec ascenseur", "Grand", "Petit", "Liste mobilier ascenseur"
- Avec ascenseur → supprimer "Étage sans ascenseur" ; Grand/Petit supprimés si taille non précisée

**Véhicule :** < 20 m³ → camion 20 m³ · 20–30 m³ → camion 30 m³ · > 30 m³ → deux camions

**Inventaire :** reçu, promis ou source Christophe → ☑ Oui · volume de confrère/client sans
inventaire → ☑ Pas d'inventaire + source

**Parking :** « Réserve les places » uniquement sur demande explicite de réservation en mairie.

**Distances de portage :** minimum **10 mètres** pour l'entrée ET l'intérieur, au départ ET à
l'arrivée ; non mentionnées ou ≤ 10 m → `10 mètres`, sans 🟡.

**Lignes reprises sur le devis (Karim, 03/11/2026) :** les lignes cochées de « Mise en cartons » et de
« Meubles à démonter » passent dans le PDF envoyé au client. Le libellé seul (`- [x] vaisselle`) : jamais
de 🟡, de temps, de « temps à chiffrer » ni de nom de variante. Ce qui reste à chiffrer va dans les Notes.

**Éléments manquants :** 🟡 en début de ligne, mention explicite (`🟡 Information manquante`,
`🟡 À confirmer`, `🟡 En attente d'inventaire`). Pas de surlignage.

**Mise en penderie mentionnée :** `- [x] Mise en penderie : X penderies`, même en Standard.

**Monte-charge / déchetterie :** uniquement sur mention explicite, avec le rappel tarifaire
(`references/regles-remplissage.md`).

**Matériel :** total HT des articles cochés, jamais vide (`0 € HT`), mention de livraison
reproduite **exactement** comme dans le modèle, sans montant de livraison chiffré.

**Champs toujours laissés vides** : `Transport`, `Manut`, `Formule`, `Déplacement`, `Matériel`,
`Prix Total`.

### Compatibilité avec le parseur du pipeline

`outils/pipeline/fiche_notion.py` relit la note pour chiffrer : une fiche mal écrite donne un
devis faux, sans erreur.
- Une seule valeur en `m3` avant le `|` de la ligne « Volume de meuble ».
- « Meubles à démonter » : **une ligne cochée par type d'élément**, nommé comme au barème
  (`python "outils/pipeline/demontage.py" --bareme` : « Armoire 3 portes », « Lit coffre
  double », « Dressing 4 modules »…), quantité en `x2`. Le pipeline en déduit le temps. N'écrire
  une durée (`1h30`, `45 min`) que si elle est donnée : elle prime sur le barème.
- « Temps A/R » s'écrit `5h45`, pas `5,75`.
- Dans les sections Départ / Arrivée, les mots *garde-meuble*, *box*, *dépôt*, *stockage*
  font lire le lieu comme un garde-meuble si aucun type n'est coché.
- **Arrêt intermédiaire** (garde-meuble, dépose chez un tiers…) : une section par arrêt, dans
  l'ordre du trajet, placée après « Arrivée ». Même trame qu'un lieu, plus l'adresse et le
  volume déposé ou chargé sur place, qui pilote la manutention :
  ```
  ### Étape (dépose du lit) :
  Adresse : 28 Avenue Pasteur, 17640 Vaux-sur-Mer
  - [x] Maison
  - [x] Rdc
  Étage sans ascenseur : R+0 (plain-pied)
  Volume déposé : 1 m3
  Distance de portage : …(trame habituelle)
  ```
  L'itinéraire de la fiche se calcule **avec** les arrêts (`--etape`). Une variante sans arrêt
  se génère par `pipeline.py --sans-etapes`. Jamais de 🔀 dans le titre d'une étape : ce préfixe
  est réservé aux variantes de chiffrage (`finalisation.py`).
- **Relivraison** (sortie de garde-meuble vers l'adresse finale, un autre jour — Karim,
  14/10/2026) : une section `### Relivraison :` placée après « Arrivée » (et après les étapes).
  Le pipeline la chiffre dans le même devis (section « Relivraison » du calculateur). Trame :
  ```
  ### Relivraison (sortie de garde-meuble) :
  Date : 🟡 à définir
  Départ : Garde-meuble Sam'Déménage, 147 route des Valentons, 33450 Saint-Loubès
  Adresse : 12 rue X, 33000 Bordeaux
  - [x] Appartement
  Étage sans ascenseur : 1
  Volume relivré : 16 m3
  Distance de portage : 20 mètres
  ```
  « Départ » absent = garde-meuble de Saint-Loubès. « Volume relivré » absent = volume déposé.
  Le trajet du jour est calculé par le pipeline ; ne l'écrire (`Kilomètres A/R`, `Temps A/R`)
  dans la section que s'il est connu.

---

## ÉTAPE 5 — Nettoyage de la fiche

- Ne conserver que le type de logement coché (supprimer les autres)
- Meubles à démonter/remonter : ne garder que les lignes cochées
- Mise en cartons : ne garder que l'option cochée
- Meubles lourds : remplir si mentionné, sinon supprimer la section entière
- Électroménagers dans l'inventaire : débranchement noté (section ou Notes), jamais omis
- Matériel à livrer : toujours conserver intégralement
- Accès compliqués : toujours conserver

---

## ÉTAPE 6 — Itinéraire (calcul automatique)

**S'applique à TOUTES les missions**, locales comprises : les camions partent du dépôt de
**Saint-Loubès**. Diverge de la page de règles (lien Mappy « Bordeaux Centre ») : arbitrage
Samuel du 08/09/2026, voir ci-dessous.

```bash
python "outils/pipeline/itineraire/calcul_itineraire.py" --depart "<adresse départ>" --arrivee "<adresse arrivée>"
```

(un `--etape "<adresse>"` par garde-meuble / point 2 / point 3, dans l'ordre réel)

Reporter dans les lignes du modèle : `Kilomètres A/R`, `Temps A/R` (tel que rendu par le module : l'ajustement est déjà
compris — +0,25 h de marge trafic jusqu'à 1h30 de conduite A/R brute, arrondi à la demi-heure supérieure sans marge
au-delà (Karim, 14/09/2026) — ne rien y ajouter), `Péage HT`, puis **un lien
Mappy de vérification par segment**, entre backticks.

⚠ **Ne jamais fabriquer un lien Mappy unique à plusieurs points.** Testé le 08/09/2026 : le
format `#/recherche/A/B/C/D` ne retient silencieusement que les deux premiers points, et
`#/voiture/<départ>/<arrivée>/car/9` renvoie une 404 au-delà de deux points.

⚠ **Péage** : jamais calculé. Sous 19h06, il vaut 0. Au-delà : `🟡 Péage à renseigner (classe 3
÷ 1,2)`. Module en échec : `🟡 Itinéraire à renseigner manuellement` + les liens, jamais de
kilométrage estimé. Vérifier les alertes `⚠` (adresse résolue dans une autre commune).

---

## ÉTAPE 7 — Écrire la fiche sur HubSpot

```bash
python "outils/pipeline/fiche_hubspot.py" --creer "<fichier du corps>" --nom "NOM" --prenom "Prénom" --tel "06..." --email "x@y.fr" --commercial "Samuel" --depart "<adresse>" --arrivee "<adresse>" --date AAAA-MM-JJ
```

Il retrouve le contact et la transaction, souvent créés par le site, ou les crée, et pose la note. Une information
inconnue : ne pas passer l'option. Pas de date unique (créneaux, date flexible) : pas de `--date`, tous les créneaux
restent dans la fiche. Le commercial s'écrit dans une section `### Suivi :` de la note. Sortie : `transaction`, `url`,
`detail`. Code 1 : contact ou transaction ambigus, rien n'est écrit ; le dire à Samuel avec les doublons cités, jamais
choisir.

---

## ÉTAPE 8 — Vérification

1. `python "outils/pipeline/fiche_hubspot.py" --lire <transaction>` : la note revient bien, nom, téléphone et e-mail lus.
2. Transaction avec inventaire : compter les objets de la section « Inventaire (repris
   du CRM) » contre la source — un écart se corrige avant de continuer.
3. Contrôle de cohérence sur les 9 axes de `references/regles-remplissage.md`, rapporté dans
   la conversation (`⚠️ Incohérence détectée : …` ou `✅ Aucune incohérence détectée — fiche
   cohérente.`), jamais dans la fiche.
4. Si la fiche a été créée pour un devis : contrôler avec `python "outils/pipeline/pipeline.py" --fiche "NOM Prénom"`, puis générer avec `--devis` (skill `calcul-devis-samdem`, § 1).

---

## ÉTAPE 9 — Récapitulatif final

```
✅ Fiche créée — NOM Prénom (lien)

- Départ : [adresse] — Étage [X] — [Ascenseur/Sans ascenseur]
- Arrivée : [adresse] — Étage [X] — [Ascenseur/Sans ascenseur]
- Volume : [X] m³ — Camion [X] m³
- Formule : [Standard / Confort / Premium]

⚠️ Éléments 🟡 à compléter : [liste courte ou "Aucun"]
```

---

## Règles générales

- Toujours lire les règles et repartir du modèle avant de créer
- Correction d'une fiche : `--lire`, corriger les lignes dans un fichier, puis `--creer` avec les mêmes options : la
  note existante est modifiée, aucune autre n'est créée
- En cas de correction de règle → mettre à jour `references/regles-remplissage.md` ET corriger la fiche concernée
