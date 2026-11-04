# 2. Clé HubSpot

Durée : 10 minutes. C'est le lien indispensable : la fiche client, le chiffrage et les PDF vivent sur HubSpot.

Il faut être **Super Admin** du compte HubSpot de Sam'Déménage. Si ce n'est pas le cas, demande à un Super Admin de te donner ce droit.

## 1. Créer la clé

1. Dans HubSpot, clique sur la roue dentée **Paramètres**.
2. Dans le menu de gauche : **Intégrations**, puis **Service Keys**.
3. Clique sur **Créer une clé**. Nom : `Claude Code - Samuel`.

## 2. Cocher les droits

Coche exactement ces droits, pas plus :

| Droit | Pourquoi |
|---|---|
| `crm.objects.deals.read` et `.write` | Lire et mettre à jour les transactions |
| `crm.objects.contacts.read` et `.write` | Contacts des dossiers |
| `crm.objects.companies.read` et `.write` | Clients professionnels |
| `crm.schemas.deals.read` et `.write` | Propriétés et étapes des transactions |
| `crm.schemas.contacts.read` et `.write` | Propriétés des contacts |
| `crm.schemas.companies.read` | Propriétés des entreprises |
| `crm.objects.owners.read` | Commerciaux propriétaires |
| `files.read`, `files.write`, `files.ui_hidden.read`, `files.ui_hidden.write` | Joindre les PDF aux transactions. Il n'y a pas de droit « files » unique : il faut les quatre |

Ne coche ni la facturation, ni la gestion des utilisateurs en écriture, ni `files.delete`.

## 3. Écrire la clé dans `.env`

Copie la clé, puis dans le fichier `.env` (voir la fin du [guide 1](01-installer-le-dossier.md)), complète la ligne :

```
HUBSPOT_TOKEN=la-cle-copiee
```

Ne la colle nulle part ailleurs, pas même dans une conversation.

## 4. Tester

```bash
python verifier_installation.py
```

Les lignes HubSpot doivent passer à « OK ». Un « 403 » veut dire qu'un droit manque : la ligne dit lequel. Il suffit de l'ajouter sur la même clé.

Ensuite : [guide 3](03-whatsapp-beeper.md).
