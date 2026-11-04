# Chaîne de devis Sam'Déménage : par où commencer

Ce dossier permet de produire les devis avec Claude Code sur ton PC : tu demandes un devis, tu vérifies le chiffrage dans le
calculateur, tu relis le PDF, et le reste s'enchaîne (HubSpot, message à l'équipe). Sandrine envoie ensuite le devis au client.

Pour voir la chaîne d'un coup d'œil, ouvre `outils/pipeline/livrables/flowchart-chaine-devis-simple.html`.

## Installation, dans cet ordre

Compte environ une heure. Tu n'as besoin d'aucune connaissance technique : une fois Claude Code ouvert (guide 1), il peut te guider
pour tout le reste. Dis-lui simplement « guide-moi pour le guide 2 ».

| # | Guide | Pour quoi | Obligatoire |
|---|---|---|---|
| 1 | [Installer le dossier](guides/01-installer-le-dossier.md) | Python, Chrome, Claude Code, le veilleur | Oui |
| 2 | [Clé HubSpot](guides/02-cle-hubspot.md) | Lire et écrire les fiches et les devis sur HubSpot | Oui |
| 3 | [WhatsApp avec Beeper](guides/03-whatsapp-beeper.md) | Le message à l'équipe et l'inventaire | Oui |
| 4 | [Alertes Slack](guides/04-alertes-slack.md) | Être prévenu si une étape échoue | Conseillé |
| 5 | [Notion](guides/05-notion-anciens-dossiers.md) | Reprendre un dossier créé avant le transfert | Si besoin |
| 6 | [Gmail et routine](guides/06-gmail-et-routine.md) | Passer le dossier en « Devis envoyé » tout seul ; brouillons de mail | Conseillé |
| 7 | [Premier devis](guides/07-premier-devis.md) | Faire le premier devis et le contrôler | Oui |
| 8 | [Dépannage](guides/08-depannage.md) | Si quelque chose ne marche pas | Si besoin |

À tout moment, pour savoir ce qui manque :

```bash
python verifier_installation.py
```

## Au quotidien

Ouvre ce dossier dans Claude Code et écris simplement :

- « Crée la fiche de DUPONT Jean » et colle les informations du client.
- « Fais le devis de DUPONT Jean » : le calculateur s'ouvre, déjà rempli. Ajuste si besoin, puis clique sur « Exporter JSON ».
- Claude te présente alors le PDF. Tu choisis : valider, corriger le texte, ou changer le chiffrage.
- « Qu'est-ce qui attend ma relecture ? » pour rattraper un devis exporté plus tôt.
- « Ressors le devis de DUPONT Jean » pour le modifier.
- « Prépare le brouillon de mail » seulement si c'est toi qui envoies : d'habitude, c'est Sandrine.

## À garder en tête

- **Ne partage jamais le fichier `.env`** : il contient tes clés. Il ne doit pas être envoyé ni copié dans un dossier partagé.
- **Installe le dossier hors de OneDrive et de Google Drive**, et sans accent dans le chemin, par exemple `C:\SamDem\pipeline-sam`.
- **Sauvegarde `donnees/`** : c'est là que sont tes devis, et leur numérotation en dépend.
- **Un seul PC à la fois** : les numéros de devis se suivent à partir du dossier `donnees/Devis SamDem/`. Deux PC produiraient les mêmes.
