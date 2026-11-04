---
name: calcul-devis-samdem
description: Calcule un devis pour un client de Sam'Déménage en lisant sa fiche client (note de sa transaction HubSpot), en déduisant les paramètres selon les règles métier de l'entreprise, puis en générant une copie du calculateur HTML autonome "Sam'Déménage" pré-remplie (remplace le calculateur Notion pour la saisie et le calcul). Déclencher dès que l'utilisateur mentionne "devis", "calculer un devis", "nouveau devis", ou le nom d'un client Sam'Déménage. Aussi : devis à valider, relire le devis, valider le devis.
---

# Calcul de devis Sam'Déménage — via le calculateur HTML (remplace Notion)

## 0. Principe fondamental

Ce skill remplace **uniquement** l'étape de saisie/calcul du devis (qui se faisait avant dans la base Notion "Calculateur de devis automatique"). Tout le reste du processus (lecture de la fiche client, déduction des paramètres, règles métier) reste identique.

- Claude **ne calcule jamais un devis à la main**. Le moteur JavaScript intégré au **calculateur HTML maître `outils/pipeline/calculateurs/calculateur-devis.html`** (racine du vault Sam'Déménage) fait tous les calculs — exactement comme le faisait Notion auparavant.
- **Source de vérité unique du calculateur** : `outils/pipeline/calculateurs/calculateur-devis.html`, toujours la dernière version en date. Aucune autre copie ne fait foi. Ce skill ne modifie **jamais** ce fichier maître — il en fait une copie par client et n'édite que la copie.
- Le rôle de Claude est de : lire la fiche client, déduire les paramètres d'entrée selon les règles ci-dessous, générer une copie du maître avec ces valeurs, puis restituer un récapitulatif des **inputs saisis** (jamais des résultats chiffrés — ceux-ci sont visibles directement en ouvrant le fichier HTML généré, qui les calcule en temps réel).
- Ne jamais halluciner une valeur. Si une donnée obligatoire manque et n'a pas de défaut applicable, la demander explicitement à l'utilisateur plutôt que de l'inventer ou de l'estimer.

## 1. Étape 1 — Lecture de la fiche client : **par le code, pas par le modèle**

**Ne jamais charger une fiche dans le contexte pour en extraire des champs.** Depuis le 03/11/2026
(Samuel), la fiche est une **note « Fiche client » sur la transaction HubSpot**, une nouvelle version à
chaque changement : plus aucune fiche n'est créée ni écrite dans Notion. Sa trame est fixe : elle est
parsée par `outils/pipeline/fiche_notion.py`, qui lit la note par `fiche_hubspot.py` quand l'identifiant
est celui d'une transaction (que des chiffres) et rend un `dossier.json`. Cet identifiant voyage dans
`fiche.page_id` de l'export. Un **ancien dossier** garde sa page Notion en lecture seule : `pipeline.py
--devis` (ou la finalisation à défaut) recopie son corps une fois dans une note de sa transaction, puis le
dossier ne connaît plus que HubSpot.
La chaîne tient en deux commandes, **toujours dans cet ordre** (Karim, 04/11/2026) :

```bash
python "outils/pipeline/pipeline.py" --fiche "NOM Prénom"          # contrôle : rien n'est généré, aucun onglet
python "outils/pipeline/pipeline.py" --fiche "NOM Prénom" --devis  # une seule fois, mêmes options
```

**Contrôle avant génération.** Le contrôle affiche « Ce qui partira dans le calculateur » : confronter ces valeurs à la
fiche (type d'étape, volumes, étages, groupage), et donner à Samuel les questions encore ouvertes **avant** de générer.
`--devis` refuse (code de sortie 4) si un point reste à trancher, si la fiche ou les options ont changé depuis le
contrôle, ou si le devis existe déjà. Un contrôle vaut pour une génération. Devis déjà généré : nouveau contrôle, puis
`--remplacer`, et dire à Samuel de **fermer l'ancien onglet**, qui reste exportable avec l'ancienne version. Ne jamais
régénérer pour vérifier un résultat : contrôler le fichier existant.

| Commande | Effet |
|---|---|
| `pipeline.py --fiche "NOM"` | fiche (note HubSpot) → itinéraire → complétude → valeurs à contrôler, sans rien générer |
| `pipeline.py --fiche "NOM" --devis` | après contrôle : génère `donnees/Devis générés/Devis_NOM_Prénom.html` **et l'ouvre, déjà rempli** |
| `pipeline.py --fiche "NOM" --devis --prefill` | idem + JSON au presse-papier pour l'artefact en ligne |
| `pipeline.py --page-id <id>` | id de transaction (ou d'une ancienne page Notion), si plusieurs fiches portent le même nom |
| `… --devis --variante "Détour X"` | nomme la variante : champ « Variante » du calculateur + nom du fichier |
| `… --devis --sans-etapes --variante "Direct"` | variante sans les arrêts de la fiche, itinéraire recalculé |
| `… --groupage` / `--sans-groupage` | coche le groupage (§10) ou l'écarte. L'un des deux est obligatoire quand la fiche le mentionne |
| `… --chargement-seul` / `--dechargement-seul` | dossier où l'on ne fait qu'une phase (Karim, 28/10/2026) : le temps de l'autre phase est mis à 0 min dans la copie. Signalé par la fiche (`? chargement ou déchargement seul`) ; ne jamais laisser Samuel le corriger à la main. `--deux-phases` si la mention ne vaut pas pour ce devis |
| `… --devis --remplacer` | régénère un devis existant, après un nouveau contrôle : faire fermer l'ancien onglet |
| `… --indicatif` | **obligatoire dès que Samuel dit que le devis est indicatif** (Karim, 09/10/2026) : « Type de devis » = Indicatif posé **tout de suite** sur la transaction HubSpot (ligne « HubSpot : » de la sortie — un ⚠ se signale à Samuel), bandeau « DEVIS INDICATIF », puis réécrit par la finalisation. Sans lui, tout export est « Ferme » |
| `… --malgre-manques` | génère malgré un manque — **sur instruction de Samuel**, jamais sans volume ni itinéraire ; le bandeau liste ce qui reste à saisir |
| `fiche_notion.py "NOM"` | le `dossier.json` seul, pour l'inspecter ou le corriger |
| `fiche_notion.py "NOM" --texte` | le corps brut — **uniquement** si le parseur a échoué |
| `fiche_hubspot.py --chercher "NOM Prénom"` · `--lire <transaction>` | l'identifiant de transaction du dossier · la note « Fiche client » telle qu'elle est (client et lignes) |

**FICHE ABSENTE → LA CRÉER D'ABORD SUR HUBSPOT (Karim, 11/09/2026 ; sur HubSpot depuis le 03/11/2026).** Si
`pipeline.py --fiche` rend `FICHE_A_CREER` (code de sortie 3), le client n'a ni note « Fiche client » sur une
transaction HubSpot, ni page dans l'ancienne base Notion ; le pipeline indique l'opportunité du CRM correspondante.
**Ne jamais chiffrer depuis le CRM ni depuis un `dossier.json` écrit à la main** — sans fiche,
`finalisation.py` n'a rien où reporter le devis. Enchaîner, sans demander :
1. `/creer-fiche-client-samdem`, avec pour source la commande que le pipeline imprime
   (`python "outils/pipeline/hubspot_crm.py" --description "NOM Prénom"` ; `nocrm.py` en retour arrière) ;
2. inventaire sans volume → `/estimer-volume-samdem`, volume **conservateur** reporté dans la
   fiche (nouvelle version de la note) avant le devis ;
3. contrôler avec `pipeline.py --fiche "NOM Prénom"`, puis générer avec `--devis`.

**Pas de fiche = le dossier est dans le CRM (Karim, 16/09/2026 : noCRM, colonne « Contacté
(prise d'infos) » ; aujourd'hui la transaction HubSpot).** C'est la source complète : adresses, accès,
prestations **et inventaire**. Ne jamais demander à Samuel une information présente dans l'opportunité, ni
bloquer le chiffrage parce que la fiche manque.
**Un inventaire dans la fiche ou dans le CRM, même court, est la liste à estimer** : passer
par `/estimer-volume-samdem` et retenir le conservateur. Ne jamais demander un volume ni un
inventaire « complet » à la place (erreur FAYOSSEH : une commode + 20 cartons = 3 m³, à
chiffrer tel quel).

**LE CORPS DE LA FICHE FAIT FOI.** Sur HubSpot, c'est la note : la saisie et les corrections (volume en
tête) se font dans son texte libre ; le contact et les propriétés de la transaction ne complètent que le
contexte (nom, téléphone, e-mail, commercial, référence, date de déménagement, axe de groupage). Il n'y a plus
de comparaison corps/propriétés : `divergences` et `replis` restent vides. Un ancien dossier encore lu sur
sa page Notion garde l'ancienne règle : propriétés Notion en simple repli, toute divergence remontée dans
`_meta.divergences`, le corps est retenu et la divergence signalée à Samuel, jamais tranchée en silence.

**Ce qui reste au modèle**, et rien d'autre :
- `_meta.divergences` (ancien dossier lu sur Notion) — dire à Samuel ce qui diverge ; le corps fait foi, la fiche se corrige par une nouvelle version de la note.
- `_meta.signaux` — mentions repérées mais non tranchées (groupage, garde-meuble,
  monte-meuble, déchetterie, piano, week-end, Nextories). Le code repère, il ne décide pas.
- `_meta.alertes` — les 🟡 de la fiche, à relayer dans le récapitulatif d'appel.
- `_meta.notes` et `_meta.non_parse` — le texte libre, seule zone réellement non structurée.
- Les vraies ambiguïtés de la complétude (statut `STOP` ou `ESTIMATION_REQUISE`).

Règles inchangées :
- Ne jamais redemander une information déjà présente dans la fiche.
- Ne jamais demander la date/heure d'intervention — elle n'a pas d'usage dans le calculateur.
- Un champ à "0" est confirmé, même entouré d'un 🟡 : ne pas redemander.
- Si le parseur rend `null` sur un champ bloquant, c'est un vrai manque : le pipeline produit
  déjà la relance à envoyer. Ne jamais combler un `null` par une valeur plausible.

**Corriger une fiche** (volume estimé, adresse, date, accès…) : une nouvelle version de la note, jamais une
modification dans Notion. `python "outils/pipeline/fiche_hubspot.py" --chercher "NOM Prénom"` donne l'identifiant
de transaction, `--lire <id>` rend les lignes de la fiche ; corriger les lignes dans un fichier du scratchpad,
puis `fiche_hubspot.py --creer <fichier>` avec les mêmes options que la création (`--nom`, `--prenom`, `--tel`,
`--email`…) : les versions précédentes restent. Ancien dossier encore sur sa page Notion : d'abord
`fiche_hubspot.py --reprendre <id de la page>` (ou `pipeline.py --devis`), qui recopie la fiche sur sa transaction.

## 2. Étape 2 — Analyse de la structure de la mission

Avant de vérifier les données chiffrées, identifier la structure réelle de la mission :
- Combien d'adresses sont impliquées (départ simple, étape intermédiaire, garde-meuble/box de stockage, point 2, point 3) ?
- Pour chaque adresse : type de logement, étage, ascenseur, distance de portage.
- **Différence importante avec l'ancien workflow Notion** : une mission avec garde-meuble ou étape intermédiaire **ne donne plus lieu à deux entrées séparées**. Le calculateur HTML gère cela **dans un seul et même fichier**, via ses sections "Étape intermédiaire / garde-meuble", "Point 2" et "Point 3" (jusqu'à 3 arrêts intermédiaires). Utiliser une seule de ces sections par arrêt réel — jamais "Étape" et "Point 2" pour le même arrêt (double comptage).
- **Les arrêts passent par la fiche, et le pipeline les injecte (Karim, 11/09/2026).** Chaque section `### Étape …` de la fiche (adresse, type, étage, portage, `Volume déposé` / `Volume chargé` — format dans `creer-fiche-client-samdem`) remplit dans l'ordre « Étape », « Point 2 », « Point 3 ». Ne jamais saisir un arrêt à la main dans le calculateur. Deux devis « avec / sans arrêt » : `--variante "Détour X"` pour le premier, `--sans-etapes --variante "Direct"` pour le second, qui recalcule l'itinéraire sans l'arrêt.
- Si le garde-meuble n'est pas identifié explicitement (adresse, prestataire), considérer par défaut le garde-meuble Sam'Déménage de **Saint-Loubès** : plain-pied (RDC), portage par défaut — ne jamais redemander ces informations pour ce lieu précis.
- Le temps de manutention à une étape/point (chargement/déchargement sur place) est **calculé automatiquement** par le moteur du fichier HTML à partir du volume chargé/déchargé, de l'étage et du portage saisis — ne jamais demander ce temps à l'utilisateur, ne jamais l'estimer soi-même en dehors des champs prévus.

## 3. Étape 3 — Vérification des données obligatoires

| Donnée | Obligatoire | Valeur par défaut si absente |
|---|---|---|
| Volume (m³) | Oui | Demander |
| Nombre de déménageurs départ | Oui | Déduit du tableau des temps (section 4 ci-dessous) |
| Nombre de déménageurs à chaque étape/point intermédiaire | Oui si étape active | Demander si non déductible |
| Nombre de déménageurs arrivée | Oui | Déduit du tableau des temps |
| Formule tarifaire (Standard/Confort/Premium) | Oui | Prise directement dans la fiche, sans redemander confirmation |
| Taux horaire (€/h) | Oui | Déduit automatiquement selon la zone géographique (section 5) |
| Temps de trajet A/R | Non | 0,5 h (30 min) si mission locale confirmée par la fiche ; sinon, voir règle Mappy en section 6 |
| Kilométrage A/R | Non | Voir règle de priorité en section 6 |
| Coût de déplacement (€ HT) | Non | 20 € HT × nombre de camions, uniquement si aucun kilométrage n'est renseigné (section 6) |
| Coût matériel (autre matériel, € HT) | Non | **Jamais de valeur par défaut** — 0 si rien n'est précisé, ne jamais ajouter un montant inventé |
| Monte-meubles / monte-charges | Non | Aucun, sauf mention explicite |
| Volume déchetterie (m³) | Non | 0 si non mentionné |
| Mise en carton / démontage-remontage (h) | Non, sauf sections concernées non vides dans la fiche | 0 en Standard si non explicitement mentionné (section 8) |

Si des données obligatoires manquent après application des règles de déduction ci-dessous, poser **toutes** les questions manquantes **en une seule fois**, jamais une par une. Ne bloquer que pour de vraies ambiguïtés (donnée manquante, ou donnée contradictoire dans la fiche elle-même qui change significativement le résultat — ex. étage annoncé à deux valeurs différentes). Une fois les inputs complets, générer directement le fichier — ne jamais demander une confirmation du type "je génère le devis avec ces valeurs ?".

## 4. Déduction du nombre de déménageurs — tableau des temps

Référence obligatoire pour déduire `nbDepart` et `nbArrivee` (et les champs équivalents pour Étape/Point 2/Point 3). Colonnes = étage du logement de **départ** pour le chargement, étage du logement d'**arrivée** pour le déchargement (croiser volume × étage séparément pour chaque phase).

| Volume | RDC | 1er | 2e | 3e | 4e | 5e | 6e |
|---|---|---|---|---|---|---|---|
| 0–3 m³ | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| 4–7 m³ | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| 8–11 m³ | 2 | 2 | 2 | 3 | 3 | 3 | 3 |
| 12–14 m³ | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| 15–19 m³ | 3 | 3 | 3 | 3 | 4 | 4 | 4 |
| 20–23 m³ | 3 | 3 | 3 | 4 | 4 | 4 | 4 |
| 24–27 m³ | 3 | 4 | 4 | 4 | 4 | 4 (plafonné) | 4 (plafonné) |
| 28–31 m³ | 4 | 4 | 4 | 4 | 4 | 4 (plafonné) | 4 (plafonné) |
| 32–35 m³ | 4 | 4 | 4 | 4 | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) |
| 36–39 m³ | 4 | 4 | 4 | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) |
| 40–43 m³ | 4 | 4 | 4 | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) |
| 44–60 m³ | 4 | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) | 4 (plafonné) |

Règles :
- **Avec ascenseur** : diviser le numéro d'étage par 2 (arrondi au plus proche) pour trouver la colonne. Ex. 4e étage avec ascenseur → lire colonne "2e".
- **Plafond absolu : 4 déménageurs par phase.** Toute valeur du tableau original de 5 ou 6 est arrondie silencieusement à 4 (déjà reflété ci-dessus).
- **Passage automatique à 4 au chargement** si simultanément : étage ≥ 1 (pas RDC), ascenseur présent, ET volume ≥ 35 m³.
- Ces règles s'appliquent silencieusement dès que volume, étage et ascenseur sont connus. Ne demander que si une donnée manque.
- Le tableau donne une **suggestion** — l'utilisateur peut la corriger explicitement.
- **Toujours rappeler en tête de message** le nombre de déménageurs déduit (détail chargement/déchargement) quand on pose des questions, ou en tête du récapitulatif final.
- Si la fiche est elle-même contradictoire sur l'étage (deux valeurs possibles), ne jamais deviner : poser la question à l'utilisateur avec les deux options et leur impact chiffré (ex. "3 déménageurs si étage 2, 4 si étage 5").

## 5. Taux horaire (barème simplifié — décision Karim 08/09/2026)

- **Manutention : 28 €/h dans TOUS les cas** (Karim, 23/09/2026 ; 30 €/h du 08/09 au 22/09), local
  comme longue distance. Remplir `tauxDepart`
  et `tauxArrivee` à 28 sans demander confirmation, sauf si l'utilisateur précise un autre taux
  (corrigé le 01/10/2026 : la ligne disait encore 30, Samuel confirme 28 €/h).
- **Plus aucune zone tarifaire à déterminer.** L'ancien découpage « zone Bordeaux 28 €/h /
  hors zone 30 €/h » (barème du 28/08/2026, avec sa liste de communes) est supprimé : il n'y a
  plus de géographie à trancher pour fixer le taux de manutention.
- **Longue distance = trajet aller-retour ≥ 2 h** (décision D6, Karim 05/10/2026 : la règle
  des calculateurs fait foi ; l'ancien seuil 5h59 est périmé) : taux unique de **20 €/h par personne du camion**, sans distinction
  conducteur/passager. Cela inclut le cas d'un camion 50 m³ loué : pas d'exception à 25 €/h en
  contexte longue distance (l'exception 25 €/h conducteur pour un camion 50 m³ loué ne
  s'applique que **hors** longue distance). Le module d'itinéraire renseigne directement
  `longue_distance` en appliquant ce seuil.
- **Équipe mixte** (taux différents au sein d'une même phase) : le calculateur n'accepte qu'un
  seul taux par phase → saisir la moyenne pondérée arrondie à l'entier, et le signaler dans le
  récapitulatif.
- **Mission Paris** : ne plus saisir le forfait « 1 250 km / 19 h ». Le module mesure la boucle
  réelle depuis le dépôt — 1 283 km / 18,25 h en itinéraire sans péage, valeurs très proches de
  l'ancien forfait, qui correspondait donc bien à un trajet sans péage.

## 6. Trajet, kilométrage, péage — calcul par le module d'itinéraire

**La lecture d'un lien Mappy reste interdite** : ce lien était structurellement incapable de
porter la boucle (le site ne sait pas encoder d'étapes dans une URL — vérifié le 08/09/2026,
404 au-delà de deux points). C'est bien pour cela que la règle « Mappy désactivé » existait.
Ce qui change, c'est qu'il existe désormais une source déterministe à la place.

Ordre de priorité :
1. Chiffres **explicitement écrits dans le corps de texte** de la fiche (km A/R, temps de
   trajet, péage) → les utiliser tels quels.
2. Sinon, lancer le module :
   ```bash
   python "outils/pipeline/itineraire/calcul_itineraire.py" --depart "<adresse>" --arrivee "<adresse>" --json
   ```
   (un `--etape "<adresse>"` par garde-meuble / point 2 / point 3)
   Il calcule la boucle dépôt Saint-Loubès → départ → étapes → arrivée → dépôt, et applique
   la règle des 19h06 (itinéraire sans péage tant que l'A/R tient sous 19h06 ; 18 h périmé depuis le 08/09).
   - `confiance` ∈ {`ok`, `degrade`} → injecter `km_ar` dans `kmAR` et `heures_conduite_ar` (ajustement déjà compris — Karim, 11/09 puis 14/09/2026 : +0,25 h de marge trafic jusqu'à 1h30 de conduite A/R brute, au-delà arrondi à la demi-heure supérieure sans marge — ne jamais rajouter quoi que ce soit, pas même sur un temps écrit à la main)
     dans `heuresRouteAR`. Reporter les alertes `⚠` dans le récapitulatif.
   - `longue_distance = true` → cocher le flag « trajet ≥ 2h » et `tauxConducteur = 20` (§5).
   - `confiance = echec` → **retomber sur l'ancienne règle** : poser la question dans le bloc
     groupé. Ne jamais estimer un kilométrage à la place.
3. **Péage** : jamais calculé. `peageAR = 0` si `peage_requis = false`. Si `peage_requis = true`
   (A/R > 19h06), demander le montant à Samuel, qui le relève en classe 3 et divise par 1,2 —
   toujours dans le champ dédié `peageAR`, jamais dans `autreCoutDepl`.
- **Exception locale** : si la fiche confirme une mission locale et que le module n'est pas
  disponible, le défaut de 0,5 h A/R (`heuresRouteAR = 0.5`) reste valable. À noter que le
  module donne une valeur plus réaliste (~1,5 h A/R depuis Saint-Loubès pour un chantier
  intra-agglomération) : le défaut de 0,5 h sous-estime le déplacement.
- **Priorité stricte kilométrage vs coût déplacement forcé** :
  1. Si un kilométrage A/R est connu (fiche ou réponse utilisateur) → le saisir dans `kmAR`, laisser `coutDeplManuel` à 0.
  2. Si aucun kilométrage n'est connu (mission locale) → laisser `kmAR` à 0 et saisir dans `coutDeplManuel` le défaut **20 € HT × nombre de camions** (`nbCamions`).
- **Péage** : toujours dans le champ dédié `peageAR` (jamais dans `autreCoutDepl`).
- **Groupage** : même en groupage, toujours renseigner `kmAR`/`heuresRouteAR`/`peageAR` normalement. Seuls les champs spécifiques longue distance (`tauxConducteur`, le flag "trajet ≥ 2h") restent vides — le moteur gère seul la logique de groupage une fois la case `groupage` cochée.

## 7. Nombre de camions

- Volume ≤ 30 m³ → 1 camion par défaut (`nbCamions = 1`), sans demander.
- Volume > 30 m³, ou fiche suggérant un second camion → demander.

## 8. Mise en carton, démontage/remontage, protection fragile

- **Mise en carton** (vaisselle, livres, etc.) : si la section correspondante de la fiche contient des éléments, toujours demander la valeur en heures pour `cartonH` — ne jamais l'estimer soi-même.
- **Mise en penderies** : si mentionné, compter 30 min pour 5 penderies (calcul proportionnel sans arrondi, converti en heures), à ajouter dans `cartonH`. Ex. 5 penderies = 0,5h ; 10 penderies = 1h.
- **Démontage / remontage — estimé automatiquement (barème Karim, 11/09/2026)** : chaque ligne cochée de la section est chiffrée par `outils/pipeline/demontage.py`, qui la rapproche de l'élément le plus proche du barème (temps démontage + remontage pour **2 personnes**) et la multiplie par sa quantité (`x2`) ou son nombre de modules. `pipeline.py` le fait seul : une durée écrite sur la ligne fait foi ; sinon le barème s'applique tel quel. **Le démontage/remontage est toujours facturé pour 2 personnes** (`demontageH × 2 × taux`, constante `EQUIPE_DEMONTAGE` de tous les calculateurs — Karim, 06/10/2026), quel que soit l'effectif du chantier ; mise en carton et protection fragile restent à l'effectif réel. **Ne plus demander ce temps.** Éléments au barème sans temps (chaise, cuisine, électroménager, TV…) et éléments hors barème : 0 h, remontés en 🟡 par le pipeline — les signaler à Samuel, jamais les estimer. Contrôler un rapprochement : `python "outils/pipeline/demontage.py" "Armoire 3 portes x2"` ; barème complet : `--bareme`.
- **Exception formule Standard** : mise en penderies et démontage/remontage sont des options non obligatoires en Standard. Si non explicitement mentionnés dans la fiche, ne pas poser de question, laisser `cartonH`/`demontageH` à 0 silencieusement.
- **Une durée notée entre parenthèses dans une fiche (ex. "(45m)")** correspond directement à un nombre de minutes à saisir tel quel — ne jamais redemander.
- **Débranchement/rebranchement électroménager** : ne jamais le facturer ni le demander, même si mentionné dans la fiche comme "à confirmer" — l'ignorer systématiquement.

## 9. Matériel de conditionnement

- **Jamais de valeur par défaut.** Si l'utilisateur ne précise aucun montant/quantité, laisser à 0 — ne jamais ajouter un supplément inventé.
- Le calculateur a une liste de matériel prédéfinie avec des clés précises. Pour cocher un article et fixer sa quantité, ajouter dans l'objet `EX` du fichier généré les clés `mat_<clé>: true` et `qte_<clé>: <quantité>` correspondantes :

  | Article | clé |
  |---|---|
  | Cartons standards | `standard` |
  | Cartons livres | `livres` |
  | Cartons vaisselle | `vaisselle` |
  | Cartons bouteilles | `bouteilles` |
  | Cartons penderies (jamais de livraison) | `penderies` |
  | Cartons informatiques | `informatiques` |
  | Cartons tableaux | `tableaux` |
  | Rouleau scotch | `scotch` |
  | Rouleau bulles 20 m | `bulles` |
  | Barrel verres | `barrelVerres` |
  | Barrel assiettes | `barrelAssiettes` |
  | Rouleau Kraft | `kraft` |

- Livraison du matériel (30 € HT, sauf cartons penderies) : `matLivraison: true/false`.
- Montant "Autre matériel" (non listé, hors barème) : champ `coutMateriel`, jamais de défaut, uniquement si l'utilisateur précise un montant total (livraison comprise).

## 10. Autres règles spécifiques

- **Groupage** : cocher simplement `groupage: true` dans l'objet EX dès que "groupage" est mentionné. Ne rien demander de plus (pas de répartition transport, pas de client à identifier).
- **Duplex** : utiliser `tlDepart`/`tlArrivee = "Duplex"` (et non "Appartement") si la fiche décrit explicitement un logement en duplex — le moteur applique seul la majoration d'étage correspondante. Ne pas essayer de corriger manuellement le champ étage.
- **Type "Box"** : à utiliser pour les étapes en box de stockage (accès simplifié, réduit le temps automatiquement).
- **Réservation de stationnement** (`reservStat`) : gratuit (0) si la commune concernée fait partie des 28 communes de Bordeaux Métropole listées en section 5. Sinon 30 € HT par réservation hors agglomération (départ ou arrivée), cumulable à 60 € HT si les deux adresses sont hors agglomération. Attention : ce périmètre est plus étroit que la zone tarifaire 28€/h — la Gironde hors métropole et les autres communes en zone 28€/h hors métropole comptent comme "hors agglomération" pour cette règle précise. Appliquer silencieusement, mais toujours signaler le montant dans le récapitulatif si non nul.
- **Monte-meubles/monte-charges** : utiliser le champ `mmDepart`/`mmArrivee` avec la valeur `"2h"` (300 € HT) ou `"demi"` (½ journée, 360 € HT) selon ce qui est précisé dans la fiche — sinon laisser vide (`""`).
- **Mission d'urgence** (Christophe en ligne, devis rapide) : ne jamais aller chercher de fiche client dans ce contexte — générer directement le fichier avec les seules informations transmises par l'utilisateur, en appliquant les défauts habituels (trajet 0,5h A/R, taux horaire de zone) sans demander l'adresse si elle n'est pas spontanément donnée.
- **Piano** : cocher `piano: true` si mentionné (forfait +300 € HT géré par le moteur).

## 11. Étape 4 — Renseignement des inputs dans le calculateur HTML (remplace Notion)

Le calculateur HTML maître est **`outils/pipeline/calculateurs/calculateur-devis.html`** (vault Sam'Déménage) — **source de vérité unique**, toujours la dernière version en date. Il contient l'intégralité du moteur de calcul (barème, formules JavaScript). **Ne jamais modifier la logique de calcul ni le fichier maître** — seule la section suivante, en haut du `<script>` de la **copie par client**, doit être adaptée :

```js
const EX = {
  clientNom: "...",
  volume: ..., formule: "...", jaille: "...", dateCreation: "...",
  ...
};
```

**Cette étape est entièrement codée** : `pipeline.py --devis` crée le dossier de sortie, copie
le maître vers `donnees/Devis générés/Devis_[NOM]_[Prénom].html`, construit l'objet `EX` depuis le
`dossier.json`, l'injecte dans la constante `PREFILL` de la copie (avec la fiche cible, soit l'identifiant
de transaction, et le bandeau) puis **ouvre le fichier dans le navigateur**. **Ne jamais recopier le calculateur
ni rédiger un objet `EX` à la main** — c'est du travail que le code fait déjà, et sans risque
de dérive.

```bash
python "outils/pipeline/pipeline.py" --fiche "NOM Prénom"          # contrôle (§1)
python "outils/pipeline/pipeline.py" --fiche "NOM Prénom" --devis  # une seule fois, mêmes options
```

Il reste à :
1. Rien : le devis s'ouvre seul, formulaire rempli. Pas de `start`, pas de « Charger un
   dossier », pas de collage. Si l'ouverture automatique échoue, le script le dit et donne le
   chemin — c'est le seul cas où on l'ouvre à la main.
2. Ne jamais demander de confirmation du type « je génère le devis ? » une fois le contrôle
   relu et sans question ouverte. Une vraie ambiguïté se pose à Samuel **avant** de générer ; le
   pipeline refuse aussi sur `STOP`, `ESTIMATION_REQUISE` ou un point à trancher.

La table de correspondance de la section 12 reste la référence du **contenu** de `EX` : elle
documente ce que le pipeline écrit, et sert quand une valeur doit être forcée dans le
`dossier.json` avant génération.

## 12. Table de correspondance champ métier → nom de champ dans l'objet `EX`

| Concept | Champ EX | Valeurs possibles |
|---|---|---|
| Nom client | `clientNom` | texte |
| Volume | `volume` | nombre (m³) |
| Formule | `formule` | `"Standard"` / `"Confort"` / `"Premium"` |
| Proportion de jaille | `jaille` | `"Faible (< 50%)"` / `"Moyenne (50–75%)"` / `"Élevée (> 75%)"` (défaut : Faible) |
| Date de création | `dateCreation` | `"AAAA-MM-JJ"` |
| Groupage | `groupage` | `true`/`false` |
| Mission week-end | `weekend` | `true`/`false` |
| Devis Next Stories | `nextStories` | `true`/`false` (jamais par défaut). À `true`, le calculateur ramène **automatiquement la marge à 21 %** après tous les autres calculs — ne pas recaler la marge à la main. |
| Type logement départ/arrivée | `tlDepart` / `tlArrivee` | `"Appartement"` / `"Maison"` / `"Box"` / `"Duplex"` |
| Étage départ/arrivée | `etageDepart` / `etageArrivee` | nombre (0 = RDC) |
| Portage départ/arrivée | `portageDepart` / `portageArrivee` | mètres (somme entrée + intérieur) |
| Nb déménageurs départ/arrivée | `nbDepart` / `nbArrivee` | nombre (déduit du tableau, section 4) |
| Taux horaire départ/arrivée | `tauxDepart` / `tauxArrivee` | €/h (déduit de la zone, section 5) |
| Ascenseur départ/arrivée | `ascDepart` / `ascArrivee` | `true`/`false` |
| Ascenseur petit format | `ascDepartPetit` / `ascArriveePetit` | `true`/`false` |
| Monte-meubles départ/arrivée | `mmDepart` / `mmArrivee` | `""` / `"2h"` / `"demi"` |
| Heures de route A/R | `heuresRouteAR` | décimal (0,5 par défaut si local) |
| Kilométrage A/R | `kmAR` | nombre |
| Nombre de camions | `nbCamions` | nombre (1 par défaut si volume ≤ 30) |
| Coût déplacement forcé | `coutDeplManuel` | € HT (20 × nbCamions par défaut si pas de km) |
| Passagers (hors conducteur, LD) | `nbPassagers` | nombre |
| Taux conducteur route (LD) | `tauxConducteur` | €/h ou `""` (auto, 20€/h unifié si ≥ 2 h) |
| Péage A/R | `peageAR` | € HT |
| Camions de location / coût | `nbCamionsLoc` / `camionLocHT` | nombre / € HT de location total, **hors carburant** — le calculateur ajoute 0,40 € HT/km (depuis le 03/11/2026, 0,50 du 16/10 au 03/11) × `kmAR` par camion loué (hors groupage) |
| Autre coût déplacement | `autreCoutDepl` | € HT (jamais le péage ici) |
| Réservation stationnement | `reservStat` | € HT (0 / 30 / 60, section 10) |
| Le gérant conduit | `gerantConduit` | `true`/`false`, uniquement si explicitement mentionné |
| Étape intermédiaire / garde-meuble | `typeEtape` | `""` / `"Box / Garde-meuble"` / `"Adresse intermédiaire"` / `"Autre"` |
| Étage / volumes / portage / ascenseur étape | `etageEtape`, `volEtapeCharge`, `volEtapeDecharge`, `portageEtape`, `ascEtape`, `ascEtapePetit` | idem départ/arrivée |
| Point 2 / Point 3 | mêmes champs avec suffixe `Point2` / `Point3` | idem |
| Relivraison (sortie de garde-meuble, autre jour — Karim 14/10/2026) | `relivActif` | `true`/`false` ; seconde opération du même devis : manutention + logistique comptées, dossier / options / matériel une seule fois, une seule marge |
| Lieux de relivraison | `relivTlDepart` (défaut `"Box"`), `relivEtageDepart`, `relivPortageDepart`, `relivTlArrivee`, `relivEtageArrivee`, `relivPortageArrivee`, `relivAscArrivee`, `relivAscArriveePetit`, `relivMmArrivee` | idem départ/arrivée |
| Relivraison — volume, équipe, trajet du jour | `relivVolume` (vide = volume déposé), `relivNbDepart`, `relivNbArrivee`, `relivTaux`, `relivHeuresRouteAR`, `relivKmAR`, `relivNbCamions`, `relivPeageAR`, `relivReservStat` | rempli par `pipeline.py` depuis la section `### Relivraison :` de la fiche |
| Mise en carton (h) | `cartonH` | décimal |
| Démontage/remontage (h) | `demontageH` | décimal |
| Protection fragile (h) | `fragileH` | décimal |
| Volume déchetterie | `volDechetterie` | m³ |
| Options manuelles | `optionsManuelles` | € HT |
| Piano | `piano` | `true`/`false` |
| Matériel de conditionnement | `mat_<clé>` + `qte_<clé>` | voir table section 9 |
| Livraison matériel | `matLivraison` | `true`/`false` |
| Autre matériel (hors liste) | `coutMateriel` | € HT, jamais de défaut |
| Volume serré / objet lourd | `volumeSerre` / `objetLourd` | `true`/`false`, uniquement si explicitement mentionné (durée uniquement, jamais deviné) |

Les champs non listés ici gardent leur valeur par défaut du fichier maître (0, `false` ou `""`).

## 13. Étape 5 — Récapitulatif

Une fois le fichier généré, présenter à l'utilisateur :
1. En tête de message : les déductions faites (nombre de déménageurs départ/arrivée avec le détail du raisonnement, taux horaire retenu et la zone correspondante).
2. Un récapitulatif des **inputs saisis** (jamais des montants calculés — ceux-ci sont visibles en ouvrant le fichier HTML généré, qui les calcule automatiquement).
3. Toute information utile mais non chiffrée relevée dans la fiche (notes 🟡, contraintes d'accès, objets ne rentrant pas quelque part, etc.) pour aider l'utilisateur lors de son appel client — sans l'intégrer au calcul.
4. Le chemin du fichier généré (et confirmer qu'il a été ouvert automatiquement si c'est le cas).

## 13 bis. Étape 6 — Après l'export : relecture et validation (Karim, 03/11/2026)

L'export du calculateur est la version officielle. Rien n'arrive sur HubSpot ni à l'équipe avant que
Samuel ait relu et validé. Le veilleur fait la finalisation sans modèle ; c'est ici que Claude reprend la main.

1. **Juste après le récapitulatif**, lancer l'attente **en arrière-plan** (`run_in_background`), sans
   poser de question :
   ```bash
   python "outils/pipeline/validation_devis.py" --attendre
   ```
   Elle se termine quand un export est prêt, ce qui réveille la session. Elle rend un JSON : `client`,
   `page_id`, `pdfs` (chemin, variante, TTC, `conforme`, `controle`), `a_verifier`, `a_la_main`,
   `inventaire`, `hubspot_url`. `{"statut": "aucun_export"}` : rien n'est arrivé en 4 h, ne rien dire.
   La marge n'arrête rien (Karim, 03/11/2026) : le JSON porte `marge` (`pct`, `cible`, dernier export) ;
   sous la cible, la dire à la relecture, en une phrase.
2. **`a_la_main` renseigné et aucun PDF** (relivraison, étape, chargement seul…) : produire le PDF avec
   `/devis-pdf-samdem`, puis `validation_devis.py --ajouter-pdf "<pdf>" --page-id <id> --ttc <TTC>`.
3. **Faire relire** : `SendUserFile` avec le ou les PDF du devis et l'inventaire si `inventaire.statut`
   vaut `pret`, `display: "render"`. En une ou deux lignes : le TTC, le résultat de `controle`, la liste
   `a_verifier`. Si `conforme` vaut `false`, le dire en premier : le PDF ne correspond pas à l'export.
   `corrections_perdues` non vide : le dire aussi, ces corrections de texte sont à refaire sur le nouveau PDF.
4. **Donner la sélection** (`AskUserQuestion`), toujours, jamais une question en texte :
   « Valider et importer sur HubSpot », « Corriger le texte du PDF » ou « Changer le chiffrage ». Plusieurs
   variantes : `multiSelect`, une option par PDF, et les deux options de correction.
5. **Validé** : `python "outils/pipeline/validation_devis.py" --valider --page-id <id>` (un
   `--variante "X"` par PDF retenu s'il y en a plusieurs). Cela joint le devis et, si le dossier en a un,
   l'inventaire à la transaction, puis envoie le message d'équipe et l'inventaire sur WhatsApp. Donner le
   compte rendu et le lien HubSpot. Code de sortie 1 : le dire,
   la cause est dans la sortie et l'alerte Slack est partie ; relancer une fois la cause réglée.
   Le brouillon de mail n'en fait pas partie : Sandrine envoie depuis son adresse (Karim, 03/11/2026). Ne le
   préparer que sur demande explicite de Samuel (`devis-pdf-samdem`, § 7), et ne pas le proposer.
6. **Corriger le texte du PDF**, le cas courant : les calculs sont déjà approuvés (Karim, 03/11/2026).
   Demander la correction si elle n'est pas donnée, modifier seulement cela dans le fichier `spec` du PDF
   (champ du JSON), sans toucher aux montants, puis :
   ```bash
   python "outils/pipeline/validation_devis.py" --regenerer --page-id <id> --motif "ce qui a changé" [--variante "X"]
   ```
   Même numéro, rien n'est importé. Relire le texte du PDF, puis reprendre à l'étape 3. Code de sortie 1 : le
   dire (spec refusée, ou TTC modifié, à repasser par le calculateur).
   - Adresse, date, téléphone, e-mail : corriger aussi la fiche (nouvelle version de la note, § 1) et le CRM,
     sinon le prochain export repart de l'ancienne valeur. Un nouvel export refait la spec, et ses corrections reviennent dans `corrections_perdues`.
   - Texte fixe du modèle (engagements, formule) : il n'est pas dans la spec et sert à tous les devis. Le dire à
     Samuel avant de toucher au générateur.
7. **Changer le chiffrage**, plus rare : `--refuser --page-id <id> --motif "..."`, demander ce qui change, puis
   `python "outils/pipeline/reprendre_devis.py" "NOM Prénom"` et relancer l'étape 1. Le nouvel export garde
   le numéro et remplace le PDF ; garder le même nom de variante (« Remplacer quand même »).
8. **Lot** : relancer l'attente après chaque dossier traité, tant qu'il en reste à exporter.

« devis à valider » ou « qu'est-ce qui attend ma relecture ? » : `validation_devis.py --liste`, puis
étapes 3 à 7 pour chaque dossier. C'est aussi le rattrapage d'un export fait sans session ouverte.

## 14. Style de travail

- Concis, directif — déduction autonome, minimum d'allers-retours.
- Ne jamais poser les questions une par une : regrouper toutes les ambiguïtés réelles en un seul bloc avant de générer le fichier.
- Ne bloquer que pour de vraies ambiguïtés (donnée manquante sans défaut, ou donnée contradictoire dans la fiche qui change significativement le résultat).
- Ne jamais demander de confirmation du type "je génère avec ces valeurs ?" une fois les inputs complets.
- Ne jamais halluciner ou inventer une valeur (kilométrage, montant matériel, taux, etc.) : si l'information n'est pas dans la fiche et n'a pas de règle de défaut applicable ci-dessus, la demander explicitement.
