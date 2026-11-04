# 8. Dépannage

Le premier réflexe : `python verifier_installation.py`. Le deuxième : décrire le problème à Claude Code, dans ce dossier.

| Ce que tu vois | Cause probable | Que faire |
|---|---|---|
| Rien ne se passe après « Exporter JSON » | Veilleur arrêté | Relance `installer.bat`, ou redémarre le PC. Journal : `.claude/scripts/devis-export.log` |
| Claude ne présente pas le PDF | Export fait sans session Claude ouverte | Écris « qu'est-ce qui attend ma relecture ? » |
| « Aucune fiche trouvée » | Pas de note « Fiche client » sur la transaction, ou ancien dossier sans accès Notion | Fais créer la fiche, ou suis le [guide 5](05-notion-anciens-dossiers.md) |
| « Transaction ambiguë », rien n'est écrit | Plusieurs transactions ouvertes pour ce client | Fusionne les doublons dans HubSpot, l'originale en principale, puis réexporte |
| HubSpot répond 401 | Clé fausse ou supprimée | Refais la clé : [guide 2](02-cle-hubspot.md) |
| HubSpot répond 403 | Un droit manque sur la clé | Ajoute-le sur la même clé : [guide 2](02-cle-hubspot.md) |
| Le message n'est pas parti, alerte Slack | Beeper fermé | Ouvre Beeper, puis `python outils/pipeline/notif.py --vider-file-attente` |
| Le PDF n'est pas remplacé | Il est ouvert dans un lecteur | Ferme-le, puis relance |
| Le PDF reste « à la main » | Relivraison, étape, chargement seul, accès à confirmer | Normal : Claude le produit avec le skill `devis-pdf-samdem`, puis il passe par la même relecture |
| Inventaire non produit | Dossier de Christophe, moins de 10 m³, ou rien trouvé | Normal : le motif est donné à la relecture. Journal : `.claude/scripts/inventaires-auto.log` |
| Numéro de devis qui repart trop bas | Fichier de `donnees/Devis SamDem/` supprimé | Remets le fichier du dernier numéro. Garde tes PDF à cet endroit |
| « python » n'est pas reconnu | Python installé sans le PATH | Réinstalle en cochant « Add python.exe to PATH » |

## Où sont les journaux

Dans `.claude/scripts/` : `devis-export.log` (veilleur), `inventaires-auto.log`, `alertes.jsonl`, `whatsapp-file-attente.jsonl`.
