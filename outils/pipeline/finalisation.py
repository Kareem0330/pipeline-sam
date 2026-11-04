#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finalisation d'une fiche client — du JSON du calculateur au bloc de chiffrage de la fiche.

Remplace le projet Cowork « FINALISATION FICHE SANDRINE » : les regles 1 a 9 de ce prompt
sont ici du code. Le modele n'a plus a transcrire des montants ni a poser des divisions.

    Calculateur (artefact en ligne)  --« Exporter JSON »-->  presse-papier
                                                                  |
                                                          finalisation.py
                                                                  |
                                     note « Fiche client » et proprietes de la transaction HubSpot

Plus d'ecriture dans Notion ni dans le Google Sheet (Karim, 03/11/2026). Un ancien dossier voit
sa fiche Notion, lue sans y ecrire, recopiee une fois sur sa transaction (fiche_hubspot.py).

Usage :
    python finalisation.py --presse-papier --fiche "HAENSLER Louis"     # controle, n'ecrit rien
    python finalisation.py export.json --fiche "HAENSLER Louis" --appliquer
    python finalisation.py - --page-id <id> --appliquer                 # JSON sur stdin
    python finalisation.py export.json --fiche "NOM" --ttc-cible 2400   # regle 1
    python finalisation.py export.json --fiche "NOM" --json             # sortie machine

Par defaut le script AFFICHE ce qu'il ecrirait et ne touche a rien : il faut --appliquer.
La marge n'arrete plus rien (Karim, 03/11/2026) : elle est affichee, le devis continue et
Samuel le relit avant qu'il parte.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import unicodedata

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import export                                     # noqa: E402  (config, token, base)
import fiche_notion as fn                         # noqa: E402  (lecture de la fiche, recherche)
import fiche_hubspot                               # noqa: E402  (note Fiche client de la transaction)
import regles                                     # noqa: E402  (seuils metier)
import notif                                       # noqa: E402  (WhatsApp via Beeper Desktop)
import nocrm                                       # noqa: E402  (pipeline commercial)
import hubspot_crm                                 # noqa: E402  (pipeline commercial, migration)
import crm                                         # noqa: E402  (interrupteur SAMDEM_CRM)
import reprise                                     # noqa: E402  (relance immediate d'une etape)
import devis_auto                                  # noqa: E402  (PDF du devis, préparé en local)
import validation_devis                            # noqa: E402  (relecture avant HubSpot)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA = "samdem.devis.export/1"
# CRM de la derniere etape : « nocrm », « hubspot » ou « les-deux » (transition). Ligne
# SAMDEM_CRM=... dans outils/crm.env (interrupteur general), ou variable d'environnement. Retour arriere : « nocrm ».
CRMS = crm.CRMS
crm_actif = crm.actif
ETAPES_REPRISE = ("texte", "crm")
_EXPORT = None                                  # fichier de l'export, pour la commande de reprise
RACINE = os.path.normpath(os.path.join(ICI, "..", ".."))
JOURNAL = os.path.join(regles.DEVIS_GENERES, "exports")   # un fichier par fiche
PREFIXE_VARIANTE = "\U0001f500 "                             # 🔀, comme sur les fiches existantes


# --- Format ------------------------------------------------------------------

def eur(v):
    """1860.0 -> « 1 860,00 » (espace milliers, virgule decimale — format des fiches)."""
    if v is None:
        return ""
    s = "{:,.2f}".format(round(float(v) + 0.0, 2))
    return s.replace(",", " ").replace(".", ",")


def hhmm(minutes):
    """450 -> « 7h30 ». Toujours deux chiffres pour les minutes."""
    if minutes is None:
        return ""
    t = max(0, int(round(minutes)))
    return "%dh%02d" % (t // 60, t % 60)


def hhmm_min(minutes):
    """450 -> « 7h30 (450 min) » — forme retenue sur les fiches pour les temps de phase."""
    if minutes is None:
        return ""
    return "%s (%d min)" % (hhmm(minutes), int(round(minutes)))


def pct(v):
    return "—" if v is None else ("%.1f %%" % (v * 100)).replace(".", ",")


def demi_proche(minutes):
    """Arrondi a la DEMI-HEURE LA PLUS PROCHE (regle 3, Karim 08/09/2026).

    152,3 min -> 150 ; 168 min -> 180. Un temps non nul ne tombe jamais a zero :
    une phase qui existe vaut au moins 30 min sur la fiche.
    """
    if minutes is None:
        return None
    m = max(0.0, float(minutes))
    arrondi = int(math.floor(m / 30.0 + 0.5) * 30)
    return 30 if (arrondi == 0 and m > 0) else arrondi


def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


# --- Entree ------------------------------------------------------------------

def lire_presse_papier():
    """Recupere le JSON copie depuis le calculateur, sans passer par un fichier."""
    if sys.platform.startswith("win"):
        # [Console]::OutputEncoding est indispensable : sans elle, PowerShell rend le texte
        # dans la page de codes de la console (cp1252), un tiret cadratin devient « ?" » et
        # casse la chaine JSON. Le symptome est un « Expecting ',' delimiter » incomprehensible.
        cmd = ["powershell", "-NoProfile", "-Command",
               "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard -Raw"]
    elif sys.platform == "darwin":
        cmd = ["pbpaste"]
    else:
        cmd = ["xclip", "-selection", "clipboard", "-o"]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=20).stdout.decode("utf-8", "replace")
    except Exception as e:
        raise SystemExit("Presse-papier illisible (%s)." % e)


def charger(source):
    if source == "--presse-papier":
        brut = lire_presse_papier()
    elif source == "-":
        brut = sys.stdin.read()
    else:
        with open(source, encoding="utf-8-sig") as fh:
            brut = fh.read()
    brut = (brut or "").strip()
    if not brut:
        raise SystemExit("Aucun contenu à lire. Cliquer « Exporter JSON » dans le calculateur.")
    if not brut.startswith("{"):
        deb, fin = brut.find("{"), brut.rfind("}")
        if deb < 0 or fin < deb:
            raise SystemExit("Ce n'est pas le JSON du calculateur — c'est peut-être le récap "
                             "TEXTE. Utiliser le bouton « Exporter JSON ».")
        brut = brut[deb:fin + 1]
    try:
        d = json.loads(brut)
    except ValueError as e:
        raise SystemExit("JSON illisible : %s" % e)
    if d.get("schema") != SCHEMA:
        print("⚠  schéma %r inattendu (attendu %r) — le calculateur en ligne est peut-être "
              "d'une autre version." % (d.get("schema"), SCHEMA))
    return d


# --- Regle 1 : ajustement a un TTC cible -------------------------------------

def ajuster_ttc(ex, ttc_cible):
    """Repositionne le SEUL transport pour atteindre un TTC cible (regle 1).

    Reprend l'algebre du calculateur (fonction applyTtcTarget) plutot que celle du prompt
    Cowork : la base de commission du moteur inclut toute la masse salariale de route
    (forfait trajet court, route LD, trajet depot, retour chef d'equipe), pas seulement
    transport + manut + options. Deux algebres differentes donneraient deux montants.
    Depuis le 09/09/2026 le taux vaut 0 sur tout devis Sam'Demenage (Next Stories compris) :
    le terme s'annule, l'algebre ne sert plus que pour Acces Demenagement (7 %).
    """
    c = (ex.get("commission") or {}).get("taux", regles.COMMISSION_TAUX)
    A = (ex.get("commission") or {}).get("ht_avant_commission_hors_transport")
    B0 = (ex.get("commission") or {}).get("base_hors_transport")
    # Paniers repas : dans manut_ht depuis le 22/10/2026 (paniers_dans = "manut") ; les exports
    # plus anciens les fondaient dans transport_ht, qu'on recompose alors comme avant.
    ch0 = ex.get("champs_fiche") or {}
    paniers = 0 if ch0.get("paniers_dans") == "manut" else (ch0.get("paniers_repas_ht") or 0)
    mopt = (ex.get("marge") or {}).get("fixe_hors_transport")
    if A is None or B0 is None or mopt is None:
        raise SystemExit("Le JSON ne porte pas les termes de commission/marge nécessaires "
                         "à l'ajustement : refaire l'export depuis le calculateur à jour.")

    ht_cible = round(ttc_cible / (1 + regles.TVA))
    T = (ht_cible - (A + c * B0)) / (1 + c)
    if T < 0:
        T = 0.0                      # TTC visé sous le plancher : transport ramené à 0
    commission = (B0 + T) * c
    ht_exact = A + T + commission
    ch = dict(ex.get("champs_fiche") or {})
    ch["transport_ht"] = round(T + paniers + commission, 2)
    ch["total_ht"] = round(ht_exact)
    ch["total_ttc"] = round(round(ht_exact) * (1 + regles.TVA))
    ex = dict(ex)
    ex["champs_fiche"] = ch
    ex["commission"] = dict(ex.get("commission") or {}, montant=round(commission, 2))
    marge_e = T + mopt
    ex["marge"] = dict(ex.get("marge") or {},
                       pct=(marge_e / ht_exact) if ht_exact else None,
                       euro=round(marge_e, 2),
                       ajuste_sur_ttc=ttc_cible,
                       transport_ramene_a_zero=(T == 0))
    return ex


# --- Regle 3 : temps de mission ----------------------------------------------

def temps_fiche(ex, diviseur=1.1, sans_division=False):
    """Temps a inscrire sur la fiche, a partir des temps bruts du devis.

    Regle 3 (Karim, 08/09/2026) : chargement et dechargement sont divises par 1,1 puis
    arrondis CHACUN a la demi-heure la plus proche ; trajet et options ne sont ni divises ni
    arrondis ; le total est arrondi a son tour a la demi-heure la plus proche.

    (Ancienne regle du prompt Cowork, remplacee : / 1,3 puis quart d'heure superieur.)
    """
    t = ex.get("temps_min") or {}
    d = 1.0 if sans_division else float(diviseur)
    charge = demi_proche((t.get("chargement") or 0) / d)
    decharge = demi_proche((t.get("dechargement") or 0) / d)
    route = int(round(t.get("route") or 0))
    options = int(round(t.get("options") or 0))
    etapes = int(round(t.get("etapes") or 0))
    if not route:
        route = 30                    # regle 3 : defaut 30 min quand aucun trajet n'est connu
    exact = charge + decharge + route + options + etapes
    total = demi_proche(exact)
    return {"chargement": charge, "dechargement": decharge, "route": route,
            "options": options, "etapes": etapes, "mission": total, "mission_exacte": exact,
            "brut": {"chargement": t.get("chargement"), "dechargement": t.get("dechargement")},
            "diviseur": d}


# --- Regle 2 : verification arithmetique --------------------------------------

POSTES_FICHE = ["transport_ht", "manut_ht", "formule_ht", "deplacement_ht",
                "materiel_ht", "dossier_ht", "autres_frais_ht"]


def verifier(ex, tolerance=1.0):
    """Controles a passer avant toute ecriture. Rend une liste de messages (vide = OK)."""
    ch = ex.get("champs_fiche") or {}
    pbs = []
    somme = sum(ch.get(k) or 0 for k in POSTES_FICHE)
    ht = ch.get("total_ht")
    if ht is None:
        pbs.append("Total HT absent du JSON.")
    elif abs(somme - ht) > tolerance:
        pbs.append("Somme des postes %s € ≠ Total HT %s € (écart %.2f €)."
                   % (eur(somme), eur(ht), somme - ht))
    ttc = ch.get("total_ttc")
    if ht is not None and ttc is not None and abs(round(ht * (1 + regles.TVA)) - ttc) > tolerance:
        pbs.append("Total HT × 1,2 = %s € ≠ Total TTC %s €." % (eur(ht * 1.2), eur(ttc)))
    autres = (ch.get("monte_charge_ht") or 0) + (ch.get("piano_ht") or 0) + (ch.get("divers_ht") or 0)
    if abs(autres - (ch.get("autres_frais_ht") or 0)) > 0.01:
        pbs.append("Autres frais HT (%s €) ≠ monte-charge + piano + divers (%s €)."
                   % (eur(ch.get("autres_frais_ht")), eur(autres)))
    return pbs


# --- Le bloc de chiffrage de la fiche ----------------------------------------
# Chaque entree : (cle, etiquette exacte de la ligne, texte complet de la ligne).
# L'ordre est celui du modele de fiche ; il commande aussi les insertions (regles 7, 8, 9).

def lignes_fiche(ex, tps):
    ch = ex.get("champs_fiche") or {}
    eq = ex.get("equipe") or {}
    L = []
    A = L.append
    A(("mission", "Temps de mission estimé",
       "Temps de mission estimé : %s" % hhmm_min(tps["mission"])))
    A(("trajet", "Temps de trajet total", "Temps de trajet total : %s" % hhmm(tps["route"])))
    A(("charge", "Temps de chargement", "Temps de chargement : %s" % hhmm_min(tps["chargement"])))
    A(("interv_charge", "Nombre d'intervenants",
       "Nombre d'intervenants : %s" % (eq.get("intervenants_chargement") or "")))
    A(("decharge", "Temps de déchargement",
       "Temps de déchargement : %s" % hhmm_min(tps["dechargement"])))
    A(("interv_decharge", "Nombre d'intervenants",
       "Nombre d'intervenants : %s" % (eq.get("intervenants_dechargement") or "")))
    if tps["options"]:
        A(("options", "Temps d'options", "Temps d'options : %s" % hhmm_min(tps["options"])))
    rv, rt = ex.get("relivraison"), (ex.get("temps_min") or {}).get("relivraison")
    if rv and rt:                                   # seconde operation, un autre jour (14/10/2026)
        A(("relivraison", "Relivraison",
           "Relivraison : %s m³ — %s (trajet %s · chargement %s · déchargement %s) — "
           "%s / %s intervenants — %s € HT inclus au total"
           % (rv.get("volume"), hhmm(rt.get("mission") or 0), hhmm(rt.get("route") or 0),
              hhmm(rt.get("chargement") or 0), hhmm(rt.get("dechargement") or 0),
              rv.get("intervenants_chargement"), rv.get("intervenants_dechargement"),
              eur(rv.get("montant_ht")))))
    A(("transport", "Transport", "Transport : %s € HT" % eur(ch.get("transport_ht"))))
    A(("manut", "Manut", "Manut : %s € HT" % eur(ch.get("manut_ht"))))
    A(("formule", "Formule", "Formule : %s € HT" % eur(ch.get("formule_ht"))))
    if ch.get("piano_ht"):                                             # regle 9
        A(("piano", "Piano", "Piano : %s € HT" % eur(ch.get("piano_ht"))))
    A(("deplacement", "Déplacement", "Déplacement : %s € HT" % eur(ch.get("deplacement_ht"))))
    if ch.get("monte_charge_ht"):                                      # regle 7
        A(("monte_charge", "Monte-charge hors taxes",
           "Monte-charge hors taxes : %s € HT" % eur(ch.get("monte_charge_ht"))))
    A(("materiel", "Matériel", "Matériel : %s € HT" % eur(ch.get("materiel_ht"))))
    A(("dossier", "Dossier", "Dossier %s € HT" % eur(ch.get("dossier_ht"))))   # jamais reecrit
    A(("total_ht", "Prix Total HT", "Prix Total HT : %s € HT" % eur(ch.get("total_ht"))))
    A(("total_ttc", "Prix Total", "Prix Total : %s € TTC" % eur(ch.get("total_ttc"))))
    for div in (ch.get("divers") or []):                               # regle 8
        libelle = div.get("libelle") or "Autres frais"
        A(("divers_" + _sans_accents(libelle), "%s hors taxes" % libelle,
           "%s hors taxes : %s € HT" % (libelle, eur(div.get("montant")))))
    return L


# --- Reperage du bloc dans la page -------------------------------------------

DEBUT = "temps de mission estime"


def blocs_de_lignes(lignes):
    """Lignes de la fiche, au format de fiche_notion.lire_corps, en blocs pour reperer_blocs() et
    composer(). Une ligne fait un bloc ; `id` est sa position, `prefixe` sa syntaxe."""
    out = []
    for i, ligne in enumerate(lignes):
        s_ = ligne.strip()
        m = re.match(r"(- \[[ xX]\] |- |### )", s_)
        prefixe = m.group(1) if m else ""
        type_ = {"### ": "heading_3", "- ": "bulleted_list_item", "": "paragraph"}.get(prefixe, "to_do")
        if s_ in ("[divider]", "---"):
            type_ = "divider"
        texte = "" if type_ == "divider" else s_[len(prefixe):]
        out.append({"id": i, "type": type_, "texte": texte, "lignes": [texte], "prefixe": prefixe, "brut": ligne})
    return out


def _lignes_blocs(page_id, token):
    return blocs_de_lignes(fn.lire_corps(page_id, token))


def appliquer_patchs(blocs, patchs, titres=None):
    """Rend les lignes de la fiche après `patchs` ({id: {texte}}, voir composer) ; `titres` ({id: ligne})
    pose une ligne juste avant un bloc."""
    out = []
    for b in blocs:
        if titres and b["id"] in titres:
            out.append(titres[b["id"]])
        if b["id"] in patchs:
            parts = patchs[b["id"]]["texte"].split("\n")
            out += [b["prefixe"] + parts[0]] + parts[1:]
        else:
            out.append(b["brut"])
    return out


def reperer_blocs(blocs):
    """Rend la liste des blocs de chiffrage (index de debut/fin dans `blocs`).

    Une fiche peut en porter PLUSIEURS (variantes « Version Standard », devis successifs) :
    on ne devine pas, on les rend tous et l'appelant choisit.
    """
    groupes, courant = [], None
    for i, b in enumerate(blocs):
        plat = _sans_accents(b["texte"])
        if DEBUT in plat and courant is None:
            courant = {"debut": i, "fin": i, "titre": None}
        elif courant is not None:
            if b["type"] == "divider" or (b["type"].startswith("heading") and b["texte"].strip()):
                groupes.append(courant)
                courant = None
                continue
            courant["fin"] = i
            if "rdv acompte" in plat:
                groupes.append(courant)
                courant = None
    if courant is not None:
        groupes.append(courant)
    for g in groupes:      # titre = heading immediatement au-dessus du bloc, s'il y en a un
        g["titre"] = ""
        for j in range(g["debut"] - 1, max(-1, g["debut"] - 4), -1):
            if blocs[j]["type"].startswith("heading") and blocs[j]["texte"].strip():
                g["titre"] = blocs[j]["texte"].strip()
                break
    return groupes


def _etiquette(ligne):
    """« Transport : 727,82 € HT » -> « transport ». Cle de comparaison sans accents."""
    l = (ligne or "").strip()
    if not l:
        return ""
    tete = l.split(":", 1)[0] if ":" in l else l
    return _sans_accents(tete).strip(" .-—")


def composer(blocs, groupe, lignes):
    """Applique les lignes voulues au bloc de chiffrage, sans toucher au reste.

    - une ligne dont l'etiquette existe deja est REMPLACEE sur place ;
    - une ligne absente (piano, monte-charge, autres frais, temps d'options) est INSEREE
      juste apres son ancre, dans le meme bloc Notion — l'ordre du modele est conserve ;
    - la ligne « Dossier » n'est jamais reecrite (frais fixe, hors perimetre).
    Rend (patchs, journal) : patchs = {block_id: {type, texte}}.
    """
    zone = blocs[groupe["debut"]:groupe["fin"] + 1]
    plan, vus = [], {}
    for bi, b in enumerate(zone):
        for li, ligne in enumerate(b["lignes"]):
            e = _etiquette(ligne)
            n = vus.get(e, 0) + 1
            vus[e] = n
            plan.append({"bi": bi, "li": li, "cle": e, "n": n, "texte": ligne})

    def trouver(etiquette, occurrence=1):
        cible = _sans_accents(etiquette)
        for p in plan:
            if p["cle"] == cible and p["n"] == occurrence:
                return p
        return None

    occ, nouvelles, inserts, journal = {}, {}, [], []
    ancre = None
    for cle, etiquette, texte in lignes:
        occ[etiquette] = occ.get(etiquette, 0) + 1
        p = trouver(etiquette, occ[etiquette])
        if cle == "dossier":
            if p and p["texte"].strip() != texte.strip():
                journal.append(("info", "Dossier laissé tel quel sur la fiche (« %s ») — "
                                        "le devis dit « %s »." % (p["texte"].strip(), texte)))
            ancre = p or ancre
            continue
        if p:
            if p["texte"].strip() != texte.strip():
                nouvelles[(p["bi"], p["li"])] = texte
                journal.append(("maj", "%s  →  %s" % (p["texte"].strip() or "(vide)", texte)))
            ancre = p
        else:
            if ancre is None:
                journal.append(("alerte", "Ligne « %s » non insérée : aucune ancre trouvée "
                                          "au-dessus." % texte))
                continue
            inserts.append((ancre["bi"], ancre["li"], texte))
            journal.append(("ajout", texte))

    patchs = {}
    for bi, b in enumerate(zone):
        lignes_b = list(b["lignes"])
        for (pbi, pli), txt in nouvelles.items():
            if pbi == bi:
                lignes_b[pli] = txt
        # inserer en partant de la fin pour ne pas decaler les positions deja calculees
        for pbi, pli, txt in sorted([x for x in inserts if x[0] == bi],
                                    key=lambda x: x[1], reverse=True):
            lignes_b.insert(pli + 1, txt)
        neuf = "\n".join(lignes_b)
        if neuf != b["texte"]:
            patchs[b["id"]] = {"type": b["type"], "texte": neuf}
    return patchs, journal


def bloc_variante(variante, lignes):
    """Bloc de chiffrage complet pour une variante qui n'existe pas encore.

    Une variante ne recycle jamais le bloc d'une autre : un titre et un bloc neuf en bas de fiche,
    la convention des fiches à plusieurs devis (« 🔀 Version Standard » sur DROZAC Rodrigo).
    """
    return ["### " + PREFIXE_VARIANTE + variante] + [texte for _, _, texte in lignes] + ["RDV acompte (si applicable)"]


def note_chiffree(lignes_note, lignes, variante, numero, ex, avec_itineraire):
    """Rend (lignes de la nouvelle version de la fiche, compte rendu). Rien n'est écrit ici."""
    bl = blocs_de_lignes(lignes_note)
    gs_ = reperer_blocs(bl)
    g_, titre_ = choisir_groupe(gs_, bl, variante, numero) if (gs_ or variante) else (None, None)
    faits = []
    if g_ is None and variante:
        neuves = list(lignes_note) + bloc_variante(variante, lignes)
        faits.append("variante « %s » ajoutée en bas de fiche" % variante)
    else:
        pt = composer(bl, g_, lignes)[0] if g_ else {}
        titres = {bl[g_["debut"]]["id"]: "### " + PREFIXE_VARIANTE + titre_} if (titre_ and g_) else None
        neuves = appliquer_patchs(bl, pt, titres)
        if titres:
            faits.append("titre « %s%s » posé sur le bloc" % (PREFIXE_VARIANTE, titre_))
        if pt:
            faits.append("%d ligne(s) du chiffrage mise(s) à jour" % len(pt))
    # Section « Itinéraires » : elle n'existe qu'en un exemplaire, elle porte donc le devis retenu.
    if avec_itineraire:
        bl = blocs_de_lignes(neuves)
        pi, di = patcher_itineraire(bl, ex)
        if pi:
            neuves = appliquer_patchs(bl, pi)
            faits.append("%d ligne(s) d'itinéraire mise(s) à jour" % len(di))
    return neuves, " ; ".join(faits) or "déjà à jour"


def _vierge(blocs, groupe):
    """Un bloc encore au gabarit : aucune ligne de montant ne porte de chiffre."""
    for b in blocs[groupe["debut"]:groupe["fin"] + 1]:
        for ligne in b["lignes"]:
            if _etiquette(ligne) in ("transport", "manut", "prix total", "prix total ht"):
                if any(c.isdigit() for c in ligne.split(":", 1)[-1]):
                    return False
    return True


def choisir_groupe(groupes, blocs, variante=None, numero=None):
    """Rend (groupe, titre_a_poser) ; (None, variante) quand le bloc reste a creer.

    Sans variante, comportement d'avant : le dernier bloc. Avec une variante, on cherche
    son titre ; a defaut on adopte un gabarit encore vierge en le nommant ; a defaut on cree.
    """
    if numero:
        return groupes[numero - 1], None
    if not variante:
        return (groupes[-1] if groupes else None), None
    cible = _sans_accents(variante)
    for g in groupes:
        titre = _sans_accents(g["titre"] or "").replace("\U0001f500", "").strip()
        if titre in (cible, "version " + cible):
            return g, None
    for g in groupes:
        if _vierge(blocs, g):
            return g, variante          # gabarit encore vide : on l'adopte et on le nomme
    sans_titre = [g for g in groupes if not (g["titre"] or "").strip()]
    if len(sans_titre) == 1:
        # Le bloc historique d'une fiche deja chiffree avant l'ere des variantes : on l'adopte
        # et on lui donne son nom, plutot que de creer un doublon a cote d'un devis valide.
        return sans_titre[0], variante
    return None, variante


# --- Journal des variantes d'une fiche ---------------------------------------

def journal(page_id, variante=None, infos=None):
    """Retient ce qui a ete ecrit sur une fiche, variante par variante.

    Sert au message groupe : on previent une fois, en listant tout ce qui a ete produit pour
    ce client. Un fichier par fiche, lisible, sans base de donnees.
    """
    os.makedirs(JOURNAL, exist_ok=True)
    chemin = os.path.join(JOURNAL, "%s.variantes.json" % page_id.replace("-", ""))
    donnees = {}
    if os.path.exists(chemin):
        try:
            with open(chemin, encoding="utf-8") as fh:
                donnees = json.load(fh)
        except ValueError:
            donnees = {}
    if variante:
        donnees[variante] = infos or {}
        _ecrire_journal(page_id, donnees)
    return donnees


def _ecrire_journal(page_id, donnees):
    os.makedirs(JOURNAL, exist_ok=True)
    chemin = os.path.join(JOURNAL, "%s.variantes.json" % page_id.replace("-", ""))
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(donnees, fh, ensure_ascii=False, indent=2)


def variantes_sur_fiche(groupes):
    """Noms des variantes reellement presentes sur la fiche, d'apres leurs titres."""
    noms = set()
    for g in groupes or []:
        titre = (g.get("titre") or "").replace(PREFIXE_VARIANTE, "").strip()
        if titre:
            noms.add(titre)
    return noms


def elaguer_journal(page_id, groupes):
    """Ne garde au journal que les variantes encore presentes sur la fiche.

    Le journal note chaque export ; la fiche porte ce qui a ete retenu. Un essai supprime de
    la fiche par Samuel ne doit pas reapparaitre dans le message a l'equipe : le message
    annonce les devis qui tiennent, pas l'historique des creations et des suppressions.

    Une fiche sans aucun titre de variante n'a qu'un devis : rien a filtrer, on rend le
    journal tel quel plutot que de le vider a tort.
    """
    donnees = journal(page_id)
    gardees = variantes_sur_fiche(groupes)
    if not donnees or not gardees:
        return donnees
    restant = {nom: infos for nom, infos in donnees.items() if nom in gardees}
    if restant != donnees:
        oubliees = sorted(set(donnees) - set(restant))
        print("Journal : %d variante(s) retirée(s) — absente(s) de la fiche : %s"
              % (len(oubliees), ", ".join(oubliees)))
        _ecrire_journal(page_id, restant)
    return restant


# --- Recherche de la fiche (regle 5) -----------------------------------------

def resoudre_fiche(nom, token):
    """Cherche dans la base Fiches Client uniquement. En cas d'ambiguite, prefere la fiche
    datee (« COSNEFROY Ophélie 01/07 ») : les pages non datees sont des modeles."""
    try:
        return fn.chercher_fiche(nom, token)
    except SystemExit as e:
        lignes = [l.strip() for l in str(e).splitlines() if "—" in l]
        datees = [l for l in lignes if re.search(r"\d{1,2}[/-]\d{1,2}", l)]
        if len(datees) == 1:
            titre, pid = [x.strip() for x in datees[0].rsplit("—", 1)]
            print("Plusieurs fiches trouvées — retenue : « %s » (seule fiche datée)." % titre)
            return pid, titre
        raise


# --- Rapport -----------------------------------------------------------------

# --- Ligne de dossier pour le CRM ---------------------------------------------

def _nb(v):
    """« 27 » -> 27.0 ; « » et None -> None. Le Sheet doit recevoir des nombres, pas du texte."""
    if isinstance(v, bool) or v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def _client_depuis_nom(nom):
    """« Lucile VIGNERON » -> nom/prenom. Repli quand la fiche Notion n'a pas ete relue :
    le calculateur ne connait qu'une chaine libre, saisie a la main."""
    bouts = (nom or "").strip().split()
    if not bouts:
        return {}
    # convention des fiches : le NOM est en majuscules, le reste est le prenom
    majs = [b for b in bouts if b.isupper() and len(b) > 1]
    if majs:
        return {"nom": " ".join(majs),
                "prenom": " ".join(b for b in bouts if b not in majs) or None}
    return {"nom": bouts[-1], "prenom": " ".join(bouts[:-1]) or None}


def ref_archive(ex, page_id=None, ref_fiche=None):
    """Cle de la ligne : UNE LIGNE PAR DEVIS.

    Deux devis pour un meme client — Standard et Confort, avec et sans piano — sont deux
    variantes, donc deux refs, donc deux lignes. Aucun ecrasement possible entre eux. Le
    calculateur nomme la variante tout seul quand le champ est vide (« Standard + piano »).

    Reexporter la MEME variante apres correction remplace sa propre ligne : c'est le meme
    devis corrige, pas un second. Variante sans nom : l'horodatage de l'export sert de
    suffixe, sans quoi deux devis anonymes du meme client se marcheraient dessus.
    """
    base = (ref_fiche or "").strip() or (page_id or "").replace("-", "")[:8] \
        or _sans_accents(ex.get("client") or "devis").replace(" ", "-")
    variante = (ex.get("variante") or "").strip()
    if not variante:
        horo = "".join(c for c in (ex.get("genere_le") or "") if c.isdigit())[:14]
        variante = horo or "devis"
    return "%s · %s" % (base, variante)


def ligne_archive(ex, tps, page_id=None, token=None, fichier=None):
    """Aplatit l'export du calculateur en une ligne de dossier pour le CRM (le Google Sheet qui la
    recevait est coupé depuis le 03/11/2026).

    La fiche est relue quand on la connait : elle seule porte l'adresse, le telephone, le commercial
    et la date de chargement, que l'export du calculateur n'a jamais eus. Une lecture qui echoue ne
    fait pas echouer la ligne — elle part avec ce que le devis contient.
    """
    dossier = {}
    if page_id and token:
        try:
            dossier, _ = fn.lire_fiche(page_id, token)
        except Exception as e:                     # reseau, fiche supprimee, parseur
            print("  (fiche non relue : %s)" % e)
            dossier = {}

    i = ex.get("ex") or {}
    mis = ex.get("mission") or {}
    eq = ex.get("equipe") or {}
    ch = ex.get("champs_fiche") or {}

    if not (dossier.get("client") or {}).get("nom"):
        dossier["client"] = _client_depuis_nom(ex.get("client"))

    # Le devis fait foi sur ce qui a ete chiffre : le calculateur porte les valeurs
    # eventuellement corrigees a la main, la fiche celles d'avant le chiffrage.
    m = dossier.setdefault("mission", {})
    for cle, val in (("volume_m3", _nb(mis.get("volume"))),
                     ("formule", mis.get("formule") or None),
                     ("date_creation", mis.get("date_creation") or None),
                     ("peage_ht", _nb(i.get("peageAR")))):
        if val is not None:
            m[cle] = val

    it = dossier.setdefault("itineraire", {})
    for cle, val in (("km_ar", _nb(i.get("kmAR"))),
                     ("heures_conduite_ar", _nb(i.get("heuresRouteAR")))):
        if val is not None:
            it[cle] = val

    volume = m.get("volume_m3")
    deductions = {
        "nb_depart": _nb(eq.get("intervenants_chargement")),
        "nb_arrivee": _nb(eq.get("intervenants_dechargement")),
        "nb_camions": _nb(i.get("nbCamions")),
        "gabarit": regles.gabarit_camion(volume) if volume else None,
    }

    ht, ttc = ch.get("total_ht"), ch.get("total_ttc")
    nombres = isinstance(ht, (int, float)) and isinstance(ttc, (int, float))
    chiffres = {
        "transport_ht": ch.get("transport_ht"), "manut_ht": ch.get("manut_ht"),
        "formule_ht": ch.get("formule_ht"), "deplacement_ht": ch.get("deplacement_ht"),
        "materiel_ht": ch.get("materiel_ht"), "dossier_ht": ch.get("dossier_ht"),
        "autres_ht": ch.get("autres_frais_ht"),
        "total_ht": ht, "total_ttc": ttc,
        "tva": round(ttc - ht, 2) if nombres else None,
        "marge_pct": (ex.get("marge") or {}).get("pct"),
        "commission_ht": (ex.get("commission") or {}).get("montant"),
    }

    ligne = export.ligne_sheet(dossier, deductions, chiffres, fichier)
    meta = dossier.get("_meta") or {}
    ligne["ref"] = ref_archive(ex, page_id, m.get("ref"))
    # Le lien vers l'ancienne page Notion reste sur la transaction ; un dossier HubSpot n'en a pas.
    url = (ex.get("fiche") or {}).get("url") or meta.get("url")
    ligne["notion_url"] = url if "notion" in (url or "") else None
    ligne["variante"] = (ex.get("variante") or "").strip() or None
    ligne["mission_min"] = (tps or {}).get("mission")
    ligne["exporte_le"] = ex.get("genere_le")
    return ligne


# --- Itineraire : les trois lignes de la section « Itinéraires » --------------
#
# Elles vivent HORS du bloc de chiffrage, donc hors de portee de composer(). Les valeurs
# sont connues depuis le debut — le module d'itineraire les a posees dans le calculateur au
# pre-remplissage, elles reviennent par l'export — mais personne ne les recopiait sur la
# fiche. Ecrites au format que fiche_notion.py sait relire (« 256 km », « 4h30 »), pour que
# la fiche reste sa propre source au prochain devis.

def lignes_itineraire(ex):
    """Rend [(etiquette, texte)] pour les lignes d'itineraire renseignables."""
    i = ex.get("ex") or {}
    km, heures, peage = _nb(i.get("kmAR")), _nb(i.get("heuresRouteAR")), _nb(i.get("peageAR"))
    L = []
    if km:
        # entier quand c'est rond : « 256 km », pas « 256.0 km »
        L.append(("kilometres a/r", "Kilomètres A/R : %s km"
                  % (int(km) if float(km).is_integer() else km)))
    if heures:
        L.append(("temps a/r", "Temps A/R : %s" % hhmm(round(heures * 60))))
    if peage is not None:
        # Un peage a 0 est une information, pas un trou : le devis ne facture pas de peage,
        # soit que l'itineraire l'evite, soit que Samuel ne l'ait pas releve — et dans ce
        # second cas c'est le devis qui est faux, pas la fiche. On ecrit ce qui a ete chiffre.
        L.append(("peage ht", "Péage HT : %s € HT" % eur(peage)))
    return L


def patcher_itineraire(blocs, ex):
    """Rend (patchs, journal) pour les lignes d'itineraire DEJA PRESENTES sur la fiche.

    On ne cree jamais ces lignes : une fiche qui n'a pas la section suit un autre modele, et
    inventer un emplacement ferait plus de degats que de la laisser vide.
    """
    voulues = dict(lignes_itineraire(ex))
    patchs, detail = {}, []
    if not voulues:
        return patchs, detail
    for b in blocs:
        lignes = list(b["lignes"])
        change = False
        for k, ligne in enumerate(lignes):
            cle = _etiquette(ligne)
            if cle in voulues and ligne.strip() != voulues[cle].strip():
                detail.append(("maj", "%s  →  %s"
                               % (ligne.strip() or "(vide)", voulues[cle])))
                lignes[k] = voulues[cle]
                change = True
        if change:
            patchs[b["id"]] = {"type": b["type"], "texte": "\n".join(lignes)}
    return patchs, detail


def rapport(ex, tps, lignes, pbs, groupes):
    marge =(ex.get("marge") or {}).get("pct")
    m = ex.get("mission") or {}
    ns = bool(m.get("next_stories"))
    out = ["Client   : %s" % (ex.get("client") or "—"),
           "Mission  : %s m³ · %s%s%s" % (m.get("volume"), m.get("formule"),
                                          " · groupage" if m.get("groupage") else "",
                                          " · Next Stories" if ns else ""),
           "",
           "Temps (règle 3 — ÷ %s puis demi-heure la plus proche) :"
           % str(tps["diviseur"]).replace(".", ","),
           "  chargement    %6s brut  →  %s" % (hhmm(tps["brut"]["chargement"]),
                                                hhmm_min(tps["chargement"])),
           "  déchargement  %6s brut  →  %s" % (hhmm(tps["brut"]["dechargement"]),
                                                hhmm_min(tps["dechargement"])),
           "  trajet %s · options %s  →  cumul %s  →  mission %s"
           % (hhmm(tps["route"]), hhmm(tps["options"]),
              hhmm(tps.get("mission_exacte")), hhmm_min(tps["mission"])),
           "",
           "Bloc de chiffrage à écrire :"]
    out += ["  " + texte for _, _, texte in lignes]
    out += ["",
            "Marge    : %s  (cible %s%s)"
            % (pct(marge), pct(regles.cible_marge(ns)), " · Next Stories" if ns else "")]
    if pbs:
        out += ["", "Contrôles arithmétiques :"] + ["  ⚠ " + p for p in pbs]
    if len(groupes) > 1:
        out += ["",
                "⚠ %d blocs de chiffrage sur cette fiche : %s"
                % (len(groupes), ", ".join("#%d %s" % (i + 1, g["titre"] or "(sans titre)")
                                           for i, g in enumerate(groupes))),
                "  Choisir avec --bloc N (défaut : le dernier)."]
    return "\n".join(out)


# --- CLI ---------------------------------------------------------------------

def _incident(quoi, ou, cause, ex=None, faire=None, trace=None, essais=None, etapes=False):
    """Signale un echec a Samuel sur Slack (repli e-mail) et le dit dans la sortie du script.

    Appele a chaque etape qui peut echouer sans faire tomber le reste (Sheet, WhatsApp,
    CRM) : sans cela, un echec ne se voit que dans une console que personne ne relit.
    `essais` : ce qu'a tente reprise.executer ; `etapes` : les etapes a rejouer (None = toute
    la finalisation, False = pas de commande de reprise).
    """
    fiche = (ex or {}).get("fiche") or {}
    dossier = fiche.get("titre") or (ex or {}).get("client")
    if essais:
        cause = "%s\n%s" % (cause, reprise.bilan(essais))
    cmd = reprise.commande(_EXPORT, etapes) if etapes is not False else None
    if cmd:
        faire = "%s\nRejouer : %s" % (faire or "", cmd)
    _, detail = notif.alerte(quoi=quoi, ou=ou, cause=cause, dossier=dossier,
                             faire=faire, trace=trace)
    print("  🔔 alerte — %s" % detail)


def _relecture(fonction, *args):
    """L'état de relecture n'arrête jamais la finalisation : la fiche et le CRM sont déjà écrits."""
    try:
        return fonction(*args)
    except Exception as e:
        print("Relecture : état non mis à jour — %s: %s" % (type(e).__name__, e))
        return None


def lancer_inventaire(page_id, volume, extra=()):
    """Lance inventaire_auto.py DÉTACHÉ, et rend tout de suite (ok, detail).

    Détaché, parce que la mise en forme d'un inventaire libre peut prendre une minute : le
    veilleur du presse-papier, qui attend la fin de ce script, ne doit pas rester aveugle
    pendant ce temps — un second export copié entre-temps serait perdu. Le processus enfant
    écrit son propre journal (.claude/scripts/inventaires-auto.log) et lève ses propres
    alertes : son sort ne regarde plus la finalisation.
    """
    script = os.path.join(ICI, "inventaire_auto.py")
    cmd = [sys.executable, script, "--page-id", page_id.replace("-", "")]
    if volume:
        cmd += ["--volume", str(volume)]
    cmd += list(extra)
    journal = os.path.join(RACINE, ".claude", "scripts", "inventaires-auto.log")
    drapeaux = 0
    if os.name == "nt":
        drapeaux = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_BREAKAWAY_FROM_JOB)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        with open(journal, "a", encoding="utf-8") as sortie:
            try:
                subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=sortie, creationflags=drapeaux,
                                 close_fds=True, cwd=ICI, env=env)
            except OSError:
                # Le job du veilleur peut interdire de s'en détacher : sans ce drapeau, l'enfant
                # reste attaché mais survit tout de même à la fin de la finalisation.
                drapeaux &= ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
                subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=sortie, creationflags=drapeaux,
                                 close_fds=True, cwd=ICI, env=env)
        return True, "recherche lancée en arrière-plan (journal : inventaires-auto.log)"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def main():
    ap = argparse.ArgumentParser(description="Finalisation d'une fiche client Sam'Déménage")
    ap.add_argument("fichier", nargs="?", default="--presse-papier",
                    help="JSON du calculateur ; « - » pour stdin ; défaut : presse-papier")
    ap.add_argument("--presse-papier", action="store_true", help="lire le presse-papier")
    ap.add_argument("--fiche", help="nom du client")
    ap.add_argument("--page-id", help="id de la transaction (ou d'une ancienne page Notion), si le nom est ambigu")
    ap.add_argument("--ttc-cible", type=float, help="règle 1 : repositionner le transport")
    ap.add_argument("--bloc", type=int, help="numéro du bloc de chiffrage (défaut : le dernier)")
    ap.add_argument("--variante", help="nom de la variante (défaut : celui porté par le JSON)")
    ap.add_argument("--diviseur", type=float, default=1.1, help="règle 3 (défaut 1,1)")
    ap.add_argument("--sans-division", action="store_true",
                    help="inscrire les temps bruts, sans diviser")
    ap.add_argument("--appliquer", action="store_true", help="écrire la fiche sur HubSpot")
    ap.add_argument("--sans-crm", action="store_true",
                    help="ne pas faire avancer le dossier dans le pipeline commercial")
    ap.add_argument("--crm", choices=CRMS,
                    help="CRM à mettre à jour (défaut : SAMDEM_CRM de outils/crm.env, sinon nocrm)")
    ap.add_argument("--whatsapp", action="store_true",
                    help="préparer le PDF et la relecture ; le message d'équipe part à la validation")
    ap.add_argument("--sans-inventaire", action="store_true",
                    help="ne pas chercher / envoyer l'inventaire après le message d'équipe")
    ap.add_argument("--seulement",
                    help="reprise : ne rejouer que ces étapes, séparées par des virgules, parmi "
                         "%s (jamais le WhatsApp ni l'inventaire)" % ", ".join(ETAPES_REPRISE))
    ap.add_argument("--json", action="store_true", help="sortie machine")
    a = ap.parse_args()
    global _EXPORT
    _EXPORT = None if a.presse_papier else a.fichier
    if a.seulement:
        etapes = set(e.strip() for e in a.seulement.split(",") if e.strip())
        inconnues = etapes - set(ETAPES_REPRISE)
        if inconnues:
            ap.error("étape(s) inconnue(s) : %s" % ", ".join(sorted(inconnues)))
        a.whatsapp, a.sans_inventaire = False, True
    else:
        etapes = set(ETAPES_REPRISE)

    ex = charger("--presse-papier" if a.presse_papier else a.fichier)
    if a.ttc_cible:
        ex = ajuster_ttc(ex, a.ttc_cible)
    tps = temps_fiche(ex, a.diviseur, a.sans_division)
    lignes = lignes_fiche(ex, tps)
    pbs = verifier(ex)
    ch = ex.get("champs_fiche") or {}

    # La fiche cible peut venir de trois endroits, par ordre de priorite : l'option
    # --page-id, l'option --fiche (recherche par nom), ou le JSON lui-meme — le
    # pre-remplissage y a depose l'identite de la page, elle a fait l'aller-retour.
    du_json = (ex.get("fiche") or {}).get("page_id")
    groupes, blocs, page_id, titre = [], [], None, None
    if a.fiche or a.page_id or du_json:
        token = fn._token()
        if a.page_id:
            page_id, titre = a.page_id, "(page %s)" % a.page_id
        elif a.fiche:
            page_id, titre = resoudre_fiche(a.fiche, token)
        else:
            page_id = du_json
            titre = (ex.get("fiche") or {}).get("titre") or "(page %s)" % du_json
            print("Fiche reprise du JSON : %s" % titre)
        if a.appliquer and not fn.est_transaction(page_id):
            deal_id, motif = fiche_hubspot.reprendre_notion(page_id, token)
            print("Ancien dossier : %s" % motif)
            if not deal_id:
                _incident("la fiche Notion n'a pas pu rejoindre sa transaction HubSpot",
                          "finalisation.py → fiche_hubspot.reprendre_notion",
                          "Transaction introuvable ou ambiguë : %s" % motif, ex,
                          faire="Rien n'est écrit. Rejouer avec --page-id <id de transaction> après avoir "
                                "fusionné les doublons.", etapes=False)
                return 1
            page_id = deal_id
            ex["fiche"] = dict(ex.get("fiche") or {}, page_id=deal_id)
        blocs = _lignes_blocs(page_id.replace("-", ""), token)
        groupes = reperer_blocs(blocs)

    variante = a.variante or ex.get("variante")
    txt = rapport(ex, tps, lignes, pbs, groupes)
    patchs, detail, a_creer, titre_a_poser, g = {}, [], False, None, None
    if groupes or variante:
        g, titre_a_poser = choisir_groupe(groupes, blocs, variante, a.bloc)
        a_creer = g is None and bool(variante)
    if g:
        patchs, detail = composer(blocs, g, lignes)
        txt += "\n\nFiche « %s » — bloc %s :\n" % (
            titre, g["titre"] or (("nouvelle variante « %s »" % titre_a_poser)
                                  if titre_a_poser else "principal"))
        marques = {"maj": "~", "ajout": "+", "info": "·", "alerte": "⚠"}
        for genre, msg in detail:
            txt += "  %s %s\n" % (marques[genre], msg)
        if not patchs and not titre_a_poser:
            txt += "  (aucune modification : la fiche porte déjà ces valeurs)\n"
    elif a_creer:
        txt += ("\n\nFiche « %s » : la variante « %s » n'existe pas encore — un bloc complet "
                "sera ajouté en bas de fiche, sans toucher aux %d bloc(s) déjà présents."
                % (titre, variante, len(groupes)))
    elif page_id:
        txt += "\n\n⚠ Aucun bloc de chiffrage trouvé sur la fiche « %s ». Rien à écrire." % titre

    if a.json:
        print(json.dumps({"champs_fiche": ch, "temps": tps, "marge": ex.get("marge"),
                          "lignes": [l[2] for l in lignes], "controles": pbs,
                          "page_id": page_id,
                          "blocs_trouves": len(groupes), "patchs": len(patchs)},
                         ensure_ascii=False, indent=2))
    else:
        print(txt)

    if not a.appliquer:
        if patchs or a_creer:
            print("\n→ Rien n'a été écrit. Relancer avec --appliquer pour mettre à jour la fiche.")
        return 0

    if pbs:
        print("\n⛔ Écriture refusée : les contrôles arithmétiques ne passent pas (voir plus haut).")
        return 1
    if not page_id:
        print("\n⛔ Aucune fiche indiquée : ajouter --fiche \"NOM\" ou --page-id.")
        return 1

    token = fn._token()
    # Un export qui previent l'equipe (le dernier) porte le devis retenu.
    prevenir = ex.get("prevenir", True)
    if "texte" in etapes:
        def ecrire_texte():
            # Une relance relit la fiche et recompose : rien n'est ajoute deux fois.
            neuves, detail_note = note_chiffree(fn.lire_corps(page_id, token), lignes, variante, a.bloc, ex, prevenir)
            return True, "%s — %s" % (detail_note, fiche_hubspot.ecrire(page_id, neuves))

        ok, rep, essais = reprise.executer("texte de la fiche", ecrire_texte)
        print("\nFiche : %s" % (rep if ok else "ÉCHEC — %s" % rep))
        if not ok:
            _incident("le bloc de chiffrage n'a pas été écrit sur la fiche HubSpot",
                      "finalisation.py → HubSpot (note Fiche client)",
                      "HubSpot a refusé ou n'a pas répondu : %s" % rep, ex,
                      faire="Rien n'est parti à l'équipe ni au CRM. Vérifier la clé HubSpot puis rejouer.",
                      essais=essais, etapes=None)
            return 1
    if variante and "texte" in etapes:
        cj = ex.get("champs_fiche") or {}
        journal(page_id, variante, {"total_ttc": cj.get("total_ttc"),
                                    "total_ht": cj.get("total_ht"),
                                    "mission_min": tps["mission"]})

    # La ligne de dossier sert au CRM (nom, telephone, adresses) et coute une relecture de la fiche.
    lg = None
    if not a.sans_crm and "crm" in etapes:
        source = None if a.presse_papier or a.fichier in ("-", "--presse-papier") else a.fichier
        ok, rep, essais = reprise.executer(
            "ligne de dossier", lambda: (True, ligne_archive(ex, tps, page_id, token, source)))
        if ok:
            lg = rep
        else:
            print("Ligne de dossier non construite — %s" % rep)

    # relecture de controle (regle 10 du prompt Cowork). Illisible : le message d'equipe part
    # quand meme, avec le journal tel quel (gs vide = rien a elaguer).
    gs = []
    if "texte" in etapes:
        ok, relus, _ = reprise.executer(
            "relecture", lambda: (True, _lignes_blocs(page_id.replace("-", ""), token)))
        if ok:
            gs = reperer_blocs(relus)
            gr = choisir_groupe(gs, relus, variante, a.bloc)[0] if gs else None
            if gr:
                restants, _ = composer(relus, gr, lignes)
                print("Relecture : %s" % ("conforme" if not restants
                                          else "⚠ %d bloc(s) encore différents" % len(restants)))
        else:
            print("Relecture : impossible — %s" % relus)
    # Label Indicatif pose dans HubSpot avant le devis (Karim, 09/10/2026) : lu avant le
    # message pour que Sandrine applique le bon modele d'e-mail, et reporte dans l'export pour
    # que la synchro CRM plus bas ne le repasse pas en « Ferme ».
    if (not a.sans_crm and lg and "crm" in etapes and not (ex.get("fiche") or {}).get("indicatif")
            and crm_actif(a.crm) in ("hubspot", "les-deux")):
        valeur, detail = hubspot_crm.lire_type_devis(
            page_id=page_id, tel=lg.get("telephone"), email=lg.get("email"),
            nom=lg.get("client_nom"), prenom=lg.get("client_prenom"))
        if valeur == "Indicatif":
            ex["fiche"] = dict(ex.get("fiche") or {}, indicatif=True)
        print("HubSpot : type de devis %s — %s" % (valeur or "non lu", detail))
    # Le CRM passe avant le message (Karim, 03/11/2026) : le message porte le lien de la
    # transaction, qui doit donc exister. Même règle que les propriétés et l'itinéraire : seule
    # la variante retenue fait bouger le pipeline commercial, une variante intermédiaire ne
    # « ferme » rien.
    crm = crm_actif(a.crm)
    if not a.sans_crm and prevenir and "crm" in etapes and lg is None:
        # Sans ligne d'archive, ni nom ni telephone : l'appariement creerait un dossier vide.
        print("CRM : non mis à jour — ligne d'archive absente (voir plus haut).")
        _incident("le dossier n'a pas été mis à jour dans le CRM",
                  "finalisation.py → ligne_archive", "La ligne d'archive n'a pas pu être "
                  "construite (fiche illisible, ou ni nom ni téléphone) : le CRM n'est "
                  "pas touché.", ex, etapes=["crm"])
    elif not a.sans_crm and prevenir and "crm" in etapes:
        # `page_id` et `token` donnent au CRM l'acces au corps de la fiche : c'est ce qui
        # lui permet de recopier le dossier et d'y lire les totaux TTC. Les deux CRM
        # retrouvent le dossier existant a chaque passage : une relance ne cree rien deux fois.
        if crm in ("nocrm", "les-deux"):
            ok, msg, essais = reprise.executer("noCRM", lambda: nocrm.avancer_dossier(
                lg, appliquer=True, page_id=page_id, token=token))
            print("noCRM : %s%s" % ("" if ok else "ÉCHEC — ", msg))
            if not ok:
                _incident("le dossier n'a pas été mis à jour dans noCRM",
                          "finalisation.py → noCRM (nocrm.avancer_dossier)",
                          "Le CRM n'a pas pu être enrichi ou le dossier n'a pas été retrouvé. "
                          "Détail : %s" % msg,
                          ex, faire="La fiche est faite. Régler la cause, puis rejouer le CRM seul.",
                          essais=essais, etapes=["crm"])
        if crm in ("hubspot", "les-deux"):
            ok, msg, essais = reprise.executer("HubSpot", lambda: hubspot_crm.avancer_dossier(
                lg, appliquer=True, page_id=page_id, token=token, ex=ex))
            print("HubSpot : %s%s" % ("" if ok else "ÉCHEC — ", msg))
            if not ok:
                _incident("le dossier n'a pas été mis à jour dans HubSpot",
                          "finalisation.py → HubSpot (hubspot_crm.avancer_dossier)",
                          "Le CRM n'a pas pu être mis à jour ou le dossier n'a pas été retrouvé. "
                          "Détail : %s" % msg,
                          ex, faire="La fiche est faite. Régler la cause, puis rejouer le CRM seul.",
                          essais=essais, etapes=["crm"])
    elif not a.sans_crm:
        print("CRM : inchangé (variante intermédiaire) — le pipeline suivra le devis retenu.")

    if a.whatsapp and not prevenir:
        print("Variante intermédiaire : « autre variante à suivre ». PDF et relecture viendront au "
              "dernier export de ce client, avec toutes les variantes.")
    elif a.whatsapp:
        # `gs` vient de la relecture ci-dessus : c'est l'etat REEL de la fiche, apres les
        # suppressions faites a la main. Le message n'annonce que ces devis-la.
        # Le lien Notion ne sert que de repli, pour un ancien dossier sans transaction retrouvée.
        if not (ex.get("fiche") or {}).get("url") and not fn.est_transaction(page_id):
            ex["fiche"] = dict(ex.get("fiche") or {},
                               url="https://app.notion.com/p/" + page_id.replace("-", ""))
        if crm_actif(a.crm) in ("hubspot", "les-deux"):
            cl = lg or {}
            url, detail = hubspot_crm.url_transaction(
                page_id=page_id, tel=cl.get("telephone"), email=cl.get("email"),
                nom=cl.get("client_nom"), prenom=cl.get("client_prenom"))
            if url:
                ex["fiche"] = dict(ex.get("fiche") or {}, hubspot_url=url)
            else:
                print("WhatsApp : lien HubSpot introuvable (%s) — lien Notion à la place." % detail)
        variantes = elaguer_journal(page_id, gs)
        # Chaque export produit son PDF (Karim, 03/11/2026) : l'export est la version officielle,
        # même quand le prix n'a pas bougé. Le PDF reste en local et attend la relecture de Samuel
        # (validation_devis.py).
        pdf = {"pdfs": [], "numero": None, "inventaire_dans_devis": False, "christophe": False,
               "a_verifier": [], "raison": None}
        try:
            pdf = devis_auto.produire(ex, page_id, token, variantes,
                                      numeros=validation_devis.numeros_en_cours(page_id))
        except Exception as e:
            pdf["raison"] = "génération en échec"
            _incident("le PDF du devis n'a pas été généré",
                      "finalisation.py → devis_auto.produire",
                      "%s : %s" % (type(e).__name__, e), ex,
                      faire="Produire le PDF avec /devis-pdf-samdem, puis le remettre en relecture : "
                            "validation_devis.py --ajouter-pdf.", etapes=False)
        print("Devis PDF : %s" % (", ".join(p["chemin"] for p in pdf["pdfs"])
                                  or "à la main — %s" % pdf["raison"]))
        # Le message d'équipe et l'inventaire partent à la validation de Samuel (Karim, 03/11/2026) :
        # sans cet état, le devis n'arriverait ni sur HubSpot ni à l'équipe. Il garde donc de quoi
        # composer le message, avec les variantes du journal, et c'est lui qui vide le journal.
        try:
            validation_devis.enregistrer(page_id, ex, pdf, lg, tps, variantes)
            print("WhatsApp : message d'équipe à la validation du devis.")
        except Exception as e:
            _incident("le devis n'a pas pu être mis en relecture",
                      "finalisation.py → validation_devis.enregistrer",
                      "%s : %s" % (type(e).__name__, e), ex,
                      faire="La fiche et le CRM sont faits. Réexporter le devis pour relancer "
                            "la relecture.", etapes=False)

        # Inventaire (Karim, 18/09/2026), en arrière-plan : rien ici n'attend ni ne dépend de son
        # résultat. Il est préparé tout de suite pour la relecture, et rejoint HubSpot et l'équipe à
        # la validation ; à source inchangée, il ne coûte rien.
        # Sous 10 m³ (Karim, 24/09/2026) : l'inventaire est noté sur le devis, pas de PDF.
        # Un devis qui renvoie à « Voir inventaire » appelle l'inventaire, quel que soit le
        # volume. Dossier de Christophe (Karim, 02/11/2026) : jamais, c'est fait à la main.
        volume = (ex.get("mission") or {}).get("volume")
        motif = None
        if a.sans_inventaire:
            motif = "coupé par --sans-inventaire"
        elif pdf["christophe"]:
            motif = "dossier de Christophe, laissé à la main"
        elif pdf["inventaire_dans_devis"]:
            motif = "liste courte dans le devis"
        elif not pdf["pdfs"] and not regles.inventaire_pdf_requis(volume):
            motif = "%s m³ < %s m³, noté sur le devis" % (volume, regles.SEUIL_INVENTAIRE_PDF_M3)
        if motif:
            print("Inventaire : non produit — %s" % motif)
            _relecture(validation_devis.noter_inventaire, page_id, "sans_objet", None, motif)
        else:
            # Devis indicatif : PDF « inventaire indicatif … », pour HubSpot seulement.
            extra = ["--indicatif"] if (ex.get("fiche") or {}).get("indicatif") else []
            if pdf["numero"]:
                extra += ["--numero", pdf["numero"]]
            ok_inv, det_inv = lancer_inventaire(page_id, volume, extra)
            print("Inventaire : %s" % det_inv)
            if not ok_inv:
                _relecture(validation_devis.noter_inventaire, page_id, "erreur", None, det_inv)
                _incident("la recherche d'inventaire n'a pas pu être lancée",
                          "finalisation.py → inventaire_auto.py (lancement)",
                          "Le processus d'arrière-plan n'a pas démarré : %s" % det_inv,
                          ex, faire="Lancer à la main : python outils/pipeline/"
                                    "inventaire_auto.py --page-id %s" % page_id)
    return 0


def _main_protege():
    """Filet de securite : une exception non rattrapee ne doit pas s'eteindre en silence.

    Le veilleur de presse-papier lance ce script sans console visible : sans ce filet, une
    finalisation qui casse en plein milieu ne se remarquerait que le jour ou quelqu'un
    constate qu'une fiche est restee vide. Ctrl+C n'est pas un incident et ne declenche rien.
    """
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130
    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        print(trace, file=sys.stderr)
        try:
            notif.alerte(
                quoi="la finalisation du devis s'est interrompue en cours de route",
                ou="finalisation.py (erreur imprévue, traitement arrêté)",
                cause="Le script s'est arrêté sur une erreur qu'il ne sait pas gérer "
                      "(%s : %s). Ce qui avait déjà été écrit avant l'arrêt l'est resté ; "
                      "la suite ne s'est pas faite." % (type(e).__name__, e),
                faire=("Relancer : %s" % reprise.commande(_EXPORT) if reprise.commande(_EXPORT)
                       else "Remettre le JSON du devis au presse-papier (bouton « Exporter "
                            "JSON » du calculateur) puis relancer : python outils/pipeline/"
                            "finalisation.py --presse-papier --appliquer --whatsapp.")
                      + " Les étapes déjà faites ne sont pas doublées. Si l'erreur revient "
                        "à l'identique, elle vient du code et pas du dossier.",
                trace=trace)
        except Exception:
            pass                        # une alerte qui echoue ne doit rien aggraver
        return 3


if __name__ == "__main__":
    sys.exit(_main_protege())
