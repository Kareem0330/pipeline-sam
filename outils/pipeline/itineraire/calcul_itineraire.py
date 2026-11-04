#!/usr/bin/env python3
"""
Calcul d'itineraire pour une mission Sam'Demenage.

Boucle : depot Saint-Loubes -> depart client -> (etapes) -> arrivee client -> depot.
Produit : km A/R, temps de conduite A/R, variante retenue, liens Mappy de verification.

Le peage n'est JAMAIS calcule (arbitrage Karim 08/09/2026) : Samuel le releve a la main
en classe 3 sur Mappy et divise par 1,2. Le script signale seulement s'il est requis.

Regles metier appliquees :
  - Variante sans peage retenue tant que le temps de conduite A/R <= 19h06 (seuil releve
    de 18 h a 19,1 h le 08/09/2026 : le profil poids lourd est ~12 % plus lent que Mappy,
    sur lequel le seuil d'origine avait ete cale, et Bordeaux-Paris sortait juste au-dessus).
    Au-dela, bascule sur l'itineraire avec peage et signale le peage a relever.
  - Longue distance = temps de conduite A/R > 2 h, 2 h pile = court (Karim 21/10/2026 ; decision D6 du dictionnaire, Karim 05/10/2026 :
    la regle des calculateurs fait foi ; 5h59 du 28/08/2026 perime) : taux unique de
    20 EUR/h par personne du camion. La manutention est a 28 EUR/h dans tous les cas.
  - Marge trafic (Karim, 14/09/2026) : jusqu'a 1h30 de conduite A/R brute, +15 min fixes.
    Au-dela, plus de marge fixe — le temps est arrondi a la demi-heure superieure a la place.

Sources : geocodage = API Adresse (BAN, data.gouv.fr) ; routage = Valhalla FOSSGIS,
profil truck. Aucune cle API requise.

Usage :
    python calcul_itineraire.py --depart "12 rue des Lilas, Talence" \
                                --arrivee "5 rue de Rivoli, 75004 Paris"
    python calcul_itineraire.py --depart "..." --arrivee "..." --etape "..." --json
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --- Constantes metier -------------------------------------------------------

DEPOT = "147 route des Valentons, 33450 Saint-Loubes"
SEUIL_SANS_PEAGE_H = 19.1        # au-dela, on bascule sur l'itineraire avec peage
SEUIL_LONGUE_DISTANCE_H = 2.0   # A/R > 2 h ; 2 h pile = court (Karim 21/10/2026 ; D6, Karim 05/10/2026 ; 5h59 du 28/08 perime)
# Marge embouteillages (Karim, 11/09/2026, revise le 14/09/2026) : jusqu'a 1h30 de conduite
# A/R brute, +15 min ajoutees une fois, avant toute comparaison aux seuils — le calculateur,
# qui recoit ce temps, juge lui aussi ses bascules (2 h, 6 h, hotel) sur le temps ajuste.
# Au-dela de 1h30 brutes, la marge fixe ne s'applique plus : le temps est arrondi a la demi-
# heure superieure a la place (Karim, 14/09/2026) — l'arrondi absorbe deja plus que 15 min des
# que le trajet depasse ce seuil. Le cache garde toujours le temps brut, jamais l'ajuste.
MARGE_TRAFIC_H = 0.25
SEUIL_ARRONDI_DEMI_HEURE_H = 1.5


def _temps_ar_ajuste(h_brut):
    """Temps de conduite A/R apres ajustement metier. Rend (temps_ajuste, marge_appliquee) :
    marge_appliquee vaut MARGE_TRAFIC_H sous le seuil, 0.0 au-dela (le temps est deja arrondi
    a la hausse, il ne porte plus de marge distincte)."""
    if h_brut > SEUIL_ARRONDI_DEMI_HEURE_H:
        return math.ceil(h_brut * 2) / 2, 0.0
    return h_brut + MARGE_TRAFIC_H, MARGE_TRAFIC_H

BAN_URL = "https://api-adresse.data.gouv.fr/search/"
VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
MAPPY_TPL = "https://fr.mappy.com/itineraire#/voiture/{a}/{b}/car/9"
USER_AGENT = "SamDemenage-itineraire/1.0 (interne)"

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "axes-itineraires.csv")
CACHE_COLS = ["depart", "arrivee", "etapes", "km_ar", "h_ar", "variante",
              "longue_distance", "date_calcul"]


# --- Acces reseau ------------------------------------------------------------

def _get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _hm(h):
    """5.9833 -> '5h59' ; 19.1 -> '19h06'."""
    m = int(round(h * 60))
    return "%dh%02d" % (m // 60, m % 60)


def _repartir(valeurs, total, decimales):
    """Arrondit chaque valeur a `decimales` en garantissant que la somme vaut exactement
    `total` (au prorata, plus forts restes). Les totaux A/R sont arrondis (km a l'unite,
    temps au quart d'heure) : sans cette repartition, la somme des segments s'en ecarte."""
    unite = 10 ** decimales
    cible = int(round(total * unite))
    brut = sum(valeurs)
    if brut <= 0:
        return [0.0] * len(valeurs)
    parts = [v * cible / brut for v in valeurs]
    entiers = [int(p) for p in parts]
    reste = cible - sum(entiers)
    ordre = sorted(range(len(parts)), key=lambda i: parts[i] - entiers[i], reverse=reste > 0)
    for i in ordre[:abs(reste)]:
        entiers[i] += 1 if reste > 0 else -1
    return [e / unite for e in entiers]


def _sans_accents(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _commune_coherente(saisie, props):
    """La BAN fait du rapprochement approximatif et peut renvoyer une adresse d'une AUTRE
    commune avec un score acceptable (constate : '12 rue des Lilas, Talence' -> '12 Rue de
    Talence, 33000 Bordeaux', score 0,58). Sans ce controle, on routerait vers la mauvaise
    ville sans que personne ne le voie."""
    cps = re.findall(r"\b\d{5}\b", saisie)
    if cps:
        return props.get("postcode") in cps
    ville = _sans_accents(props.get("city", ""))
    return bool(ville) and ville in _sans_accents(saisie)


def geocode(adresse):
    """Adresse libre -> point normalise. Leve ValueError si non resolue."""
    url = BAN_URL + "?" + urllib.parse.urlencode({"q": adresse, "limit": 1})
    data = _get(url, timeout=20)
    feats = data.get("features") or []
    if not feats:
        raise ValueError("adresse introuvable : %s" % adresse)
    f = feats[0]
    p = f["properties"]
    if p.get("score", 0) < 0.5:
        raise ValueError("adresse trop imprecise (score %.2f) : %s" % (p.get("score", 0), adresse))
    lon, lat = f["geometry"]["coordinates"]
    return {
        "saisie": adresse,
        "label": p["label"],
        "lon": lon,
        "lat": lat,
        "precision": p.get("type"),      # housenumber | street | municipality | locality
        "score": round(p.get("score", 0), 3),
        "commune_coherente": _commune_coherente(adresse, p),
    }


class AucunTrajet(RuntimeError):
    """Valhalla 442 : aucun trajet poids lourd entre ces points, dans CE sens. Definitif —
    inutile de retenter, contrairement aux pannes du service communautaire."""


def route(points, use_tolls, retries=2):
    """Trajet entre N points (>=2). Retourne (km, heures)."""
    payload = {
        "locations": [{"lat": p["lat"], "lon": p["lon"]} for p in points],
        "costing": "truck",
        "costing_options": {"truck": {"use_tolls": 1 if use_tolls else 0}},
        "units": "kilometers",
    }
    # separateurs compacts + quote (et non urlencode) : Valhalla ne relit pas les espaces
    # encodes en '+' et repond 400 "Failed to parse json request".
    url = VALHALLA_URL + "?json=" + urllib.parse.quote(
        json.dumps(payload, separators=(",", ":")), safe="")
    last = None
    for attempt in range(retries + 1):
        try:
            summary = _get(url)["trip"]["summary"]
            return summary["length"], summary["time"] / 3600.0
        except urllib.error.HTTPError as exc:
            # Le code metier n'est que dans le CORPS de la reponse : str(HTTPError) se resume a
            # « HTTP Error 400: Bad Request », identique pour un 442 et pour un JSON malforme.
            corps = ""
            try:
                corps = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            if "No path could be found" in corps or '"error_code":442' in corps:
                raise AucunTrajet("aucun trajet poids lourd entre ces points, dans ce sens")
            last = exc if not corps else "%s — %s" % (exc, corps[:200])
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        except Exception as exc:                 # service communautaire : on retente
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("routage indisponible : %s" % last)


# --- Liens de verification ---------------------------------------------------

def lien_mappy(a, b):
    """Un lien par segment : le site Mappy ne sait pas encoder d'etapes dans une URL
    (teste le 08/09/2026 : au-dela de 2 points -> 404 Route not found)."""
    q = lambda s: urllib.parse.quote(s, safe="")
    return MAPPY_TPL.format(a=q(a["label"]), b=q(b["label"]))


# --- Cache d'axes ------------------------------------------------------------

def cache_key(depart, arrivee, etapes):
    """Cle batie sur les adresses NORMALISEES par la BAN, jamais sur la saisie brute :
    '12 rue de Bazeilles, 33400 Talence' et '12 Rue de Bazeilles 33400 Talence' doivent
    tomber sur la meme entree."""
    def n(s):
        s = _sans_accents(s)
        return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())
    return "|".join([n(depart), n(arrivee), ";".join(n(e) for e in etapes)])


def cache_lire(depart, arrivee, etapes):
    """Retourne l'entree la plus recente et non perimee, le fichier etant append-only."""
    if not os.path.exists(CACHE):
        return None
    key = cache_key(depart, arrivee, etapes)
    trouve = None
    with open(CACHE, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if cache_key(row["depart"], row["arrivee"],
                         [e for e in row["etapes"].split(";") if e]) != key:
                continue
            if date.today().year - int(row["date_calcul"][:4]) > 1:
                continue
            if trouve is None or row["date_calcul"] >= trouve["date_calcul"]:
                trouve = row
    return trouve


def cache_ecrire(res):
    neuf = not os.path.exists(CACHE)
    with open(CACHE, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CACHE_COLS)
        if neuf:
            w.writeheader()
        w.writerow({
            "depart": res["depart"]["label"],
            "arrivee": res["arrivee"]["label"],
            "etapes": ";".join(e["label"] for e in res["etapes"]),
            "km_ar": res["km_ar"],
            "h_ar": res.get("heures_conduite_brutes", res["heures_conduite_ar"]),
            "variante": res["variante"],
            "longue_distance": res["longue_distance"],
            "date_calcul": res["calcule_le"],
        })


# --- Coeur -------------------------------------------------------------------

def calculer(adr_depart, adr_arrivee, adr_etapes=(), utiliser_cache=True):
    res = {
        "km_ar": None, "heures_conduite_ar": None, "variante": None,
        "peage_ht": None, "peage_requis": False, "longue_distance": None,
        "segments": [], "source": None, "calcule_le": date.today().isoformat(),
        "confiance": None, "alertes": [],
    }

    # 1. Geocodage — toujours en premier : c'est lui qui produit les adresses normalisees
    # sur lesquelles le cache est indexe, et il coute quelques centaines de ms.
    try:
        depot = geocode(DEPOT)
        depart = geocode(adr_depart)
        arrivee = geocode(adr_arrivee)
        etapes = [geocode(e) for e in adr_etapes]
    except Exception as exc:
        res["confiance"] = "echec"
        res["alertes"].append("Geocodage impossible : %s" % exc)
        return res

    res["depart"], res["arrivee"], res["etapes"], res["depot"] = depart, arrivee, etapes, depot

    for nom, pt in [("depart", depart), ("arrivee", arrivee)] + \
                   [("etape %d" % (i + 1), e) for i, e in enumerate(etapes)]:
        if not pt["commune_coherente"]:
            res["alertes"].append(
                "⚠ Adresse %s : saisie \"%s\" resolue en \"%s\" — commune differente de "
                "celle demandee. A verifier avant d'utiliser ces km."
                % (nom, pt["saisie"], pt["label"]))
        elif pt["precision"] != "housenumber":
            res["alertes"].append(
                "⚠ Adresse %s resolue au niveau '%s' (\"%s\") : km estime depuis la ville, "
                "pas depuis l'adresse exacte." % (nom, pt["precision"], pt["label"]))

    # 2. Boucle decoupee en troncons a deux points, etapes comprises : un segment et un lien
    # Mappy par troncon (un lien Mappy a plus de deux points est impossible, cf. lien_mappy)
    arrets = [("depot", depot), ("depart", depart)] \
        + [("etape %d" % (i + 1), e) for i, e in enumerate(etapes)] \
        + [("arrivee", arrivee), ("depot", depot)]
    segments = [("S%d %s -> %s" % (i + 1, arrets[i][0], arrets[i + 1][0]),
                 [arrets[i][1], arrets[i + 1][1]]) for i in range(len(arrets) - 1)]
    liens = [{"segment": lib, "lien_mappy": lien_mappy(*pts)} for lib, pts in segments]

    # 3. Cache — interroge sur les adresses normalisees, evite les appels de routage
    if utiliser_cache:
        hit = cache_lire(depart["label"], arrivee["label"], [e["label"] for e in etapes])
        if hit:
            h_brut = float(hit["h_ar"])
            h_ajuste, marge = _temps_ar_ajuste(h_brut)
            res.update({
                "km_ar": int(float(hit["km_ar"])),
                "heures_conduite_brutes": h_brut,
                "heures_conduite_ar": h_ajuste,
                "marge_trafic_h": marge,
                "variante": hit["variante"],
                "longue_distance": h_ajuste > SEUIL_LONGUE_DISTANCE_H,
                "peage_requis": hit["variante"] == "avec_peage",
                "segments": liens,
                "source": "cache",
                "calcule_le": hit["date_calcul"],
            })
            res["alertes"].append("Valeurs reprises du cache d'axes (calcul du %s)."
                                  % hit["date_calcul"])
            if res["peage_requis"]:
                res["alertes"].append("Peage a relever manuellement sur Mappy (classe 3, / 1,2).")
            res["confiance"] = "degrade" if any(a.startswith("⚠") for a in res["alertes"]) else "ok"
            return res

    def segment(libelle, points, use_tolls):
        """Un troncon, avec repli sur le sens inverse. Une rue interdite aux poids lourds
        dans OSM se route dans un sens et pas dans l'autre : Valhalla rend alors 442 « No path
        could be found » et, sans ce repli, tout l'itineraire tombe en echec pour un seul
        troncon. Le sens inverse donne le meme trajet a quelques dizaines de metres pres."""
        try:
            return route(points, use_tolls)
        except AucunTrajet:
            time.sleep(0.4)
            km, h = route(list(reversed(points)), use_tolls)
            msg = ("⚠ %s : aucun trajet poids lourd dans ce sens (acces probablement interdit "
                   "aux PL dans OSM) — troncon mesure en sens inverse." % libelle)
            if msg not in res["alertes"]:      # boucle rejouee avec peage : une seule alerte
                res["alertes"].append(msg)
            return km, h

    def boucle(use_tolls):
        detail = []
        for libelle, points in segments:
            km, h = segment(libelle, points, use_tolls)
            detail.append({"segment": libelle, "km": km, "heures": h,
                           "lien_mappy": lien_mappy(*points)})
            time.sleep(0.4)          # service communautaire : on reste courtois
        return sum(s["km"] for s in detail), sum(s["heures"] for s in detail), detail

    # 3. Regle des 19h06 (sans peage tant que l'A/R tient sous 19h06)
    try:
        km, h, detail = boucle(use_tolls=False)
        variante = "sans_peage"
        h_ajuste_test, _ = _temps_ar_ajuste(h)
        if h_ajuste_test > SEUIL_SANS_PEAGE_H:
            res["alertes"].append(
                "Itineraire sans peage a %.1f h A/R ajustee (> %.1f h) : bascule "
                "sur l'itineraire avec peage." % (h_ajuste_test, SEUIL_SANS_PEAGE_H))
            km, h, detail = boucle(use_tolls=True)
            variante = "avec_peage"
    except Exception as exc:
        res["confiance"] = "echec"
        res["alertes"].append("Routage impossible : %s" % exc)
        res["segments"] = liens
        return res

    km_ar, h_ar = round(km), round(h * 4) / 4          # temps arrondi au quart d'heure
    # segments arrondis de sorte que leur somme retombe exactement sur les totaux A/R
    for seg, seg_km, seg_h in zip(detail, _repartir([s["km"] for s in detail], km_ar, 1),
                                  _repartir([s["heures"] for s in detail], h_ar, 2)):
        seg["km"], seg["heures"] = seg_km, seg_h
    h_ajuste, marge = _temps_ar_ajuste(h_ar)
    res.update({
        "km_ar": km_ar,
        "heures_conduite_ar": h_ajuste,
        "heures_conduite_brutes": h_ar,             # somme des segments, sans marge ni arrondi
        "marge_trafic_h": marge,
        "variante": variante,
        "peage_requis": variante == "avec_peage",
        "longue_distance": h_ajuste > SEUIL_LONGUE_DISTANCE_H,
        "segments": detail,
        "source": "valhalla-truck",
        "confiance": "degrade" if any(a.startswith("⚠") for a in res["alertes"]) else "ok",
    })
    if variante == "avec_peage":
        res["alertes"].append("Peage a relever manuellement sur Mappy (classe 3, / 1,2).")
    return res


# --- Restitution -------------------------------------------------------------

def bloc_notion(r):
    """Bloc pret a coller dans la section Itineraire de la fiche Notion."""
    if r["confiance"] == "echec":
        lignes = ["🟡 Itineraire a renseigner manuellement (calcul automatique indisponible)"]
        for s in r["segments"]:
            lignes.append("  %s : %s" % (s["segment"], s["lien_mappy"]))
        return "\n".join(lignes)

    h = r["heures_conduite_ar"]
    marge = r.get("marge_trafic_h", MARGE_TRAFIC_H)
    if marge > 0:
        detail_marge = "dont %s h de marge trafic" % ("%.2f" % marge).rstrip("0").rstrip(".")
    else:
        detail_marge = ("arrondi a la demi-heure superieure, sans marge trafic distincte "
                        "(brut > %s)" % _hm(SEUIL_ARRONDI_DEMI_HEURE_H))
    arrets = ["depot", "depart"] + ["etape %d" % (i + 1) for i in range(len(r.get("etapes") or []))] \
        + ["arrivee", "depot"]
    lignes = [
        "Km A/R (%s) : %d km" % (" -> ".join(arrets), r["km_ar"]),
        "Temps de conduite A/R : %s h, %s — itineraire %s" % (
            ("%.2f" % h).rstrip("0").rstrip("."), detail_marge,
            r["variante"].replace("_", " ")),
    ]
    if r["peage_requis"]:
        lignes.append("🟡 Peage a renseigner (classe 3 / 1,2) — A/R > %s" % _hm(SEUIL_SANS_PEAGE_H))
    else:
        lignes.append("Peage : 0 € (itineraire sans peage, sous le seuil de %s)"
                      % _hm(SEUIL_SANS_PEAGE_H))
    lignes.append("Longue distance : %s (au-dela de %s A/R)"
                  % ("oui" if r["longue_distance"] else "non", _hm(SEUIL_LONGUE_DISTANCE_H)))
    if r.get("segments"):
        lignes.append("Verification :")
        for s in r["segments"]:
            # les segments issus du cache ne portent que le lien, pas le detail chiffre
            detail = (" (%s km / %s h)" % (s["km"], s["heures"])) if "km" in s else ""
            lignes.append("  %s%s : %s" % (s["segment"], detail, s["lien_mappy"]))
    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser(description="Itineraire d'une mission Sam'Demenage")
    ap.add_argument("--depart", required=True)
    ap.add_argument("--arrivee", required=True)
    ap.add_argument("--etape", action="append", default=[],
                    help="etape intermediaire (garde-meuble, point 2/3), repetable")
    ap.add_argument("--json", action="store_true", help="sortie JSON brute")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-save", action="store_true", help="ne pas ecrire dans le cache")
    a = ap.parse_args()

    r = calculer(a.depart, a.arrivee, a.etape, utiliser_cache=not a.no_cache)

    if r["confiance"] != "echec" and r["source"] != "cache" and not a.no_save:
        cache_ecrire(r)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(bloc_notion(r))
        if r["alertes"]:
            print("\n--- Alertes ---")
            for al in r["alertes"]:
                print("  - " + al)
        print("\nchamps calculateur : kmAR=%s  heuresRouteAR=%s  peageAR=%s"
              % (r["km_ar"], r["heures_conduite_ar"],
                 "a saisir" if r["peage_requis"] else 0))

    return 1 if r["confiance"] == "echec" else 0


if __name__ == "__main__":
    sys.exit(main())
