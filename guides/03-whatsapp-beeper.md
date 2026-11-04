# 3. WhatsApp avec Beeper

Durée : 15 minutes. Quand tu valides un devis, le message à l'équipe et l'inventaire partent sur la conversation WhatsApp « Devis/inventaire ».
La chaîne passe par **Beeper Desktop**, une application qui regroupe tes messageries et se pilote depuis ton PC.

**Beeper doit rester ouvert** pour que le message parte. S'il est fermé, rien n'est perdu : le message attend, et tu reçois une alerte.

## 1. Installer Beeper et connecter WhatsApp

1. Installe Beeper Desktop depuis [beeper.com](https://www.beeper.com/download) et crée ton compte.
2. Dans ses réglages, ajoute le compte **WhatsApp** : il affiche un code à scanner depuis ton téléphone.
3. Vérifie que la conversation « Devis/inventaire » apparaît. Tu dois en être membre.

## 2. Créer le jeton d'accès

Dans Beeper Desktop : **Settings**, puis **Developers** (ou « API »). Active l'accès local si besoin, puis crée un jeton.
Les libellés peuvent varier selon la version ; si tu ne les trouves pas, envoie une capture à Claude Code.

Dans `.env` :

```
BEEPER_ACCESS_TOKEN=le-jeton
```

## 3. Trouver le numéro de la conversation

```bash
python verifier_installation.py --conversations
```

Cherche la ligne « Devis/inventaire ». Recopie le numéro qui la précède dans `.env` :

```
SAMDEM_WHATSAPP_CHAT=le-numero
```

Il change d'un PC à l'autre : ne reprends pas celui de quelqu'un d'autre.

## 4. Tester

```bash
python verifier_installation.py
```

Pour envoyer pour de vrai un message d'essai à l'équipe, seulement si tu le souhaites :

```bash
python outils/pipeline/notif.py "Essai de la chaîne de devis, à ignorer"
```

Ensuite : [guide 4](04-alertes-slack.md).
