# Règles détaillées de remplissage — fiche client Sam'Déménage

> Reconstitué le 08/09/2026 depuis le prompt maître de Samuel. **Ce fichier fait foi** (Samuel,
> 03/11/2026) : la page de règles Notion n'est plus consultée, et une règle qui change se corrige ici.

## Formule à cocher

- ☑ **Standard** — aucune option (ni démontage/remontage, ni mise en carton). La mise en
  penderie est incluse dans le standard.
- ☑ **Confort** — au moins une option parmi : mise en carton partielle, protection du
  fragile, ou démontage/remontage.
- ☑ **Premium** — mise en carton complète **et** démontage/remontage.

**Règle stricte** : ne cocher la mise en carton, le démontage/remontage, la réservation de
places de parking ou toute autre option **que si c'est explicitement mentionné**. Ne jamais
déduire une option à partir de l'inventaire ou du contexte. Si rien n'est mentionné →
Standard par défaut, et supprimer les sections concernées.

## Abréviations à comprendre

`std` = cartons standards · `livres` = cartons livres · `bull` / `bulle` = rouleau de papier
bulle · `bouteilles` = cartons bouteilles · `penderies` = cartons penderies · `R+1` = RDC +
1 étage sans ascenseur.

## Nomenclature des étages — règle stricte

- **Maison** → notation `R+1`, `R+2`, etc.
- **Appartement** → numéro d'étage seul : `1`, `2`, `3`. **Jamais** `R+X`.
- **Appartement duplex avec ascenseur** → renseigner les deux champs : « Étage avec
  ascenseur » = étage d'accès (ex. 4) **et** « Étage sans ascenseur » = 1 (l'étage intérieur
  du duplex). Ajouter « (duplex) » à côté du type de logement.

## Distances de portage

Minimum **10 mètres** toujours appliqué, pour les deux distances (entrée et intérieur), au
départ **et** à l'arrivée.
- Non mentionnées → inscrire 10 mètres, **sans pastille 🟡**.
- Communiquées mais ≤ 10 m → inscrire quand même 10 mètres.
- Communiquées > 10 m → inscrire la valeur réelle.
- 🟡 uniquement si la distance est explicitement incertaine ou à confirmer.

**Parking ≠ portage** : « on peut se garer devant » signifie seulement que le portage est
standard. Ne cocher « Réserve les places de parking » que sur demande explicite du client.

## Meubles à démonter / remonter

Cocher la case correspondante ; si plusieurs unités, ajouter `x2`, `x3`, etc. Ne conserver
que les lignes cochées.

## Monte-charge / monte-meuble

Uniquement si le terme est **explicitement** mentionné. Ajouter une ligne dédiée
immédiatement sous « Meubles à démonter / remonter » :

```
- [x] Monte-charge (mention explicite)
```

**Tarifs en vigueur (arbitrage Karim 08/09/2026) — toujours par côté :**

| Prestation | Prix |
|---|---|
| 1 ou 2 éléments | **180 € HT** |
| 2 h | **300 € HT** |
| Demi-journée | **360 € HT** |

« Par côté » = au départ **et** à l'arrivée si le monte-meuble est nécessaire aux deux
adresses, donc facturé deux fois. Ce barème remplace celui du prompt maître
(200/350/400 € HT) et clôt la divergence entre les trois sources.

## Inventaire

- ☑ **Inventaire : Oui** dans tous ces cas : le prospect s'engage à en envoyer un plus tard ;
  l'inventaire est déjà reçu ; la source du volume est **Christophe** (il fournit
  systématiquement un inventaire dans un document séparé).
- ☑ **Pas d'inventaire** uniquement si le prospect donne un volume déjà estimé (cubage
  confrère, autre déménageur, volume fourni sans inventaire) → renseigner le volume avec sa
  source, ex. « 16 m³ — source : cubage confrère ».

**Date inventaire** : laisser la ligne vide dans les deux cas ci-dessus. Exceptions : date de
réception explicitement mentionnée → l'inscrire ; attendu avec date → `🟡 En attente
d'inventaire — prévu le JJ/MM` ; attendu sans date → `🟡 En attente d'inventaire`.

## Mise en cartons

Ne conserver que l'option cochée. **Mise en penderie** : si « mise en penderie : oui » est
mentionné sous quelque forme que ce soit, ajouter obligatoirement une ligne cochée
`- [x] Mise en penderie : X penderies` (nombre exact si précisé ; sinon `- [x] Mise en
penderie` et 🟡 dans les Notes, car cette ligne passe sur le devis) — **même quand la formule est Standard**, où la penderie est incluse.

## Matériel à livrer — calcul obligatoire

Toujours conserver la section intégralement. Calculer le total HT des articles cochés :

| Article | € HT / unité |
|---|---|
| Carton standard | 1,25 |
| Carton livres | 1,00 |
| Carton vaisselle | 4,75 |
| Carton bouteilles | 1,75 |
| Carton penderies | 0,00 (pas de livraison) |
| Carton informatique | 1,25 |
| Carton tableaux | 7,00 |
| Rouleau scotch | 2,50 |
| Rouleau bulles 20 m | 12,50 |
| Barrel verres | 5,00 |
| Barrel assiettes | 5,00 |
| Rouleau Kraft | 120,00 |

**Livraison du matériel : 30,00 € HT** dès qu'un article payant est commandé (les cartons
penderies, prêtés, ne la déclenchent pas). L'ancienne consigne « aucun montant de livraison
depuis le 29/07/2026 » est périmée (Karim, 05/10/2026, décision D4 du dictionnaire de données).
Ne jamais laisser le champ vide — `0,00 € HT` si rien n'est coché.

En dehors de la fiche (récap de conversation), détailler le calcul ligne par ligne.

## Déchetterie

Uniquement si explicitement mentionnée (évacuation, encombrants, débarras). Ajouter dans les
Notes ou à la suite des accès compliqués :

```
- [x] Déchetterie (mention explicite)
```

Tarifs : 1 à 3 m³ **90 € HT** · 4 à 6 m³ **130 € HT** · 12 m³ **200 € HT + 285 € HT/tonne**.

## Règles de nettoyage de la fiche

Pour chaque section Départ et Arrivée :
- **Sans ascenseur** → supprimer « Étage avec ascenseur », « Grand », « Petit », « Liste du
  mobilier qui ne rentre pas dans l'ascenseur ».
- **Avec ascenseur (non duplex)** → supprimer « Étage sans ascenseur » ; supprimer « Grand »
  et « Petit » si la taille n'est pas précisée.
- **Avec ascenseur (duplex)** → conserver les deux lignes d'étage.
- Ne conserver que le type de logement coché.

**Rez-de-chaussée** : la case « Rdc » est **indépendante** du type de logement. Si l'accès est
en RDC, cocher « Rdc » **en plus** du type de logement — les deux cases sont complémentaires.

Autres sections : meubles à démonter/remonter → ne garder que les lignes cochées · mise en
cartons → ne garder que l'option cochée · matériel à livrer → conserver intégralement ·
meubles lourds → remplir si mentionné, sinon supprimer la section · accès compliqués →
conserver telle quelle.

**Champs toujours laissés vides** (remplis à l'étape devis) : Transport, Manut, Formule,
Déplacement, Matériel, Prix Total.

## Vérification de cohérence — après remplissage

Signaler chaque incohérence dans le récapitulatif de conversation (**jamais dans la fiche**), sous la forme `⚠️ Incohérence détectée : [description]`.

**Formule / options** — Standard + démontage, Standard + mise en carton, Standard +
protection fragile → incohérent. Confort avec mise en carton complète **et** démontage →
c'est du Premium. Premium sans ces deux options → incohérent. Aucune formule cochée, ou
plusieurs → incohérent. *La mise en penderie n'est jamais une incohérence.*

**Volume / camion** — < 20 m³ → 1 camion 20 m³ · 20-30 m³ → 1 camion 30 m³ · > 30 m³ →
2 camions.

**Inventaire / source** — « Inventaire : Oui » avec un volume de confrère → incohérent.
« Pas d'inventaire » avec un inventaire Sam'Déménage joint → incohérent.

**Étage / logement** — Appartement en notation R+X → incohérent. Maison en numéro seul →
incohérent. Étage avec ascenseur renseigné sans case ascenseur cochée (ou l'inverse, hors
duplex) → incohérent.

**Parking** — case cochée sans demande explicite → incohérent.

**Matériel** — quantités cochées mais total vide ou faux → incohérent. Total incluant des
frais de livraison → incohérent.

**Débranchement électroménagers** — appareils dans l'inventaire (lave-linge, frigo,
congélateur, lave-vaisselle…) mais section supprimée → incohérent.

**Itinéraire** — voir l'étape 6 du `SKILL.md` : l'itinéraire est désormais calculé pour
**toutes** les missions, locales comprises, par `outils/pipeline/itineraire/calcul_itineraire.py`.
Section itinéraire vide alors que le module a produit un résultat → incohérent.

**Meubles lourds** — marbre, fonte ou bois massif dans l'inventaire mais section supprimée →
incohérent.

Si rien n'est détecté, conclure par : `✅ Aucune incohérence détectée — fiche cohérente.`
