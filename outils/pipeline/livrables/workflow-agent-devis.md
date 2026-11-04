> Document ancien : il décrit encore Notion et noCRM. `outils/pipeline/README.md` fait foi.

---
type: synthese
tags: [process, automatisation, agent, devis, efficience]
created: 2026-09-08
updated: 2026-09-18
sources: 3
---

# Workflow de l'agent devis — arbre de décision et pistes d'efficience

> Origine : session du 08/09/2026 (construction du pipeline) + observations réelles sur la
> base Notion et sur les skills existants. Mise à jour 18/09/2026 : message WhatsApp d'équipe
> et inventaire automatique ajoutés à l'arbre (`inventaire_auto.py`, voir `README.md`).
> Complète [[pipeline-fiche-client-devis]], qui décrit la spec ; ce document décrit
> **l'exécution** et **ce qui reste à gagner**.

## 1. Arbre de décision

```
ENTRÉE : message client, transcript, note commerciale, ou nom d'une fiche existante
   │
   ├── Fiche Notion déjà créée ? ──── non ──▶ /creer-fiche-client-samdem
   │                                          (duplication, remplissage, propriétés,
   │                                           itinéraire calculé, pastilles 🟡)
   │        oui
   ▼
LECTURE DE LA FICHE  →  dossier.json
   │
   ▼
ITINÉRAIRE  (calcul_itineraire.py, automatique)
   │
   ├── confiance = ok / degrade ──▶ km + heures injectés
   ├── peage_requis = true ───────▶ 🟡 péage à relever (classe 3 ÷ 1,2)
   └── confiance = echec ─────────▶ 🟡 + 3 liens Mappy, on demande à Samuel
   │
   ▼
SCORE DE COMPLÉTUDE  (pipeline.py)
   │
   ├── volume absent  ET  inventaire présent
   │        └──▶ ESTIMATION_REQUISE ──▶ /estimer-volume-samdem
   │                                     └─▶ volume CONSERVATEUR ──▶ retour au score
   │
   ├── bloquant absent (adresse, étage, formule…)
   │        └──▶ STOP ──▶ fiche créée quand même
   │                      + relance client rédigée, prête à envoyer
   │
   ├── bloquants OK mais fragilité (itinéraire dégradé, adresse à la commune,
   │   volume sans inventaire, incohérence formule/options, volume > 30 m³)
   │        └──▶ GO_AVEC_RESERVES ──▶ devis produit + bandeau des fragilités
   │
   └── tout OK ──▶ GO
   │
   ▼
DEVIS PRÉ-REMPLI  (pipeline.py --devis : copie du calculateur, dossier injecté)
   │            └──▶ s'ouvre dans le navigateur, formulaire déjà rempli
   │                 (--prefill : JSON au presse-papier pour l'artefact en ligne)
   ▼
▓▓▓ VALIDATION KARIM ▓▓▓   marge · réalisme du temps · options · péage si requis
   │                        (seul point d'arrêt humain — jamais court-circuité)
   ├── refusé ────────────▶ ajustement des inputs, on repasse au calculateur
   └── validé ────────────▶ « Exporter JSON »  (seul geste humain : le veilleur du
   │                                            presse-papier prend la suite)
   ▼
FICHE NOTION  (finalisation.py)  ──▶ bloc de chiffrage + propriétés typées
   │                                ├──▶ section « Itinéraires » (km, temps, péage)
   │                                └──▶ ARCHIVAGE Google Sheet, une ligne par devis
   │                                     (automatique, clé « réf. fiche · variante »)
   ▼
WHATSAPP « Devis/inventaire »  (notif.py, Beeper Desktop)
   │    « Devis prêt à vérifier » → Sandrine
   │
   ├──▶ INVENTAIRE  (inventaire_auto.py, en arrière-plan — 18/09/2026)
   │      │
   │      ├── section Inventaire de la fiche Notion ? ── oui ──┐
   │      ├── sinon fichier « inventaire » sur la fiche ? ── oui ─┤
   │      ├── sinon pièce jointe / description noCRM ? ─── oui ─┤
   │      └── rien ──▶ fin silencieuse, le workflow continue    │
   │                                                             ▼
   │         déjà envoyé (même source) ? ── oui ──▶ fin, zéro coût
   │                                     └─ non ──▶ mise en forme
   │                                                ├── format « Pièce : a · b » → parseur (0 token)
   │                                                └── texte libre / PDF → modèle (claude -p)
   │                                                ▼
   │                                    PDF Prod_inventaires ──▶ même conversation WhatsApp
   │
   └──▶ PIPELINE noCRM (nocrm.py) : « Devis envoyé »,
        ou « Trajets Axe Paris » si le trajet touche l'IdF
```

Chaque étape qui échoue prévient Samuel sur Slack (`notif.alerte`) sans arrêter les suivantes ;
un message ou un PDF non parti attend dans la file WhatsApp.

## 2. Répartition actuelle code / modèle

| Étape | Aujourd'hui | Codable ? |
|---|---|---|
| Comprendre un message client non structuré | modèle | non |
| Lire la fiche Notion → `dossier.json` | **modèle** | **oui, en grande partie** — §3.1 |
| Itinéraire (km, temps, variante, seuils) | code | fait |
| Effectifs, taux, camions, portage, cohérence formule | code | fait |
| Identifier les objets d'un inventaire | modèle | non |
| Coefficients et sommes de volume | code | fait |
| Score de complétude, relance client | code | fait |
| Remplir l'objet `EX` du calculateur | code | fait |
| Calcul du prix | moteur JS du calculateur | fait |
| Relever les chiffres du calculateur | code — bouton « Exporter JSON » | fait (§3.3) |
| Générer le devis HTML client | supprimé — l'artefact en ligne est le document | sans objet (§3.2) |
| Reporter le devis sur la fiche Notion | code — `finalisation.py` | fait |
| Archivage Sheet + Notion | code | fait — automatique à chaque export (09/09) |
| Itinéraire reporté sur la fiche | code | fait (09/09) |
| Avancement du dossier dans noCRM | code — `nocrm.py` | fait (09/09) |
| Message d'équipe WhatsApp (« Devis prêt à vérifier ») | code — `notif.py` via Beeper | fait |
| Chercher l'inventaire (Notion, noCRM) et l'envoyer | code — `inventaire_auto.py` | fait (18/09) |
| Mettre l'inventaire au format maison | parseur si structuré, sinon modèle | en partie — le texte libre reste au modèle |
| Rendu du PDF d'inventaire | code — `Prod_inventaires/generer_inventaire.py` | fait (18/09) |
| Arbitrer une ambiguïté, valider la marge | Samuel | non |

## 3. Les trois chantiers qui restent — par gain décroissant

### 3.1 Lire la fiche Notion par le code — `notion_vers_dossier.py`

**C'est l'étape la plus coûteuse du process aujourd'hui.** Le modèle charge la fiche entière
(propriétés + corps, plusieurs milliers de tokens) pour en extraire une vingtaine de champs.

Or la fiche n'est pas du texte libre : c'est un **modèle dupliqué, toujours identique**.
- Les **propriétés** sont déjà structurées → lecture directe par l'API REST, zéro token.
- Le **corps** suit toujours la même trame : `### Départ :`, `Étage avec ascenseur : 3`,
  `Volume de meuble : 14 m3 | source : …`, cases `- [x]`. Largement parsable en regex.

Le modèle ne resterait nécessaire que pour la section Notes en texte libre et les cas
atypiques. Gain estimé : l'essentiel du coût par dossier.

**Précaution** : sur les 200 fiches de la base, 40 ont `Volume (m3)` vide alors que le corps
porte le volume. Le parseur doit donc **croiser propriété et corps**, et signaler les
divergences plutôt que de faire confiance à l'une des deux.

### 3.2 ~~Générer le devis HTML par le code~~ — **chantier annulé** *(Karim, 08/09/2026)*

> **Il n'y a pas de calculateur à régénérer.** Le moteur existe une fois — `outils/pipeline/calculateurs/calculateur-devis.html`,
> publié en `outils/pipeline/calculateurs/calculateur-devis.html`. On ne le
> recrée pas, on le **remplit**.
>
> **Mise à jour 2026-09-09** (Samuel : le collage manuel n'est pas acceptable) : `pipeline.py --devis`
> copie le maître, y injecte le dossier dans `const PREFILL` et **ouvre le fichier** — le
> formulaire est rempli à l'ouverture, plus de « Charger un dossier » ni de collage. La copie
> porte aussi la fiche Notion cible, donc l'export JSON sait quelle fiche remplir. `--prefill`
> conserve la voie artefact en ligne (presse-papier), utile sur tablette ou pour partager.
>
> Le raisonnement ci-dessous reste valable pour un futur **devis client** (le document
> contractuel envoyé au client), qui est un autre document que le calculateur.

<details><summary>Analyse initiale (conservée)</summary>

Le prompt Cowork « devis HTML » fait plusieurs milliers de tokens et décrit un document
**entièrement fixe** : CSS intégral à recopier à l'identique, structure de tableau imposée,
textes d'engagements et notes de bas de page mot pour mot. Seules une quinzaine de valeurs
changent d'un devis à l'autre.

Faire régénérer ce document par un modèle à chaque devis, c'est payer pour recopier un
gabarit — et prendre le risque qu'il dérive (un CSS reformulé, une note de bas de page
paraphrasée, une clause perdue).

**Un template et un dictionnaire suffisent.** Le modèle n'aurait plus rien à faire ici. Les
règles restantes sont toutes arithmétiques et déjà écrites : acompte = 30 % du TTC arrondi,
solde = TTC − acompte, date limite d'annulation = date de déménagement − 14 j, sous-total HT =
TTC ÷ 1,2 ; la commission (10 %) était fondue dans la ligne transport — **retirée du devis le 09/09/2026**, taux 0 sur tout devis Sam'Déménage (Next Stories compris) ; seul Accès Déménagement garde 7 % (voir [[commission-devis]]). Les options par formule sont un
tableau fixe.

Bénéfice secondaire : les mentions légales et les clauses d'engagement deviennent **garanties
identiques** sur tous les devis, ce qui compte pour un document contractuel.

</details>

### 3.3 Faire sortir les chiffres du calculateur en JSON — **fait le 08/09/2026**

> Le calculateur porte deux boutons : **« Exporter JSON »** (contrat `samdem.devis.export/1` :
> ventilation par champ de fiche, marge, commission, temps bruts) et **« Charger un dossier »**
> (pré-remplissage). `finalisation.py --presse-papier --fiche "NOM"` reprend l'export et écrit
> la fiche Notion — bloc de chiffrage **et** propriétés typées. La boucle est fermée : plus
> aucun modèle ne re-parse du texte qui était structuré une seconde plus tôt.

<details><summary>Analyse initiale (conservée)</summary>

Aujourd'hui Samuel copie le récapitulatif texte et le colle dans un autre projet. Ce
copier-coller est le seul point de rupture de la chaîne : il impose un aller-retour humain et
oblige un modèle à re-parser du texte qui était structuré une seconde plus tôt.

Ajouter au calculateur un bouton « Exporter JSON » (ou l'écriture d'un `.json` à côté du
`.html`) donnerait directement à `export.py` et au générateur de devis la ventilation exacte —
transport, manut, formule, déplacement, matériel, dossier, total HT/TTC, marge, commission.

Petite modification du calculateur, elle ferme la boucle complète.

</details>

---

## 4. Ce qui aurait le plus de valeur, et qui n'est pas dans le plan actuel

### 4.1 Boucler estimation → réalité, pour calibrer

**C'est la suggestion à plus fort effet de levier, et elle ne coûte presque rien à mettre en
place** — parce que les deux moitiés existent déjà séparément.

Aujourd'hui, personne ne sait si le volume conservateur est trop haut ou trop bas, ni si les
temps du calculateur correspondent au terrain. Les coefficients (marges de volume, table
`REFERENCES`, temps de manutention) ont été posés une fois et ne sont jamais confrontés aux
faits.

Or :
- le **Google Sheet** archive désormais volume estimé, temps estimés et prix, dossier par dossier ;
- les **fiches récap de fin de mission** portent le réel (temps passé, difficultés), et un
  skill les importe déjà (`/import-recap-fin-de-mission`) ;
- `axes-itineraires.csv` accumule les trajets réellement calculés.

Il suffit d'ajouter au Sheet quelques colonnes de réel (volume constaté, temps réel,
dépassements facturés ou non) et de comparer. Au bout de quelques dizaines de chantiers, on
saura chiffrer :
- l'écart moyen entre volume conservateur et volume réel → recalibrer les marges plutôt que
  de les avoir choisies au jugé ;
- l'écart entre temps estimé et temps réel → c'est directement la [[fuite-de-marge]], mesurée
  au lieu d'être supposée ;
- quels types de dossiers dérapent (formule, étage, axe, commercial).

**Sans cette boucle, l'agent restera aussi juste que le jour où on l'a réglé.** Avec elle, il
s'améliore avec le volume d'affaires. C'est le seul chantier de cette liste qui rende les
autres plus justes.

### 4.2 Contrôle de cohérence en lot sur la base Notion

L'audit improvisé de cette session a trouvé **40 fiches sur 200 sans volume** et 5 sans
formule. Ce contrôle a pris une requête. En faire un script lancé chaque semaine (zéro token,
zéro modèle) donnerait la liste des fiches à compléter avant qu'elles ne bloquent un devis.

Extensible à d'autres contrôles déjà écrits dans les skills mais jamais vérifiés en masse :
incohérences formule/options, appartements en notation `R+X`, parkings cochés sans demande,
volume > 30 m³ sans second camion.

### 4.3 Garde-fou de marge — **fait le 08/09/2026, retiré le 03/11/2026**

Samuel a retiré le blocage à 30,5 % le 03/11/2026 : la marge reste affichée, le devis continue et
Samuel le relit avant qu'il parte. Voir [[marge-cible]].

### 4.4 Numéro de devis automatique

Le numéro séquentiel est fourni à la main. Le Google Sheet contient toutes les `ref` : le
prochain numéro se déduit. Détail, mais c'est une saisie de moins et une source d'erreur en
moins sur un document contractuel.

---

## 5. Faut-il un second agent ?

**Pour la chaîne devis : non.** Le bon découpage n'est pas « un agent par domaine » mais
« code pour le déterministe, modèle pour l'interprétation ». Multiplier les agents sur la même
chaîne multiplierait les contextes à réamorcer sans rien résoudre.

**Un second agent se justifierait sur le groupage / les tournées** ([[groupage-tournees]],
axe Paris) : données différentes (noCRM, plannings, camions), logique différente (appariement
locomotive/compléments, contrainte LIFO, fenêtres horaires), et surtout **pas de recouvrement**
avec la chaîne devis. Aujourd'hui `/etat-axe-paris` fait le minimum ; si l'optimisation des
tournées devient un sujet, elle mérite son propre espace plutôt que d'alourdir celui-ci.

**L'analyse de marge n'a pas besoin d'un agent** : une fois le Google Sheet alimenté, c'est
un tableau croisé dynamique, pas une conversation.

## 6. Moyens techniques — ce qui n'est pas nécessaire

Par honnêteté, ce qui ne vaut pas l'investissement aujourd'hui :

- **Un VPS.** Tout le pipeline tourne en batch, à la demande, en quelques secondes. Un serveur
  ne servirait qu'à héberger un déclencheur permanent (webhook Notion sur création de fiche,
  watcher). Utile seulement si le déclenchement automatique devient un besoin — pas avant.
- **Une API de péage payante.** Le péage est sorti du périmètre ; la question est close tant
  que la règle des 19h06 tient.
- **Une base de données.** Le CSV de cache et le Google Sheet suffisent au volume actuel
  (quelques centaines de dossiers). Introduire une base ajouterait de l'infrastructure sans
  résoudre de problème existant.

## Pages liées

[[pipeline-fiche-client-devis]] · [[calcul-devis]] · [[moteur-tarification-devis]] ·
[[fuite-de-marge]] · [[pilotage-marge-tresorerie]] · [[groupage-tournees]] ·
[[fiches-recap-fin-mission]]
