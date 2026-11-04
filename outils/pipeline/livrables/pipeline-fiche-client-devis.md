> Document ancien : il décrit encore Notion et noCRM. `outils/pipeline/README.md` fait foi.

---
type: synthese
tags: [process, automatisation, fiche-client, devis, itineraire]
created: 2026-09-08
updated: 2026-09-18
sources: 4
---

# Pipeline « Prise de contact → devis envoyable »

> Origine : conversation Karim 08/09/2026 (spec agent itinéraire, arbitrages en fin de doc)
> + skills `/creer-fiche-client-samdem`, `/calcul-devis-samdem` + prompt Cowork « devis HTML »
> + tests navigateur sur fr.mappy.com du 08/09/2026 (§4.3).
> Spec d'exécution destinée à un agent IA outillé. Ne remplace pas les skills : décrit
> comment les enchaîner et ce qu'il faut leur ajouter.

## 0. Ce qui change par rapport à aujourd'hui

| Étape | Aujourd'hui | Cible |
|---|---|---|
| Fiche Notion | Prompt Cowork, manuel mais outillé | Inchangé (skill `/creer-fiche-client-samdem`) |
| **Km et temps de trajet** | **Samuel ouvre Mappy et relève à la main** | **Calculés automatiquement sur la boucle complète** |
| **Péage** | Relevé classe 3 sur Mappy, ÷ 1,2 | **Hors périmètre — Samuel l'ajoute à la main si besoin** (arbitrage 08/09) |
| Point de départ trajet | « Bordeaux Centre » (obsolète) | **Dépôt Saint-Loubès — 147 route des Valentons, 33450** |
| Itinéraire retenu | Au jugé | **Sans péage tant que ≤ 19h06 A/R**, avec péage au-delà |
| Décision « fiche prête ? » | Jugement humain | **Score de complétude formalisé → GO / GO⚠ / STOP** |
| Devis | Samuel relance le skill à la main | Chaîné automatiquement si GO |
| Validation marge | Samuel | **Inchangé — point de contrôle humain obligatoire** |

**Gain visé** : les minutes de Mappy par dossier, et la ressaisie qui va avec.

---

## 1. Vue d'ensemble

```
[1] INGESTION          brut (WhatsApp / mail / transcript / dictée / note commercial)
       |                          ↓ normalisation
[2] OBJET DOSSIER      dossier.json  ← contrat de données unique du pipeline
       |
       ├──[3] GÉOCODAGE      adresses → coordonnées + adresse normalisée
       |        ↓
       ├──[4] ITINÉRAIRE     boucle dépôt → départ → (étapes) → arrivée → dépôt, un segment par tronçon
       |        ↓            = km A/R + temps de conduite A/R (péage exclu)
       |
[5] FICHE NOTION       création + remplissage + propriétés + itinéraire renseigné
       |
[6] SCORE COMPLÉTUDE   GO / GO⚠ / STOP
       |        ↓ (si GO ou GO⚠)
[7] CALCULATEUR        copie HTML pré-remplie → récap chiffré
       |
       ▓▓ VALIDATION KARIM (marge, péage éventuel, cohérence) ▓▓  ← arrêt humain
       |        ↓ « Exporter JSON » (le veilleur du presse-papier prend la suite)
[8] FINALISATION       fiche Notion (chiffrage, propriétés, itinéraire) + Google Sheet
       |
[9] WHATSAPP           « Devis prêt à vérifier » → Sandrine, conversation « Devis/inventaire » ; le PDF du devis reste en local
       |
       ├──[9b] INVENTAIRE   s'il existe (fiche Notion, puis noCRM) : PDF Prod_inventaires
       |                    envoyé sur la même conversation — en arrière-plan (18/09/2026)
       |
[10] noCRM             « Devis envoyé » ou « Trajets Axe Paris »
```

*Mise à jour 18/09/2026 : l'ancienne étape « [8] devis HTML/PDF » est remplacée — l'artefact
calculateur est le document (voir §9) ; la chaîne se prolonge jusqu'au message d'équipe,
l'inventaire et le CRM (voir §9 bis).*

**Règle d'or** : à aucun moment un LLM n'invente un chiffre. Les km et le temps viennent d'un
**outil déterministe** ; le péage vient de **Samuel**. La doctrine actuelle du skill devis
(« Mappy désactivé ») n'est pas levée par confiance dans le modèle — elle l'est parce qu'on
lui donne une source vérifiable. Si l'outil échoue, on retombe sur la question à Samuel,
jamais sur une estimation.

---

## 2. Le contrat de données — `dossier.json`

Pivot unique entre toutes les étapes.

```jsonc
{
  "client":   { "nom": "DUPONT", "prenom": "Marie", "tel": "...", "email": "..." },
  "depart":   {
    "adresse_brute": "12 rue des Lilas, Talence",
    "adresse_normalisee": null,      // rempli par [3]
    "coord": null,                   // [lon, lat] rempli par [3]
    "precision": null,               // housenumber | street | municipality
    "type_logement": "appartement",
    "etage": 3, "ascenseur": false, "rdc": false, "duplex": false,
    "portage_m": 10                  // minimum 10 imposé (règle métier)
  },
  "arrivee":  { /* même schéma */ },
  "etapes":   [],                    // garde-meuble / point 2 / point 3
  "mission":  {
    "volume_m3": 22, "source_volume": "inventaire client",
    "formule": "Confort", "date_chargement": "2026-10-14",
    "inventaire_fourni": true, "commercial": "Christophe",
    "nb_camions": 1, "monte_charge": false, "dechetterie_m3": 0
  },
  "itineraire": {                    // rempli par [4] — jamais à la main par le LLM
    "km_ar": null,
    "heures_conduite_ar": null,
    "variante": null,                // "sans_peage" | "avec_peage"
    "peage_ht": null,                // TOUJOURS null : renseigné par Samuel si besoin
    "peage_requis": false,           // true si variante = avec_peage → 🟡 en fiche
    "segments": [],                  // un par tronçon (3 sans étape) : km, durée, lien Mappy
    "source": null,                  // "cache" | "ors" | "saisie-karim"
    "calcule_le": null,
    "confiance": null                // "ok" | "degrade" | "echec"
  },
  "completude": { "statut": null, "manquants": [], "jaunes": [] },
  "notion":   { "page_id": null, "url": null }
}
```

Champ inconnu = `null`, **jamais** une valeur plausible. Le `null` déclenche la pastille 🟡
en fiche et alimente `completude.manquants`.

---

## 3. Étape géocodage

**Pourquoi une étape à part** : un routeur a besoin de coordonnées, et « Talence » sans
numéro renvoie un point de centre-ville qui décale le kilométrage. Séparer permet de savoir
*à quel point* l'adresse est précise, donc quelle confiance accorder au km.

- **Source** : API Adresse (Base Adresse Nationale) — `api-adresse.data.gouv.fr`. Gratuite,
  sans clé, sans quota bloquant, la meilleure sur les adresses françaises.
- Retour : coordonnées + `score` + `type` (`housenumber` / `street` / `municipality`).
- **Règle de précision** :
  - `housenumber` → km fiable, pas de pastille.
  - `street` ou `municipality` → km calculé mais fiche annotée `🟡 km estimé depuis la ville
    (adresse exacte non fournie)`. C'est l'information que le relevé manuel perd aujourd'hui :
    taper « Talence » dans Mappy produit un chiffre d'apparence aussi ferme qu'une adresse
    complète.
  - Score < 0,5 ou zéro résultat → `manquants += adresse` → **STOP**.

---

## 4. Module Itinéraire — la spec détaillée

### 4.1 Géométrie du trajet

**Boucle découpée en tronçons à deux points**, pas un aller-retour — 3 segments sans étape,
un de plus par étape :

```
S1 : Dépôt Saint-Loubès  →  Adresse de départ client
S2 : Adresse de départ   →  Étape 1        (sans étape : directement l'adresse d'arrivée)
…  : Étape n             →  Adresse d'arrivée client
Sn : Adresse d'arrivée   →  Dépôt Saint-Loubès
```

Dépôt : **147 route des Valentons, 33450 Saint-Loubès** — constante du système, jamais
ressaisie. Remplace le « Bordeaux Centre » du prompt actuel, devenu faux depuis que les
camions dorment au dépôt tous les soirs.

- `km_ar` = somme des segments. **Ce n'est pas 2 × la distance client** : c'est tout l'intérêt
  de la boucle, et la raison pour laquelle le relevé manuel est fastidieux.
- `heures_conduite_ar` = somme des durées des segments, **conduite seule** (aucune
  manutention, aucune pause). Le calculateur ajoute le reste lui-même.
- Étapes (garde-meuble, point 2/3) : chacune ouvre un segment, dans l'ordre chronologique réel,
  avec son propre lien Mappy — un lien Mappy ne porte jamais que deux points.
- Km et durées par segment sont arrondis au prorata pour que leur somme retombe **exactement**
  sur `km_ar` (unité) et `heures_conduite_ar` (quart d'heure).
- Profil de calcul : **poids lourd** (`driving-hgv`). À défaut, profil voiture accepté mais
  `confiance: "degrade"`.

### 4.2 Choix de la variante — la règle des 19h06

*(arbitrage Karim 08/09/2026)*

1. Calculer la boucle en **itinéraire sans péage**.
2. `heures_conduite_ar` **≤ 19h06** → on retient cette variante. `peage_ht = 0`, rien à
   relever. **C'est le cas courant**, Bordeaux–Paris inclus (1 283 km / 18,25 h).
3. `heures_conduite_ar` **> 19h06** → trop long : recalculer la boucle en **itinéraire avec
   péage** et retenir celle-là (km + temps). Le montant du péage n'est pas calculé :
   `peage_requis = true` → la fiche porte `🟡 Péage à renseigner (classe 3 ÷ 1,2)` et les
   trois liens Mappy de vérification, pour que Samuel le relève en quelques clics.

Le péage est donc **hors du périmètre automatisé**. Samuel relève la classe 3 (camion 30 m³)
et divise par 1,2 — méthode correcte, les péages autoroutiers français étant soumis à la TVA
à 20 %. Aucune API n'a à être souscrite pour cela.

Le seuil a été relevé de 18 h à 19,1 h le 08/09 : il avait été fixé en lisant Mappy, alors que
le module calcule en poids lourd (~12 % plus lent). À 18 h, la boucle Bordeaux–Paris sortait
six minutes au-dessus et basculait l'axe principal en « avec péage ». À 19h06, elle rend
**1 283 km / 18,25 h sans péage** — à comparer à l'ancien forfait maison de 1 250 km / 19 h.

### 4.3 ⚠ Résultat vérifié — pourquoi le lien Mappy ne pouvait pas marcher

Le lien produit par le prompt actuel a été testé le 08/09 dans un navigateur. Deux constats,
qui expliquent entièrement pourquoi la lecture du lien avait été interdite dans le skill :

1. **Format `#/recherche/A/B/C/D`** (celui du prompt) : Mappy charge la page en ne retenant
   que **les deux premiers points** et ignore silencieusement les suivants. Le lien affichait
   donc « dépôt → départ client » au lieu de la boucle — sans le moindre message d'erreur.
   C'est exactement le symptôme décrit : « ça faisait le trajet entre le départ et l'arrivée ».
2. **Vrai format d'URL de Mappy** : `https://fr.mappy.com/itineraire#/voiture/<départ>/<arrivée>/car/9`
   (adresses encodées en URL). Testé avec 4 points, il renvoie une **erreur 404 « Route not
   found »** et la page reste blanche.

**Conclusion : le site Mappy ne sait pas encoder un itinéraire à étapes dans une URL.** Ce
n'était pas une syntaxe à corriger, la fonction n'existe pas. Aucun lien unique ne pourra
jamais représenter la boucle.

**Conséquence de conception** : la boucle est traitée comme **3 itinéraires indépendants**
que l'on additionne. C'est aussi ce qui rend la vérification humaine possible — la fiche
porte trois liens Mappy simples, un par segment, chacun cliquable et contrôlable :

```
S1  dépôt → départ   : https://fr.mappy.com/itineraire#/voiture/147%20Route%20des%20Valentons%2C%2033450%20Saint-Loub%C3%A8s/<DEPART>/car/9
S2  départ → arrivée : https://fr.mappy.com/itineraire#/voiture/<DEPART>/<ARRIVEE>/car/9
S3  arrivée → dépôt  : https://fr.mappy.com/itineraire#/voiture/<ARRIVEE>/147%20Route%20des%20Valentons%2C%2033450%20Saint-Loub%C3%A8s/car/9
```

Mappy affiche pour chaque trajet les trois variantes (« Le plus rapide », « Sans péage »,
« Moins de km ») avec durée, km et montant du péage : c'est la variante **Sans péage** qui
sert de référence de contrôle, conformément à §4.2.

### 4.4 Source des données

Le péage étant sorti du périmètre, il ne reste que de la distance et du temps — donnée
gratuite, ouverte et fiable. Plus besoin d'API commerciale.

**Niveau 0 — Cache d'axes**
Sam'Déménage tourne sur un nombre restreint d'axes. Une table `outils/pipeline/axes-itineraires.csv`
mémorise chaque boucle déjà calculée :
`ville_depart ; cp_depart ; ville_arrivee ; cp_arrivee ; km_ar ; h_ar ; variante ; date_calcul`
Lecture d'abord, toujours : hit → réponse instantanée et chiffre déjà éprouvé. Recalcul
au-delà de 12 mois. Bénéfice secondaire : cette table servira aussi au chiffrage du groupage
axe Paris.

**Niveau 1 — Routage**
OpenRouteService : clé gratuite en self-service, profil `driving-hgv` (poids lourd) et
évitement des routes à péage (`avoid_features: ["tollways"]`) — les deux paramètres dont on a
besoin pour §4.2. Alternative si les quotas gênent : OSRM auto-hébergé.
À confirmer à l'implémentation : comportement exact de l'évitement péage sur les axes
français, et écart constaté avec la variante « Sans péage » de Mappy sur 2-3 trajets connus.

**Niveau 2 — Échec assumé**
Le routeur ne répond pas ou une adresse ne se géocode pas → `confiance: "echec"`, `km_ar` et
`heures_conduite_ar` restent `null`, la fiche porte `🟡 Itinéraire à renseigner manuellement`
**et les trois liens Mappy** pour que ce soit l'affaire de quelques clics. Le reste de la
fiche est créé normalement. **Jamais d'estimation de secours.**

*(Pour mémoire : Mappy commercialise bien une « API Itinéraire Multimodal » avec péages et
profil poids lourd, mais sans portail self-service — accès sur devis via contact@mappy.com.
Écartée le 08/09, le péage sortant du périmètre automatisé. À rouvrir seulement si le péage
devait un jour être automatisé.)*

### 4.5 Cas particuliers

- **Mission locale** : la boucle est calculée quand même — elle a un coût réel, une vingtaine
  de km rien que pour sortir de Saint-Loubès et y revenir. La règle actuelle « local →
  itinéraire vide » date de l'époque « Bordeaux Centre » et sous-estime le déplacement.
  → Toujours calculer, et laisser la **règle tarifaire** arbitrer entre forfait
  (20 € HT × camion) et km réels. Arbitrage Samuel (§10).
- **Aller simple sans retour au dépôt** (camion qui enchaîne) : cas non géré par le process
  actuel non plus. Signaler en 🟡 si mentionné, ne pas modéliser tant que la règle n'est
  pas posée.
- **Groupage** : la boucle complète est calculée et renseignée normalement ; le moteur du
  calculateur applique la logique de répartition une fois la case `groupage` cochée.
- **Trajet ≥ 2 h** : déclenche le seuil longue distance (décision D6, Karim 05/10/2026 : la règle
  des calculateurs fait foi ; l'ancien seuil 5h59 du 28/08 est périmé) → taux unique de 20 €/h par personne du camion. `heures_conduite_ar` doit être précis
  autour de ce seuil et jamais arrondi vers le bas. La manutention est à 28 €/h partout (23/09/2026).

---

## 5. Étape fiche Notion

Inchangée sur le fond : le skill `/creer-fiche-client-samdem` fait déjà autorité (duplication
du modèle, déplacement dans la base, propriétés select, pastilles 🟡, nettoyage des sections,
calcul du matériel, checklist de cohérence). **Trois corrections** :

1. Section Itinéraire **remplie** au lieu d'être laissée vide :
   ```
   Km A/R (dépôt → départ → arrivée → dépôt) : 812 km
   Temps de conduite A/R : 18,25 h — itinéraire sans péage
   Péage : 0 € (sans péage, sous le seuil de 19h06)
   Vérification :  S1 <lien>  ·  S2 <lien>  ·  S3 <lien>
   ```
   Quand `peage_requis = true`, la ligne péage devient
   `🟡 Péage à renseigner (classe 3 ÷ 1,2) — itinéraire avec péage retenu, A/R > 19h06`.
2. **Un lien par segment**, jamais un lien unique à 4 points (§4.3 — il ne fonctionne pas).
3. Point de départ « Bordeaux Centre » → **dépôt Saint-Loubès**.

---

## 6. Étape score de complétude — la décision GO / STOP

Remplace le coup d'œil de Samuel. Une seule question : **le calculateur peut-il produire un
chiffre défendable avec ce qu'on a ?**

### Champs BLOQUANTS (absent → STOP)

| Champ | Pourquoi bloquant |
|---|---|
| Volume m³ | Entrée n°1 du moteur, aucun défaut possible |
| Adresse départ **et** arrivée (au moins la commune) | Sans elles, ni itinéraire ni zone tarifaire |
| Étage + ascenseur, départ et arrivée | Déterminent le nombre de déménageurs (table du skill) |
| Formule (Standard / Confort / Premium) | Change la structure de prix |
| Km et temps A/R **si longue distance** | Sinon le déplacement est faux |

Le péage n'est **pas** bloquant : son absence est normale sous 19h06, et au-delà il relève de
Samuel (🟡, à la validation).

### Champs NON bloquants (absent → 🟡, le devis part quand même)

Email, notes, inventaire détaillé, date exacte de chargement, matériel à livrer, distances de
portage (défaut 10 m), nombre de camions si volume ≤ 30 m³ (défaut 1), péage.

### Les trois verdicts

- **GO** — tous les bloquants présents, itinéraire en `confiance: "ok"`.
  → Enchaînement direct sur le calculateur.
- **GO⚠** — bloquants présents mais au moins un signal de fragilité : itinéraire `degrade`,
  adresse géocodée à la commune, `peage_requis = true`, volume sans inventaire, contradiction
  relevée par la checklist du skill fiche.
  → Devis produit **avec un bandeau listant les fragilités en tête du récap**, pour concentrer
  l'attention au lieu de tout re-vérifier.
- **STOP** — au moins un bloquant manquant.
  → Fiche créée quand même (rien n'est perdu), et l'agent rend **la liste exacte des questions
  à poser au client**, rédigée, prête à copier dans WhatsApp. Le livrable d'un STOP n'est pas
  un message d'erreur, c'est une relance.

---

## 7. Étape calculateur de devis

Skill `/calcul-devis-samdem`, inchangé sur le fond, avec **une modification de sa §6**
(« règle Mappy désactivé ») :

> Ancienne règle : km / temps / péage sont demandés à l'utilisateur.
> Nouvelle règle : si `dossier.itineraire.confiance ∈ {ok, degrade}`, `km_ar` et
> `heures_conduite_ar` sont injectés dans `kmAR` et `heuresRouteAR`, source mentionnée dans le
> récap. `peageAR` reste à 0 sauf saisie de Samuel. Si `echec`, on retombe **exactement sur
> l'ancienne règle** : la question rejoint le bloc de questions groupées.

L'esprit est préservé — Claude ne devine toujours pas — seule la provenance du chiffre change.
Et l'interdiction de lire un lien Mappy reste justifiée : ce lien était structurellement
incapable de porter la boucle (§4.3).

**Sur l'artefact calculateur** : la version qui fait foi reste `outils/pipeline/calculateurs/calculateur-devis.html`
(copie locale pré-remplie par client), parce qu'un agent peut y écrire des valeurs, ce qu'il
ne peut pas faire dans un artefact hébergé.
→ Amélioration possible (P2) : lecture d'un paramètre `#data=<json base64>` dans l'URL, pour
produire un **lien pré-rempli** partageable sans fichier local.

---

## 8. ▓ Validation Samuel — le point d'arrêt

Non automatisable : marge, réalisme du temps, options, et **saisie du péage** quand
`peage_requis = true`. Le pipeline s'arrête ici et attend. Seul endroit où la chaîne doit
être lente.

Ce que l'agent fournit pour rendre ce contrôle rapide :
- le récap des **inputs** (jamais des résultats recalculés à la main) ;
- les fragilités du GO⚠ en tête ;
- les trois liens de vérification de l'itinéraire ;
- les incohérences relevées par la checklist du skill fiche ;
- la marge affichée par le calculateur et son écart à la cible (30 %).

---

## 9. Étape devis HTML final

Prompt Cowork existant, inchangé. Chaînage automatique possible en P2 une fois la validation
donnée. Le numéro séquentiel de devis est **fourni par Samuel**, jamais inventé.

---

## 9 bis. Inventaire automatique — après le message d'équipe *(Karim, 18/09/2026)*

Même déclencheur que le message WhatsApp : l'export du devis. Une fois « Devis prêt à
produire » parti, `finalisation.py` lance `inventaire_auto.py` en arrière-plan :

> **Sous 6 m³** (Karim, 22/09/2026) : étape sautée — l'inventaire est noté sur le devis,
> pas de PDF annexe. Seuil `regles.SEUIL_INVENTAIRE_PDF_M3`.


1. **Recherche**, le premier qui répond l'emporte : section « Inventaire » de la fiche Notion
   → fichiers de la fiche rangés sous cette section ou nommés « inventaire » → pièces jointes
   et description de l'opportunité noCRM (appariée par téléphone / e-mail, jamais sur le seul
   nom). Rien : fin silencieuse, le reste de la chaîne suit son cours.
2. **Mise en forme** : parseur codé pour le format « Pièce : article dims xN · … » ; modèle
   (`claude -p`) pour le texte libre, un PDF ou un tableur, avec les règles de
   `Prod_inventaires/SKILL.md`, réponse validée avant rendu.
3. **PDF** au format maison (`Prod_inventaires`) : client, adresses, date / créneau lus dans
   la fiche, volume du devis, n° d'inventaire laissé vide (champ modifiable).
4. **Envoi** sur la même conversation WhatsApp.

Jamais deux fois le même inventaire (registre `.claude/scripts/inventaires-envoyes.jsonl`,
vérifié avant tout appel au modèle) ; tout incident part en alerte Slack.
Mode d'emploi : `outils/pipeline/README.md`, section « Inventaire automatique ».

---

## 10. Décisions

**Tranchées le 08/09/2026 :**

| Sujet | Décision |
|---|---|
| Péage | **Hors périmètre automatisé** — relevé à la main par Samuel en **classe 3** (camion 30 m³), divisé par 1,2. Jamais calculé ni estimé. |
| Variante d'itinéraire | **Sans péage tant que l'A/R tient sous 19h06**, avec péage au-delà. Seuil relevé de 18 h le 08/09 (voir §4.2). |
| Origine et retour | **Dépôt Saint-Loubès**, jamais Bordeaux Centre. Boucle en **un segment par tronçon** (3 sans étape). |
| Manutention | **28 €/h partout** depuis le 23/09/2026 (30 €/h du 08/09 au 22/09), local comme longue distance. Plus aucune zone tarifaire, donc plus de seuil géographique local/LD. |
| Longue distance | **A/R ≥ 2 h** (D6, Karim 05/10/2026 ; 5h59 périmé) → taux unique **20 €/h par personne** du camion, sans distinction conducteur/passager. |
| Profil de routage | **Poids lourd** (`truck`). |
| Forfait « Mission Paris » | Abandonné au profit de la mesure réelle (1 283 km / 18,25 h, contre 1 250 km / 19 h au forfait). |
| Conception | **Tout ce qui est déterministe est codé**, exécuté en local, et jamais re-raisonné par le modèle. |

**Encore ouvertes :**

| # | Question | Options | Reco |
|---|---|---|---|
| 1 | Calculateur | Copie HTML locale / artefact à lien pré-rempli (`#data=`) | Local aujourd'hui, lien pré-rempli en P2 |
| 2 | Déclenchement | Sur demande / automatique à l'arrivée d'un lead | **Sur demande** d'abord, le temps que le score de complétude fasse ses preuves |
| 3 | Hébergement | Poste de Samuel / VPS | À trancher quand un service devra tourner en continu (watcher, webhook) |

---

## 11. Mise en œuvre par lots

### P0 — Le gain principal ✅ livré le 08/09/2026
1. ✅ Module itinéraire autonome : `outils/pipeline/itineraire/calcul_itineraire.py` (géocodage BAN +
   Valhalla `truck` sans péage, boucle en 3 segments, règle des 18 h, seuil LD à 2 h, cache
   d'axes, sortie bloc Notion ou JSON). Mode d'emploi : `outils/pipeline/itineraire/README.md`.
2. ✅ Calage contre Mappy sur Bordeaux–Paris et un local : km à −0,4 % / +3 %, temps ~+12 %
   (profil poids lourd). Voir le point d'arbitrage n°1 du §10.
3. ✅ `/creer-fiche-client-samdem` : origine → dépôt Saint-Loubès, lien unique → 3 liens,
   itinéraire calculé aussi en local. `/calcul-devis-samdem` : §5 (28 €/h, LD > 2 h) et §6
   (injection du module au lieu de la question) réécrites.
4. ✅ `outils/pipeline/axes-itineraires.csv` amorcé.

### P1 — Chaîner ✅ livré le 08/09/2026
5. ✅ Score de complétude et trois verdicts : `outils/pipeline/pipeline.py`, avec relance
   rédigée en cas de STOP.
6. ✅ Règles métier codées : `outils/pipeline/regles.py` (table des déménageurs, taux,
   camions, portage minimum, cohérence formule) — ce que le modèle re-déduisait à chaque
   dossier.
7. ✅ Génération de la copie du calculateur pré-remplie (objet `EX`) par le code.
8. Reste : écriture automatique de l'itinéraire dans la fiche Notion par le skill fiche
   (dépend du MCP Notion, donc non codable hors LLM).

### P2 — Confort
9. ✅ Archivage des devis validés : `outils/pipeline/export.py` → Google Sheet (Apps Script
   Web App) + propriétés chiffrées de la fiche Notion (API REST). Reste à déployer côté
   Samuel : créer le Sheet, coller le script, renseigner `.env`.
10. ✅ Taux par défaut porté à 30 €/h dans les deux calculateurs (`EX`, `BLANK` et les
    valeurs de repli) — fin des zones tarifaires.
11. Lien calculateur pré-rempli (`#data=`), pour se passer du fichier local.
12. Chaînage automatique vers le devis HTML après validation.
13. ✅ Inventaire automatique après le message d'équipe (18/09/2026) :
    `outils/pipeline/inventaire_auto.py` + skill `outils/pipeline/Prod_inventaires/` — voir §9 bis.

---

## 12. Garde-fous permanents

1. **Aucun chiffre inventé.** Km et temps : outil. Péage : Samuel. Un `null` assumé vaut mieux
   qu'une estimation plausible — c'est la règle qui rend l'automatisation acceptable.
2. **Traçabilité** : `source` + date sur toute valeur d'itinéraire.
3. **Les liens Mappy de vérification survivent à l'automatisation** — un par segment.
4. **La validation Samuel n'est jamais court-circuitée.**
5. **Un STOP produit une relance rédigée**, pas une erreur.
6. **Aucune écriture Notion silencieuse** : toute création est restituée avec l'URL.
7. **Le fichier maître `outils/pipeline/calculateurs/calculateur-devis.html` n'est jamais modifié** par le pipeline.
8. **Un inventaire ne s'invente pas et ne part qu'une fois** : chaque article vient de la
   source (fiche ou CRM), et un même inventaire n'est jamais renvoyé à l'équipe.

## Pages liées

[[calcul-devis]] · [[moteur-tarification-devis]] · [[process-devis-crm]] · [[groupage-tournees]]
· [[methode-chantier]] · [[structure-de-couts]]
