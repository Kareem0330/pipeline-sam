---
name: inventaire-samdem
description: Transforme la liste d'inventaire d'un client (texte collé, mail, notes) en PDF « Inventaire de déménagement » Sam'Déménage, à l'identique du modèle maison (logo, tampon, charte, champs modifiables). Déclencher sur : inventaire client, mettre au propre un inventaire, PDF d'inventaire, générer l'inventaire, annexe inventaire du devis.
---

# Inventaire client → PDF Sam'Déménage

Le skill complet vit avec ses fichiers dans `outils/pipeline/Prod_inventaires/`.

**Lire `outils/pipeline/Prod_inventaires/SKILL.md` en entier et le suivre à la lettre** avant de
traiter une liste : déroulé, format du dossier JSON, règles de rédaction des articles.
Le PDF est produit par `outils/pipeline/Prod_inventaires/generer_inventaire.py` — ne jamais recréer
la mise en page à la main.
