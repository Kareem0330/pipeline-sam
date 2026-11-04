> Dans ce dossier, le calculateur est un fichier local : `calculateurs/calculateur-devis.html`. La voie « artefact en ligne » décrite plus bas n'existe pas ici : `--prefill` se colle dans ce fichier, bouton « Charger un dossier ».

---
type: concept
tags: [outil, pipeline, devis, automatisation]
created: 2026-09-08
updated: 2026-11-03
sources: 1
---

# Pipeline dossier → devis — mode d'emploi

> Origine : P1 du [[pipeline-fiche-client-devis]], construit le 08/09/2026.
> Objectif : que le traitement d'un dossier exécute du code déjà écrit plutôt que de faire
> re-raisonner le modèle à chaque fois.

## Carte du dossier

Tout ce qui sert à la chaîne de devis vit ici depuis le 03/11/2026 (décision Karim).

| Où | Quoi |
|---|---|
| racine | les scripts de la chaîne (`pipeline.py`, `fiche_hubspot.py`, `fiche_notion.py`, `finalisation.py`, `devis_auto.py`, `validation_devis.py`, `inventaire_auto.py`, `hubspot_crm.py`…), le veilleur `watch-devis-export.ps1`, le cache `axes-itineraires.csv` |
| `calculateurs/` | le maître `calculateur-devis.html`, l'atelier (généré), le terrain |
| `itineraire/` | le module d'itinéraire (`calcul_itineraire.py`) |
| `devis-pdf/` | le générateur du PDF de devis et le brouillon d'envoi |
| `références/` | les devis validés aux formats particuliers, un dossier par cas, à reprendre comme modèles (Karim, 04/11/2026) ; tous anonymisés, rangés par `reference_devis.py` |
| `Prod_inventaires/` | le générateur du PDF d'inventaire |
| `livrables/` | les deux flowcharts, la spec, l'arbre de décision, `pj-envoi/` (pièces d'un brouillon, vidé après l'envoi ; ignoré par git) |
| `sans-notion/` | le projet « chaîne sans Notion » (décision du 03/11/2026) : `plan-projet.md`, `taches.json`, `planning.html`, `correspondance-rapport.md` |
| `tests/`, `relivraison-calculateur/`, `reprise-auto/` | les tests et les projets terminés |

Restent ailleurs : les skills dans `.claude/skills/` (seul endroit où Claude Code les trouve), les livrables qui
s'accumulent sur `donnees/` (`Devis générés\` : copies du calculateur, exports, relectures ; `Devis SamDem\` : PDF ; Karim, 04/11/2026), `outils/crm.env` (interrupteur commun à tous les outils) et le
calculateur Accès Déménagement, outil autonome, hors chaîne. **Groupage** (`outils/Groupage/`) et le workflow
**Nextories** gardent leurs copies autonomes de la chaîne, encore sur Notion : ils ne sont pas adaptés à la fiche
HubSpot à ce stade (03/11/2026).

Flowcharts : [en bref](outils/pipeline/calculateurs/calculateur-devis.html) (`livrables/flowchart-chaine-devis-simple.html`)
et [détaillée](outils/pipeline/calculateurs/calculateur-devis.html) (`livrables/flowchart-chaine-devis.html`). Les étapes de
la version détaillée sont des données en tête du script de la page : les mettre à jour quand la chaîne change, puis republier.

## Ce qui est passé du modèle au code

| Étape | Avant | Maintenant |
|---|---|---|
| Lecture de la fiche | Fiche entière chargée dans le contexte du modèle | `fiche_notion.py`, qui lit la note HubSpot par `fiche_hubspot.py` |
| Km, temps de trajet | Relevé manuel sur Mappy | `outils/pipeline/itineraire/calcul_itineraire.py` |
| Nombre de déménageurs | Table croisée relue par le modèle à chaque dossier | `regles.nb_demenageurs()` |
| Taux horaires, camions, portage minimum | Règles relues et appliquées à la main | `regles.py` |
| « La fiche est-elle complète ? » | Coup d'œil humain | `pipeline.evaluer_completude()` |
| Relance client si incomplet | Rédigée à la main | Générée, prête à copier |
| Copie du calculateur pré-remplie | Objet `EX` édité par le modèle | `pipeline.generer_devis()` — le maître est copié et rempli, jamais réécrit |
| Relevé des chiffres du calculateur | Copier-coller du récap texte | Bouton « Exporter JSON » de l'artefact |
| Report du devis sur la fiche | Projet Cowork « finalisation fiche Sandrine » | `finalisation.py` |

Il ne reste au modèle que ce qui ne se code pas : comprendre un message client non structuré
lors de la **création** de la fiche, arbitrer une divergence ou un signal, et rédiger.

## Utilisation

Le cas courant — trois commandes, une par étape, et rien à retaper entre elles :

```bash
# 1. un dossier : contrôle sans onglet, puis génération une seule fois, mêmes options. Ou tout un lot d'un coup
python "outils/pipeline/pipeline.py" --fiche "PLANCHAIS Benoit"
python "outils/pipeline/pipeline.py" --fiche "PLANCHAIS Benoit" --devis
python "outils/pipeline/pipeline.py" --fiches "PLANCHAIS Benoit" "HAENSLER Louis" "VIGNERON Lucile"

# 2. le devis s'ouvre tout seul, déjà rempli : ajuster → « Exporter JSON »
#    (voie tablette / partage : ajouter --prefill et coller dans l'artefact en ligne
#     outils/pipeline/calculateurs/calculateur-devis.html)

# 3. la fiche (note HubSpot) se met à jour toute seule si le veilleur tourne (voir plus bas) ;
#    sinon, à la main — le JSON sait déjà quelle fiche il vise :
python "outils/pipeline/finalisation.py" --presse-papier            # contrôle
python "outils/pipeline/finalisation.py" --presse-papier --appliquer
```

## Un seul geste humain — le veilleur de presse-papier

`outils/pipeline/watch-devis-export.ps1` surveille le presse-papier. Dès que « Exporter JSON »
y dépose un devis, il archive l'export dans `donnees/Devis générés/exports/` et lance
`finalisation.py --appliquer` sur **la fiche que le JSON désigne lui-même**. Rien à taper, rien
à nommer.

**Il démarre avec Windows** — `SamDemenage-DevisWatcher.bat` dans le dossier Démarrage appelle
`~/.local/bin/samdem-devis-watcher.ps1`, lanceur ASCII qui reconstruit le chemin accentué
(même convention que le watcher du wiki : un `.bat` ou un `.ps1` contenant « Déménage » en clair
casse au démarrage, PowerShell 5.1 lisant ces fichiers dans l'encodage système). Pour le lancer
à la main :

```powershell
powershell -Sta -ExecutionPolicy Bypass -File "outils\pipeline\watch-devis-export.ps1"
```

Un mutex global garantit **une seule instance** : le lancement manuel s'arrête tout seul si
celui du démarrage tourne déjà. Journal et empreintes restent dans `.claude/scripts/`
(dossier masqué pour Obsidian, contrairement à `outils/`).

- **L'identité de la fiche voyage avec le dossier** : `pipeline.py` la met dans le
  pré-remplissage (`fiche.page_id`, l'identifiant de la transaction HubSpot), le calculateur la garde en `sessionStorage` — donc par
  onglet, plusieurs dossiers ouverts en parallèle ne se mélangent pas — et la rend dans
  l'export. `finalisation.py` s'en sert quand ni `--fiche` ni `--page-id` n'est donné.
- **Marge basse** : plus aucun blocage (Karim, 03/11/2026, plancher de 30,5 % retiré). Le devis
  suit toute la chaîne, quelle que soit sa marge, jusqu'à la relecture de Samuel.
- **Idempotence** : empreinte SHA1 de chaque export traité dans `.claude/scripts/.devis-exports-vus`.
  Réappuyer sur le bouton sans rien changer ne réécrit pas la fiche.
- **Ce que le message WhatsApp annonce** (règle Karim, 09/09/2026) : **les devis qui tiennent**,
  pas l'historique du travail. Le journal des exports enregistre chaque clic ; la fiche
  porte ce qui a été retenu. Avant l'envoi, `elaguer_journal()` croise les deux et ne garde que
  les variantes **encore présentes sur la fiche** — un essai créé puis supprimé à la main ne
  ressort pas dans le message, et il est retiré du journal au passage. Le message ne raconte ni
  création ni suppression.
- **Notification WhatsApp** (testée le 08/09/2026) : `notif.py` poste le récap sur le chat « Devis/inventaire » via
  l'**API locale de Beeper Desktop** (`http://localhost:23373`) — appel HTTP direct, zéro token,
  aucun modèle réveillé. Deux clés à renseigner dans `.env` (`BEEPER_ACCESS_TOKEN`, jeton
  créé dans Beeper Desktop > Settings > Developer/API, et `SAMDEM_WHATSAPP_CHAT=10`). Sans
  elles, rien n'est envoyé : le message va dans `.claude/scripts/whatsapp-file-attente.jsonl`,
  et `python notif.py --vider-file-attente` le renverra plus tard. Vérifier : `python notif.py --test`.
- **Où la marge se voit** : dans le calculateur (badge « sous la cible », note « Validation
  requise »), à titre d'indication. Aucune confirmation au clic sur « Exporter JSON ».
- **Pourquoi le presse-papier et pas un webhook** : l'artefact publié tourne sous une CSP qui
  bloque tout `fetch` vers un autre hôte — il ne peut appeler aucun serveur local. Le
  presse-papier est le seul canal, et c'est déjà le geste que fait Samuel.

Les autres entrées restent disponibles :

```bash
python "outils/pipeline/pipeline.py" --exemple > dossier.json    # squelette à remplir
python "outils/pipeline/pipeline.py" dossier.json                # rapport lisible
python "outils/pipeline/pipeline.py" dossier.json --devis        # + devis rempli, ouvert
python "outils/pipeline/pipeline.py" dossier.json --json         # sortie machine
python "outils/pipeline/pipeline.py" - --devis                   # dossier.json sur stdin
```

| Option | Effet |
|---|---|
| `--fiche "NOM"` | Lit la fiche (note de la transaction HubSpot, à défaut la page Notion d'un ancien dossier) et en dérive le dossier (voir `fiche_notion.py`). |
| `--page-id <id>` | Idem, avec l'identifiant de la transaction (ou d'une ancienne page Notion), quand plusieurs fiches portent le même nom. |
| `--devis` | Écrit `donnees/Devis générés/Devis_<NOM>_<Prénom>.html` — copie du calculateur maître avec le dossier injecté — et l'**ouvre dans le navigateur, déjà rempli**. Refusé, code de sortie 4, sans contrôle préalable des mêmes valeurs et options (`pipeline.py --fiche "NOM"`, Karim 04/11/2026), si un point reste à trancher ou si le statut est STOP. |
| `--remplacer` | Regénère un devis existant, après un nouveau contrôle. L'ancien onglet reste exportable : le faire fermer. |
| `--sans-groupage` · `--deux-phases` | Écartent une mention de groupage ou de phase seule : ces mentions bloquent `--devis` tant qu'elles ne sont pas tranchées. |
| `--prefill` | En plus : `donnees/Devis générés/Prefill_<NOM>_<Prénom>.json` dans le presse-papier, à coller dans l'artefact en ligne (tablette, partage). |
| `--pas-ouvrir` | Génère le devis sans l'ouvrir. |
| `--copie-html` | Ancien nom de `--devis`, conservé pour les scripts existants. |
| `--json` | Sortie JSON (complétude, déductions, itinéraire, chemin du devis, `fiche`). |
| `--sans-itineraire` | N'appelle pas le module d'itinéraire (dossier déjà renseigné, ou hors ligne). |
| `--variante "NOM"` | Nomme la variante : pré-remplie dans le champ « Variante » du calculateur, et reprise dans le nom du fichier (`Devis_<NOM>_<Prénom>_<variante>.html`) — deux variantes d'un client ne s'écrasent plus sur disque. |
| `--sans-etapes` | Variante directe d'une fiche qui porte des sections « Étape » : arrêts ignorés, itinéraire et péage de la fiche écartés, boucle recalculée sans eux. |
| `--groupage` | Coche « Groupage ». La fiche le signale (`? groupage`), le modèle tranche. |
| `--chargement-seul` / `--dechargement-seul` | On ne fait qu'une phase (Karim, 28/10/2026) : le temps de manutention de l'autre phase est mis à 0 min dans la copie, comme un ajustement manuel. La fiche le signale (`? chargement ou déchargement seul`), le modèle tranche. Fiche : arrivée (ou départ) = même adresse, plain-pied. Copie locale seulement, sans effet sur `--prefill`. Le transport et le déplacement restent comptés. |
| `--malgre-manques` | Génère le devis malgré un champ bloquant absent (ex. étage d'arrivée, sur hypothèse de Samuel) — **jamais** sans volume ni itinéraire. Le bandeau du calculateur liste ce qui reste à saisir, péage compris. |

**Ancien dossier** (Karim, 03/11/2026). Avec `--devis`, `--copie-html` ou `--prefill`, et en mode lot, une fiche
trouvée sur une page Notion est d'abord recopiée sur sa transaction HubSpot (`fiche_hubspot.reprendre_notion()`, une
seule fois ; pour `pipeline.py`, seulement quand `SAMDEM_CRM` vaut `hubspot` ou `les-deux`), puis le dossier est
identifié par sa transaction. Sans ces options, `--fiche` lit la page sans rien écrire. Voir « Lecture de la
fiche ».

L'itinéraire est calculé automatiquement si `dossier.itineraire.km_ar` est vide.

**Arrêts intermédiaires** (Karim, 11/09/2026). Chaque section `### Étape …` de la fiche devient
un arrêt : adresse, type, étage, ascenseur, portage, `Volume déposé` / `Volume chargé`. Le
pipeline remplit dans l'ordre les sections « Étape », « Point 2 » et « Point 3 » du calculateur
(au-delà de trois, alerte). L'itinéraire écrit dans la fiche est celui **avec** arrêts. Avant
tout géocodage, la mention d'attente accolée à une adresse (« — 🟡 n° à compléter ») est retirée.

**Doublon de variante** (Karim, 11/09/2026). Le `PREFILL` porte `variantes_existantes`, lu dans
le journal `donnees/Devis générés/exports/<page>.variantes.json`. Le calculateur y ajoute les exports de
la page et du navigateur, et **bloque** l'export d'un nom déjà pris — « ⚠ Attention, variante
avec le même nom » — tant qu'on ne renomme pas la variante ou qu'on ne clique pas « Remplacer
quand même ». L'export porte alors `remplace_variante: true`.

## Les trois verdicts

- **GO** — tous les champs bloquants présents, itinéraire fiable. Le devis peut être généré.
- **GO_AVEC_RESERVES** — le devis est produit, avec en tête la liste des fragilités
  (itinéraire dégradé, adresse résolue à la commune, volume sans inventaire, incohérence
  formule/options, volume > 30 m³).
- **STOP** — un bloquant manque. Aucun devis n'est généré, et la sortie contient **une relance
  rédigée**, prête à copier dans WhatsApp. Un STOP produit un message à envoyer, jamais une
  erreur.

Avant ces trois verdicts, `--fiche` peut rendre **FICHE_A_CREER** (code de sortie 3) : aucune
fiche à ce nom, ni note « Fiche client » sur une transaction HubSpot, ni page dans l'ancienne base Notion. Le
pipeline cherche alors l'opportunité du CRM et renvoie vers `/creer-fiche-client-samdem`, source
`python "outils/pipeline/hubspot_crm.py" --description "NOM"` (`nocrm.py` en retour arrière).
**Aucun devis ne se chiffre depuis le CRM** : la fiche est créée sur HubSpot d'abord (Karim, 11/09/2026 ; sur
HubSpot depuis le 03/11/2026), sinon `finalisation.py` n'a aucune fiche où reporter le devis.
`--fiches` (lot) marque ces dossiers du même statut.

## Démontage / remontage — le barème

`demontage.py` porte le barème de Samuel (11/09/2026) : temps de démontage **plus** remontage,
par élément, pour une équipe de **2 personnes** (Karim, 06/10/2026 ; lu pour 3 avant). Chaque
ligne cochée de « Meubles à démonter / remonter » est rapprochée de l'élément le plus proche
(mots-clés, du plus spécifique au plus général) et multipliée par sa quantité (`x2`) ou son
nombre de modules. Le temps se saisit tel quel : tous les calculateurs facturent
`demontageH × 2 × taux` (constante `EQUIPE_DEMONTAGE`), quel que soit l'effectif du chantier.

- Durée écrite sur la ligne (`1h30`, `45 min`, `(45m)`) → elle fait foi, pas de barème.
- Élément au barème sans temps (chaise, cuisine, électroménager, TV…) ou hors barème → 0 h et
  🟡 dans la sortie (statut `GO_AVEC_RESERVES`) : à chiffrer à la main, jamais estimé.

```bash
python "outils/pipeline/demontage.py" "Armoire 3 portes x2" "Lit coffre double"
python "outils/pipeline/demontage.py" --bareme
```

**Champs bloquants** : volume, adresses de départ et d'arrivée, étage + ascenseur de part et
d'autre, formule, et l'itinéraire s'il est en échec sur une longue distance. Tout le reste
(email, notes, matériel, date exacte, portage — défaut 10 m) passe en réserve.

## Le dossier.json

Contrat de données unique, décrit au §2 de [[pipeline-fiche-client-devis]]. Règle absolue :
**un champ inconnu vaut `null`, jamais une valeur plausible**. C'est le `null` qui déclenche
la pastille 🟡 et alimente les manquants.

## Le calculateur est en ligne — on le remplit, on ne le recrée pas

Décision Karim du 08/09/2026. Le seul document nécessaire est l'artefact publié :

**outils/pipeline/calculateurs/calculateur-devis.html**

`outils/pipeline/calculateurs/calculateur-devis.html` en est la **source** : on édite ce fichier, puis on republie à
la même URL (Claude Code, outil Artifact, en passant l'URL). Le pipeline ne réécrit jamais ce
moteur — il en **copie** le fichier et n'y touche qu'à une ligne, `const PREFILL = null;`,
remplacée par le dossier. Le devis ouvert est donc le calculateur lui-même, déjà rempli.

| Bouton de l'artefact | Ce qu'il fait |
|---|---|
| **Charger un dossier** | Colle le JSON `samdem.devis.prefill/1` de `pipeline.py --prefill` et remplit le formulaire — voie manuelle, quand on travaille dans l'artefact en ligne. |
| **Exporter JSON** | Copie le devis au format `samdem.devis.export/1` — l'entrée de `finalisation.py`. |
| **Copier le texte** | Le récap texte d'avant, conservé pour la lecture humaine. |

**Paniers repas → Manut (Karim, 22/10/2026)** : dans le récap texte et l'export, les paniers repas
(devis et relivraison) sont fondus dans « Manutention départ » / « Relivraison · manutention
chargement », donc dans `manut_ht` et la ligne « Manut » de la fiche, plus dans le transport.
L'export porte `champs_fiche.paniers_dans = "manut"` ; sans ce champ (exports antérieurs),
`finalisation.py --ttc-cible` les remet dans `transport_ht` comme avant. Marge inchangée : les
paniers n'y sont jamais entrés.

**Location de camion → Manut (Karim, 26/10/2026)** : le « Coût camion location » sort de
`deplacement_ht` et entre dans `manut_ht` (ligne « Manut » du bloc de chiffrage de la fiche). Seul
l'export change : le récap texte garde la location dans « Frais de déplacement », et le
carburant du camion loué reste en déplacement. L'export porte `champs_fiche.location_dans =
"manut"` et `location_camion_ht`. Total HT et marge inchangés.

⚠ L'artefact est partagé par lien, et les personnes qui l'ouvrent voient une **version épinglée**,
pas la version vivante. Republier ne change donc rien pour elles tant que le partage n'est pas
repointé.

## Plusieurs devis pour un même client — les variantes

Un client peut demander deux ou trois devis (formules différentes, avec/sans piano). Chacun
s'écrit **dans son propre bloc** sur la fiche, sous un titre `🔀 <variante>` — la convention
déjà présente sur les fiches à plusieurs devis. Une variante n'écrase jamais sa voisine.

| Bouton du calculateur | Effet |
|---|---|
| **Exporter JSON** | écrit la variante **et** prévient l'équipe — cas courant, inchangé |
| **Exporter — autre variante à suivre** | écrit la variante, ne prévient pas |

Le nom de la variante est déduit du calcul (`Standard`, `Confort + piano`, `Standard + piano +
monte-meubles`) et reste modifiable dans le champ **Variante** : c'est lui qui titre le bloc.

Comment le script choisit le bloc, dans l'ordre :

1. un bloc déjà titré du même nom → il le met à jour ;
2. sinon un gabarit encore vierge → il l'adopte et lui pose son titre ;
3. sinon **le bloc historique non titré** d'une fiche déjà chiffrée → il l'adopte et le nomme
   (migration douce : pas de doublon à côté d'un devis valide) ;
4. sinon → il **crée** un bloc complet en bas de fiche, sous son titre.

Deux conséquences voulues :

- **Le CRM et la section « Itinéraires » ne sont écrits que par l'export final.** Les propriétés `sd_*` de la
  transaction et cette section de la fiche n'existent qu'en un exemplaire : elles portent le devis retenu, pas
  le dernier calculé.
- **Un seul message par client.** `donnees/Devis générés/exports/<page_id>.variantes.json` retient ce
  qui a été écrit ; à la validation, le message liste les variantes retenues et leurs prix, puis
  le journal est vidé.

```
Devis prêt à vérifier — VIGNERON Lucile
27 m³
  Confort           3 120 € TTC
  Standard          2 095 € TTC
  Standard + piano  2 830 € TTC
Transaction HubSpot :
https://app-eu1.hubspot.com/contacts/149055515/record/0-3/<id>
```

Le message part **quand Samuel valide le devis**, plus à l'export (Karim, 03/11/2026). Il porte le lien
de la transaction HubSpot, et plus celui de la fiche Notion. La transaction existe toujours à ce
moment-là : le CRM passe à l'export, et une transaction absente est créée. Lien introuvable (CRM en panne, transaction ambiguë, retour à noCRM) : le
message porte la fiche Notion en repli, sous « Transaction HubSpot introuvable, fiche Notion : », et
la sortie le signale.

## Finalisation de la fiche — `finalisation.py`

Le projet Cowork « FINALISATION FICHE SANDRINE » est devenu du code. Les règles 1 à 9 de ce
prompt sont implémentées ; le modèle n'a plus à transcrire de montants ni à poser de divisions.

**Depuis le 03/11/2026 (Samuel), elle n'écrit plus que la note « Fiche client » de la transaction HubSpot, puis le
CRM.** `note_chiffree()` compose le nouveau texte de la note (bloc de chiffrage, variantes en `### 🔀 Nom`,
section « Itinéraires » pour le devis retenu) et `fiche_hubspot.ecrire()` la crée ou modifie celle qui existe : rien n'est écrit si le texte n'a pas
changé. Plus aucune écriture dans Notion ni dans le Google Sheet : les propriétés
Notion et `proprietes()` n'existent plus, les options `--sans-sheet` et `--sans-proprietes` sont retirées. Pour un
ancien dossier, la page Notion est lue puis recopiée une fois sur sa transaction (voir « Lecture de la fiche »).

```bash
python finalisation.py --presse-papier --fiche "NOM"            # contrôle, n'écrit rien
python finalisation.py export.json --fiche "NOM" --appliquer    # pose la note de la fiche, puis le CRM
python finalisation.py export.json --fiche "NOM" --ttc-cible 2400
python finalisation.py - --page-id <id> --json                  # stdin, sortie machine
```

| Règle Cowork | Implémentation |
|---|---|
| 1 — ajustement à un TTC cible | `ajuster_ttc()` : seul le transport bouge, les autres postes sont figés. **Algèbre du calculateur**, pas celle du prompt : la base de commission du moteur inclut toute la masse salariale de route, pas seulement transport + manut + options ([[commission-devis]]). Depuis le 09/09/2026 le taux vaut 0 sur tout devis Sam'Déménage, Next Stories compris — le terme s'annule, l'algèbre ne sert plus que pour Accès Déménagement (7 %). |
| 2 — commission fondue dans Transport | Le calculateur range chaque poste dans un champ de fiche et un seul ; `verifier()` contrôle que Σ champs = Total HT et que HT × 1,2 = TTC (tolérance 1 €). Depuis le 09/09/2026 il n'y a plus de poste « Commission » sur un devis Sam'Déménage : la règle ne joue plus que pour Accès Déménagement. |
| 3 — temps de mission | `temps_fiche()` : chargement et déchargement **÷ 1,1 puis arrondis chacun à la demi-heure la plus proche** (règle Samuel du 08/09/2026, qui remplace ÷ 1,3 + ¼ h supérieur), trajet et options intacts, total arrondi à son tour. Trajet absent → 30 min. |
| 4 | Marge affichée, avec sa cible (**21 %** quand l'export porte `mission.next_stories`). Elle n'arrête plus l'écriture depuis le 03/11/2026 (Samuel). |
| 5 — désambiguïsation | `fiche_notion.chercher_fiche()` : la note HubSpot d'abord (plusieurs fiches : la seule transaction ouverte), la base Fiches Client des anciens dossiers ensuite ; à égalité sur Notion, la fiche **datée** l'emporte. |
| Classement Manut / Déplacement | **Manut** = manutention départ, arrivée, garde-meuble, points 2-3 **+ forfait trajet, trajet dépôt** (heures d'équipe, Karim 06/10/2026 ; retour chef d'équipe retiré le 21/10/2026). **Déplacement** = route longue distance, frais de véhicules (km, forfait 10 €, péage, location, hôtel, autre coût) et réservation de stationnement. Table `CHAMP_FICHE` des calculateurs. |
| 7 / 9 — monte-charge, piano | Sortis du déplacement et des options : ligne texte dédiée (« Monte-charge hors taxes » sous Déplacement, « Piano » après Formule) et cumul dans **Autres frais HT**. |
| 8 — autres frais annexes | `champs_fiche.divers` : une ligne texte par type, en bas du bloc, et cumul dans Autres frais HT. Aucun champ du calculateur ne l'alimente aujourd'hui — à injecter à la main dans le JSON si le cas se présente. |
| 10 — relecture après écriture | Le bloc est relu et recomposé : « conforme » ou la liste de ce qui diffère encore. |
| 11 — ne toucher à rien d'autre | Seules les lignes du bloc de chiffrage sont réécrites. **Dossier** n'est jamais modifié (une divergence est signalée, pas corrigée) ; Statut, Réf, Commercial, adresses ne sont pas touchés. |

### Ce que le script ne tranche pas

- **Plusieurs blocs de chiffrage sur une fiche.** Certaines fiches portent des variantes
  (« 🔀 Version Standard », devis successifs). Le script les liste et prend **le dernier** ;
  `--bloc N` choisit. Écrire dans le mauvais bloc écraserait un devis valide : le rapport
  affiche toujours le nombre de blocs trouvés.
- **Le diviseur 1,3.** Il vient du prompt maître Notion, écrit pour le calculateur Notion. Le
  contrôle affiche les temps bruts **et** les temps calculés — à valider sur le premier dossier
  réel, `--sans-division` si la division ne s'applique pas à ce calculateur.
- **Rien n'est écrit sans `--appliquer`.** Le mode par défaut affiche le bloc à écrire et le
  diff ligne à ligne avec la fiche.

### Reprise automatique après une panne (Karim, 09/10/2026)

Chaque étape (texte de la fiche, itinéraire compris, puis CRM) passe par
`reprise.executer()` : sur une **panne passagère** (réseau, délai dépassé, 5xx, 429), elle est
relancée **tout de suite, deux fois au plus**. Une erreur de données (contact ambigu, URL de Web
App changée, refus de format) n'est pas relancée : elle échouerait pareil.

- Reprise réussie : une ligne `↻ … réussi au 2e essai` dans le terminal, pas d'alerte.
- Échec persistant : **une** alerte Slack qui dit les essais faits et la commande pour rejouer
  l'étape seule, depuis l'export enregistré dans `donnees/Devis générés/exports/` :
  `finalisation.py "<export>" --appliquer --seulement crm` (étapes : `texte`, `crm`).
  `--seulement` ne renvoie jamais le WhatsApp ni l'inventaire.
- Les deux étapes sont rejouables sans doublon : le texte et l'itinéraire relisent la fiche
  avant de réécrire (rien n'est posé si le texte n'a pas changé), les CRM retrouvent le dossier
  (HubSpot garde en mémoire ce qu'il vient de créer, son index de recherche ayant quelques
  secondes de retard). Le message d'équipe n'est jamais envoyé deux fois pour un même devis
  (fiche, variante, prix) : registre `.claude/scripts/messages-equipe-envoyes.jsonl`.
- Le texte de la fiche en échec arrête la finalisation avant tout envoi : la commande rendue
  rejoue alors toute la finalisation (`--whatsapp` compris).

Plan du projet : `reprise-auto/plan-projet.md`.

## Garanties

- Le fichier maître `outils/pipeline/calculateurs/calculateur-devis.html` **n'est jamais modifié** par le pipeline :
  `--devis` en fait une copie et n'injecte le dossier que dans la copie. L'ancre attendue est
  `const PREFILL = null;` — si elle disparaît du maître, la génération s'arrête net au lieu de
  produire un devis vide.
- Aucune valeur n'est inventée. Un effectif non déductible s'affiche `?` au lieu d'être deviné.
- Le calcul de prix reste entièrement dans le moteur JavaScript du calculateur : le pipeline
  ne produit que des **entrées**, jamais un résultat chiffré.

## Lecture de la fiche — `fiche_notion.py` et `fiche_hubspot.py`

**Depuis le 03/11/2026 (Samuel), la fiche est une note « Fiche client » sur la transaction HubSpot**, une seule,
modifiée à chaque changement (04/11/2026) ; plus aucune fiche n'est créée dans Notion. Son texte garde les lignes que lisait
`fiche_notion.lire_corps` (`### Titre`, `- [x] Case`, `- Puce`, lignes libres) : `parser_corps` et ses règles n'ont
pas changé, seule la source a changé. Le dossier est identifié par l'identifiant de transaction (que des chiffres),
qui voyage dans `fiche.page_id` de l'export là où voyageait l'identifiant de page Notion. `fiche_notion.lire_corps`,
`lire_fiche` et `chercher_fiche` aiguillent vers `fiche_hubspot.py` quand l'identifiant est celui d'une transaction ;
`chercher_fiche` cherche la note d'abord, la base Notion ensuite. Modèle de la trame :
`.claude/skills/creer-fiche-client-samdem/references/modele-fiche.md`.

La fiche est un **modèle dupliqué** : sa trame ne varie pas (`### Départ :`, `Étage avec ascenseur : 3`, cases
`- [x]`). La faire lire par le modèle revenait à payer des milliers de tokens pour extraire vingt champs d'un
document structuré. Le script lit la note en **HTTP direct** (clé HubSpot) et rend le `dossier.json`.

```bash
python "outils/pipeline/fiche_notion.py" "PLANCHAIS Benoit"      # dossier.json (note HubSpot, sinon page Notion)
python "outils/pipeline/fiche_notion.py" --page-id <id>          # transaction ou page Notion, si le nom est ambigu
python "outils/pipeline/fiche_notion.py" --url <url Notion>      # ancien dossier
python "outils/pipeline/fiche_notion.py" "PLANCHAIS" --texte     # corps brut, si le parseur échoue
python "outils/pipeline/fiche_notion.py" --audit 200             # corps vs propriétés, sur la base Notion
python "outils/pipeline/fiche_hubspot.py" --chercher "NOM Prénom"    # [identifiant de transaction, titre]
python "outils/pipeline/fiche_hubspot.py" --lire <transaction>       # la note : client et lignes
python "outils/pipeline/fiche_hubspot.py" --creer corps.md --nom "NOM" --prenom "Prénom" --tel 06... \
    --email x@y.fr --commercial Samuel --depart "..." --arrivee "..." --date 2026-11-20
python "outils/pipeline/fiche_hubspot.py" --reprendre <id de page Notion>   # ancien dossier : sa fiche vers sa transaction
```

`--creer` retrouve ou crée le contact et la transaction (souvent créés par le site), puis pose la fiche ; il rend
`transaction`, `url` et `detail`, et sort en code 1 sans rien écrire si le contact ou la transaction sont ambigus.
Le commercial s'écrit dans une section `### Suivi :` quand le corps n'en porte pas. Corriger une fiche : `--lire`,
corriger les lignes, `--creer` avec les mêmes options ; la note existante est modifiée, aucune autre n'est créée.

### Ancien dossier : une seule recopie

Un ancien dossier garde sa page Notion en lecture seule, et la chaîne n'y écrit plus. `pipeline.py --devis` (ou la
finalisation, à défaut) appelle `fiche_hubspot.reprendre_notion()` : le corps de la page est recopié dans une note
de la transaction du dossier, retrouvée ou créée par `hubspot_crm.assurer_transaction()`. Une seule fois : une
transaction qui a déjà sa note la garde, elle est plus récente. Ensuite le dossier ne connaît plus que HubSpot.
`inventaire_auto.py` lit encore les fichiers de l'ancienne page (`lien_fiche_notion` de la transaction). Transaction
introuvable ou ambiguë : rien n'est écrit, la finalisation alerte sur Slack et donne la commande pour rejouer avec
`--page-id <id de transaction>`.

### Le corps fait foi

Sur HubSpot, le corps est la note : la saisie et les corrections se font dans son texte libre, le volume au premier
chef. Le contact (nom, téléphone, e-mail) et les propriétés de la transaction (commercial, référence, date de
déménagement, axe de groupage) ne complètent que le contexte, et il n'y a plus de comparaison corps/propriétés :
`divergences` et `replis` restent vides. Pour un ancien dossier encore lu sur sa page Notion, l'ancienne règle
vaut : les propriétés Notion ne servent que de repli quand le corps est muet, et toute divergence est remontée dans
`_meta.divergences`, affichée par le pipeline, et **jamais tranchée en silence** : le corps est retenu, l'écart est
signalé.

Le script lit **tout le corps**, systématiquement : il n'y a pas de liste de « lignes à surveiller » à tenir à jour,
et une correction manuelle de Samuel dans n'importe quelle ligne est captée par construction.

### Ce que le script ne tranche pas

| Champ `_meta` | Contenu |
|---|---|
| `divergences` | corps ≠ propriété, avec les deux valeurs. Le corps est retenu. Vide pour une fiche HubSpot. |
| `replis` | champ absent du corps, repris de la propriété. Vide pour une fiche HubSpot. |
| `signaux` | mentions repérées, non décidées : groupage, garde-meuble, monte-meuble, déchetterie, piano, week-end, Nextories. Les tournures négatives (« pas de stockage ») sont écartées. |
| `alertes` | les lignes 🟡 de la fiche, à relayer dans le récap d'appel. |
| `notes` | la section Notes, seule zone réellement non structurée. |
| `non_parse` | lignes cochées non reconnues dans une section structurée — à lire. |
| `deja_chiffre` | la fiche porte déjà un chiffrage (devis antérieur). |

### Points de vigilance du parseur

- **Sectionnement obligatoire.** Une ligne des Notes (« Départ : stationnement facile ») ne
  doit jamais être lue comme l'adresse de départ. Le découpage se fait sur les titres `###`,
  jamais sur un `grep` de tout le corps.
- **Portage** : le calculateur attend un total (entrée + intérieur), la fiche donne les deux
  composantes — sauf quand elle écrit « portage total mentionné : X », auquel cas additionner
  doublerait la distance. Le script détecte le cas.
- **Itinéraire relu dans le corps** : les chiffres écrits à la main ne portent pas les
  drapeaux du module. `longue_distance` et `peage_requis` sont donc recalculés depuis les
  seuils de `calcul_itineraire.py` (2 h et 19h06), sinon un A/R de 14 h perdrait
  silencieusement le taux conducteur à 20 €/h.
- **Adresses et portages** se comparent par jeu de mots ou par somme, pas caractère par
  caractère : « Cenon (33150) — 20 Av. X » et « 20 Av. X, 33150 Cenon » ne sont pas une
  divergence.

## Estimation de volume — `volume.py`

Quand une fiche a un inventaire mais pas de volume, on ne demande plus le volume au client :
on l'estime. Le pipeline le signale par le statut **`ESTIMATION_REQUISE`**.

Le travail est coupé en deux : le modèle identifie les objets et produit un JSON (skill
`/estimer-volume-samdem`), le script applique les coefficients et somme. L'arithmétique n'est
jamais refaite de tête.

```bash
python "outils/pipeline/volume.py" inventaire.json            # rapport
python "outils/pipeline/volume.py" inventaire.json --detail   # ligne par ligne
python "outils/pipeline/volume.py" --references               # volumes moyens connus
```

**Le volume retenu pour le devis est le CONSERVATEUR** (décision Karim 08/09/2026). Standard
et longue distance restent calculés, à titre de comparaison seulement.

Règles portées par le script : marges +6/+10 % (dimensions fournies), +10/+20 % (sans
dimensions), démonté ×1,15/1,25, géométrie irrégulière ×1,3/1,5, objet pro-atypique-fragile
×1,1/1,3, élément incertain +20 % en conservateur, marge globale +10 %, arrondi entier.
La **règle de la colonne neutralisée** (arbres et pots ≥ 40 cm : emprise du feuillage ×
hauteur totale, jamais le volume du pot) est implémentée et vérifiée sur l'exemple validé —
olivier 150×150×250 → 7,31 / 8,44 m³.

**Saturation de palier** : un conservateur qui atteint la capacité nominale d'un palier
(15/20/30 m³) déclenche la recommandation du palier supérieur — le remplissage réel n'égale
jamais la capacité théorique.

⚠ **Table des volumes de référence à valider.** Le prompt maître renvoie aux « dimensions
moyennes standard du métier » sans les chiffrer. Le dictionnaire `REFERENCES` de `volume.py`
est une **proposition non validée** : seuls les trois cartons viennent du prompt. Ces valeurs
pilotent le volume de tout objet cité sans dimensions, donc le prix.

## Archivage — Google Sheet et Notion (retiré le 03/11/2026)

**Retiré le 03/11/2026 (Samuel) : la chaîne n'écrit plus ni dans le Google Sheet ni dans Notion**, propriétés typées
comprises. Les chiffres du devis vivent sur HubSpot, dans les propriétés `sd_*` de la transaction et dans sa note
« Fiche client » ; le rapport hebdo les y lit (code repris par une autre personne, voir
`sans-notion/correspondance-rapport.md`). Historique : du 09/09/2026 au 03/11/2026, chaque export écrivait la fiche
Notion et une ligne par devis (clé `réf. de la fiche · variante`) dans le Google Sheet. Le Sheet n'est plus alimenté.

`export.py` garde ses voies manuelles (`--sheets`, `--notion`, `--test`), que la chaîne n'appelle plus ; sa
fonction `ligne_sheet()` ne sert plus qu'à `finalisation.ligne_archive()`, qui construit la ligne de dossier du CRM.

### Configuration — `.env`

Cherché dans cet ordre : la variable d'environnement `SAMDEM_ENV`, puis `outils/pipeline/.env`
(emplacement retenu), puis `.env`. Un fichier encore rempli de placeholders
`REMPLACER` est ignoré au profit du suivant. Même convention que `nocrm.env` :

```
SAMDEM_SHEETS_URL=https://script.google.com/macros/s/.../exec    # Web App Apps Script : repli e-mail des alertes, envois du rapport
SAMDEM_SHEETS_TOKEN=<chaîne aléatoire, identique à celle du script>
NOTION_TOKEN=ntn_xxx                                              # lecture des anciens dossiers
```

### Le script Apps Script

`apps_script_devis.gs` reste déployé pour les envois du rapport et pour le repli e-mail des alertes (voir « Alertes
d'incident »). Mise en place d'origine : Extensions → Apps Script, coller le fichier, remplacer `CHANGER_MOI` par une
chaîne aléatoire longue (le jeton partagé), Déployer → Nouveau déploiement → Application web, exécuter en tant que
soi-même, accès « Tout le monde », puis copier l'URL `/exec` dans `SAMDEM_SHEETS_URL` et le jeton dans
`SAMDEM_SHEETS_TOKEN`. L'accès « Tout le monde » signifie que l'URL seule permet d'agir : c'est pour cela que le
jeton existe. Ne pas publier l'URL, et la régénérer si elle fuit.

### Notion : lecture seule

L'intégration interne Notion reste autorisée sur la base « 🗂️ Fiches Client (base) » : elle sert à lire les anciens
dossiers (fiche et fichiers d'inventaire), plus à y écrire. `export.py --test` vérifie la clé et l'accès.

## Itinéraire reporté sur la fiche

La section « Itinéraires : » de la fiche (`Kilomètres A/R`, `Temps A/R`, `Péage HT`) est
remplie par `finalisation.py`, dans la même version de la note que le bloc de chiffrage (`note_chiffree()`). Les valeurs ne sont
pas recalculées : elles ont été posées dans le calculateur au pré-remplissage et reviennent
telles quelles par l'export.

Ces trois lignes vivent **hors** du bloc de chiffrage, donc hors de portée de `composer()` —
d'où une passe dédiée, `patcher_itineraire()`. Deux règles :

- **On ne crée jamais ces lignes.** Une fiche qui n'a pas la section suit un autre modèle ;
  inventer un emplacement ferait plus de dégâts que de la laisser vide.
- **Seule la variante retenue écrit**, comme le CRM : la section n'existe qu'en un
  exemplaire, elle porte le devis retenu, pas une variante intermédiaire.

Le format écrit est celui que `fiche_notion.py` sait relire — `256 km`, `4h30`, `0,00 € HT` —
pour que la fiche reste sa propre source au devis suivant. Un péage à 0 est écrit : c'est ce
que le devis facture. S'il aurait dû y en avoir un, c'est le devis qui est faux, pas la fiche.

## Pipeline noCRM — `nocrm.py`

Dernière étape de la chaîne : une fois le devis parti, le dossier est **enrichi** puis avance
dans le tunnel de vente. `finalisation.py --appliquer` l'appelle tout seul.

**Retour arrière (03/11/2026).** `SAMDEM_CRM=nocrm` ne rétablit pas l'écriture d'une fiche dans Notion : le retour
arrière noCRM ne peut plus écrire de fiche. `finalisation.py` pose la note sur HubSpot quel que soit le CRM, et
l'opportunité noCRM n'est qu'enrichie du corps de cette fiche (`corps_notion()` lit la note HubSpot, ou la page
Notion d'un ancien dossier).

### Les quatre gestes, dans cet ordre (Karim, 10/09/2026)

| # | Geste | Détail |
|---|---|---|
| 1 | **Description** | le corps de la fiche (note HubSpot, ou page Notion d'un ancien dossier) est recopié dans le texte de l'opportunité |
| 2 | **Montant** | `amount` reçoit le **TTC** ; plusieurs devis sur la fiche → **le plus élevé** |
| 3 | **Rappel** | statut « En attente », échéance **J+2**, note « à relancer » |
| 4 | **Colonne** | le déplacement, et lui seul, reste la dernière étape |

**Pourquoi la description.** Le CRM cessait d'être une coquille dès qu'on voulait y travailler :
tout le dossier était dans Notion, l'opportunité ne portait qu'un nom. Le commercial y lit
désormais l'ensemble — accès, volume, matériel, chiffrage — sans ouvrir un second outil.
L'en-tête contact généré par noCRM (avant le `---`) est **conservé**, tout ce qui suit est
remplacé : rejouer un export ne duplique donc rien. Une description **sans** `---` est gardée
entièrement et le corps s'ajoute dessous — une note tapée à la main par un commercial n'est
jamais détruite. Le rendu vise le copier-coller humain : `###` et puces retirées, cases
`[x]` gardées, espaces doubles réduits, traits de séparation rendus en `______` (jamais `---`,
qui couperait la description au passage suivant). **noCRM n'affiche aucune ligne vide**
(Karim, 11/09/2026) — ni vraie, supprimée à l'enregistrement, ni portée par un espace insécable,
rendue en retrait : la séparation passe par les titres de section, en gras Unicode entre deux
filets (`━━ 𝗗𝗘́𝗣𝗔𝗥𝗧 ━━`, fonction `gras()`).

**Pourquoi le plus élevé des TTC** (Karim, 10/09/2026). Une fiche porte souvent plusieurs
variantes (Standard et Confort, avec et sans piano). C'est le potentiel du dossier qui doit
apparaître dans le tunnel ; l'arbitrage entre variantes se fait à la signature, pas à
l'ouverture de l'opportunité. Les
montants sont lus sur les lignes `Prix Total : … € TTC` du corps — la ligne `Prix Total HT :`
ne peut pas être confondue, le deux-points doit suivre `Total` immédiatement.

**Pourquoi le report au lundi.** J+2 tombe un samedi ou un dimanche une fois sur trois. Un
rappel posé le week-end est vu le lundi au mieux, perdu au pire : il est donc **reporté au
lundi suivant**. Les jours fériés ne sont pas traités — faute de calendrier fiable, et parce
qu'ils ne coûtent qu'un jour de décalage.

**Rappel déjà posé avec une heure.** Un rappel créé à la main par un commercial porte une
heure (`remind_time`) ; noCRM fige alors sa date et ignore une nouvelle `remind_date` envoyée
seule — avec un 200. `enrichir()` le voit à la relecture et renvoie la date **avec l'heure
existante** (le rappel passe à J+2, à l'heure choisie par le commercial). Effacer l'heure n'est
possible qu'en repassant le lead en `todo` puis en `standby` (`null` et `""` sont ignorés).

**Opportunité introuvable → elle est créée.** Titre `NOM Prénom`, corps de la fiche, montant, et
affectation au **commercial nommé sur la fiche** (repli sur le compte principal, résolu par
son e-mail). Elle suit ensuite les mêmes étapes. Un dossier chiffré ne reste plus hors du CRM.
La création n'a lieu que s'il y a **zéro** candidat : un appariement ambigu ne fabrique jamais
un doublon.

```bash
# voir ce qui serait recopié, et quel TTC serait retenu — sans rien écrire
python "outils/pipeline/nocrm.py" --corps --page-id <id de transaction ou de page Notion>
```

| Destination | Quand |
|---|---|
| **Devis envoyé** (`638965`) | par défaut |
| **Trajets Axe Paris** (`730698`) | un bout du trajet est en Île-de-France (75, 77, 78, 91–95) |

Un déplacement vers l'axe Paris **pose aussi le tag de groupage**, dans le sens du trajet :
`groupage:bordeaux-paris` (départ hors IdF) ou `groupage:paris-bordeaux` (départ en IdF) —
la convention déjà en place, celle sur laquelle `/etat-axe-paris` filtre. Le tag est **ajouté**
aux tags existants, jamais substitué : l'API remplace la liste entière, envoyer le seul tag de
groupage effacerait les autres.

La colonne axe Paris est **en aval** de « Devis envoyé » dans le tunnel : elle dit les deux
choses à la fois, devis parti *et* à apparier en groupage. Un dossier déjà en aval (axe Paris,
Négociation) n'est jamais **ramené en arrière** par un avenant.

```bash
python "outils/pipeline/nocrm.py" --etapes                                  # les colonnes
python "outils/pipeline/nocrm.py" --chercher "VIGNERON Lucile" --tel 06...  # trouve, n'écrit rien
python "outils/pipeline/nocrm.py" --devis-envoye "NOM Prénom" --tel 06... --page-id <id> --appliquer
python "outils/pipeline/nocrm.py" --lead <id> --etape <id> --appliquer      # déplacement direct
```

Sans `--page-id`, l'opportunité est **seulement déplacée** : pas de corps de fiche à recopier,
donc ni description ni montant. `finalisation.py` le passe toujours.

Sans `--appliquer`, le script dit ce qu'il ferait et ne touche à rien. `--sans-crm` coupe
l'étape dans `finalisation.py`.

### Comment on est sûr de bouger le bon dossier

⚠ **L'API v2 de noCRM n'a pas de recherche serveur.** `?query=`, `?search=` et `?q=` sont
acceptés puis **ignorés** : ils renvoient les leads les plus récents. Faire confiance au
premier résultat déplacerait un dossier au hasard. On pagine donc (8 × 100 leads, triés par
date de mise à jour) et on filtre en local. Même piège sur `?step_id=`, ignoré lui aussi —
le filtre qui marche est `?step=<id ou nom>`.

L'appariement se fait sur le **téléphone d'abord**, puis l'e-mail, puis le nom. Le numéro vit
dans la description du lead (`Téléphone: 06…`), pas dans un champ dédié : on cherche donc dans
le texte entier, sur les 9 derniers chiffres (insensible aux points, espaces, `+33`).

Quatre garde-fous, parce qu'une opportunité déplacée au hasard coûte plus cher qu'un dossier
oublié :

| Situation | Ce que fait le script |
|---|---|
| Apparié par téléphone ou e-mail | enrichit et déplace |
| Apparié par le **nom seul** | **n'écrit rien** — signale le lead et donne la commande de rattrapage complète (`--devis-envoye … --page-id … --sur-le-nom --appliquer`) |
| Plusieurs candidats de même rang | **n'écrit rien** — rend la liste, l'humain tranche |
| Aucun candidat | **crée** l'opportunité, puis l'enrichit et la déplace |

Un homonyme enrichi avec le devis d'un autre client serait pire qu'un dossier oublié : c'est
pourquoi les deux cas ambigus n'écrivent toujours rien, création comprise.

Et après chaque `PUT`, le lead est **relu** : « fait » n'est affiché que si la description, le
montant, le rappel, la colonne et le tag y sont réellement. Un 200 ne prouve rien sur cette
API — elle accepte un champ qu'elle ne connaît pas, répond 200, et l'ignore.

Le seuil automatique est `RANG_MINIMUM_AUTO` dans le module. En ligne de commande,
`--sur-le-nom` autorise l'appariement faible — l'humain a vu le candidat et l'assume. Le
rattrapage recopie alors dans l'en-tête du lead le téléphone et l'e-mail de la fiche qui lui
manquent (`Téléphone (fiche Notion): …`) : le passage suivant l'apparie par téléphone.
`--lead/--etape` ne fait que déplacer la colonne — ni description, ni montant, ni rappel.

Config : `~/.claude/nocrm.env` (`NOCRM_BASE_URL`, `NOCRM_API_KEY`), ou `outils/pipeline/nocrm.env`.

## Pipeline HubSpot — `hubspot_crm.py` (migration, 06/10/2026)

Même contrat que `nocrm.avancer_dossier` (`(ok, message)`, ne lève jamais), appelé par
`finalisation.py` selon l'interrupteur **`SAMDEM_CRM`** (fichier général `outils/crm.env`, variable
d'environnement ou option `--crm`) : `nocrm` (défaut), `hubspot`, `les-deux` (transition).
**Retour arrière** : `SAMDEM_CRM=nocrm` ; pour le code, l'étiquette git `avant-hubspot`.

Les gestes, dans l'ordre : contact (téléphone, puis e-mail, jamais le nom ; créé s'il manque,
complété sans écrasement) → transaction (identifiant de transaction du dossier, lu directement par `trouver_transaction` ; sinon lien de la fiche Notion d'un ancien dossier, puis réf. `CLI-nnn`, puis
seule transaction ouverte du contact, puis seule transaction ouverte **sans contact** au nom du
client — cas d'une saisie manuelle, 09/10/2026 ; créée sinon) → **chiffrage réécrit** (propriétés `sd_*`,
`amount` en HT = le devis le plus cher de la fiche, D1/D2) et **suivi complété** (adresses,
date, lien, réf., commercial, `entite`) → plus de note : depuis le 03/11/2026,
`avancer_dossier` n'écrit plus la note, c'est la finalisation qui pose la note « Fiche client »
(`fiche_hubspot.ecrire()`), avant le CRM ; une seule note, créée si elle manque, modifiée sinon
(Karim, 04/11/2026), rien d'écrit si le texte n'a pas changé. La propriété `sd_type_devis` (« Type de devis »)
vaut **Indicatif** si le devis a été généré par `pipeline.py --indicatif`, **Ferme** sinon
(09/10/2026) : le drapeau passe par l'en-tête `fiche` du pré-remplissage, que le calculateur
recopie dans son export → plus de tâche « Relancer » depuis le 03/11/2026 (`POSER_TACHE_RELANCE`, personne ne la lisait ; `relances-quotidiennes` lit encore `remind_date`, à revoir s'il reprend) → étape
« Devis en révision » pour tout dossier, groupage compris (C-041, 30/10/2026) : Samuel envoie le
devis, puis passe lui-même en « Devis envoyé », ou en « Demandes groupage » sur l'axe
Île-de-France (le compte rendu le rappelle). Un nouveau devis sur un dossier déjà envoyé le
ramène en révision (Karim, 30/10/2026). Signé/Perdu ne bougent pas. Ambiguïté (deux contacts, deux transactions ouvertes) : aucune écriture.

**Formats** : chaque valeur passe par le schéma réel du portail (type, liste fermée, propriété
masquée ou en lecture seule) ; ce qui ne colle pas n'est pas écrit et figure dans le compte
rendu. `sd_saisie_json` n'est jamais touché (saisie de l'outil de Ben, autres clés).

**E-mail jamais bloquant** (Karim, 08/10/2026) : absent, `🟡 Information manquante` ou mal formé,
il est omis (`email_valide()`), pas refusé — le contact est retrouvé ou créé au téléphone, le reste
de l'étape s'écrit et le compte rendu dit « e-mail absent de la fiche, contact écrit sans ». Une
fois l'e-mail ajouté à la fiche, relancer `--export … --appliquer` : le contact est complété.

```bash
python outils/pipeline/hubspot_crm.py --test                       # clé, étapes, propriétés du mapping
python outils/pipeline/hubspot_crm.py --export "donnees/Devis générés/exports/<fichier>.json"   # simulation
python outils/pipeline/hubspot_crm.py --fiche --page-id <id>       # fiche seule : contact + transaction, sans note (simulation)
# ajouter --appliquer pour écrire
```

### Un seul interrupteur pour toute la boîte à outils — `crm.py`

`SAMDEM_CRM` du fichier général **`outils/crm.env`** décide pour tous les outils, workflows
autonomes compris (leur `lib/crm.py` remonte jusqu'à `outils/`). Aucun fichier propre à un outil
n'entre en jeu (Karim, 06/10/2026). Retour arrière de tout : `SAMDEM_CRM=nocrm`. `les-deux` écrit dans les deux CRM mais **lit** noCRM.

| Outil | Sur HubSpot |
|---|---|
| `finalisation.py` | `hubspot_crm.avancer_dossier` (voir plus haut) |
| `gros_dossiers.py`, `relances-quotidiennes/relances.py` | Devis envoyé + Relance + Demandes groupage ; rappel = 1re tâche ouverte ; lien = la transaction |
| `pipeline.py` (+ clone Nextories) | fiche absente → transaction trouvée par téléphone, e-mail ou nom |
| `inventaire_auto.py` | pièces jointes des notes de la transaction, puis ses notes libres |
| `Groupage/collecte.py`, `crm_groupage.py` | signées dont l'axe de groupage est Bordeaux ↔ Paris ; l'activité devient une note (le CRM d'un plan déjà validé est gardé) |
| `reporting/collecte.py` | « Visites fixées » → étape « Qualification / RDV », historique `dealstage` |

Les outils lisent une transaction HubSpot **au format d'une opportunité noCRM** (`hubspot_crm.leads()`
& co.) : leurs règles métier n'ont pas bougé. Dernière activité = dernière note/tâche, ou
`derniere_activite_nocrm`, jamais la modification en bloc du jour d'import (05/10).
Reprise ponctuelle à lancer une fois par Samuel : `python outils/hubspot/reprise_activite_nocrm.py`
(simulation) puis `--appliquer` — dernière activité noCRM + rappels en retard non importés.

## Routine « Devis envoyé Hubspot » — `devis_envoye.py` (Karim, 03/11/2026)

Tous les jours à 8 h et 14 h, la tâche planifiée locale `devis-envoye-hubspot` lit les mails de
Sandrine (`secretariat@`, Samuel en copie) et de Samuel (Sandrine en copie), adressés hors de
l'entreprise, avec un PDF « Devis … » joint, et les passe au script. Un transfert interne ou un
rappel sans PDF ne compte pas. Le modèle ne fait que cette lecture : le connecteur Gmail lui est
réservé. Tout le reste est dans le code.

- **Rapprochement** : adresse du destinataire → contact → transactions ; sinon nom du PDF →
  nom de la transaction. Tous les mots de l'un doivent être dans l'autre : un prénom commun ne
  suffit pas. Sur les 14 mails contrôlés le 03/11, 2 clients n'avaient pas de contact à cette adresse.
- **Déplacement** : seule une transaction en « Devis en révision » bouge, et seulement si le mail
  est postérieur à son entrée en révision. Vers « Demandes groupage » si le trajet touche
  l'Île-de-France ou si la case Groupage est cochée, quel que soit l'axe ; vers « Devis envoyé » sinon.
- **Rien ne bouge** : déjà passée ou mail plus ancien, en silence ; aucune transaction, plusieurs en
  révision, ou pas encore en révision : alerte Slack, une seule fois par mail.
- **Registre** : `.claude/scripts/devis-envoye-hubspot.jsonl` (hors git, noms de clients). Une
  panne de HubSpot ne journalise rien : le passage suivant reprend les mêmes mails.

```bash
python outils/pipeline/devis_envoye.py --preparer                  # requête Gmail, messages déjà traités
python outils/pipeline/devis_envoye.py --mails F.json              # simulation
python outils/pipeline/devis_envoye.py --mails F.json --appliquer  # déplace, journalise, alerte
```

Tâche locale, et non routine cloud, car la clé HubSpot reste dans `.env` : elle
tourne quand l'application Claude est ouverte, et un passage manqué repart au lancement suivant.
Schéma et règles : `crm-manager/F4 - Workflows/registre-des-workflows.md`.

## Devis PDF automatique — `devis_auto.py`

Décision Karim du 02/11/2026, revue le 03/11/2026 : **chaque clic sur « Exporter JSON » produit le PDF
du devis, et les coûts de l'export font foi**. Même si le prix n'a pas bougé : c'est la version
officielle. Le PDF reste en local dans `donnees/Devis SamDem\` et attend la relecture de Samuel
(section suivante). Une fois validé, il rejoint HubSpot et le message d'équipe en donne le nom. Il part
ensuite au client, envoyé par Sandrine depuis son adresse (brouillon préparé par Claude sur demande seulement : skill `devis-pdf-samdem`, § 7). « Exporter, autre variante à suivre » ne produit rien :
tous les PDF sortent au dernier export. Le script écrit la même spec que le skill `devis-pdf-samdem`
(`donnees/Devis SamDem\specs\`), depuis l'export (montants, volume, équipe, matériel) et la
fiche (client, adresses, date, accès, options, inventaire), puis appelle
`outils/pipeline/devis-pdf/generer_devis_pdf.py`. `brouillon_envoi.py` relit cette spec telle quelle.

- **Numéro** : le plus haut du dossier des devis + 1. Un devis fait à la main doit donc y être rangé.
  Tant qu'il n'est pas validé, une correction garde son numéro et remplace son PDF ; après validation,
  un nouveau devis prend un nouveau numéro.
- **Plusieurs variantes** : un PDF et un numéro par variante annoncée, retrouvée dans les exports.
- **Reste à la main** (motif donné à la relecture) : relivraison, étape
  intermédiaire, chargement ou déchargement seul, accès avec 🟡, montants qui ne retombent pas sur
  l'export.
- **Inventaire** : liste de 10 lignes au plus dans le devis, sans PDF séparé. Sinon « Voir inventaire
  <n°> », et `inventaire_auto.py` reprend le même numéro. Liste écartée si elle est trop libre ou
  cite quelqu'un de l'équipe (note interne). Case « Pas d'inventaire » cochée et aucune liste : aucun
  renvoi sous le transport (`sans_inventaire`, Karim, 04/11/2026).
- **Formule Standard** : ligne formule à 0 € sur le PDF, son montant passe dans « Forfait manutention »
  (Karim, 04/11/2026). L'export et la note de la fiche gardent le détail du calculateur.
- **Dossier de Christophe** (`regles.dossier_christophe` : commercial, source du volume ou « visite
  de Christophe » dans les notes) : le devis écrit « Volume estimé lors de notre visite », aucun
  inventaire n'est généré ni envoyé. `inventaire_auto.py --forcer` reste possible sur demande.
- **Aucune trace de préparation** (Karim, 03/11/2026) : pastille, émoji, « temps à chiffrer », temps
  d'options ou nom de variante sont retirés des options, et `generer_devis_pdf.py` refuse une spec qui en
  contient encore : le PDF reste alors à produire à la main, avec une alerte Slack.
- **Notes de la fiche** : internes, jamais sur le devis (Karim, 02/11/2026), qui reste le modèle
  existant, sans consigne ni condition propre au dossier.
- **« À vérifier avant envoi »** à la relecture et dans le message : adresse à confirmer, date à relire, téléphone ou
  e-mail manquant.
- **Panne** du générateur : motif donné à la relecture, alerte Slack.

```bash
python outils/pipeline/devis_auto.py "<export.json>" --sortie "<dossier d'essai>"   # sans envoi
```

## Relecture et validation — `validation_devis.py`

Décision Karim du 03/11/2026 : **rien n'arrive sur HubSpot ni à l'équipe avant que Samuel ait relu et validé**. Le
veilleur tourne sans modèle ; il note donc l'état du dossier dans
`donnees/Devis générés/validation/<page_id>.json`, et Claude fait le reste dans sa session
(skill `calcul-devis-samdem`, § 13 bis) :

1. après `pipeline.py --devis`, Claude lance `--attendre` en arrière-plan, et reprend la main dès que
   l'export est prêt, inventaire compris (3 minutes d'attente au plus pour lui) ;
2. il présente le PDF du devis et l'inventaire, avec le contrôle du script : le PDF porte-t-il bien
   le TTC de l'export et son numéro ? ;
3. il donne une sélection à Samuel : valider, ou corriger ;
4. validé : `--valider` joint le devis et, si le dossier en a un, l'inventaire à la transaction, chacun
   dans sa note (`/Devis clients` et `/Inventaires clients` sur HubSpot), puis envoie le message d'équipe
   et l'inventaire sur WhatsApp ;
5. à corriger, le texte (cas courant, les calculs étant approuvés en amont) : Claude modifie la spec du PDF, `--regenerer` refait le PDF sous le même numéro, et la relecture repart ;
6. à corriger, le chiffrage : `--refuser`, puis `reprendre_devis.py`, un nouvel export, et la boucle repart.

```bash
python outils/pipeline/validation_devis.py --attendre            # rend la main au prochain export prêt
python outils/pipeline/validation_devis.py --liste               # « devis à valider »
python outils/pipeline/validation_devis.py --valider --page-id <id> [--variante "Standard"]
python outils/pipeline/validation_devis.py --regenerer --page-id <id> --motif "adresse fausse"   # après correction de la spec
python outils/pipeline/validation_devis.py --refuser --page-id <id> --motif "prix à revoir"
python outils/pipeline/validation_devis.py --ajouter-pdf "<pdf>" --page-id <id> --ttc 1800   # PDF fait à la main
```

- **Export sans session Claude ouverte** : l'état attend. « devis à valider » le ressort (`--liste`).
- **Correction de texte** : un PDF qui ne porte plus le TTC de l'export n'est pas importé. Un nouvel export refait
  la spec depuis la fiche : les corrections faites remontent dans `corrections_perdues`, à refaire. Une adresse,
  une date ou un téléphone se corrige donc aussi sur la fiche et le CRM.
- **Garde-fou** : un PDF dont le TTC ou le numéro ne correspond pas à l'export n'est pas importé,
  sauf `--forcer`. Une correction dont le PDF échoue retire l'ancien PDF de la relecture : un devis
  périmé ne peut pas être validé.
- **Rejouable** : un fichier déjà joint à la transaction ne l'est pas deux fois. Panne HubSpot : alerte
  Slack, le dossier reste à valider, aucun message ne part ; relancer `--valider`.
- **Beeper fermé à la validation** : la validation reste acquise, message et inventaire attendent dans
  la file WhatsApp, alerte Slack, puis `notif.py --vider-file-attente`.
- **Inventaire encore en préparation à la validation** : il rejoint la transaction et l'équipe seul, dès qu'il est prêt.
- **Dossier sans inventaire à importer** (Christophe, liste courte dans le devis, moins de 10 m³ sans
  PDF, rien trouvé) : seul le devis part.

## Inventaire automatique — `inventaire_auto.py`

Décision Karim du 18/09/2026, revue le 03/11/2026 : **à l'export**, la chaîne cherche l'inventaire du
client et, s'il existe, le met au propre avec le skill `outils/pipeline/Prod_inventaires/`, pour que Samuel
le relise avec le devis. **À la validation**, il rejoint la transaction HubSpot, puis la **même
conversation** (« Devis/inventaire ») juste après le message. Sans relecture en cours (rattrapage à la
main, dossier déjà validé), il part tout de suite.

`finalisation.py` lance le script **détaché** (arrière-plan). Une mise en forme par le modèle prend jusqu'à une minute : le
veilleur du presse-papier ne doit pas rester aveugle pendant ce temps. Le script a son journal
(`.claude/scripts/inventaires-auto.log`) et ses propres alertes. `--sans-inventaire` sur
`finalisation.py` coupe l'étape.

**Sous 10 m³, pas d'inventaire PDF** (Karim, 24/09/2026 ; seuil de 6 m³ du 22/09/2026 relevé
à 10) : l'inventaire est noté directement sur le devis. `finalisation.py` ne lance alors rien
(ni recherche, ni PDF, ni envoi) et l'écrit dans sa sortie. Seuil
`regles.SEUIL_INVENTAIRE_PDF_M3`, test `regles.inventaire_pdf_requis()` — 10 m³ pile ou volume
inconnu : l'inventaire part.

**Devis indicatif : HubSpot seulement** (Karim, 12/10/2026). Quand l'export porte
`fiche.indicatif` (`pipeline.py --indicatif`, ou « Type de devis » = Indicatif lu sur HubSpot),
`finalisation.py` lance `inventaire_auto.py --indicatif` : le PDF s'appelle
`inventaire indicatif NOM Prénom.pdf`, il **rejoint la transaction HubSpot à la validation et n'est
pas envoyé sur WhatsApp**. Le message d'équipe « Devis ⚠️ INDICATIF ⚠️ » part, lui, comme avant.

**Où il cherche — le premier qui répond l'emporte :**
1. **la fiche** : section dont le titre parle d'« inventaire » dans la note HubSpot (le corps fait foi) ; puis,
   pour un ancien dossier seulement, les fichiers (PDF, tableur, document) de sa page Notion rangés sous cette
   section ou nommés « inventaire » (la note n'en porte pas) ;
2. **noCRM** (opportunité appariée par téléphone ou e-mail — jamais sur le seul nom) : pièces
   jointes documents (devis, factures, CGV, déclarations écartés d'office ; images seulement
   si leur nom parle d'inventaire), puis texte saisi au-dessus du « --- » de la description ;
3. rien → le script s'arrête sans bruit.

**Qui met en forme :** le format structuré « Pièce : article dims xN · … » (celui qu'écrivent
nos skills sur la fiche) est lu par un **parseur codé**, zéro token. Texte libre, PDF scanné
ou tableur passent par `claude -p` (modèle `sonnet`, sans MCP, lancé hors du coffre), avec les
règles de rédaction lues dans `Prod_inventaires/SKILL.md` — source unique. La réponse est
**validée** (forme, quantités) avant tout rendu ; un document qui n'est pas un inventaire
rend `{"pieces": []}` et on passe au suivant. Trois appels au modèle au plus par dossier.

**Ce que porte le PDF :** client, adresses, date / créneau lus dans la fiche ; volume = celui
du devis exporté ; n° d'inventaire **vide** (Samuel le saisit, champ modifiable).

**Garanties :**
- **jamais deux fois le même inventaire** : registre `.claude/scripts/inventaires-envoyes.jsonl`
  (fiche + empreinte de la source), vérifié *avant* tout appel au modèle — réexporter un devis
  ne coûte rien. Un inventaire modifié repart, avec la mention « met à jour et remplace » ;
- une source illisible n'arrête pas la recherche (on passe à la suivante) ; l'alerte ne part
  que si rien n'a finalement été trouvé ;
- PDF non envoyé (Beeper fermé) → file d'attente WhatsApp, rejouée par
  `notif.py --vider-file-attente` (fichiers compris), et alerte Slack.

```bash
python outils/pipeline/inventaire_auto.py --page-id <id> --chercher     # dit ce qu'il trouve
python outils/pipeline/inventaire_auto.py --page-id <id> --sans-envoi   # produit le PDF seul
python outils/pipeline/inventaire_auto.py --page-id <id> --volume 16    # rattrapage complet
python outils/pipeline/notif.py "Inventaire — NOM Prénom" --fichier "<pdf>"   # envoi manuel
```

## Alertes d'incident — `notif.alerte()`

La chaîne tourne sans console visible (le veilleur de presse-papier). Un échec ne doit donc
pas s'éteindre en silence : **chaque étape qui peut échouer poste une alerte sur Slack**
(webhook entrant `SAMDEM_SLACK_WEBHOOK` dans `.env` — décision Karim du 18/09/2026 :
tout au même endroit, boîte mail dégagée). L'e-mail à `contact@samdemenage.fr`
(surchargeable par `SAMDEM_ALERTE_EMAIL`) ne sert plus que de **repli** quand Slack ne répond pas.

| Étape | Ce que dit l'alerte |
|---|---|
| Note de la fiche non écrite | clé HubSpot absente ou refusée, ou HubSpot injoignable : rien ne part à l'équipe ni au CRM |
| WhatsApp non parti | Beeper Desktop fermé — le message attend dans la file |
| noCRM non mis à jour | dossier introuvable ou écriture refusée, avec la commande de rattrapage |
| Inventaire non produit / non envoyé | source illisible, volume absent, Beeper fermé — avec la commande de rattrapage |
| **Exception non rattrapée** | le script s'est arrêté en plein milieu, avec la trace |

Le message est écrit pour être lu sur un téléphone entre deux chantiers : **ce qui a échoué,
où, pourquoi, quoi faire** — la trace Python reste en bas, pour le jour où il faut creuser.

**Transport : un webhook entrant Slack.** Création : api.slack.com/apps → *Create New App* →
*From scratch* → *Incoming Webhooks* (activer) → *Add New Webhook to Workspace* → choisir le
canal → copier l'URL `https://hooks.slack.com/...` dans `SAMDEM_SLACK_WEBHOOK`. Un webhook ne
peut poster que dans son canal : l'URL est un secret, à régénérer si elle fuit. Slack répond
exactement `ok` ; tout autre retour (403/404/410 = webhook révoqué ou canal archivé) fait
basculer sur le repli. Quatre filets dans l'ordre : **Slack**, puis e-mail via la Web App Apps
Script déjà déployée (celle du Google Sheet, qui n'archive plus rien depuis le 03/11/2026 ; compte Google de Samuel, `MailApp`, aucun mot de
passe SMTP), puis file d'attente WhatsApp, puis `.claude/scripts/alertes.jsonl` (champ `canal`
= `slack` / `email`). Une alerte n'est jamais perdue, et une alerte qui échoue
n'aggrave jamais l'incident qu'elle signale.

⚠ **Autoriser avant de redéployer.** Apps Script accorde les autorisations quand on
**autorise** le script, pas quand on le déploie : l'ancienne version ne touchait qu'au tableur,
elle n'avait donc que l'autorisation « feuilles de calcul ». `MailApp.sendEmail` en demande une
nouvelle, et seul un **lancement manuel depuis l'éditeur** ouvre l'écran de consentement.
Marche à suivre : choisir la fonction `autoriser` dans la liste, *Exécuter*, *Examiner les
autorisations*, choisir le compte, *Paramètres avancés* → *Accéder à … (non sécurisé)* — le
script n'est pas vérifié par Google, c'est normal — puis *Autoriser*. Un e-mail de confirmation
arrive. Vérifier aussi que le déploiement est en **« Exécuter en tant que : moi »** : en
« l'utilisateur qui accède », l'envoi se ferait au nom d'un anonyme et serait refusé.

⚠ **Le script Apps Script doit ensuite être redéployé** (coller `apps_script_devis.gs`, qui porte
maintenant l'action `alerte`, puis *Déployer > Gérer les déploiements > modifier > Nouvelle
version*). Tant que ce n'est pas fait, l'ancienne version répond `ok: true` **sans envoyer
d'e-mail** : `notif.alerte()` exige donc un accusé explicite (`alerte: true`) et bascule sur
la file WhatsApp si elle ne l'obtient pas. Vérification de bout en bout (poste sur Slack ;
`notif.py --test` dit si le webhook est renseigné) :

```bash
python "outils/pipeline/notif.py" --alerte "essai"
```

## ⚠ Secrets et OneDrive

`.env` vit dans le vault, donc dans OneDrive : le jeton de l'Apps Script et le token Notion sont
synchronisés dans le cloud, aux côtés de données clients. Acceptable pour un poste personnel,
à revoir si le vault est un jour partagé, publié ou versionné — dans ce cas, remettre le
fichier dans `~/.claude/` (le script l'y cherche toujours) ou pointer `SAMDEM_ENV` ailleurs.
En cas de doute sur une fuite : régénérer le secret Notion, et changer le jeton de l'Apps Script des
deux côtés (constante `JETON` du script + `.env`), puis redéployer.

## Relivraison — seconde opération du devis (Karim, 14/10/2026)

Section « 08 Relivraison » des calculateurs Sam'Déménage (maître, atelier, terrain, copie
Nextories ; **pas** le calculateur Accès Déménagement) : la sortie de garde-meuble vers
l'adresse finale, un autre jour, chiffrée **dans le même devis**.

- **Comptée comme une opération à part entière** pour la manutention et la logistique : le
  moteur se rappelle lui-même (`relivOperation()` → `computeDevis()`) avec le box au départ,
  l'adresse de relivraison à l'arrivée, le volume relivré (vide = volume déposé au garde-meuble,
  sinon volume du devis) et le trajet du jour. Il en garde transport, manutention, forfait
  trajet, trajet dépôt, retour chef, déplacement, péage, monte-meubles, réservation et paniers
  repas (seuil de 6 h propre à ce jour).
- **Pas d'administratif en double** : frais de dossier une seule fois ; options, matériel,
  déchetterie restent dans le devis principal ; pas de week-end ni de groupage côté relivraison.
- **Une seule marge** : le transport de la relivraison entre dans la marge, le solveur ne
  repositionne que le transport du devis principal.
- Affichage (Karim, 14/10/2026) : le transport de la relivraison est fondu dans la ligne
  « Transport » ; ses autres lignes forment un bloc séparé « Relivraison » (avec sous-total hors
  transport) après le « Devis de base », dans la ventilation comme dans le récap texte. Export :
  postes « Relivraison · … », bloc `relivraison`,
  `temps_min.relivraison`, postes classés (contrôle « somme des postes = total HT » inchangé).
  `finalisation.py` ajoute une ligne « Relivraison : … » au bloc de chiffrage de la fiche ;
  `reprendre_devis.py` réapplique les temps de relivraison retouchés.
- **Fiche** : section `### Relivraison :` (format dans le skill
  `creer-fiche-client-samdem`) lue par `fiche_notion.py` ; `pipeline.py --devis` remplit la
  section et calcule le trajet du jour (garde-meuble → adresse → dépôt). Test :
  `python outils/pipeline/tests/test_relivraison.py`.
- Banc de non-régression : `outils/pipeline/relivraison-calculateur/tests/` (ancien / nouveau moteur sur
  40 exports réels — identiques sans relivraison, le 14/10/2026).

## Pages liées

[[pipeline-fiche-client-devis]] · [[calcul-devis]] · [[moteur-tarification-devis]] · [[marge-cible]]

## Reprendre un devis déjà envoyé

```bash
python "outils/pipeline/reprendre_devis.py" "NOM Prénom"                 # dernier export de la fiche
python "outils/pipeline/reprendre_devis.py" "NOM Prénom" --variante "X"  # une variante précise
python "outils/pipeline/reprendre_devis.py" "NOM Prénom" --liste         # exports trouvés
```

Retrouve l'export dans `donnees/Devis générés/exports/` par le `page_id` de la fiche (un renommage de la
fiche ne le perd pas), régénère `Devis_<NOM>_<Prénom>_<variante>_reprise.html` depuis le maître
du jour et l'ouvre. Même nom de variante → l'export remplace la version envoyée (confirmation du
calculateur). Les réglages manuels de l'envoi sont **réappliqués** dans la copie (Karim,
12/10/2026) : d'abord les **temps de chargement / déchargement retouchés**, puis le **TTC fixé
à la main** dans « TTC cible » — la reprise rouvre au prix envoyé, pas au barème du jour. Le
bandeau dit ce qui a été réappliqué. Le code de reprise n'est injecté que dans la copie (ancre
`if (PREFILL) chargerDossier(...)` du maître) : le maître n'est pas modifié. Sans TTC fixé à la
main, le prix suit le barème du jour, qui peut avoir bougé si un tarif a changé depuis l'envoi.
