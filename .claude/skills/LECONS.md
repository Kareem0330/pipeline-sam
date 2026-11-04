# Leçons — agent Sam'Déménage

Registre des erreurs, blocages et découvertes qui se reproduiront. **À lire avant de
travailler sur la chaîne fiche → volume → devis**, et à alimenter dès qu'une leçon nouvelle
apparaît.

## Quand écrire ici

Une leçon mérite une entrée si elle remplit **les deux** conditions :
1. elle a coûté du temps, ou produit un résultat faux qui aurait pu passer inaperçu ;
2. elle se reproduira — c'est un piège structurel, pas un accident ponctuel.

**Ne pas consigner** : les erreurs de frappe, les échecs corrigés du premier coup, ce qui est
déjà écrit dans un SKILL.md ou un README, ni le récit de ce qui a été fait (ça, c'est `log.md`).
Un registre qui gonfle sans discernement ne sera plus lu.

## Format

```
### [YYYY-MM-DD] Titre court
**Symptôme** — ce qu'on observe.
**Cause** — pourquoi.
**Correctif** — quoi faire. « Corrigé dans <fichier> » si c'est déjà réglé en dur.
```

Barrer une leçon (`~~titre~~`) plutôt que la supprimer quand elle devient caduque : savoir
qu'un piège a existé aide à comprendre le code qui s'en protège.

---

## Données et sources externes

### [2026-09-08] Mappy ne sait pas encoder un itinéraire à étapes dans une URL
**Symptôme** — un lien Mappy à 4 points affichait un trajet faux, sans erreur ni avertissement.
Le skill devis avait fini par interdire toute lecture de lien Mappy.
**Cause** — le format `#/recherche/A/B/C/D` charge la page en ne retenant **que les deux
premiers points** et ignore le reste silencieusement. Le vrai format,
`#/voiture/<départ>/<arrivée>/car/9`, renvoie une 404 « Route not found » au-delà de deux points.
**Correctif** — une boucle se traite en **segments indépendants** qu'on additionne, avec un
lien de vérification par segment. Ne jamais fabriquer un lien Mappy multi-points.
Corollaire (11/09/2026) : un segment « départ → étape → arrivée » vérifié par un lien départ →
arrivée ne vérifie rien — le km comptait Vaux-sur-Mer, le lien l'ignorait, en silence. Un
segment = deux points, étapes comprises. Corrigé dans `outils/pipeline/itineraire/calcul_itineraire.py`.

### [2026-09-08] La Base Adresse Nationale renvoie des adresses d'une autre commune
**Symptôme** — `12 rue des Lilas, Talence` résolu en `12 Rue de Talence, 33000 Bordeaux`,
avec un score de 0,58 et une précision `housenumber`. Rien ne signale l'erreur, et on route
vers la mauvaise ville.
**Cause** — la BAN fait du rapprochement approximatif. Ni le score ni le type de précision ne
disent que la commune ne correspond pas.
**Correctif** — comparer le code postal (ou le nom de commune) de la saisie à celui du
résultat, et lever une alerte. Corrigé dans `outils/pipeline/itineraire/calcul_itineraire.py`
(`_commune_coherente`). Ne jamais se fier au seul score.

### [2026-09-08] Les propriétés Notion vides sont absentes du JSON
**Symptôme** — une propriété `select` non renseignée n'apparaît pas dans le retour de
`notion-fetch` sur une page : elle semble ne pas exister.
**Cause** — l'API omet les propriétés vides plutôt que de les renvoyer nulles.
**Correctif** — pour connaître le schéma réel, interroger **la base**, jamais une page seule.
C'est ce qui avait fait oublier « Mois de création » sur une fiche en septembre 2026.

### [2026-09-08] Une intégration Notion créée n'a aucun accès
**Symptôme** — token valide, mais l'API répond 404 sur chaque page.
**Cause** — créer l'intégration ne suffit pas : il faut l'autoriser sur la base
(base > ••• > Connexions). Le 404 ne le dit pas.
**Correctif** — `export.py --test` vérifie l'accès à la base et affiche cette explication.

### [2026-09-08] Le volume est dans le corps de la fiche, pas dans la propriété
**Symptôme** — `Volume (m3)` vide sur la fiche VASSE Romain alors que son corps annonce 14 m³.
Audit : **40 fiches sur 200** dans ce cas.
**Cause** — la saisie se fait dans le texte libre, la propriété n'est pas toujours reportée.
**Correctif** — ne jamais conclure qu'une donnée manque en lisant les seules propriétés.
Une fiche avec inventaire et sans volume relève de l'estimation interne
(`ESTIMATION_REQUISE`), pas d'une relance client. Généralisé le 08/09/2026 : le corps fait
foi sur **tous** les champs, les propriétés ne sont qu'un repli — `fiche_notion.py`.

### [2026-09-08] Un volume composite réduit à son premier nombre
**Symptôme** — fiche DIDRICH : « 7 m3 (mission directe) + 40 m3 (garde-meuble) = 47 m3
total ». Un parseur qui prend le premier nombre chiffre 7 m³ au lieu de 47 — facteur 7 sur
le prix, sans rien qui alerte.
**Cause** — une fiche porte parfois **deux missions**, et la ligne volume les additionne.
**Correctif** — chercher toutes les occurrences `<n> m3`, et si elles sont plusieurs, retenir
celle qui jouxte « total » ou « = ». Sans mention de total : rendre `None` et le dire, jamais
choisir. Corrigé dans `fiche_notion.py` (`_lire_volume`).

### [2026-09-08] Un bloc Notion peut contenir plusieurs lignes
**Symptôme** — portage départ lu **15 m au lieu de 25 m** sur la fiche ARAUJO Julia. Silencieux :
un portage sous-évalué sort un devis moins cher, sans rien qui alerte.
**Cause** — « Distance de portage : / Entrée … 15 m / Intérieur … 10 m » saisi avec des
**sauts de ligne internes** (Maj+Entrée) est **un seul bloc** côté API. Un parseur qui traite
un bloc comme une ligne ne voit que ce qui suit le premier « : », et perd le reste.
**Correctif** — découper le texte de chaque bloc sur `\n` avant d'analyser, en ne mettant le
préfixe (`- [x] `, `### `) que sur la première sous-ligne. Corrigé dans `fiche_notion.py`
(`lire_corps`). Plus largement : « un bloc » et « une ligne » ne sont pas la même unité.

### [2026-09-08] Une fiche client peut porter PLUSIEURS blocs de chiffrage
**Symptôme** — la fiche DROZAC Rodrigo porte deux blocs complets (le devis principal, puis un
« 🔀 Version Standard » sous un titre). Un script qui cherche « le » bloc de chiffrage et écrit
dans le premier trouvé écrase un devis valide, sans rien signaler.
**Cause** — le modèle de fiche n'interdit pas la duplication du bloc ; les variantes de scénario
et les devis successifs s'empilent sur la même page.
**Correctif** — `finalisation.reperer_blocs()` rend **la liste** des blocs (bornes + titre du
heading juste au-dessus), écrit dans le **dernier** par défaut et affiche toujours combien il en
a trouvé ; `--bloc N` choisit. Règle générale sur ces fiches : ne jamais supposer l'unicité d'une
section, la compter et le dire.

### [2026-09-08] Une donnée présente des deux côtés n'est pas comparable telle quelle
**Symptôme** — l'audit corps/propriétés annonçait des dizaines de fausses divergences :
« Cenon (33150) — 20 Av. Jean Jaurès » ≠ « 20 Av. Jean Jaurès, 33150 Cenon », portage 40 m
(somme) ≠ « Entrée : < 30 / Intérieur : < 10 » (composantes), « 🟡 x@y.fr » ≠ « x@y.fr ».
**Cause** — comparer caractère par caractère deux écritures d'une même valeur.
**Correctif** — comparer selon la nature du champ : jeu de mots pour une adresse, somme pour
un portage, pastille 🟡 retirée pour un texte. Un détecteur de divergence qui crie tout le
temps ne sera plus lu — c'est le même piège que le diagnostic qui ne peut pas échouer.

---

### [2026-09-11] La BAN ignore certaines voies et renvoie une rue voisine de la même commune
**Symptôme** — « 12 Allée Maurice Carême, 95100 Argenteuil », adresse réelle, géocodée en
« 12 Avenue Maurice Utrillo », à ~900 m : précision `housenumber`, score 0,53, **bonne
commune** — le contrôle de commune de l'entrée du 08/09 ne voit rien. Route et créneau calculés
au mauvais endroit ; pire, le score bas a fait demander à la cliente de confirmer une adresse
juste.
**Cause** — la BAN est incomplète sur les voies privées et les lotissements récents ; faute de
la voie, elle rend la rue la plus ressemblante sans le signaler. OpenStreetMap connaît l'allée.
**Correctif** — vérifier que le **nom de la voie** rendu correspond à la saisie (type compris),
basculer sur OpenStreetMap sinon, et à défaut calculer sur le centre de la commune — jamais sur
une autre rue. Ne jamais juger une adresse sur le score. Séparer « adresse client incomplète »
(on lui écrit) de « notre point est approximatif » (alerte interne). Corrigé dans
`outils/Groupage/geo.py` et `outils/Groupage/regles_groupage.py`.

### [2026-09-11] « 🟡 Péage à renseigner (classe 3 ÷ 1,2) » relu comme un péage de 3 €
**Symptôme** — fiche ZYKE Alan (Bordeaux → Perpignan, A/R > 19h06) : le devis généré portait
`peageAR = 3`, sans alerte. Le péage, qui doit être demandé à Karim, passait pour renseigné.
**Cause** — le parseur prenait le premier nombre de la ligne « Péage HT », et la mention que le
skill `creer-fiche-client-samdem` prescrit mot pour mot contient « classe 3 ». Chaque fiche
longue distance avec péage tombait dans le piège.
Second piège derrière le premier : relu depuis la fiche, `peage_requis` se déduisait du « Temps
A/R » (10h15 < 19h06), or ce temps est celui de l'itinéraire **avec** péage, déjà retenu par le
module. Le péage serait passé à 0 sans question.
**Correctif** — une ligne « Péage HT » portant 🟡 ne donne aucun montant, elle remonte en
alerte **et** force `peage_requis`. Corrigé dans `fiche_notion.py`. Plus largement : une mention
d'attente qui contient un chiffre ne doit jamais passer par `_premier_nombre`, et un temps relu
dans une fiche ne dit pas quel itinéraire l'a produit.

### [2026-09-11] Une mention 🟡 accolée à l'adresse fait échouer tout l'itinéraire
**Symptôme** — variante directe de PREMUTICO Laura : « Manque : itinéraire ». Avec
`--malgre-manques`, un devis Paris → Bordeaux sortait à **0 km** (forfait de déplacement), sans
autre signal qu'une ligne du rapport.
**Cause** — l'adresse d'arrivée relue dans la fiche était « Bordeaux — 🟡 adresse à compléter ».
Envoyée telle quelle, la BAN rend un score de 0,32 : géocodage refusé, itinéraire en `echec`. La
trame de fiche accole ce type de mention à l'adresse sur chaque dossier incomplet.
**Correctif** — `pipeline._adresse_routable()` coupe l'adresse à la première mention (« — » ou
🟡) avant le routage, et `--malgre-manques` ne force jamais sans volume **ni itinéraire** : un
0 km n'est pas une hypothèse. Corrigé dans `pipeline.py`. Au passage : Valhalla ne donne **pas**
le prix d'un péage — ses manœuvres `toll` disent combien de km passent sur autoroute à péage, et
son `cost` est un poids de routage, pas des euros.

### [2026-09-11] noCRM avale les lignes vides d'une description
**Symptôme** — description de SION Arthur recopiée depuis Notion avec 19 lignes vides ; relue
dans noCRM : 0 ligne vide, un seul bloc illisible. La relecture de contrôle a pourtant validé
l'écriture.
**Cause** — noCRM supprime les lignes vides à l'enregistrement (3 899 caractères envoyés, 3 880
stockés). Les espaces insécables et les traits `____` passent. Le contrôle ne pouvait rien voir :
`_norme()` normalise justement les espaces avant de comparer.
**Correctif** — abandonner l'espacement. Essayé le même jour : une ligne ne portant qu'un espace
insécable est bien stockée à l'identique, mais noCRM l'affiche comme un retrait de la ligne
suivante. La séparation passe par les titres de section, en gras Unicode entre deux filets
(`gras()` : noCRM n'interprète aucune mise en forme, le gras doit être dans les caractères).
Corrigé dans `nocrm.corps_notion()`. Règle : un contrôle qui normalise les espaces ne valide
jamais une mise en page, et un texte brut relu identique ne dit rien du rendu — regarder l'écran.

### [2026-09-15] L'id d'une URL Notion ne se cherche pas après retrait des tirets
**Symptôme** — `id_depuis_url("…/p/VIGNERON-Lucile-3d52…62eb")` rendait `e3d52…62e` : 404 à la
lecture de la fiche, et la ligne d'archive du Sheet partait sans réf. CLI, date, téléphone ni
adresses (elle aurait été ajoutée en doublon). Aucune erreur visible.
**Cause** — l'ancien parseur retirait les tirets puis prenait le dernier bloc de 32 hex : toute
lettre a–f ou tout chiffre en fin de slug se colle à l'id (Lucile, Solenne, Myanna, Laura,
`NEXTORIES-2026083844-11-09-…`), et une URL `?v=` rendait l'id de la **vue**. Touche une bonne
part des noms de clients.
**Correctif** — ancrer en fin de chemin (requête et fragment ôtés) : 32 hex ou UUID à tirets.
Corrigé dans `pipeline/fiche_notion.py` et ses copies `Groupage/lib`, `Workflow NextStories/lib` ;
test `pipeline/tests/test_id_depuis_url.py` (vérifie aussi les copies). Les exports passés
n'étaient pas touchés : leur `page_id` vient de l'API, pas de l'URL — préférer toujours ce
`page_id` à un id re-déduit d'un lien.

### [2026-09-18] « 0,5h » relu comme 5 heures de démontage
**Symptôme** — `nb_heures("0,5h")` rendait `5.0` (« 1h », « 30 min », « 0h30 » justes). « Lit double
(structure) - 0,5h » arrivait au calculateur en 5 h de démontage ; une fiche type à trois éléments
décimaux sortait 35 h au lieu de 4,25 h. Aucune alerte.
**Cause** — la regex des heures ne lisait que des entiers (`(\d+)\s*h`) : la recherche sautait
« 0, » et prenait le « 5 » collé au « h ». La virgule décimale française est la saisie naturelle.
**Correctif** — décimales à virgule ou point lues avant « h / heure(s) » dans `nb_heures`, et la
détection « durée écrite » des lignes de démontage accepte « heures ». Corrigé dans
`pipeline/fiche_notion.py` et sa copie `Workflow NextStories/lib` ; test
`pipeline/tests/test_nb_heures.py`. **La copie `Groupage/lib/fiche_notion.py` a toujours le défaut**
(non resynchronisée). Règle : toute regex qui lit un nombre sur une fiche accepte `\d+(?:[.,]\d+)?`
— un entier seul prend la partie décimale pour le nombre.

## Écriture de code

### [2026-09-08] `urlencode` casse les API qui attendent du JSON en query string
**Symptôme** — Valhalla répondait `400 Failed to parse json request`, alors que la même
requête passait en `curl`.
**Cause** — `urllib.parse.urlencode` encode les espaces en `+`, que le serveur ne relit pas
comme des espaces : le JSON reçu est invalide.
**Correctif** — `quote(json.dumps(payload, separators=(",", ":")), safe="")`. Les séparateurs
compacts suppriment le problème à la source.

### [2026-09-08] Un cache indexé sur la saisie brute ne sert jamais
**Symptôme** — le cache d'axes s'écrivait mais n'était jamais relu, et les lignes se
dupliquaient.
**Cause** — la clé était bâtie sur ce que l'utilisateur avait tapé, alors que le fichier
stockait l'adresse normalisée. Les deux ne coïncident jamais.
**Correctif** — géocoder **avant** d'interroger le cache, et indexer sur l'adresse normalisée,
en neutralisant casse, accents et ponctuation.

### [2026-09-08] Un diagnostic qui valide ses propres valeurs d'exemple
**Symptôme** — `--test` annonçait « défini » sur un fichier de configuration encore rempli de
placeholders.
**Cause** — le test vérifiait la présence de la clé, pas la plausibilité de sa valeur.
**Correctif** — détecter les valeurs gabarit et le dire. Plus largement : un diagnostic qui ne
peut pas échouer ne diagnostique rien.

### [2026-09-08] PowerShell rend le presse-papier dans la page de codes de la console
**Symptôme** — `finalisation.py --presse-papier` échouait sur `Expecting ',' delimiter: line 114`
alors que le même JSON, lu depuis un fichier, passait sans broncher. Message incompréhensible :
rien n'indique un problème d'encodage.
**Cause** — `powershell -Command "Get-Clipboard -Raw"` écrit sur stdout dans **cp1252**, pas en
UTF-8. Le tiret cadratin de « Affaire validée — dans les critères » ressort en `?"` : le guillemet
parasite ferme la chaîne JSON. Seuls les dossiers contenant un caractère hors ASCII cassent —
c'est-à-dire presque tous, mais pas les jeux de test.
**Correctif** — préfixer la commande par `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.
Corrigé dans `finalisation.lire_presse_papier()`. Vaut pour **tout** appel PowerShell dont on
capture la sortie depuis Python.

### [2026-09-08] `/tmp` n'existe pas pour Python sous Git Bash
**Symptôme** — une redirection shell vers `/tmp/x.json` réussit, puis `open('/tmp/x.json')`
lève `FileNotFoundError`.
**Cause** — Git Bash simule `/tmp` ; Python voit un chemin Windows inexistant.
**Correctif** — utiliser le répertoire scratchpad de la session pour tout fichier temporaire.

### [2026-09-08] Heredoc bash en échec sur un gros contenu accentué
**Symptôme** — `cat > fichier <<'EOF'` avec plusieurs centaines de lignes de markdown
français échoue sur `unexpected EOF`.
**Correctif** — écrire les fichiers volumineux avec l'outil Write, pas par heredoc.

### [2026-09-09] Un ternaire multi-lignes ne se patche pas par morceaux
**Symptôme** — `badgeFor()` réduit de trois à deux branches par deux remplacements de chaînes
indépendants : la troisième ligne (`: "envoi bloqué…"`) est restée orpheline, produisant
`cond ? a : b : c` — JavaScript invalide, page morte.
**Cause** — chaque remplacement pris isolément trouvait bien sa cible ; c'est leur composition qui
était fausse. Une assertion « la chaîne existe » ne dit rien de la validité du résultat.
**Correctif** — pour une expression qui s'étend sur plusieurs lignes, remplacer **le bloc entier**
(repérage première ligne → dernière ligne, réécriture complète), jamais des fragments. Et faire
suivre toute édition de calculateur d'un passage du banc `bun` : une page HTML cassée ne signale
rien tant qu'on ne l'exécute pas.

### [2026-09-09] `0.07 * 100` vaut `7.000000000000001` en JavaScript
**Symptôme** — un libellé construit par `` `Commission ${taux * 100} %` `` afficherait
« Commission 7.000000000000001 % » sur un devis client. Passé inaperçu tant que le taux valait
0,10 (`0.10 * 100 === 10` tombe juste) ; 0,05 et 0,07 ne tombent pas juste.
**Cause** — flottants binaires. Le piège n'apparaît que sur certains taux, donc il dort jusqu'au
jour où on change la valeur.
**Correctif** — helper `pctTaux(t) { return Math.round(t * 1000) / 10; }` dans les calculateurs.
Ne jamais afficher un pourcentage par simple multiplication par 100.

---

## Règles métier — pièges de cohérence

### [2026-09-18] La case « Rdc » écrasait l'étage écrit : maisons R+X chiffrées de plain-pied
**Symptôme** — BARONDIOT (maison, « Rdc » coché + « Étage sans ascenseur : R+1 ») sortait
`etageDepart = 0`. La règle de fiche fait cocher « Rdc » en plus du type de logement : **toute
maison à étage** était donc chiffrée comme un plain-pied, sans alerte.
**Correctif** — `pipeline.py` : un étage écrit prime, la case Rdc ne vaut 0 que si l'étage est
vide (l'intention de `_etage_connu`). Chiffrages antérieurs de maisons R+X : vérifier l'étage.

### [2026-09-08] Trois barèmes monte-meuble coexistaient
**Symptôme** — le prompt maître (200/350/400 € HT), le skill (180/300/360) et le calculateur
(300/360 par côté) donnaient trois prix différents pour la même prestation.
**Correctif** — barème unique arbitré par Karim : **180 / 300 / 360 € HT, par côté**
(départ et arrivée facturés séparément). *Mise à jour 2026-10-05 (Karim) : palier à 180 € retiré —
barème = celui du calculateur, **300 € HT (2 h) / 360 € HT (demi-journée)** par côté.* Avant de chiffrer une option rare, vérifier qu'une
seule source fait foi.

### [2026-09-08] Un skill renvoyait à un fichier qui n'a jamais existé
**Symptôme** — `creer-fiche-client-samdem` disait « voir `references/regles-remplissage.md`
pour l'ensemble des règles détaillées ». Le fichier était introuvable.
**Cause** — le skill avait été résumé sans que son annexe soit créée. À l'exécution, les
règles détaillées étaient donc simplement absentes.
**Correctif** — fichier reconstitué depuis le prompt maître. Vérifier qu'un chemin cité dans
un skill existe réellement.

### [2026-09-08] Les seuils calés sur un outil ne valent pas pour un autre
**Symptôme** — le seuil « sans péage sous 18 h », défini en lisant Mappy, faisait basculer
Bordeaux–Paris du mauvais côté une fois calculé en profil poids lourd (~12 % plus lent).
**Cause** — un seuil hérite implicitement de l'outil qui a servi à le fixer.
**Correctif** — seuil relevé à 19h06. Quand on change d'outil de mesure, revérifier tous les
seuils exprimés dans son unité.

### [2026-09-09] L'assiette de la commission ne correspondait pas à la règle énoncée
**Symptôme** — Karim demande de « vérifier » que la commission porte bien sur transport +
manutention + options. Trois écarts silencieux : les manutentions **garde-meuble / point 2 /
point 3** n'étaient pas dans l'assiette, la **route longue distance** non plus alors que le
**forfait trajet court** — même nature — y était.
**Cause** — une assiette écrite en dur comme une somme de six termes, jamais recontrôlée quand
de nouveaux postes (étapes, points 2/3) ont été ajoutés au moteur. Rien ne signale l'oubli :
le total du devis reste juste, seul le montant de la commission est faux.
**Correctif** — assiette explicitée à 11 termes dans les quatre calculateurs, et **contrôle
d'exhaustivité** à rejouer après toute évolution du moteur : `assiette + postes hors assiette
= total HT avant commission`, à l'euro près. Tout poste nouveau tombe forcément d'un côté ou de
l'autre. Règle et exclusions : `wiki/concepts/commission-devis.md`.

### [2026-09-09] Un fichier local modifié ≠ un outil modifié — republier l'artefact
**Symptôme** — trois calculateurs corrigés, vérifiés, documentés ; Karim rouvre son outil et voit
toujours l'ancienne règle. « Je t'avais demandé de la supprimer. »
**Cause** — Karim n'utilise pas les fichiers du vault, il utilise les **artefacts publiés**.
`outils/*.html` est la source ; l'artefact est le produit. Modifier l'un ne touche pas l'autre.
**Correctif** — toute évolution d'un calculateur se termine par la republication des artefacts
concernés (maître `a65f888c…`, atelier `6f9300e7…`, terrain `39de3ff2…`), sinon on annonce
explicitement qu'elle **reste à faire** et on ne présente pas le changement comme livré.
`Artifact action:"list"` donne la date de dernière mise à jour de chacun — un coup d'œil suffit à
voir qu'un artefact a décroché. Republier exige d'avoir lu la version en ligne en entier :
prévoir le coût, et en profiter pour `diff` la version publiée contre le fichier local (le seul
écart attendu, ce sont les modifications du jour).

### [2026-09-09] Commission et marge sont deux assiettes différentes
**Symptôme** — consigne « compter dans la marge la manutention aux étapes / points ». Interprétée
littéralement, elle aurait modifié la formule de marge de tous les devis.
**Cause** — les deux calculs se ressemblent (tous deux partent du transport) mais n'ont rien à voir.
**Assiette de la commission** = transport + toute la manutention + masse salariale de route +
options. **Marge proxy** = transport + 15 % des options (25 % en Premium) + marge de la prime de
dimanche — **la manutention n'y entre jamais**, cohérent avec une MO facturée 28 €/h pour un coût
de 25-28 €/h.
**Correctif** — devant une consigne qui touche « la marge » ou « la commission », vérifier de
laquelle des deux assiettes il s'agit **avant** de coder. Conséquence contre-intuitive à retenir :
ajouter de la manutention **augmente** l'assiette de commission et **fait baisser** le taux de
marge. Règle et tableau comparatif : `wiki/concepts/commission-devis.md`.

### [2026-09-09] Retirer la commission fait *monter* le taux de marge affiché
**Symptôme** — commission supprimée du devis, le badge de marge passe de 34,7 % à 35,9 % sur le
même dossier. Contre-intuitif : le prix a baissé.
**Cause** — la commission n'entre pas dans la marge proxy (`marge = transport + marge fixe hors
transport`) mais **au dénominateur** : elle est ajoutée au-dessus du total HT. La supprimer réduit
le total HT sans toucher le numérateur.
**Correctif** — ne jamais toucher au taux de commission sans réviser la cible de marge dans le
même mouvement (ici 32 % → 35 %), sinon la cible devient trivialement atteignable et cesse de
filtrer quoi que ce soit. Voir `wiki/concepts/marge-cible.md`.

---

## Environnement

### [2026-09-08] Les skills ne sont découverts qu'à des emplacements imposés
**Symptôme** — un dossier `SKILLS/` à la racine du vault serait plus visible, mais ne serait
jamais chargé.
**Correctif** — `.claude/skills/<nom>/SKILL.md`, avec `name` et `description` en frontmatter.
Le dossier peut embarquer ses fichiers compagnons (`references/`, scripts).

### [2026-09-08] Les suppressions de fichiers sont refusées par les permissions
**Symptôme** — `rm` refusé plusieurs fois, laissant des fichiers de test derrière.
**Correctif** — ne pas réessayer : lister les fichiers à retirer dans la réponse pour que
Karim les supprime, ou écrire par-dessus quand c'est possible.

### [2026-09-09] `open(chemin, "w")` tronque le fichier AVANT de valider ses arguments
**Symptôme** — `io.open(p, "w", encoding="utf-8", newline="\n")` (antislash doublé par erreur
dans un script de patch) a levé `ValueError: illegal newline value`. Le fichier cible,
`outils/pipeline/finalisation.py`, s'est retrouvé à **0 octet** : ouvert et tronqué avant que
l'argument `newline` ne soit vérifié. Aucun git dans le vault → source perdue localement.
**Cause** — un script de patch qui écrit directement sur le fichier de production. L'ouverture
en `"w"` détruit l'original avant même que le contenu ne soit produit.
**Correctif** — dans tout script qui réécrit un fichier existant : écrire dans un fichier
temporaire (`<cible>.tmp`) puis `os.replace()`, ou faire une copie de sauvegarde avant. Ne
jamais ouvrir la cible en `"w"` tant que le nouveau contenu n'est pas entièrement en mémoire
ET l'appel validé. Récupération : historique de versions OneDrive (clic droit sur le fichier
dans l'Explorateur → « Historique des versions »).

### [2026-10-14] Un patch Python réécrit tout le fichier en fins de ligne Windows
**Symptôme** — après des correctifs par script (`open(p, encoding="utf-8").read()` puis
`open(tmp, "w", encoding="utf-8").write(s)`), `git diff` montrait le calculateur maître et
plusieurs `.py` entièrement modifiés (1 900 lignes pour une retouche de 40), et un `patch`
appliqué ensuite sur une copie en LF échouait sur les 26 blocs (« different line endings »).
**Cause** — sous Windows, Python en mode texte traduit `\n` en `\r\n` à l'écriture. Le dépôt
mélange les deux conventions : la plupart des fichiers sont en LF, `fiche_notion.py` en CRLF.
**Correctif** — lire et écrire avec `newline=""` (conserve les fins de ligne d'origine), ou en
binaire. Après un patch, contrôler `git diff --stat` : un nombre de lignes disproportionné
signale une conversion, à annuler avant de continuer.

### [2026-10-09] `SystemExit` passe à travers le filet `except Exception`
**Symptôme** — une coupure réseau pendant l'écriture du bloc de chiffrage Notion arrêtait la
finalisation (code 1 dans `devis-export.log`) **sans alerte Slack**, alors que `_main_protege()`
est censé prévenir de toute erreur imprévue.
**Cause** — `ecrire_blocs()` et `ajouter_blocs()` signalent leurs échecs par `raise SystemExit(...)`.
`SystemExit` hérite de `BaseException`, pas d'`Exception` : le filet ne le voit pas.
**Correctif** — chaque étape passe par `reprise.executer()`, qui rattrape `(Exception, SystemExit)`,
relance les pannes passagères et alerte sur le reste. Règle : un `raise SystemExit` dans une
fonction appelée en cours de traitement contourne tout `except Exception` en amont — le réserver
aux erreurs de saisie au démarrage du script.

### [2026-10-09] HubSpot : une relance immédiate ne retrouve pas ce qu'on vient de créer
**Symptôme** — risque de doublon (contact + transaction) quand une étape HubSpot est relancée
dans la seconde après une coupure survenue juste après une création.
**Cause** — `/search` interroge un index qui a quelques secondes de retard sur les créations.
**Correctif** — `hubspot_crm._CREES` garde en mémoire, pour le processus, les contacts et
transactions créés par dossier ; `avancer_dossier()` s'en sert quand la recherche ne trouve rien.
Les notes et tâches sont lues par les associations, qui ne souffrent pas de ce retard.

### [2026-09-09] noCRM accepte `?query=` puis l'ignore — silencieusement
**Symptôme** — `GET /leads?query=VIGNERON` répond 200 avec une liste de leads… qui n'ont rien
à voir : ce sont simplement les plus récents. Idem `?search=`, `?q=`, `?title=`. Le paramètre
`?fields=` est ignoré de la même façon (réponse complète).
**Cause** — l'API v2 n'a pas de recherche serveur, et ne renvoie pas d'erreur pour un
paramètre inconnu. Un code qui prend le premier résultat pour « le bon lead » déplacerait un
dossier au hasard, sans rien signaler.
**Correctif** — pagination + filtre local (`nocrm.py`), appariement par téléphone d'abord.
Règle générale : quand une API répond 200 à un filtre, **vérifier que le filtre a filtré**,
sur un cas dont on connaît la réponse — un 200 ne prouve rien.

### [2026-10-05] noCRM ignore `?page=` : la « pagination » relisait 100 fois les mêmes dossiers
**Symptôme** — `GET /leads?page=1..10&limit=100` : 1 000 résultats, **100 uniques**. Aucune
erreur, aucun écart visible : `chercher_lead` (PAGES_MAX = 8) ne balayait en réalité que les
100 dossiers les plus récemment modifiés sur 691 — un client plus ancien n'était jamais
trouvé, et l'enrichissement pouvait **créer un doublon** d'opportunité.
**Cause** — `page` n'est pas un paramètre de l'API v2 ; comme pour `?query=`, elle l'accepte
puis l'ignore. La boucle ne s'arrêtait que sur `PAGES_MAX`, jamais sur un lot court.
**Correctif** — `?offset=` (0, 100, 200…), via `nocrm.lots_leads()` : arrêt sur lot court
**ou** lot sans id nouveau (garde-fou quota). Corrigé dans `outils/pipeline/nocrm.py`,
`gros_dossiers.py`, `relances-quotidiennes/relances.py` et les copies `lib/nocrm.py`.
Règle : une pagination se teste en **comptant les ids uniques** sur deux lots, pas les lignes.

### [2026-09-10] noCRM ignore aussi un champ inconnu en ÉCRITURE, et répond 200
**Symptôme** — `PUT /leads/<id>` avec `{"zzz_champ_inexistant": 1}` répond **200** et rend le
lead complet, inchangé. Rien ne distingue cette réponse de celle d'une écriture réussie.
**Cause** — même indulgence que sur les paramètres de requête (`?query=`, `?step_id=`), mais
côté écriture, donc bien plus coûteuse : une faute de frappe dans un nom de champ produit un
succès apparent à **chaque dossier**, indéfiniment.
**Correctif** — toute écriture est suivie d'une **relecture qui compare champ par champ** ce
qui a été envoyé à ce qui est revenu. `nocrm.enrichir()` rend `(ok, faits, écarts)` sur ce
principe. Comparer les textes en normalisant les espaces : noCRM re-rend la description
(insécables, retours à la ligne) et un octet d'écart ne prouve rien.

### [2026-09-10] Redéployer un Apps Script ne lui accorde pas les nouvelles autorisations
**Symptôme** — action `alerte` ajoutée à la Web App, script redéployé en nouvelle version,
et l'envoi échoue quand même : « autorisations requises ». Rien dans la procédure de
déploiement ne mentionne d'autorisation.
**Cause** — Apps Script fige le périmètre OAuth au moment où l'utilisateur **autorise** le
script, pas au moment où on le déploie. Le script d'origine ne touchait qu'au tableur : il
n'avait que le périmètre « feuilles de calcul ». `MailApp.sendEmail` en demande un nouveau,
et **seul un lancement manuel depuis l'éditeur** ouvre l'écran de consentement.
**Correctif** — fonction `autoriser()` dans `apps_script_devis.gs` : la lancer une fois
depuis l'éditeur (Exécuter → Examiner les autorisations → Paramètres avancés → Accéder à…
(non sécurisé) → Autoriser), vérifier l'e-mail de confirmation, **puis** redéployer. Vaut
pour toute évolution de ce script qui touche à un nouveau service Google (Drive, Agenda,
Docs…). Vérifier aussi que le déploiement reste en « Exécuter en tant que : moi » — en
« l'utilisateur qui accède », l'envoi se ferait au nom d'un anonyme et serait refusé.

### [2026-09-10] Un accusé de réception générique valide une action qui n'a pas eu lieu
**Symptôme** — la nouvelle action `alerte` de la Web App Apps Script « fonctionnait » avant
même que le script ne soit redéployé : l'ancienne version, qui ne connaît que l'archivage,
lisait `corps.lignes` (indéfini), n'écrivait rien, et répondait `{ok: true}`. Une alerte
d'incident aurait donc été comptée comme envoyée — et on ne s'en serait aperçu que le jour
d'un vrai incident, c'est-à-dire au pire moment.
**Cause** — `ok: true` dit « la requête a été comprise », pas « ton action a été faite ».
**Correctif** — faire répondre à chaque nouvelle action un **accusé qui lui est propre**
(`{ok: true, alerte: true}`) et n'accepter que celui-là. Règle générale : quand on ajoute une
action à un service déjà déployé, prévoir comment l'ANCIENNE version répondra — elle tournera
encore un moment.

### [2026-09-09] Sur noCRM, `?step_id=` est ignoré — c'est `?step=` qui filtre
**Symptôme** — `GET /leads?step_id=730698` répond 200 avec les leads les plus récents, toutes
colonnes confondues. Vérifié : les résultats portaient « A relancer », « Visites fixées »,
« Contacté ».
**Correctif** — `?step=730698` (ou `?step=Trajets Axe Paris`) filtre correctement : 8 leads,
tous en « Trajets Axe Paris ». Le skill `/etat-axe-paris` utilise déjà la bonne forme ; c'est
la mémoire `nocrm-acces` qui portait la mauvaise, corrigée le 09/09/2026.

### [2026-09-10] Le champ `amount` de noCRM est vide sur la moitié des leads
**Symptôme** — un filtre « devis > 2 500 € » bâti sur `lead["amount"]` ne remontait que 5 des
10 gros dossiers en attente. Les absents (LELEIVAI 4 094 €, ADJIMI 4 559 €, ROSSET 3 490 €,
CHARENSAC 2 992 €, LE MINEZ 2 695 €) avaient bien un devis chiffré — mais `amount: null`.
**Cause** — le prix est saisi dans le **corps** de la fiche (`Prix Total : … € TTC`), pas dans
le champ montant de l'opportunité, qui n'est renseigné que quand `finalisation.py` est passé.
Sur 39 leads des colonnes devis, 17 seulement portaient un `amount`. Même piège que
[[notion-fiches-client-corps-texte]] : **le corps fait foi, la propriété est un repli**.
**Correctif** — `outils/pipeline/gros_dossiers.py` lit les deux et garde le **maximum** :
plusieurs lignes `Prix Total` = plusieurs variantes du même devis (avec/sans piano, deux
scénarios), et c'est la variante haute qui décide si le dossier est « gros ». Corollaire :
`amount` est du **TTC**, un seuil comparé à ce champ s'entend donc TTC.

### [2026-09-10] Une marge « exactement à la cible » ne l'est pas en flottant
**Symptôme** — en calant automatiquement les devis Next Stories à 21 %, le solveur de marge
(§6.2) ressort parfois `0.20999999999999996` au lieu de `0.21`. Avec la comparaison stricte
d'origine (`marge >= plancher`), **chaque** devis NS serait tombé en « envoi bloqué », et
`finalisation.py` aurait exigé `--forcer-marge` — pour 4e-17 d'écart.
**Cause** — le solveur reconstruit la marge à partir d'un transport calculé (`T + Mopt` divisé
par un HT recomposé) : le résultat est égal à la cible en algèbre, pas en IEEE 754. Vaut pour
toute cible posée par un solveur, pas seulement 21 % — les puces 30,5 % et 35 % portaient le
même risque latent.
**Correctif** — toute comparaison de marge à un seuil passe par une tolérance : `margeAtteint(m,
seuil)` côté HTML, `regles.EPS_MARGE` (1e-9) côté Python. Règle générale : un seuil qu'un
solveur est censé **atteindre** se teste avec une tolérance ; un seuil qu'on doit **dépasser**
peut rester strict.

### [2026-09-11] Les antislashs ne survivent pas aux scripts passés en heredoc dans l'outil Bash
**Symptôme** — une regex `r"\b\d{5}\b"` écrite par un patch Python en heredoc s'est retrouvée
dans le fichier avec des caractères de contrôle (`^H`) à la place de `\b` : la fonction
renvoyait faux sur toutes les adresses, sans erreur. D'autres patches du même type ont échoué
au lancement (« unexpected EOF while looking for matching `'` »).
**Cause** — la commande traverse une couche de citation shell qui réinterprète les antislashs ;
dans une chaîne Python non brute, `\b` devient en plus un retour arrière.
**Correctif** — tout script contenant des antislashs s'écrit avec l'outil **Write**, puis
s'exécute ; dans le script, chaînes brutes (`r'...'`). Après un patch de regex, contrôler le
fichier avec `cat -A`.

### [2026-09-11] Un veilleur relancé depuis l'outil Bash meurt avec la commande
**Symptôme** — veilleur du presse-papier arrêté puis relancé (`Start-Process`, ou le `.bat` du
dossier Démarrage) depuis une session Claude : le processus apparaît, puis disparaît sans rien
écrire au journal. Plus aucun export n'est traité, et rien ne le signale.
**Cause** — les processus lancés par l'outil Bash restent attachés à la commande qui les a
créés et sont tués quand elle se termine. `timeout N powershell -File ...` a le même effet, et
laisse en plus le mutex du veilleur abandonné.
**Correctif** — relancer hors de la session :
`Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = '...'}`,
puis vérifier **10 s plus tard** la ligne « Surveillance du presse-papier demarree » dans
`.claude/scripts/devis-export.log`. Un processus visible ne prouve pas qu'il tourne ; la ligne
de journal, si. Ne jamais arrêter un veilleur sans avoir ce moyen de le relancer.

### [2026-09-15] noCRM efface le montant quand on passe une opportunité en « gagnée »
**Symptôme** — `PUT /leads/<id>` avec `{"status":"won"}` répond 200 ; à la relecture, le statut
est bien `won` mais `amount` est revenu à `null` (812 € perdus sur LAMBERT Guillaume).
**Cause** — noCRM remet le montant à zéro lors du changement de statut, sans le signaler.
**Correctif** — après tout passage en `won`, renvoyer `{"amount": <TTC>}` puis relire. Le
passage en gagné efface aussi le rappel (`remind_date` à null), ce qui est voulu pour un
dossier conclu.

### [2026-09-25] Une rue interdite aux PL faisait tomber TOUT l'itinéraire
**Symptôme** — LOURADOUR (Bordeaux → Bordeaux, 2 km) : `calcul_itineraire.py` rendait
« 🟡 Itinéraire à renseigner manuellement — Routage impossible : HTTP Error 400 ». Le même
module marchait sur Paris → Talence la minute d'après. Trois relances, même résultat.
**Cause** — deux pièges superposés. (1) Valhalla refuse d'**entrer** dans la rue René Roy de
Clotte en profil `truck` (interdiction PL dans OSM) : `A → dépôt` passe, `dépôt → A` rend un
442 « No path could be found ». Un seul tronçon sur trois mettait la boucle entière en échec.
(2) Le code métier n'est que dans le **corps** de la réponse : `str(HTTPError)` vaut
« HTTP Error 400: Bad Request », identique pour un 442 et pour un JSON malformé — donc le 442
était retenté deux fois comme une panne passagère, puis remonté en échec générique.
**Correctif** — `route()` lit le corps du 400, lève `AucunTrajet` sur un 442 (sans retenter,
c'est définitif) ; `calculer()` remesure alors le tronçon **en sens inverse** et pose une
alerte ⚠ (statut dégradé). Corrigé dans `outils/pipeline/itineraire/calcul_itineraire.py`.
Règle : une erreur HTTP dont le code métier est dans le corps ne se diagnostique jamais sur
`str(exception)` — et un échec de routage sur un tronçon n'est pas un échec de l'itinéraire.

### [2026-09-18] L'URL d'une pièce jointe noCRM mène à la page de connexion — avec un 200
**Symptôme** — `GET https://samdemenage.nocrm.io/attachments/<id>` (le champ `url` rendu par
`/leads/<id>/attachments`) répond **200** en `text/html` : 13 ko de page de connexion, clé
d'API ou pas. Enregistré tel quel, ce « fichier » passerait pour une pièce jointe lue.
**Cause** — cette URL est celle de l'interface web (session navigateur), pas de l'API.
**Correctif** — `GET /api/v2/leads/<lead>/attachments/<id>` rend `{"url": …}`, un lien S3
signé valable **180 s** : le télécharger aussitôt. Fait par `inventaire_auto.telecharger_nocrm()`.
Même famille que les `?query=` ignorés : un 200 ne prouve rien — vérifier le type de contenu.

### [2026-09-16] La description noCRM accepte du HTML — en texte brut, aucun espace n'est rendu
**Symptôme** — la fiche Notion recopiée dans l'opportunité s'affiche en un bloc compact : lignes
vides supprimées, espace insécable ignoré. Conclu à tort le 11/09 que noCRM « n'affiche aucune
ligne vide ».
**Cause** — l'interface lit `html_description`. Un texte brut y est recopié tel quel, sans `<p>`
ni `<br>`. Un copier-coller Google Docs, lui, arrive en HTML (tableaux, paragraphes).
**Correctif** — envoyer du HTML dans `description` (`<p>`, `<br>`, `<strong>`, `<p>&nbsp;</p>`
pour une ligne vide) : noCRM le garde dans `html_description` et en dérive un `description` texte.
Relire et comparer le **texte**, pas le HTML. Fait par `nocrm.en_html()`.

### [2026-09-16] Volume surestimé de ~8 m³ : `incertain` posé par prudence et tailles ignorées
**Symptôme** — BODARD Maylis : 36 m³ retenus (conservateur) ; le projet Claude de Karim donne
26–28 m³ sur le même PDF.
**Cause** — deux écarts au prompt de référence, cumulés : (1) `incertain` posé sur 22 lignes sur
51 parce que les libellés étaient génériques (« Meuble », « Étagère petite »), alors que le
prompt le réserve aux formulations conditionnelles du client et aux quantités vagues → +3 m³ ;
(2) qualificatifs de taille ignorés : « Étagère petite » comptée 0,40 m³, « Buffet petit »
1,00 m³ → +4 à 5 m³. Aucun des deux ne vient du script : les coefficients sont justes.
**Correctif** — prompt du projet recopié dans
`estimer-volume-samdem/references/prompt-projet.md`, à lire avant chaque estimation ; règle
explicite sur `incertain` ; références par taille dans `volume.py` (`etagere_petite`,
`buffet_petit`…). Rejoué : 26 m³ standard / 29 m³ conservateur.

### [2026-09-21] noCRM ignore une nouvelle date de rappel quand le rappel existant a une heure
**Symptôme** — « rappel non posé (relu : statut standby, date <aujourd'hui>) » sur RAYNFELD
(16/09) et BODARD ×2 (18/09) : `PUT` 200, mais `remind_date` inchangée à la relecture.
**Cause** — un rappel posé à la main par un commercial porte un `remind_time` ; tant qu'il
existe, noCRM ignore toute `remind_date` envoyée sans heure. Reproduit sur le lead FONTAINE le
21/09 : sans heure → ignoré ; avec `remind_time` → accepté. `remind_time: null` ou `""` sont
eux aussi ignorés ; seule la séquence `status: todo` puis `standby` efface l'heure.
**Correctif** — `nocrm.enrichir()` : date relue ≠ date visée et heure présente → renvoi de la
date avec l'heure existante, puis nouvelle relecture.

### [2026-11-03] Une ligne de fiche recopiée telle quelle sur le devis client
**Symptôme** — devis Confort de PUJO : « Vaisselle (variante Emballage société) : 🟡 temps à chiffrer. » dans la liste des options du PDF. Le même devis ne disait plus que l'emballage des effets personnels restait au client.
**Cause** — `devis_auto.options()` recopiait la ligne cochée en ne retirant que les durées chiffrées, et comptait la mise en penderie comme une mise en carton.
**Correctif** — libellés nettoyés dans `options()`, penderie écartée, et `generer_devis_pdf.py` refuse toute spec avec pastille, émoji, « à chiffrer », temps ou variante d'option. Règle : ce qui peut finir sur un document client se filtre au dernier maillon, jamais seulement à la saisie.

### [2026-11-03] Un PDF ouvert dans un lecteur n'est pas remplacé, et rien ne le dit
**Symptôme** — devis PUJO refait : `generer_devis_pdf.py` affiche le chemin et rend 0, mais le fichier garde l'heure et le contenu d'avant. Seule la relecture du texte du PDF l'a montré.
**Cause** — `chrome --print-to-pdf` ne peut pas écrire sur un fichier verrouillé et sort quand même sans erreur.
**Correctif** — impression dans un dossier temporaire puis copie : un fichier ouvert devient une erreur explicite. Corrigé dans `generer_devis_pdf.py`. Règle : après toute régénération, relire le contenu du PDF, pas seulement le code de sortie.

### [2026-11-04] « garde-meuble » dans le titre d'une étape n'est pas lu
**Symptôme** — LE TRIVIDIC : `### Étape (garde-meuble Saint-Loubès) :` et une adresse sans le mot. `typeEtape` sort en « Adresse intermédiaire », sans alerte : 1 h de manutention au dépôt au lieu de 30 min.
**Cause** — `fiche_notion` retire la ligne de titre du bloc avant de chercher « garde-meuble », « box », « dépôt » ou « stockage ». Ni « Saint-Loubès » ni l'adresse du dépôt ne suffisent.
**Correctif** — titre et adresse du dépôt lus dans `fiche_notion.py` ; étape sans type, sans adresse ou sans volume bloquante. Corrigé le jour même. Le second lancement avait laissé deux onglets ouverts, dont un exportable avec la version fausse : `pipeline.py` contrôle désormais les valeurs sans onglet, puis ne génère que ces valeurs-là, une fois. Règle : ce qui ouvre un document exportable passe après la vérification, jamais avant.

### [2026-11-03] HubSpot : le « nom » d'un contact peut porter le nom complet
**Symptôme** — GUENA : contact `firstname` = « Thibaud », `lastname` = « Thibaud Guena ». Lu tel quel, le client devient « THIBAUD GUENA Thibaud », sans erreur, et ce nom part sur le PDF.
**Cause** — les contacts créés depuis le formulaire du site ne découpent pas toujours le nom.
**Correctif** — la note porte `Client : NOM Prénom` dans sa section « Suivi », qui fait foi ; à défaut, le prénom est retiré du nom. Corrigé dans `fiche_hubspot.lire_fiche`. Ne jamais recomposer un nom depuis le seul contact.

### [2026-11-03] HubSpot : une date corrigée sur la fiche n'arrive pas sur la transaction
**Symptôme** — MAGINOT : date changée dans Notion, finalisation rejouée (`--seulement sheet,crm`), compte rendu sans erreur. La note et le Sheet portent la nouvelle date, `date_demenagement` garde l'ancienne.
**Cause** — le suivi (adresses, date, commercial) n'est que complété : `completer()` n'écrit que les champs vides. Or HubSpot fait foi sur la date (D7).
**Correctif** — après un changement de date ou d'adresse, écrire la propriété à part (`HubSpot(cle, ecrire=True)`, PATCH de la transaction) puis la relire. Penser aussi au PDF (spec + `generer_devis_pdf.py`), au brouillon Gmail et au PDF déjà envoyé à Sandrine.

### [2026-10-06] HubSpot : « dernière modification » = le jour de l'import pour 691 transactions
**Symptôme** — gros dossiers branchés sur HubSpot : 16 dossiers « actifs depuis 15 jours » contre
5 sur noCRM ; 7 « sans prix » qui n'auraient jamais passé le filtre d'activité.
**Cause** — l'import du 05/10 a modifié toutes les transactions d'un bloc : `hs_lastmodifieddate`
vaut le 05/10 partout et ne dit plus rien de l'activité. L'import n'a pas non plus repris
`updated_at` ni les rappels noCRM déjà échus (seulement ceux à venir).
**Correctif** — `hubspot_crm.derniere_activite()` : max(dernière note/tâche,
`derniere_activite_nocrm`, entrée dans l'étape actuelle hors `JOURS_IMPORT`). **Jamais
`hs_lastmodifieddate`** : la reprise du 06/10 l'a remise à jour partout une 2e fois (32 relances
au lieu de 10). Reprise ponctuelle : `outils/hubspot/reprise_activite_nocrm.py`.

### [2026-10-06] HubSpot : fichiers refusés (403) sans le bon droit ni User-Agent
**Symptôme** — dépôt du PDF d'inventaire : 403 « files.ui_hidden.write » ; puis lecture d'une
pièce jointe par son URL signée : 403 alors que l'URL est valide.
**Cause** — (1) la clé n'avait aucun droit fichiers : il en faut quatre, `files.read`,
`files.write`, `files.ui_hidden.read`, `files.ui_hidden.write` (pas de droit « files » unique
dans l'écran des Service Keys) ; (2) le CDN `hubspotusercontent` rejette un client sans
User-Agent de navigateur — urllib n'en envoie pas.
**Correctif** — droits ajoutés par Karim, guide de la clé corrigé ; `inventaire_auto.telecharger()`
envoie un User-Agent.

### [2026-10-09] HubSpot : finalisation qui crée un doublon au lieu de déplacer la transaction
**Symptôme** — DUPRAT Lucie : la transaction « Lucie DUPRAT » reste en « Devis à produire » et
une seconde, « DUPRAT Lucie », apparaît en « Devis envoyé ».
**Cause** — transaction saisie à la main depuis le formulaire : **aucun contact associé**,
téléphone et e-mail seulement dans le texte, ni lien Notion ni référence (fiche créée après
coup). `trouver_transaction()` ne cherchait que lien Notion → réf. → contact : rien trouvé,
donc contact + transaction créés.
**Correctif** — repli `transaction_orpheline()` : transaction ouverte au nom du client **et
sans contact** ; une seule → reprise (contact associé au passage), plusieurs → aucune écriture.
**Nettoyage** — fusion API `POST /crm/v3/objects/deals/merge` (originale en principale) : la
fusion **change l'identifiant** (525507058922) et garde l'étape de la principale — remettre
l'étape à la main ; contact, notes, tâche et propriétés `sd_*` suivent.
