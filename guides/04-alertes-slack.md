# 4. Alertes Slack

Durée : 10 minutes. Conseillé : quand une étape échoue, la chaîne te prévient sur Slack, avec la cause et ce qu'il faut faire.
Sans ce réglage, l'erreur reste seulement dans les journaux, et tu risques de ne pas la voir.

## 1. Créer l'adresse d'alerte

1. Va sur [api.slack.com/apps](https://api.slack.com/apps) et connecte-toi à l'espace Slack de Sam'Déménage.
2. **Create New App**, puis **From scratch**. Nom : `Alertes devis`.
3. Menu **Incoming Webhooks** : active l'interrupteur.
4. **Add New Webhook to Workspace** : choisis le canal ou ta messagerie privée, puis **Autoriser**.
5. Copie l'adresse qui commence par `https://hooks.slack.com/services/`.

Si tu n'as pas Slack, tu peux créer un espace gratuit, ou sauter ce guide en acceptant de ne pas être prévenu.

## 2. L'écrire dans `.env`

```
SAMDEM_SLACK_WEBHOOK=https://hooks.slack.com/services/...
```

## 3. Tester

```bash
python verifier_installation.py --essai-slack
```

Un message d'essai doit arriver sur Slack.

Ensuite : [guide 5](05-notion-anciens-dossiers.md) si tu as d'anciens dossiers à reprendre, sinon [guide 6](06-gmail-et-routine.md).
