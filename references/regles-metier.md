# Règles métier

Ce que la chaîne a appris sur le terrain, en plus des skills. Une règle datée plus récente dans un skill prime sur ce fichier.

## Prix

- **Manutention** : 28 € HT/h partout, sans zone. Conducteur sur la route : 30 €/h sous 2 h d'A/R, 20 €/h par personne du camion à partir de 2 h d'A/R.
- **Kilomètres** : 0,60 € HT/km avec un camion à nous. Camion loué : 0,40 € HT/km de carburant, en plus de la location.
- **Forfait déplacement** : 10 € HT hors groupage. Groupage : 60 € HT + 20 € HT par camion. La ligne « Frais de déplacement » garde un plancher de 43 € HT.
- **Transport en groupage** : volume × 50 € HT, avec un minimum de 150 € jusqu'à 1 m³, 200 € jusqu'à 3 m³, 250 € jusqu'à 5 m³. Pas de majoration week-end, garde-meuble ni Premium.
- **Dimanche** : prime de 37,50 € HT par salarié présent (30 € margés à 25 %). **Week-end** : +10 % du transport. Cocher le dimanche coche aussi le week-end ; un samedi n'a pas de prime.
- **Paniers repas** : 16 € HT par personne au-delà de 6 h de chantier, sans marge. Ils sont compris dans la ligne « Manut » de la fiche.
- **Marge** : cible 35 %, 21 % sur un devis Next Stories. Elle n'arrête aucun devis : elle s'affiche, et Samuel décide à la relecture. La manutention n'entre jamais dans la marge.
- **Commission** : aucune sur un devis Sam'Déménage. Accès Déménagement a son calculateur à part, cible 30 %, commission 7 %, hors chaîne : on l'ouvre et on chiffre à la main.
- **Garantie dommage** : 1 % du montant déclaré (40 000 € donnent 400 €), réglée avec l'acompte. La garantie incluse reste gratuite (6 500 €, 650 € par meuble).

### Matériel, prix unitaires HT

Carton standard 1,25 · livres 1,00 · vaisselle 4,75 · bouteilles 1,75 · penderie 0 · informatique 1,25 · tableaux 7,00 · scotch 2,50 · rouleau de bulles 20 m 12,50 · barrel verres 5,00 · barrel assiettes 5,00 · rouleau kraft 120,00. Livraison : 30 € HT, sauf pour des penderies seules.

### Garde-meuble, tarif client HT par mois

5 m³ 50 € · 8 m³ 65 € · 10 m³ 75 € · 12 m³ 85 € · 15 m³ 105 € · 20 m³ 130 € · 25 m³ 160 € · 30 m³ 190 € · 35 m³ 220 € · 40 m³ 250 € · 45 m³ 270 € · 50 m³ 290 € · 55 m³ 315 € · 60 m³ 340 € · 65 m³ 365 € · 70 m³ 385 € · 75 m³ 405 € · 80 m³ 430 €. Un volume prend le prix du plus petit palier supérieur ou égal. Le calculateur l'affiche à titre indicatif, hors total du devis.

## Volume

- Sur inventaire, le chiffre du devis est toujours le volume **conservateur**, jamais le standard. Source : « estimation Sam'Déménage sur inventaire client (conservateur) ».
- Un inventaire sans volume ne donne pas de relance au client : on l'estime en interne.
- Un ascenseur « 4 à 5 personnes » n'est pas un petit format : on coche seulement l'ascenseur, jamais Petit ou Grand déduit d'une capacité.

## Itinéraire

- Le trajet est une **boucle** depuis le dépôt, 147 route des Valentons, 33450 Saint-Loubès : dépôt, départ client, arrivée client, dépôt.
- Sans péage tant que l'A/R tient sous 19h06 de conduite, avec péage au-delà.
- Le péage ne se calcule jamais : il se relève sur Mappy en classe 3, puis se divise par 1,2 pour le HT.
- Un lien Mappy ne porte que deux points : un lien par segment, jamais un lien unique.

## Fiche

- Plusieurs dates possibles : on écrit tous les créneaux, on coche « Date flexible », sans 🟡. Le 🟡 est réservé à ce qui manque vraiment.
- Une information manquante n'est jamais écrite dans une propriété HubSpot et ne fait rien échouer : la propriété reste vide, le manque reste lisible dans la note.
- **Visite de Christophe** : il fait l'inventaire lui-même. Ne jamais recopier celui du formulaire client, ni rien en déduire. La chaîne ne génère aucun inventaire pour ses dossiers : c'est une intervention humaine.
- Chercher les dossiers d'une date ou d'un axe : la date est souvent dans le texte de la note, pas dans la propriété. Lire la fiche et les notes de toutes les transactions, sauf les perdues, sans filtrer d'avance par colonne.

## Devis

- **Contrôle avant génération** : `pipeline.py --fiche "X"` affiche les valeurs sans rien ouvrir ; on les relit, on pose les questions ouvertes, puis `--devis` avec les mêmes options génère une seule fois. Devis existant : nouveau contrôle, `--remplacer`, et fermer l'ancien onglet.
- **Navigateur** : le calculateur s'ouvre dans le navigateur intégré de Claude, jamais dans le navigateur externe. C'est Samuel qui clique sur « Exporter JSON ».
- **Indicatif** : « fais un devis indicatif pour X » se contrôle avec `pipeline.py --fiche "X" --indicatif`, puis se génère avec `--devis --indicatif`. Sans ce drapeau, le devis repasse en « Ferme ». Son inventaire rejoint HubSpot sans partir sur WhatsApp.
- **Chargement ou déchargement seul** : `--chargement-seul` ou `--dechargement-seul` met à 0 le temps de la phase absente. Le PDF se fait à la main.
- **Ressortir un devis** : `python outils/pipeline/reprendre_devis.py "NOM Prénom"` rouvre le dernier export, modifiable, au lieu d'un résumé. Il n'existe que pour les exports faits dans ce dossier.
- **Rien sur un devis qui trahisse sa préparation** : ni 🟡 ni émoji, ni « temps à chiffrer », ni temps d'options, ni nom de variante. Le client ne doit jamais deviner qu'une IA a préparé le devis. Le générateur refuse une spec qui en contient.
- **Aucun détail logistique ni mention interne pour le client** : ni valeur d'un objet (« cher »), ni kraft ou couverture, ni « à protéger », ni ordre de tournée, ni consigne d'équipe. Ces éléments restent dans les notes de la fiche.
- **Ne rien supposer** : ce que la source ne dit pas se demande à Samuel avant de générer le devis, sans retenir d'hypothèse.
- **Stockage dans notre local** : le calculateur ne le chiffre pas. Le PDF porte l'adresse de stockage, 147 route des Valentons, 33450 Saint-Loubès, entre le départ et l'arrivée, et une ligne « Stockage en garde-meuble du … au … ». Offert ou facturé dépend du dossier : le demander à Samuel à chaque fois, sans déduire un prix de la grille. Le détail est dans le skill `devis-pdf-samdem`.
- **Références** : `outils/pipeline/références/` garde les devis aux formats particuliers, un dossier par cas (« Standard + stockage + groupage »), tous anonymisés. À relire avant un cas similaire pour reprendre la présentation, jamais les montants. Après la validation d'un nouveau format, le ranger avec `reference_devis.py`, jamais par une copie.
- **Envoi** : Sandrine envoie depuis son adresse. Pas de brouillon de mail sans demande explicite de Samuel.
- **Relecture** : ce qui se corrige est le plus souvent du texte, par la spec du PDF et `validation_devis.py --regenerer`, sans rouvrir le calculateur.

## Textes pour les clients

- Écriture naturelle, sans aucune marque d'IA : ni tiret long, ni « n'hésitez pas », ni formule toute faite, ni émoji, ni liste systématique, ni introduction creuse.
- Texte au « nous », comme le site. Signature :

```
Bien cordialement,

Equipe Sam'Déménage
05.54.54.03.08
```

- Exception : le mail d'envoi du devis reste à la première personne, signé Sandrine, car elle reprend la relation client après le devis.

## Société

SARL Sam'Déménage, SIRET **928 903 921 00049** (00015 est périmé : à corriger s'il réapparaît), TVA FR36928903921, siège 77 rue Reinette, 33100 Bordeaux.

## HubSpot

- La fiche est **une seule note** par transaction : créée si elle manque, modifiée sinon. Jamais de seconde note identique.
- Doublons de transactions : on les fusionne, l'originale en principale. La fusion change l'identifiant et garde l'étape de la principale : la vérifier ensuite.
- Les transactions créées par le site ont Samuel Cohen pour propriétaire par défaut.
