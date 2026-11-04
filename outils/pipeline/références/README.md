# Références de devis

Devis validés aux formats particuliers, à reprendre comme modèles quand un dossier ressemble à l'un d'eux
(Karim, 04/11/2026). Ils servent pour la présentation : les montants se chiffrent toujours au calculateur.

Un dossier par cas, au format `Formule + particularité + particularité`, avec le PDF et sa spec. **Tous sont anonymisés** :
client, adresses, numéro et inventaire sont remplacés, seule l'adresse de notre local reste. Toujours les ranger par le
script, qui refuse d'écrire s'il reste une trace du client, jamais par une copie :

```bash
python "outils/pipeline/reference_devis.py" "<spec du devis validé>.json" "Standard + stockage + groupage"
```

| Cas | Date | Ce qui change par rapport à un devis courant |
|---|---|---|
| [Standard + stockage + groupage](Standard%20+%20stockage%20+%20groupage/) | 04/11/2026 | Adresse de stockage entre le départ et l'arrivée (`client.adresse_stockage`). Ligne « Stockage en garde-meuble du … au … » à 0 €, détail « Offert ». Titre « Forfait transport groupage 5 m3 », et « Tarif préférentiel (groupage) » retiré des options non incluses. Date écrite « chargement le …, livraison le … ». Inventaire court, sans mention interne. |
