# 6. Gmail et routine « devis envoyé »

Durée : 10 minutes. Conseillé.

Quand Sandrine envoie un devis, avec toi en copie sur `contact@samdemenage.fr`, une routine le repère dans la boîte et passe la transaction
de « Devis en révision » à « Devis envoyé », ou « Demandes groupage » quand c'est le cas. Sans elle, tu déplaces la transaction à la main.

## 1. Connecter Gmail à Claude

1. Dans Claude Code, ouvre les réglages des connecteurs (ou sur claude.ai : **Paramètres**, **Connecteurs**).
2. Ajoute **Gmail** et connecte la boîte **`contact@samdemenage.fr`** : c'est celle qui reçoit les devis en copie.

## 2. Créer la tâche planifiée

Dans Claude Code, ouvre ce dossier et écris :

> Crée une tâche planifiée « devis-envoye-hubspot », tous les jours à 8 h et 14 h, dans ce dossier, avec le texte de `guides/routine-devis-envoye.md`.

Le PC doit être allumé et Claude Code ouvert aux heures prévues. Un passage manqué est rattrapé au suivant.

## 3. Tester

Écris : « Lance la routine devis envoyé maintenant. » Sans devis récent, elle répond « aucun nouveau devis ».

## Si l'adresse de Sandrine ou la tienne change

Les adresses sont au début de `outils/pipeline/devis_envoye.py` : le devis doit partir de l'une, avec l'autre en copie. Demande à Claude Code de les changer.

## Brouillons de mail, sur demande

C'est Sandrine qui envoie, donc Claude n'en prépare pas tout seul. Si tu envoies toi-même un devis, écris « prépare le brouillon de mail ».
Il faut alors le connecteur Gmail ci-dessus, et l'extension **Claude in Chrome** pour joindre les pièces (CGV, RIB…). Aucun mail ne part sans toi.
Les documents joints sont dans `donnees/Docs Devis SamDem/` : un document qui change (nouveau RIB…) se remplace là, sous le même nom.

Ensuite : [guide 7](07-premier-devis.md).
