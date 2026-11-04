# Chaîne de devis Sam'Déménage

Ce dossier contient tout ce qu'il faut pour produire un devis : scripts, calculateurs, skills, règles, documents d'envoi.
Il ne dépend de rien d'autre sur ce PC, en dehors des logiciels et des accès décrits dans `LISEZ-MOI.md`.

## Pour qui

Tu travailles avec **Samuel Cohen**, gérant de Sam'Déménage, société de déménagement basée à Bordeaux. Il relit et valide chaque
devis. **Sandrine** envoie les devis aux clients depuis son adresse. **Christophe** fait les visites. La chaîne a été construite avec
Karim Bordeau : dans les documents, « (Samuel, date) » indique simplement l'origine d'une règle.

## Comment travailler

- Parle simplement : pas de jargon technique, une action à la fois quand tu guides Samuel.
- Si quelque chose ne marche pas, lance `python verifier_installation.py` et suis le guide qu'il indique dans `guides/`.
- Si Samuel demande d'installer ou de connecter un outil, suis le guide concerné, étape par étape, en attendant sa réponse entre deux.
- Les règles métier sont dans `references/regles-metier.md`. Les pièges de la chaîne sont dans `.claude/skills/LECONS.md` : à lire avant de la modifier.
- Chaque clé d'API va dans le fichier `.env` à la racine, jamais ailleurs. N'affiche jamais une clé.
- Le calculateur s'ouvre dans ton navigateur intégré (`preview_start`), jamais dans le navigateur externe : suis la ligne « à ouvrir dans le navigateur intégré » que rend le pipeline.
- Rien ne part à un client sans Samuel. Ne supprime aucune donnée sans son accord.
- Les dates des règles sont celles de leur décision. Une date qui te semble dans le futur n'est pas une erreur.
- Ce dossier ne contient pas tout l'historique : un renvoi vers `wiki/`, `crm-manager/`, `outils/Groupage/`, `outils/Workflow NextStories/`, `gros-dossiers-sam` ou `gros_dossiers.py` vise un document resté ailleurs. Ignore-le, et ne le cherche pas sur ce PC. Les devis Nextories et le groupage ne passent pas par ce dossier.
- Notion ne sert plus qu'à lire les anciens dossiers, et seulement si `NOTION_TOKEN` est renseigné. Tu n'écris jamais dans Notion. noCRM n'est plus utilisé.

## Dans ce dossier

| Où | Quoi |
|---|---|
| `.claude/skills/` | fiche client, volume, devis, PDF, inventaire |
| `outils/pipeline/` | les scripts, les calculateurs, les flowcharts (`livrables/`), les devis modèles anonymisés (`références/`) |
| `donnees/` | PDF des devis et des inventaires, documents d'envoi (CGV, RIB…) |
| `references/` | règles métier, spec d'exemple |
| `guides/` | installation et connexion des outils, étape par étape |


## Agent devis — skills, outils et leçons

La chaîne **prise de contact → fiche client → volume → devis** vit dans ce vault :
- `.claude/skills/` — les trois skills (`creer-fiche-client-samdem`, `estimer-volume-samdem`,
  `calcul-devis-samdem`), un dossier chacun. Voir `.claude/skills/README.md`.
- `outils/pipeline/` — **dossier unique de la chaîne** (Karim, 03/11/2026) : les scripts qui portent tout le
  déterministe, calculateurs, itinéraire, générateurs de PDF et d'inventaires. Les livrables qui s'accumulent restent hors du coffre
  (Karim, 04/11/2026) : `donnees/Devis générés\` (copies du calculateur, exports, relectures), `Devis SamDem\`, `Inventaires\`.
  Carte en tête de son `README.md`. Tout nouveau fichier de la chaîne s'y range.
- `outils/pipeline/livrables/pipeline-fiche-client-devis.md` — spec du process complet, et
  `outils/pipeline/README.md` — mode d'emploi des trois commandes.

**Le calculateur de devis n'est jamais réécrit** — le maître est
`outils/pipeline/calculateurs/calculateur-devis.html`, à ouvrir en local
(`outils/pipeline/calculateurs/calculateur-devis.html`). `pipeline.py --devis`
en **copie** le maître, y injecte le dossier dans la constante `PREFILL` et ouvre le fichier :
le formulaire est rempli dès l'ouverture, sans « Charger un dossier » ni collage. Le moteur de
calcul reste celui du calculateur, à l'octet près. `--prefill` garde la voie « artefact en
ligne » (JSON au presse-papier) quand le devis doit se faire sur tablette ou être partagé. Le
devis validé sort par « Exporter JSON » et `outils/pipeline/finalisation.py` le reporte sur la
transaction HubSpot : note « Fiche client » créée ou modifiée, jamais dupliquée (Karim, 04/11/2026), variantes et itinéraire compris,
propriétés de chiffrage, étape « Devis en révision ».

**Fiche sur HubSpot (Karim, 03/11/2026)** — plus de fiche créée dans Notion, plus d'archive dans le
Google Sheet. La fiche est une note de la transaction (`outils/pipeline/fiche_hubspot.py`), au format relu
par `fiche_notion.parser_corps`. L'identifiant de transaction voyage dans `fiche.page_id`. Un ancien dossier
garde sa page Notion en lecture seule : son corps rejoint une note de sa transaction, une fois, à la reprise.
Plan et statuts : `outils/pipeline/sans-notion/`.

**Devis PDF automatique (Karim, 02/11/2026, revu le 03/11/2026)** — à chaque « Exporter JSON », `finalisation.py`
génère le PDF du devis depuis l'export, version officielle (`outils/pipeline/devis_auto.py`), et le garde en
local. **Claude le présente à Samuel, puis lui donne une sélection : valider, corriger le texte du PDF (cas courant,
`validation_devis.py --regenerer`) ou changer le chiffrage**. Validé, le PDF et
l'inventaire (si le dossier en a un) sont importés sur la transaction HubSpot, puis le message « Devis prêt
à vérifier » part sur WhatsApp, avec le lien HubSpot. Rien ne part
avant (`outils/pipeline/validation_devis.py`, skill `calcul-devis-samdem` § 13 bis). Relivraison, étape, chargement seul, accès à confirmer : PDF à la main,
motif dans le message. **Dossier de Christophe** (visites, devis en général manuscrits) : le PDF du
devis est préparé, mais aucun inventaire n'est généré ni envoyé, c'est une intervention humaine. **Aucune trace de préparation sur un document client**
(Karim, 03/11/2026) : ni 🟡, ni émoji, ni temps d'options, ni nom de variante ; le client ne doit jamais
deviner qu'une IA a préparé le devis. Détail : `outils/pipeline/README.md`.

**Envoi au client (Karim, 03/11/2026)** : Sandrine envoie le devis depuis son adresse. Claude ne prépare un
brouillon de mail que si Samuel le demande explicitement (`devis-pdf-samdem`, § 7), et ne le propose pas.

**Inventaire automatique (Karim, 18/09/2026)** — à l'export, `finalisation.py` lance en arrière-plan
`outils/pipeline/inventaire_auto.py` : il cherche l'inventaire (section Inventaire de la fiche, puis
pièces jointes et description du CRM) et le met au propre avec `outils/pipeline/Prod_inventaires/`. Le PDF part
à la validation du devis, sur HubSpot et sur la conversation WhatsApp, juste après le message. Rien trouvé : il s'arrête sans bruit. Un même inventaire n'est jamais
renvoyé (registre `.claude/scripts/inventaires-envoyes.jsonl`). Détail : `outils/pipeline/README.md`.

**Alertes d'incident** — chaque étape qui peut échouer (HubSpot, WhatsApp, plus
un filet sur toute exception non rattrapée) prévient Samuel **sur Slack** via `notif.alerte()`
(webhook `SAMDEM_SLACK_WEBHOOK`, Karim 18/09/2026) ; l'e-mail (Apps Script) ne sert plus que de repli.

**Marge : plus de blocage (Karim, 03/11/2026)** : le garde-fou de 30,5 % du 08/09/2026 est retiré. Quelle
que soit la marge, le devis suit toute la chaîne jusqu'à la relecture de Samuel, et la marge reste affichée.
Voir `wiki/concepts/marge-cible.md`.

**Next Stories — 21 % automatiques (Karim, 10/09/2026)** : cocher « Devis Next Stories » dans le
**maître** ou l'**atelier** ramène la marge à **21 %** *une fois tous les autres calculs faits* —
le solveur §6.2 ne déplace que le poste Transport. Réglage **modifiable** ensuite ; décocher rend
la main au barème. Sur ces dossiers, 21 % vaut **cible**. Constantes `MARGE_NS` (HTML) et
`regles.MARGE_NEXT_STORIES` ; côté pipeline tout passe par `regles.cible_marge()`, alimenté par
`mission.next_stories` de l'export. Variante terrain et calculateur AD non concernés.

**Commission et cible (Karim, 09/09/2026)** : plus aucune commission sur un devis Sam'Déménage
(maître, atelier, terrain), **Next Stories compris** ; cible de marge **35 %** (`regles.MARGE_CIBLE`).
Seule exception : **Accès Déménagement, 7 %**, sur son propre calculateur
`outils/calculateur-devis-acces-demenagement.html` — clone du maître (cible 30 %, sans Next
Stories, sans pied de page), à faire évoluer en parallèle de lui.

⚠️ **Le pipeline ne traite QUE du Sam'Déménage** (Karim, 09/09/2026). `pipeline.py`,
`finalisation.py`, `nocrm.py`, la fiche sur HubSpot et l'atelier sont la chaîne
Sam'Déménage : **aucun devis AD n'y passe**. Le calculateur AD est un outil autonome — on l'ouvre,
on chiffre, on exporte à la main. Ne jamais y brancher le pipeline ni aligner ses règles sur
`regles.py`.
**Commission ≠ marge** : la marge vaut `Transport + 15 % des options` (25 % Premium) + marge de la
prime de dimanche ; la manutention n'y entre jamais. Assiette de la commission et exclusions :
`wiki/concepts/commission-devis.md`.
L'atelier est **généré** (`python outils/pipeline/build_atelier.py`), jamais édité à la main.

**Relivraison (Karim, 14/10/2026)** : section « Relivraison » des calculateurs Sam'Déménage
(maître, atelier, terrain, copie Nextories — pas AD) pour la sortie de garde-meuble un autre
jour, dans le même devis : manutention et logistique comptées comme une opération à part
entière, frais de dossier / options / matériel une seule fois, une seule marge. Fiche :
section `### Relivraison :`. Détail : `outils/pipeline/README.md` § Relivraison.

**`.claude/skills/LECONS.md` — registre d'apprentissage.** Le lire avant de travailler sur
cette chaîne : il consigne les pièges qui se reproduisent (API qui échouent silencieusement,
règles métier divergentes, seuils calés sur un outil). **L'alimenter** dès qu'une erreur ou
un blocage remplit ses deux critères d'entrée — coûteux *et* reproductible. Ne pas y verser
ce qui relève du `log.md` ou d'un README : un registre qui gonfle sans discernement cesse
d'être lu.

**Principe de conception** (Karim, 08/09/2026) : tout ce qui est déterministe est **codé une
fois et exécuté**, jamais re-raisonné à chaque dossier. Le modèle ne garde que le non-codable
— comprendre un message client, rédiger une fiche, arbitrer une ambiguïté.
