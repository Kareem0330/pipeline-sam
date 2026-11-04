# Skills de l'agent Sam'Déménage

Skills métier de la chaîne **prise de contact → fiche client → volume → devis**, regroupés
dans le vault. Leurs scripts, calculateurs et livrables sont tous dans `outils/pipeline/` (carte en
tête de son `README.md`) ; seuls les `SKILL.md` restent ici, Claude Code ne les trouverait pas ailleurs.

## Pourquoi ce dossier, et pas un dossier « SKILLS » à la racine

Claude Code ne découvre les skills qu'à des emplacements imposés : `.claude/skills/<nom>/SKILL.md`
(ou `.claude/commands/*.md`). Un dossier `SKILLS/` à la racine du vault ne serait jamais
chargé. `.claude/` est bien **dans** le vault — il suit la synchronisation et les sauvegardes
comme le reste — il est simplement masqué par l'explorateur et par Obsidian.

## Contenu

| Skill | Rôle | S'appuie sur |
|---|---|---|
| `creer-fiche-client-samdem/` | Crée et remplit la fiche client sur HubSpot (note « Fiche client » de la transaction, depuis le 03/11/2026) | `outils/pipeline/fiche_hubspot.py` · `outils/pipeline/itineraire/calcul_itineraire.py` · `references/modele-fiche.md` · `references/regles-remplissage.md` |
| `estimer-volume-samdem/` | Estime le volume depuis un inventaire client | `outils/pipeline/volume.py` |
| `calcul-devis-samdem/` | Chiffre le devis et génère le calculateur pré-rempli | `outils/pipeline/pipeline.py` · `outils/pipeline/calculateurs/calculateur-devis.html` |
| `gros-dossiers-sam/` | Liste les gros devis en attente et les envoie à Samuel sur WhatsApp | `outils/pipeline/gros_dossiers.py` · MCP Beeper |
| `inventaire-samdem/` | Met au propre l'inventaire d'un client en PDF (modèle maison, champs modifiables, tampon) | `outils/pipeline/Prod_inventaires/` (skill complet, gabarit, script) |
| `devis-pdf-samdem/` | Produit le PDF du devis à envoyer ; inventaire court listé dedans (≤ 10 lignes, ≤ 3 pages), sinon « Voir inventaire » + inventaire séparé | `outils/pipeline/devis-pdf/generer_devis_pdf.py` · export du calculateur · fiche client (note HubSpot) |

Un skill peut embarquer ses fichiers compagnons dans son propre dossier — c'est ce que fait
`creer-fiche-client-samdem/references/`, qui porte les règles détaillées de remplissage
(formule, étages, portage, matériel, nettoyage, contrôles de cohérence).

## Ce qui reste ailleurs, et pourquoi

- `.claude/commands/` — skills du **wiki** (`ingest`, `lint`, `query`, `save`, `auto-ingest`).
  Ils portent sur la connaissance métier, pas sur la chaîne devis.
- `~/.claude/commands/` (hors vault, donc disponibles depuis n'importe quel projet) —
  `devis-en-cours`, `etat-axe-paris`, `import-recap-fin-de-mission`, `rapport-devis-complet`,
  `recap-journalier`, `mes-skills`. Les cinq premiers sont spécifiques à Sam'Déménage et
  gagneraient à rejoindre ce dossier ; `mes-skills` est générique et doit rester global.

## Documentation liée

`outils/pipeline/livrables/pipeline-fiche-client-devis.md` (spec du process complet) ·
`outils/pipeline/README.md` · `outils/pipeline/itineraire/README.md`
