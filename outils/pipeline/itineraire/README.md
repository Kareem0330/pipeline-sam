---
type: concept
tags: [outil, itineraire, devis]
created: 2026-09-08
updated: 2026-09-08
sources: 1
---

# Module itinéraire — mode d'emploi

> Origine : P0 du [[pipeline-fiche-client-devis]], construit et testé le 08/09/2026.
> Remplace le relevé manuel sur Mappy pour les km et le temps de conduite.

## À quoi il sert

Calcule la **boucle complète** d'une mission — dépôt Saint-Loubès → départ client → étapes →
arrivée client → retour dépôt — et rend les km A/R, le temps de conduite A/R, et un lien Mappy
de vérification par segment. Le péage n'est **jamais** calculé (voir plus bas).

## Utilisation

```bash
python "outils/pipeline/itineraire/calcul_itineraire.py" --depart "12 rue de Bazeilles, 33400 Talence" --arrivee "5 rue de Rivoli, 75004 Paris"
```

| Option | Effet |
|---|---|
| `--etape "<adresse>"` | Garde-meuble / point 2 / point 3. Répétable, dans l'ordre réel de la mission. |
| `--json` | Sortie JSON brute (pour un agent). Sans l'option : bloc texte prêt à coller dans la fiche Notion. |
| `--no-cache` | Force le recalcul même si l'axe est en cache. |
| `--no-save` | N'écrit pas le résultat dans le cache (tests). |

Code de sortie 1 si le calcul a échoué (adresse non résolue, routage indisponible).

## Règles métier appliquées

- **Marge trafic ou arrondi** (Karim, 11/09/2026, révisé le 14/09/2026), appliqué une fois à
  chaque temps de conduite A/R (`_temps_ar_ajuste`) : jusqu'à **1h30** de conduite A/R brute,
  **+0,25 h** fixes (`MARGE_TRAFIC_H`) ; au-delà, plus de marge fixe — le temps est **arrondi à
  la demi-heure supérieure** à la place (l'arrondi absorbe déjà plus que 15 min sur un trajet de
  cette durée). Les seuils ci-dessous se jugent sur le temps ajusté, comme le calculateur. La
  sortie JSON garde le temps brut dans `heures_conduite_brutes` (et `marge_trafic_h` indique
  laquelle des deux règles a joué : `0.25` ou `0`), et le cache d'axes ne stocke que le brut.
- **Itinéraire sans péage** tant que le temps de conduite A/R tient sous **19h06**. Au-delà,
  bascule automatique sur l'itinéraire avec péage. (Seuil relevé de 18 h à 19,1 h le 08/09 :
  voir « Calage » ci-dessous.)
- **Longue distance** = temps de conduite A/R **≥ 2 h** (décision D6, Karim 05/10/2026 : la règle des calculateurs fait foi, l'ancien seuil 5h59 est périmé) → taux unique de 20 €/h par personne
  du camion. La manutention est à 28 €/h dans tous les cas (Karim, 23/09/2026).
- **Péage jamais calculé.** Sous 19h06 il vaut 0. Au-delà, la sortie porte
  `🟡 Péage à renseigner (classe 3 ÷ 1,2)` : c'est Samuel qui le relève sur Mappy.
- **Aucune estimation de secours.** Si le calcul échoue, la sortie est
  `🟡 Itinéraire à renseigner manuellement` accompagnée des trois liens Mappy.

## Sources de données

| Rôle | Service | Clé |
|---|---|---|
| Géocodage | API Adresse (BAN, data.gouv.fr) | aucune |
| Routage | Valhalla FOSSGIS, profil `truck` | aucune |

Aucun abonnement. Valhalla FOSSGIS est un service communautaire : le script espace ses appels
et retente deux fois. Si sa disponibilité devenait un problème, le point de bascule est la
constante `VALHALLA_URL` (instance auto-hébergée, ou OpenRouteService avec une clé gratuite).

## Calage mesuré le 08/09/2026

Saint-Loubès → Paris, aller simple, contre les relevés Mappy :

| Variante | Module (`truck`) | Mappy | Écart |
|---|---|---|---|
| Avec péage | 566,0 km / 5 h 49 | 568 km / 5 h 12 | −0,4 % km, +12 % temps |
| Sans péage | 615,7 km / 8 h 26 | 598 km / 7 h 28 | +3 % km, +13 % temps |

Les kilomètres sont fiables. Les temps sont systématiquement ~12 % plus longs que Mappy, parce
que le module calcule en profil **poids lourd** et Mappy en voiture — plus réaliste pour un
30 m³ chargé.

C'est précisément ce qui a conduit à **relever le seuil sans-péage de 18 h à 19,1 h (19h06)**
le 08/09 : le seuil d'origine avait été calé sur des temps Mappy, et la boucle Bordeaux–Paris
sortait à 18,1 h en poids lourd, soit six minutes au-dessus — ce qui basculait l'axe principal
en « avec péage » et y remettait un relevé manuel. Avec le seuil à 19h06, la boucle
Bordeaux–Paris rend **1 283 km / 18,25 h sans péage**, à comparer à l'ancien forfait maison de
1 250 km / 19 h : le calage est bon.

## Cache d'axes

`outils/pipeline/axes-itineraires.csv`, append-only. Indexé sur les **adresses normalisées par la BAN**,
donc insensible à la façon dont l'adresse est écrite. Un axe déjà calculé répond en ~0,6 s au
lieu de ~2,2 s, sans toucher au réseau de routage. Péremption : 12 mois.

## Deux pièges déjà rencontrés, et corrigés

1. **La BAN fait du rapprochement approximatif** et peut renvoyer une adresse d'une **autre
   commune** avec un score acceptable et une précision `housenumber` : `12 rue des Lilas,
   Talence` → `12 Rue de Talence, 33000 Bordeaux`. Sans garde-fou, on routerait vers la
   mauvaise ville sans que personne ne le voie. Le module compare le code postal (ou la
   commune) de la saisie à celui du résultat et lève une alerte `⚠`.
2. **Le site Mappy ne sait pas encoder d'étapes dans une URL** : l'ancien format
   `#/recherche/A/B/C/D` ne retenait silencieusement que les deux premiers points, et le vrai
   format `#/voiture/<départ>/<arrivée>/car/9` renvoie une 404 au-delà de deux points. D'où
   **un lien par segment**, jamais un lien unique.

## Pages liées

[[pipeline-fiche-client-devis]] · [[calcul-devis]] · [[moteur-tarification-devis]]
