# 5. Notion, pour les anciens dossiers

Durée : 5 minutes. **Facultatif.** Les nouvelles fiches vivent sur HubSpot. Notion ne sert qu'à reprendre un dossier créé avant le passage à HubSpot :
sa fiche est lue, sans jamais y écrire, puis recopiée une fois dans une note de sa transaction.

Sans ce réglage, tout fonctionne, sauf ces anciens dossiers : Claude te dira que la fiche est introuvable et t'en fera créer une.

## 1. Créer l'accès

1. Va sur [notion.so/profile/integrations](https://www.notion.so/profile/integrations).
2. **Nouvelle intégration**. Nom : `Lecture devis`. Espace : Sam'Déménage.
3. Dans **Capacités**, ne garde que **Lire le contenu**.
4. Copie le jeton.

## 2. Autoriser la base des fiches

Une intégration créée n'a accès à rien tant qu'on ne l'autorise pas. Ouvre la base « 🗂️ Fiches Client (base) », menu `•••` en haut à droite,
**Connexions**, puis ajoute `Lecture devis`.

## 3. L'écrire dans `.env`

```
NOTION_TOKEN=le-jeton
```

## 4. Tester

```bash
python verifier_installation.py
```

Ensuite : [guide 6](06-gmail-et-routine.md).
