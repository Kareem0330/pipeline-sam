#!/usr/bin/env python3
"""
Export des devis : Google Sheet (archive exploitable) et Notion (fiche client).

Tout passe par des requetes HTTP directes — pas de MCP, pas de SDK, pas d'OAuth
interactif — pour que l'archivage d'un dossier ne consomme ni temps ni tokens.

Configuration : .env (format KEY=valeur, une par ligne)
    SAMDEM_SHEETS_URL=https://script.google.com/macros/s/.../exec
    SAMDEM_SHEETS_TOKEN=<le meme jeton que dans apps_script_devis.gs>
    NOTION_TOKEN=ntn_xxx           # integration interne Notion, acces a la base Fiches Client

Usage :
    python export.py devis.json --sheets           # archive dans le Google Sheet
    python export.py devis.json --notion <page_id> # remplit les proprietes de la fiche
    python export.py --test                        # verifie la config et la connexion
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ICI = os.path.dirname(os.path.abspath(__file__))
# Emplacements possibles, par ordre de priorite : chemin explicite, a cote du script,
# puis ~/.claude (convention nocrm.env).
ENV_CANDIDATS = [
    os.environ.get("SAMDEM_ENV"),
    os.path.normpath(os.path.join(ICI, "..", "..", ".env")),
]
NOTION_API = "https://api.notion.com/v1/pages/"
NOTION_VERSION = "2022-06-28"


def chemin_env():
    """Premier fichier de config existant et reellement renseigne."""
    trouve = None
    for c in ENV_CANDIDATS:
        if c and os.path.exists(c):
            if trouve is None:
                trouve = c
            with open(c, encoding="utf-8") as fh:
                if "REMPLACER" not in fh.read():     # gabarit encore vierge : on continue
                    return c
    return trouve


ENV = chemin_env() or ENV_CANDIDATS[-1]


def config():
    """Lit .env (voir ENV_CANDIDATS). Meme convention que nocrm.env."""
    conf = {}
    if ENV and os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                k, v = ligne.split("=", 1)
                conf[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("SAMDEM_SHEETS_URL", "SAMDEM_SHEETS_TOKEN", "NOTION_TOKEN"):
        if os.environ.get(k):
            conf[k] = os.environ[k]
    return conf


def _post(url, payload, headers=None, methode="POST"):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=methode,
                                 headers={"Content-Type": "application/json",
                                          **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corps = r.read().decode("utf-8")
            try:
                return True, json.loads(corps)
            except ValueError:
                return True, {"reponse": corps[:500]}
    except urllib.error.HTTPError as e:
        return False, {"http": e.code, "corps": e.read().decode("utf-8", "replace")[:500]}
    except Exception as e:                                  # reseau, DNS, timeout
        return False, {"erreur": str(e)}


# --- Google Sheet ------------------------------------------------------------

def ligne_sheet(dossier, deductions, chiffres=None, fichier_devis=None):
    """Aplatit un dossier + les chiffres du devis en une ligne exploitable.

    `chiffres` reprend la ventilation du calculateur (transport, manut, formule,
    deplacement, materiel, dossier, autres, total HT/TTC, marge, commission), saisie
    apres validation par Samuel. Absent = colonnes vides, la ligne reste utile.
    """
    c = dossier.get("client") or {}
    d = dossier.get("depart") or {}
    a = dossier.get("arrivee") or {}
    m = dossier.get("mission") or {}
    it = dossier.get("itineraire") or {}
    ch = chiffres or {}

    def commune(bloc):
        lab = bloc.get("adresse_normalisee") or bloc.get("adresse_brute") or ""
        parts = [p.strip() for p in lab.split(",")]
        return parts[-1] if len(parts) > 1 else lab

    return {
        "ref": m.get("ref") or dossier.get("ref"),
        "date_creation": m.get("date_creation"),
        "date_chargement": m.get("date_chargement"),
        "statut": m.get("statut") or "À vérifier",
        "commercial": m.get("commercial"),
        "client_nom": c.get("nom"),
        "client_prenom": c.get("prenom"),
        "telephone": c.get("tel"),
        "email": c.get("email"),
        "commune_depart": commune(d),
        "commune_arrivee": commune(a),
        "adresse_depart": d.get("adresse_normalisee") or d.get("adresse_brute"),
        "adresse_arrivee": a.get("adresse_normalisee") or a.get("adresse_brute"),
        "volume_m3": m.get("volume_m3"),
        "formule": m.get("formule"),
        "source_volume": m.get("source_volume"),
        "inventaire_fourni": bool(m.get("inventaire_fourni")),
        "km_ar": it.get("km_ar"),
        "heures_conduite_ar": it.get("heures_conduite_ar"),
        "variante_itineraire": it.get("variante"),
        "longue_distance": bool(it.get("longue_distance")),
        "peage_ht": m.get("peage_ht") or 0,
        "nb_depart": (deductions or {}).get("nb_depart"),
        "nb_arrivee": (deductions or {}).get("nb_arrivee"),
        "nb_camions": (deductions or {}).get("nb_camions"),
        "gabarit_camion": (deductions or {}).get("gabarit"),
        "transport_ht": ch.get("transport_ht"),
        "manut_ht": ch.get("manut_ht"),
        "formule_ht": ch.get("formule_ht"),
        "deplacement_ht": ch.get("deplacement_ht"),
        "materiel_ht": ch.get("materiel_ht"),
        "dossier_ht": ch.get("dossier_ht"),
        "autres_ht": ch.get("autres_ht"),
        "total_ht": ch.get("total_ht"),
        "tva": ch.get("tva"),
        "total_ttc": ch.get("total_ttc"),
        "marge_pct": ch.get("marge_pct"),
        "commission_ht": ch.get("commission_ht"),
        "notion_url": (dossier.get("notion") or {}).get("url"),
        "fichier_devis": fichier_devis,
    }


def vers_sheets(lignes, conf=None):
    conf = conf or config()
    url = conf.get("SAMDEM_SHEETS_URL")
    jeton = conf.get("SAMDEM_SHEETS_TOKEN")
    if not url or not jeton:
        return False, {"erreur": "SAMDEM_SHEETS_URL ou SAMDEM_SHEETS_TOKEN absent de %s" % ENV}
    if isinstance(lignes, dict):
        lignes = [lignes]
    return _post(url, {"jeton": jeton, "lignes": lignes})


# --- Notion ------------------------------------------------------------------

def _p_text(v):
    return {"rich_text": [{"text": {"content": str(v)}}]} if v not in (None, "") else None


def _p_num(v):
    return {"number": float(v)} if isinstance(v, (int, float)) else None


def _p_select(v):
    return {"select": {"name": str(v)}} if v else None


def _p_check(v):
    return {"checkbox": bool(v)}


def proprietes_notion(dossier, deductions, chiffres=None):
    """Mappe le dossier sur le schema reel de la base « 🗂️ Fiches Client (base) ».

    Ne renvoie que les proprietes effectivement renseignees : une valeur absente n'est
    jamais ecrite, pour ne pas ecraser une saisie manuelle par du vide.
    """
    m = dossier.get("mission") or {}
    it = dossier.get("itineraire") or {}
    ch = chiffres or {}
    d = deductions or {}

    brut = {
        "Volume (m3)": _p_num(m.get("volume_m3")),
        "Formule (offre choisie)": _p_select(m.get("formule")),
        "Source volume": _p_text(m.get("source_volume")),
        "Inventaire fourni": _p_check(m.get("inventaire_fourni")),
        "Intervenants chargement": _p_num(d.get("nb_depart")),
        "Intervenants déchargement": _p_num(d.get("nb_arrivee")),
        "Gabarit camion attendu": _p_text(d.get("gabarit")),
        "Temps de trajet total": _p_text(
            ("%s h" % it["heures_conduite_ar"]) if it.get("heures_conduite_ar") is not None else None),
        "Transport HT": _p_num(ch.get("transport_ht")),
        "Manut HT": _p_num(ch.get("manut_ht")),
        "Formule (coût options) HT": _p_num(ch.get("formule_ht")),
        "Déplacement HT": _p_num(ch.get("deplacement_ht")),
        "Matériel HT": _p_num(ch.get("materiel_ht")),
        "Dossier HT": _p_num(ch.get("dossier_ht")),
        "Autres frais HT": _p_num(ch.get("autres_ht")),
        "Prix Total TTC": _p_num(ch.get("total_ttc")),
        "Statut": _p_select(m.get("statut")),
        "Axe groupage": _p_select(m.get("axe_groupage")),
    }
    return {k: v for k, v in brut.items() if v is not None}


BASE_FICHES_CLIENT = "80ce1be8ba794a0788dfae8c88eb0ab7"


def _notion_base(token, base_id=BASE_FICHES_CLIENT):
    """Verifie que le token est valide ET que l'integration est autorisee sur la base.
    Creer l'integration ne suffit pas : sans le partage, l'API repond 404."""
    req = urllib.request.Request(
        "https://api.notion.com/v1/databases/" + base_id,
        headers={"Authorization": "Bearer " + token, "Notion-Version": NOTION_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        return True, "".join(t.get("plain_text", "") for t in d.get("title", []))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s — %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:
        return False, str(e)


def vers_notion(page_id, proprietes, conf=None):
    conf = conf or config()
    token = conf.get("NOTION_TOKEN")
    if not token:
        return False, {"erreur": "NOTION_TOKEN absent de %s" % ENV}
    if not proprietes:
        return False, {"erreur": "aucune propriété à écrire"}
    return _post(NOTION_API + page_id.replace("-", ""),
                 {"properties": proprietes},
                 headers={"Authorization": "Bearer " + token,
                          "Notion-Version": NOTION_VERSION},
                 methode="PATCH")


# --- CLI ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Export des devis Sam'Demenage")
    ap.add_argument("fichier", nargs="?", help="JSON contenant dossier/deductions/chiffres")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--notion", metavar="PAGE_ID")
    ap.add_argument("--test", action="store_true", help="verifie la configuration")
    a = ap.parse_args()

    conf = config()
    if a.test:
        print("Config : %s" % ("trouvée" if os.path.exists(ENV) else "ABSENTE — " + ENV))
        reste = []
        for k in ("SAMDEM_SHEETS_URL", "SAMDEM_SHEETS_TOKEN", "NOTION_TOKEN"):
            v = conf.get(k)
            if not v:
                etat = "manquant"
            elif "REMPLACER" in v:               # gabarit non complete
                etat = "À REMPLIR (valeur d'exemple)"
                reste.append(k)
            else:
                etat = "défini (%s…%s)" % (v[:6], v[-4:]) if len(v) > 14 else "défini"
            print("  %-22s %s" % (k, etat))
        if reste:
            print("\n→ Compléter %s puis relancer --test." % ENV)
            return 1
        if conf.get("SAMDEM_SHEETS_URL"):
            ok, rep = _post(conf["SAMDEM_SHEETS_URL"],
                            {"jeton": conf.get("SAMDEM_SHEETS_TOKEN", ""), "lignes": []})
            if ok and isinstance(rep, dict) and rep.get("ok"):
                print("  Web app : OK — %s" % rep)
            elif ok:
                print("  Web app : joignable mais refusée — %s" % rep)
                print("    (jeton différent de la constante JETON du script ?)")
                return 1
            else:
                detail = rep.get("http")
                print("  Web app : ÉCHEC%s" % (" — HTTP %s" % detail if detail else " — %s" % rep))
                if detail == 404:
                    print("    URL introuvable : vérifier qu'elle finit par /exec et que le")
                    print("    déploiement est bien de type « Application web ».")
                elif detail in (401, 403):
                    print("    Accès refusé : redéployer avec « Accès : tout le monde ».")
                return 1
        if conf.get("NOTION_TOKEN"):
            ok, rep = _notion_base(conf["NOTION_TOKEN"])
            if ok:
                print("  Notion  : OK — base « %s » accessible" % rep)
            else:
                print("  Notion  : ÉCHEC — %s" % rep)
                print("    Si 404 : l'intégration existe mais n'est pas autorisée sur la base.")
                print("    Ouvrir la base > ••• > Connexions > ajouter l'intégration.")
                return 1
        return 0

    if not a.fichier:
        ap.error("fichier JSON requis (ou --test)")
    with open(a.fichier, encoding="utf-8") as fh:
        paquet = json.load(fh)
    dossier = paquet.get("dossier", paquet)
    deductions = paquet.get("deductions") or {}
    chiffres = paquet.get("chiffres") or {}

    code = 0
    if a.sheets:
        ok, rep = vers_sheets(ligne_sheet(dossier, deductions, chiffres,
                                          paquet.get("fichier_devis")), conf)
        print("Google Sheet : %s — %s" % ("OK" if ok else "ÉCHEC", rep))
        code |= 0 if ok else 1
    if a.notion:
        ok, rep = vers_notion(a.notion, proprietes_notion(dossier, deductions, chiffres), conf)
        print("Notion : %s — %s" % ("OK" if ok else "ÉCHEC",
                                    rep if not ok else rep.get("url", "page mise à jour")))
        code |= 0 if ok else 1
    if not (a.sheets or a.notion):
        print(json.dumps(ligne_sheet(dossier, deductions, chiffres,
                                     paquet.get("fichier_devis")),
                         ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
