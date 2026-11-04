# 1. Installer le dossier

Pour Windows. Durée : 20 minutes.

## 1. Mettre le dossier au bon endroit

Crée le dossier `C:\SamDem`. Tu dois obtenir `C:\SamDem\pipeline-sam`, avec `LISEZ-MOI.md` directement à l'intérieur. Deux façons :

- **Depuis GitHub, conseillé** : les améliorations pourront ensuite arriver d'une simple commande. Accepte d'abord l'invitation au dépôt reçue par e-mail, installe [Git pour Windows](https://git-scm.com/download/win), puis ouvre l'Invite de commandes et lance :

  ```bash
  git clone https://github.com/Kareem0330/pipeline-sam.git C:\SamDem\pipeline-sam
  ```

  Une fenêtre te demande de te connecter à GitHub la première fois. Pour récupérer une amélioration plus tard, écris à Claude Code : « Récupère la dernière version du dossier ». Tes clés et tes devis ne sont pas touchés.
- **Depuis un fichier compressé** : décompresse `pipeline-sam.zip` dans `C:\SamDem`. Si tu l'as téléchargé depuis GitHub, renomme le dossier `pipeline-sam-main` en `pipeline-sam`.

Pas de OneDrive ni de Google Drive : ils synchroniseraient tes clés et tes journaux. Pas d'accent dans le chemin.

## 2. Installer les logiciels

| Logiciel | Où le trouver | À vérifier |
|---|---|---|
| Python 3.12 | [python.org/downloads](https://www.python.org/downloads/windows/) | À l'installation, **coche « Add python.exe to PATH »** |
| Chrome ou Edge | Déjà présent en général | Il sert à fabriquer les PDF |
| Claude Code | [claude.com/claude-code](https://claude.com/claude-code) : application de bureau, onglet Code | Connecte-toi avec ton compte Claude |

Pour les inventaires écrits en texte libre, la chaîne appelle aussi la commande `claude`. Elle est vérifiée à l'étape 4 ; si elle
manque, demande à Claude Code de l'installer. Le reste de la chaîne marche sans elle.

## 3. Lancer l'installation

1. Ouvre `C:\SamDem\pipeline-sam`.
2. Double-clique sur **`installer.bat`**. Si Windows affiche un avertissement, clique sur « Informations complémentaires », puis « Exécuter quand même ».

Le script installe les modules Python, crée le fichier `.env`, installe le veilleur au démarrage de Windows et le lance. Le veilleur
surveille le presse-papier : c'est lui qui réagit quand tu cliques sur « Exporter JSON ». Il tourne en silence.

## 4. Ouvrir le dossier dans Claude Code

1. Ouvre Claude Code, onglet Code, et choisis le dossier `C:\SamDem\pipeline-sam`.
2. Écris : « Lance la vérification de l'installation. »

Tant que les clés ne sont pas posées, il reste des lignes « À FAIRE ». C'est normal. Passe au [guide 2](02-cle-hubspot.md).

## Ouvrir et remplir le fichier `.env`

Les guides suivants te demandent d'y écrire des clés. Ouvre-le avec le Bloc-notes : clic droit sur `.env`, « Ouvrir avec », « Bloc-notes ».
Écris chaque valeur juste après le `=`, sans espace ni guillemets, puis enregistre.

Si le fichier n'apparaît pas : dans l'Explorateur, menu Affichage, active « Éléments masqués ».
