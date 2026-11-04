# Journal de la chaîne de devis

Mémoire des changements importants de la chaîne fiche → volume → devis → PDF → HubSpot : ce qui a changé, pourquoi, et ce qu'on en a appris. Il part avec le skill et sert à toute personne qui utilise la chaîne. Le lire avant de travailler sur un devis : une entrée récente l'emporte sur une consigne plus ancienne qui la contredit, et cette contradiction se corrige dans le skill concerné.

## Quand écrire (sans attendre qu'on le demande)

Ajouter une entrée, dans la même session et avant de conclure, dès qu'on a :
- changé une règle métier ou ce qui s'écrit sur un document client ;
- modifié le comportement d'un script ou d'un skill de la chaîne ;
- reçu une consigne de la personne qui relit qui vaudra pour les prochains dossiers ;
- rencontré un piège ou trouvé un contournement qui se reproduira.

Ne pas écrire : le traitement normal d'un dossier, une faute de frappe, une correction propre à un seul client. Un piège coûteux et structurel va aussi dans `../LECONS.md`, avec son symptôme et sa cause.

## Règles d'écriture

- **Le dépôt est partagé : aucune donnée de client.** Ni nom, ni adresse, ni téléphone, ni montant d'un dossier, ni clé d'API. Dire « un dossier sans inventaire », pas son nom.
- La plus récente en haut. On n'efface pas une entrée : si une règle change, on en ajoute une nouvelle qui dit ce qu'elle remplace.
- Écrire la règle aussi là où elle s'applique (skill, script, test). Le journal garde l'historique, il ne remplace pas le skill.

## Format

```
### AAAA-MM-JJ · Titre court (qui a décidé)
**Changement** : ce qui est différent maintenant.
**Pourquoi** : la raison donnée.
**Où** : fichiers touchés.
**Leçon** : ce qu'il faut retenir. Ligne facultative.
```

## Entrées

### 2026-11-04 · Adresse intermédiaire toujours affichée (Karim)
**Changement** : toute adresse intermédiaire (stockage, passage, étape) s'affiche sur le devis entre le départ et l'arrivée. Nouveau champ `client.adresse_passage`, à côté de `client.adresse_stockage`.
**Pourquoi** : un devis avec un passage ne le montrait que dans le forfait manutention.
**Où** : `devis-pdf/generer_devis_pdf.py`, `devis-pdf-samdem/SKILL.md`.

### 2026-11-04 · Civilité conservée dans le nom du client (Karim)
**Changement** : une civilité précisée dans les notes de la transaction va sur le devis (« Mme NOM ») ; le nom seul uniquement si elle n'est pas précisée. Elle se porte dans le nom de la transaction : la fiche en tire `client.civilite`, le devis la reprend, le nom du fichier PDF ne la garde pas.
**Pourquoi** : la note précisait la civilité et le devis ne portait que le nom.
**Où** : `fiche_hubspot.py`, `devis_auto.py`, `devis-pdf/generer_devis_pdf.py`, `creer-fiche-client-samdem/references/regles-remplissage.md`.

### 2026-11-04 · Deux utilisateurs, deux chaînes (Karim)
**Changement** : une règle métier se modifie dans la chaîne de base et passe à la copie de Samuel. Tout ce qui est propre à un utilisateur (prénom, chemins, destinataires, environnement) reste de son seul côté : la chaîne de base reste adaptée à Karim, et l'adaptation à Samuel se fait uniquement dans `pipeline-sam/construire.py` et son `modele/`.
**Pourquoi** : mêmes règles au départ, mais besoins et environnements différents, et les deux chaînes vont diverger.
**Leçon** : une reconstruction remplace tout le dossier de Samuel sauf les entrées de ce journal. Une évolution faite directement chez lui doit aussi passer dans `construire.py`, ou la reconstruction l'efface.

### 2026-11-04 · Journal de la chaîne créé (Karim)
**Changement** : ce fichier existe et s'alimente à chaque changement important.
**Pourquoi** : garder une mémoire des modifications et des leçons qui suive le skill, utile aussi à Samuel.
**Où** : `calcul-devis-samdem/JOURNAL.md`, rappel en tête des skills de la chaîne ; `pipeline-sam/construire.py` ne réécrit pas les noms dans ce fichier et garde les entrées déjà présentes dans le dossier de sortie.
**Leçon** : avant de reconstruire le dossier, récupérer le dépôt GitHub (`git pull`), sinon les entrées écrites de l'autre côté ne sont pas encore là pour être gardées.

### 2026-11-04 · Formule Standard à 0 € sur le PDF (Karim)
**Changement** : en Standard, la ligne formule vaut toujours 0 € ; le montant de l'export s'ajoute au forfait manutention, le total ne bouge pas. Confort et Premium gardent leur montant. Le générateur refuse une spec Standard dont la ligne formule n'est pas à 0.
**Pourquoi** : la formule de base n'affiche pas de prix.
**Où** : `devis_auto.py`, `devis-pdf/generer_devis_pdf.py`, `tests/test_devis_auto.py`, `devis-pdf-samdem` § 1.
**Leçon** : une spec Standard écrite avant cette date avec une formule non nulle est refusée à la régénération : reporter le montant ou réexporter. L'export et la note de la fiche gardent le détail du calculateur.

### 2026-11-04 · Pas de « Voir inventaire » sans inventaire (Karim)
**Changement** : si la fiche coche « Pas d'inventaire » et n'a pas de liste, le PDF n'écrit rien sous le forfait transport (`sans_inventaire` dans la spec). Une fiche sans cette case et sans liste garde le renvoi, car l'inventaire peut être en pièce jointe, et la relecture affiche « inventaire absent de la fiche ».
**Pourquoi** : le client chercherait un document qui n'existe pas.
**Où** : `devis_auto.py`, `devis-pdf/generer_devis_pdf.py`, `devis-pdf-samdem` § 4.
**Leçon** : cocher « Pas d'inventaire » sur toute fiche sans liste, c'est cette case qui coupe la mention. Ne jamais fabriquer un inventaire à partir de quelques objets notés.

### 2026-11-04 · Corriger un devis déjà validé (constat)
**Changement** : aucun dans le code. `validation_devis.py --regenerer` refuse un devis validé et `joindre_pdf` ignore un fichier déjà joint du même nom.
**Pourquoi** : une correction de texte demandée après l'import n'a pas de commande prévue.
**Où** : contournement fait à la main : refaire le PDF avec `devis_auto.rendre`, déposer le fichier, puis remplacer `hs_attachment_ids` sur la note existante. L'ancien fichier reste dans le gestionnaire de fichiers HubSpot.
**Leçon** : garder le numéro seulement si le devis n'est pas encore parti chez le client ; sinon, nouvel export et nouveau numéro.

### 2026-11-04 · Fourchette de volume (constat)
**Changement** : aucun. Une consigne « fourchette entre X et Y m³ » se chiffre de deux façons : un seul devis avec `volume_max` (`devis-pdf-samdem` § Fourchette) ou deux variantes.
**Pourquoi** : `pipeline.py` n'a pas d'option de volume ; la variante à l'autre volume passe par `fiche_notion.py` → `dossier.json` corrigé → `pipeline.py <dossier> --variante`, l'identifiant de transaction suit.
**Leçon** : proposer les deux formats à la personne qui relit. Laisser le volume conservateur sur la fiche.

### 2026-11-04 · Contrôle avant génération (Karim)
**Changement** : `pipeline.py --fiche` contrôle sans rien générer, puis `--devis` une seule fois avec les mêmes options ; régénérer demande `--remplacer` et de fermer l'ancien onglet. Une seule note « Fiche client » par transaction, modifiée à chaque changement.
**Où** : `pipeline.py`, `fiche_hubspot.py`, `calcul-devis-samdem` § 1.

### 2026-11-03 · Fiche sur HubSpot, relecture avant import (Karim)
**Changement** : la fiche devient une note de la transaction, plus de création dans Notion ni d'archive dans le Sheet. Chaque export produit le PDF, relu puis validé avant d'aller sur HubSpot. Sandrine envoie le devis depuis son adresse.
**Où** : `fiche_hubspot.py`, `devis_auto.py`, `validation_devis.py`, `calcul-devis-samdem` § 13 bis.

### 2026-11-03 · Aucune trace de préparation sur un document client (Karim)
**Changement** : ni pastille, ni émoji, ni temps d'options, ni nom de variante sur un devis. Le générateur refuse une spec qui en contient.
**Pourquoi** : le client ne doit pas deviner qu'une IA a préparé le devis.
**Où** : `devis-pdf/generer_devis_pdf.py`, `devis-pdf-samdem`.

### 2026-11-03 · Plus de blocage sur la marge (Karim)
**Changement** : le garde-fou de 30,5 % est retiré. Quelle que soit la marge, le devis va jusqu'à la relecture, et la marge sous la cible y est signalée.
**Où** : `validation_devis.py`, `calcul-devis-samdem` § 13 bis.
