#!/usr/bin/env python3
"""
Estimation de volume de demenagement — moteur de calcul.

Le modele extrait les objets de l'inventaire (texte libre, PDF, photos) et produit une
liste JSON ; ce script applique les coefficients et fait l'arithmetique. Separation
volontaire : l'identification des objets n'est pas codable, le calcul l'est — et un
calcul code est reproductible, verifiable et gratuit.

Regles : prompt maitre « Estimation de volume Sam'Demenage » (version consolidee Cowork).

VOLUME RETENU POUR LE DEVIS = LE CONSERVATEUR (decision Karim 08/09/2026).
Les volumes standard et longue distance restent calcules, a titre de comparaison.

Usage :
    python volume.py inventaire.json                 # rapport lisible
    python volume.py inventaire.json --json          # sortie machine
    python volume.py --exemple > inventaire.json
    python volume.py --references                    # table des volumes moyens
"""

import argparse
import json
import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --- Coefficients (prompt maitre) --------------------------------------------

COEF = {
    #                        standard  conservateur
    "avec_dims":            (1.06,     1.10),
    "sans_dims":            (1.10,     1.20),
    "demonte":              (1.15,     1.25),
    "irregulier":           (1.30,     1.50),
    "pro":                  (1.10,     1.30),
    "incertain":            (1.00,     1.20),   # surcote conservatrice seulement
}
MARGE_GLOBALE = 1.10
MAJORATION_LONGUE_DISTANCE = 1.20
PALIERS = (15, 20, 30)

# --- Volumes moyens de reference (m3 par unite) ------------------------------
# ⚠ Le prompt maitre renvoie aux « dimensions moyennes standard du metier » sans les
# chiffrer. Cette table est une PROPOSITION a valider par Samuel : elle pilote le volume
# de tout objet cite sans dimensions, donc directement le prix. Seuls les trois cartons
# viennent du prompt lui-meme.

REFERENCES = {
    # cartons — valeurs du prompt maitre
    "carton_standard": 0.10, "carton_livres": 0.06, "carton_penderie": 0.17,
    # assises
    "canape_2p": 1.00, "canape_3p": 1.50, "canape_angle": 2.20,
    "fauteuil": 0.70, "clic_clac": 1.00, "chaise": 0.15, "tabouret": 0.10,
    # rangements
    "armoire_2p": 1.20, "armoire_3p": 1.80, "commode": 0.50, "buffet": 1.00,
    "bibliotheque": 0.70, "etagere": 0.40, "meuble_tv": 0.40, "meuble_cuisine": 0.60,
    "secretaire": 0.60, "coffre": 0.30,
    # tailles explicites (16/09/2026, erreur BODARD) : une taille donnee par l'inventaire prime
    # sur la reference generique. Propositions, a valider comme le reste de la table.
    "buffet_petit": 0.60, "buffet_moyen": 1.00, "buffet_grand": 1.50,
    "etagere_petite": 0.25, "etagere_moyenne": 0.40, "etagere_grande": 0.70,
    "console": 0.20, "desserte": 0.20, "coiffeuse": 0.35, "portant": 0.30,
    "malle": 0.30, "bac_plastique": 0.08,
    # tables et bureaux
    "table_repas": 0.80, "grande_table": 1.20, "table_basse": 0.30,
    "bureau": 0.60, "table_chevet": 0.15,
    # couchage
    "lit_simple": 0.80, "lit_double": 1.20, "matelas_simple": 0.30,
    "matelas_double": 0.50, "sommier_double": 0.50, "lit_superpose": 1.50,
    "berceau": 0.40,
    # electromenager
    "refrigerateur": 0.50, "refrigerateur_combine": 0.70, "congelateur": 0.40,
    "lave_linge": 0.35, "seche_linge": 0.35, "lave_vaisselle": 0.35,
    "four": 0.15, "micro_ondes": 0.10, "cuisiniere": 0.40, "cave_a_vin": 0.50,
    # divers
    "televiseur": 0.15, "velo": 0.40, "aspirateur": 0.10, "valise": 0.10,
    "tapis_roule": 0.15, "lampadaire": 0.10, "miroir": 0.10, "tableau": 0.05,
    "piano_droit": 1.50, "piano_queue": 2.50, "coffre_fort": 0.30,
    "etabli": 0.80, "barbecue": 0.40, "poussette": 0.30, "aquarium": 0.30,
    "plante_pot": 0.20, "ventilateur": 0.05, "table_repasser": 0.05, "parasol": 0.10,
    "table_jardin": 0.60,
}


# --- Calcul ------------------------------------------------------------------

def _volume_unitaire(obj, conservateur):
    """Volume d'UNE unite de l'objet, coefficients appliques.

    Retourne (volume, base, coefs_appliques) — `base` sert au rapport detaille.
    """
    i = 1 if conservateur else 0
    coefs = []

    # Regle de la colonne neutralisee : arbres, grands arbustes, pots >= 40 cm.
    # C'est l'emprise verticale de chargement qui compte, jamais le volume du pot :
    # rien ne peut etre empile autour. Prevaut sur la geometrie irreguliere.
    if obj.get("colonne_cm"):
        l, p, h = obj["colonne_cm"]
        base = (l / 100.0) * (p / 100.0) * (h / 100.0)
        v = base * COEF["irregulier"][i]
        coefs.append("colonne neutralisée ×%s" % COEF["irregulier"][i])
        source = "colonne"
    elif obj.get("dims_cm"):
        l, p, h = obj["dims_cm"]
        base = (l / 100.0) * (p / 100.0) * (h / 100.0)
        v = base * COEF["avec_dims"][i]
        coefs.append("dims +%d%%" % round((COEF["avec_dims"][i] - 1) * 100))
        source = "dimensions"
    else:
        ref = obj.get("ref")
        if ref not in REFERENCES:
            raise ValueError(
                "objet %r sans dimensions et sans référence connue (ref=%r). "
                "Fournir dims_cm, ou une ref de --references."
                % (obj.get("nom"), ref))
        base = REFERENCES[ref]
        v = base * COEF["sans_dims"][i]
        coefs.append("sans dims +%d%%" % round((COEF["sans_dims"][i] - 1) * 100))
        source = "référence « %s »" % ref

    tags = [t for t in obj.get("tags", [])]
    if obj.get("colonne_cm") and "irregulier" in tags:
        tags.remove("irregulier")          # deja porte par la colonne neutralisee
    for tag in ("demonte", "irregulier", "pro"):
        if tag in tags:
            v *= COEF[tag][i]
            coefs.append("%s ×%s" % (tag, COEF[tag][i]))
    if obj.get("incertain") and conservateur:
        v *= COEF["incertain"][1]
        coefs.append("incertain ×%s" % COEF["incertain"][1])

    return v, base, coefs


def estimer(objets):
    lignes = []
    total_std = total_cons = 0.0
    for obj in objets:
        qte = obj.get("qte", 1)
        v_std, base, c_std = _volume_unitaire(obj, False)
        v_cons, _, c_cons = _volume_unitaire(obj, True)
        total_std += v_std * qte
        total_cons += v_cons * qte
        lignes.append({
            "nom": obj.get("nom"), "qte": qte, "base_unitaire": round(base, 3),
            "standard": round(v_std * qte, 3), "conservateur": round(v_cons * qte, 3),
            "coefs_standard": c_std, "coefs_conservateur": c_cons,
            "incertain": bool(obj.get("incertain")),
        })

    std_final = int(round(total_std * MARGE_GLOBALE))
    cons_final = int(round(total_cons * MARGE_GLOBALE))
    ld = int(round(std_final * MAJORATION_LONGUE_DISTANCE))

    return {
        "lignes": lignes,
        "sous_total_standard": round(total_std, 2),
        "sous_total_conservateur": round(total_cons, 2),
        "volume_standard": std_final,
        "volume_conservateur": cons_final,
        "volume_longue_distance": ld,
        # Le devis se base sur le conservateur (decision Karim 08/09/2026).
        "volume_retenu": cons_final,
        "ecart": round(cons_final - std_final, 2),
        "camion_standard": palier(std_final),
        "camion_conservateur": palier(cons_final),
        "camion_retenu": palier_avec_saturation(cons_final),
        "saturation": saturation(cons_final),
        "changement_palier": palier(std_final) != palier(cons_final),
        "incertitude": niveau_incertitude(objets, std_final, cons_final),
        "incertains": [o.get("nom") for o in objets if o.get("incertain")],
    }


def palier(v):
    for p in PALIERS:
        if v <= p:
            return p
    return None                      # au-dela de 30 m3 : plusieurs camions


def saturation(v_cons):
    """Le taux de remplissage reel n'atteint jamais la capacite nominale : un
    conservateur qui touche le plafond du palier impose le palier superieur."""
    p = palier(v_cons)
    return p is not None and v_cons >= p


def palier_avec_saturation(v_cons):
    p = palier(v_cons)
    if p is None:
        return None
    if v_cons >= p:                                  # sature : palier au-dessus
        suivants = [x for x in PALIERS if x > p]
        return suivants[0] if suivants else None
    return p


def niveau_incertitude(objets, std, cons):
    ecart_pct = ((cons - std) / std * 100) if std else 0
    risques = sum(1 for o in objets
                  if o.get("incertain") or not (o.get("dims_cm") or o.get("colonne_cm"))
                  or set(o.get("tags", [])) & {"pro", "irregulier", "demonte"})
    part = risques / len(objets) if objets else 0
    if ecart_pct > 30 or part > 0.6:
        return "Élevé"
    if ecart_pct > 15 or part > 0.3:
        return "Modéré"
    return "Faible"


# --- Rapport -----------------------------------------------------------------

def rapport(r, nom_client="", detail=False):
    L = ["📦 Estimation de volume — %s" % (nom_client or "(client non précisé)"),
         "————————————————————————"]
    if detail:
        L.append("Détail par ligne :")
        for l in r["lignes"]:
            L.append("  %-34s ×%-3s std %6.2f  cons %6.2f   [%s]"
                     % (l["nom"][:34], l["qte"], l["standard"], l["conservateur"],
                        ", ".join(l["coefs_conservateur"])))
        L.append("————————————————————————")

    L += ["Sous-total standard (après marges) : %.2f m³" % r["sous_total_standard"],
          "Marge globale : +10% → arrondi à l'entier le plus proche",
          "   Volume standard : %d m³" % r["volume_standard"],
          "————————————————————————",
          "Sous-total conservateur (après marges) : %.2f m³" % r["sous_total_conservateur"],
          "Marge globale : +10% → arrondi à l'entier le plus proche",
          "✅ Volume conservateur : %d m³   ← RETENU POUR LE DEVIS" % r["volume_conservateur"],
          "————————————————————————",
          "🚛 Analyse camion :",
          "  Paliers disponibles : 15 m³ / 20 m³ / 30 m³",
          "",
          "  Volume standard → camion : %s" % _fmt_palier(r["camion_standard"]),
          "  Volume conservateur → camion : %s" % _fmt_palier(r["camion_conservateur"]),
          ""]

    if r["changement_palier"]:
        L += ["  ⚠️ Changement de palier : OUI",
              "  → L'incertitude fait basculer d'un camion %s à un camion %s."
              % (_fmt_palier(r["camion_standard"]), _fmt_palier(r["camion_conservateur"])),
              "    Recommandation : retenir le %s, ou lever les incertitudes"
              " par un inventaire visuel." % _fmt_palier(r["camion_retenu"])]
    elif r["saturation"]:
        L += ["  ⚠️ Changement de palier : NON, mais saturation",
              "  → Le volume conservateur atteint la capacité nominale théorique du camion"
              " — en pratique jamais totalement exploitable.",
              "    Privilégier le palier supérieur (%s), ou lever les incertitudes"
              " avant de trancher." % _fmt_palier(r["camion_retenu"])]
    else:
        L += ["  ⚠️ Changement de palier : NON",
              "  → Les deux estimations rentrent dans le même camion %s, avec marge."
              % _fmt_palier(r["camion_conservateur"])]

    L += ["————————————————————————",
          "📊 Écart entre les deux estimations : %s m³" % r["ecart"],
          "💬 Niveau d'incertitude : %s" % r["incertitude"]]
    if r["incertains"]:
        L += ["", "⚠️ Éléments incertains à confirmer avec le client :"]
        L += ["  - %s" % n for n in r["incertains"]]
    L += ["————————————————————————",
          "🛣️ Estimation longue distance — sans visite technique :",
          "   Volume standard × 1,20 = %d m³" % r["volume_longue_distance"]]
    return "\n".join(L)


def _fmt_palier(p):
    return "%d m³" % p if p else "> 30 m³ (plusieurs camions)"


EXEMPLE = [
    {"nom": "Canapé 3 places", "qte": 1, "dims_cm": [200, 90, 80]},
    {"nom": "Armoire 3 portes (démontée)", "qte": 1, "ref": "armoire_3p", "tags": ["demonte"]},
    {"nom": "Cartons standards", "qte": 25, "ref": "carton_standard"},
    {"nom": "Vélos", "qte": 2, "ref": "velo", "tags": ["irregulier"]},
    {"nom": "Olivier en pot", "qte": 1, "colonne_cm": [150, 150, 250]},
    {"nom": "Buffet ancien vitré", "qte": 1, "ref": "buffet", "tags": ["pro"],
     "incertain": True},
]


def main():
    ap = argparse.ArgumentParser(description="Estimation de volume Sam'Demenage")
    ap.add_argument("inventaire", nargs="?", help="JSON : liste d'objets, ou {client, objets}")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--detail", action="store_true", help="detail ligne par ligne")
    ap.add_argument("--exemple", action="store_true")
    ap.add_argument("--references", action="store_true", help="table des volumes moyens")
    a = ap.parse_args()

    if a.exemple:
        print(json.dumps({"client": "DUPONT Marie", "objets": EXEMPLE},
                         ensure_ascii=False, indent=2))
        return 0
    if a.references:
        print("Volumes moyens de référence (m³/unité) — À VALIDER PAR KARIM")
        for k in sorted(REFERENCES):
            print("  %-24s %.2f" % (k, REFERENCES[k]))
        return 0
    if not a.inventaire:
        ap.error("fichier inventaire requis (ou --exemple / --references)")

    with open(a.inventaire, encoding="utf-8") as fh:
        data = json.load(fh)
    objets = data if isinstance(data, list) else data.get("objets", [])
    client = "" if isinstance(data, list) else data.get("client", "")

    try:
        r = estimer(objets)
    except ValueError as exc:
        print("Erreur : %s" % exc, file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(rapport(r, client, detail=a.detail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
