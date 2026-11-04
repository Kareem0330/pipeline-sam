#!/usr/bin/env python3
"""
Temps de demontage / remontage — bareme Sam'Demenage (Karim, 11/09/2026).

Le bareme donne, par element, le temps de demontage PLUS remontage pour une equipe de
2 personnes (Karim, 06/10/2026 ; il etait lu pour 3 personnes avant). Chaque ligne cochee de « Meubles a demonter / remonter » est rapprochee de
l'element le plus proche par mots-cles, du plus specifique au plus general.

Trois issues par ligne, jamais de temps invente :
  chiffree      element au bareme : temps x quantite (ou x nombre de modules) ;
  sans temps    element repertorie sans estimation (chaise, cuisine, TV...) : 0, signale ;
  non reconnue  aucun element proche : 0, signale pour chiffrage a la main.

Le calculateur facture demontageH x 2 x taux, quel que soit l'effectif du chantier : le
temps du bareme se saisit tel quel, sans conversion.

Usage :
    python demontage.py "Lit 2 places" "Armoire 3 portes x2"
    python demontage.py --bareme
"""

import argparse
import json
import re
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EQUIPE_DEMONTAGE = 2            # bareme et facturation : 2 personnes (Karim, 06/10/2026)

# (motif sur le libelle normalise, element du bareme, heures ou None, unite)
# unite « piece » : x quantite ; « module » : x nombre de modules. Le premier motif qui
# correspond l'emporte : les plus specifiques sont en tete (canape-lit avant lit et canape).
BAREME = [
    (r"canape[ -]?lit|clic[ -]?clac|convertible", "Canapé-lit / clic-clac", 0.75, "piece"),
    (r"\bbz\b", "BZ", None, "piece"),
    (r"salon de jardin", "Salon de jardin (table + chaises)", None, "piece"),
    (r"ping[ -]?pong", "Table de ping-pong", None, "piece"),
    (r"baby[ -]?foot", "Babyfoot", 1.25, "piece"),
    (r"billard", "Billard", 1.25, "piece"),
    (r"superpose", "Lit superposé", 1.0, "piece"),
    (r"gigogne", "Lit gigogne", 1.0, "piece"),
    (r"mezzanine", "Lit mezzanine", 1.0, "piece"),
    (r"baldaquin", "Lit à baldaquin", 1.0, "piece"),
    (r"lit parapluie", "Lit parapluie", 1.0, "piece"),
    (r"lit (de )?bebe|lit (a )?barreaux", "Lit bébé / barreaux", 0.75, "piece"),
    (r"\blit\b.*coffre|coffre.*\blit\b", "Lit coffre", 0.75, "piece"),
    (r"\blit\b.*tiroir", "Lit tiroir", 0.75, "piece"),
    (r"\blits?\b|sommier|tete de lit", "Lit simple / double", 0.5, "piece"),
    (r"dressing.*(sur[ -]?mesure|encastre)", "Dressing sur-mesure / encastré", 1.0, "module"),
    (r"dressing.*\b([4-9]|\d\d)\s*modules?", "Dressing 4 modules", 1.0, "piece"),
    (r"dressing", "Dressing 1 à 3 modules", 0.75, "piece"),
    (r"armoire.*coulissant", "Armoire à portes coulissantes", 0.75, "piece"),
    (r"armoire.*\b(4|quatre)\s*portes", "Armoire 4 portes", 1.0, "piece"),
    (r"armoire", "Armoire 2-3 portes / enfant / normande", 0.75, "piece"),
    (r"penderie|portant", "Penderie autonome / portant", 1.0, "piece"),
    (r"commode", "Commode", 0.75, "piece"),
    (r"chiffonnier", "Chiffonnier", None, "piece"),
    (r"bibliotheque.*modul", "Bibliothèque modulaire", 0.75, "module"),
    (r"bibliotheque", "Bibliothèque", 0.75, "piece"),
    (r"billy|kallax", "Meuble Billy / Kallax", 0.75, "piece"),
    (r"etagere", "Étagère murale fixée", 0.75, "piece"),
    (r"meuble (tv|tele).*(mural|complexe)", "Meuble TV mural complexe", 0.75, "piece"),
    (r"meuble (tv|tele)", "Meuble TV simple", 0.5, "piece"),
    (r"vaisselier", "Vaisselier", 0.75, "piece"),
    (r"buffet|enfilade", "Buffet / enfilade", 0.75, "piece"),
    (r"chevet", "Table de chevet", 0.5, "piece"),
    (r"table basse", "Table basse", 0.5, "piece"),
    (r"console", "Table console", 0.5, "piece"),
    (r"table.*jardin", "Table de jardin", 0.5, "piece"),
    (r"table.*\b([89]|1\d)\s*(p\b|pers|places|couverts)", "Table à manger 8 personnes ou plus",
     0.75, "piece"),
    (r"\btable\b", "Table à manger / avec rallonges", 0.5, "piece"),
    (r"bureau", "Bureau", 0.75, "piece"),
    (r"canape.*angle", "Canapé d'angle", 0.75, "piece"),
    (r"canape.*modul", "Canapé modulable", 0.5, "module"),
    (r"canape.*\b2\s*(places|p\b)", "Canapé 2 places", 0.5, "piece"),
    (r"canape", "Canapé 3 places", 0.75, "piece"),
    (r"fauteuil", "Fauteuil massif", 0.75, "piece"),
    (r"luminaire|lustre|suspension", "Luminaire / lustre", 1.5, "piece"),
    (r"chaise|tabouret", "Chaise / tabouret de bar", None, "piece"),
    (r"ilot|cuisine (equipee|amenagee)|elements? de cuisine|meubles? de cuisine|hotte|plaque"
     r"|\bfour\b|lave[ -]?(vaisselle|linge)|seche[ -]?linge|frigo|refrigerateur|congelateur",
     "Cuisine & électroménager", None, "piece"),
    (r"barbecue|plancha|parasol|tonnelle|pergola|abri de jardin|cabanon|trampoline|portique"
     r"|balancoire|piscine", "Extérieur & jardin", None, "piece"),
    (r"tapis de course|rameur|velo d.?appartement|elliptique|musculation",
     "Sport & loisirs", None, "piece"),
    (r"tableau|cadre|tringle|televiseur|\btv\b|ecran|climatiseur|pompe a chaleur",
     "Tableau / tringle / TV / climatiseur", None, "piece"),
]


def _norme(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = s.replace("×", "x").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def quantite(texte):
    """« x2 », « ×3 », « 2 x », « 2 armoires » -> 2 ; rien -> 1. « 90x200 » n'en est pas une."""
    m = (re.search(r"(?:^|[\s(])x\s*(\d{1,2})\b", texte)
         or re.search(r"\b(\d{1,2})\s*x(?=\s|$)", texte)
         or re.match(r"(\d{1,2})\s+(?!places?\b|portes?\b|modules?\b|p\b|pers|couverts?\b|c?m\b)[a-z]",
                     texte))
    return max(int(m.group(1)), 1) if m else 1


def rapprocher(libelle):
    """Rend (element, heures, unite) du premier motif qui correspond, ou (None, None, None)."""
    n = _norme(libelle)
    for motif, element, heures, unite in BAREME:
        if re.search(motif, n):
            return element, heures, unite
    return None, None, None


def estimer(lignes):
    detail, sans_temps, non_reconnues, total = [], [], [], 0.0
    for ligne in lignes:
        libelle = re.sub(r"^\s*-?\s*\[[ xX]\]\s*", "", ligne or "").strip()
        if not libelle:
            continue
        n = _norme(libelle)
        element, heures, unite = rapprocher(libelle)
        if unite == "module":
            m = re.search(r"(\d{1,2})\s*modules?", n)
            nombre = int(m.group(1)) if m else 1
        else:
            nombre = quantite(n)
        if element is None:
            non_reconnues.append(libelle)
        elif heures is None:
            sans_temps.append(libelle)
        else:
            total += heures * nombre
        detail.append({"ligne": libelle, "element": element, "unitaire_h": heures,
                       "quantite": nombre, "unite": unite,
                       "heures": round(heures * nombre, 2) if heures else 0.0})
    return {"heures_bareme": round(total, 2), "effectif": EQUIPE_DEMONTAGE,
            "heures": round(total, 2),
            "detail": detail, "sans_temps": sans_temps, "non_reconnues": non_reconnues}


def _h(x):
    return ("%g" % x).replace(".", ",")


def rapport(est):
    lignes = ["Démontage / remontage : %s h au barème (facturées pour %d personnes)" % (
        _h(est["heures"]), EQUIPE_DEMONTAGE)]
    for d in est["detail"]:
        if d["element"] is None:
            lignes.append("  🟡 %s → hors barème, temps non compté" % d["ligne"])
        elif d["unitaire_h"] is None:
            lignes.append("  🟡 %s → %s : pas de temps au barème, non compté"
                          % (d["ligne"], d["element"]))
        else:
            fois = (" (%d%s × %s h)" % (d["quantite"], " modules" if d["unite"] == "module" else "",
                                        _h(d["unitaire_h"])) if d["quantite"] > 1 else "")
            lignes.append("  · %s → %s : %s h%s" % (d["ligne"], d["element"], _h(d["heures"]), fois))
    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser(description="Temps de démontage / remontage — barème Sam'Déménage")
    ap.add_argument("lignes", nargs="*", help="un élément par argument (« Armoire 3 portes x2 »)")
    ap.add_argument("--bareme", action="store_true", help="afficher le barème")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.bareme:
        for _, element, heures, unite in BAREME:
            valeur = "—" if heures is None else "%s h%s" % (_h(heures),
                                                            " / module" if unite == "module" else "")
            print("  %-42s %s" % (element, valeur))
        return 0
    if not a.lignes:
        ap.error("au moins un élément, ou --bareme")

    est = estimer(a.lignes)
    print(json.dumps(est, ensure_ascii=False, indent=2) if a.json else rapport(est))
    return 0


if __name__ == "__main__":
    sys.exit(main())
