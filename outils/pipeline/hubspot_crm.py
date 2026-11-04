#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dernière étape de la chaîne devis, version HubSpot : remplace nocrm.avancer_dossier.

    devis exporté -> note « Fiche client » (fiche_hubspot.py) -> propriétés et étape de la transaction

Mêmes gestes que sur noCRM, transposés au modèle HubSpot (wiki/crm-manager/
dictionnaire-de-donnees.md, décisions D1 à D16 du 05/10/2026) :
  1. CONTACT — retrouvé par téléphone puis e-mail, créé s'il manque ; un champ déjà rempli
     n'est jamais écrasé.
  2. TRANSACTION — retrouvée par son identifiant, le lien d'une ancienne fiche Notion, la référence CLI-nnn, puis
     le contact (une seule transaction ouverte). Créée si le client n'en a aucune ouverte.
     Le chiffrage (propriétés sd_*, montant) est réécrit à chaque devis : le calculateur fait
     foi. Le suivi (adresses, date, commercial, lien, référence) n'est que complété.
  3. NOTE « Fiche client » — le corps de la fiche (D8), écrit par la finalisation : une seule note par
     transaction, modifiée à chaque changement (Karim, 04/11/2026).
  4. TÂCHE « Relancer » — coupée le 03/11/2026 (POSER_TACHE_RELANCE) : personne ne la lit, les relances
     passeront par W3. Le code reste : J+2, reportée au lundi, mise à jour si elle existe déjà.
  5. ÉTAPE — « Devis en révision » pour tout dossier, groupage compris (C-041, Karim 29/10/2026) :
     Sandrine ou Samuel envoie le devis, l'autre en copie ; la routine devis_envoye.py passe alors en
     « Devis envoyé », ou en « Demandes groupage » quand le trajet touche l'Île-de-France ou que
     la case Groupage est cochée (Karim, 03/11/2026). Un nouveau devis sur un dossier déjà envoyé
     le ramène en révision (Karim, 30/10/2026). Une transaction signée ou perdue ne bouge pas.

Chaque valeur passe par le schéma réel du portail avant d'être envoyée : type (nombre, date,
booléen, liste fermée), valeur autorisée, propriété masquée ou en lecture seule. Une valeur
qui ne colle pas n'est pas écrite et figure dans le compte rendu — jamais rejetée en bloc par
l'API au milieu d'une finalisation.

Ne touche jamais à sd_saisie_json : c'est la saisie de l'outil de devis de Ben, que son outil
rejoue ; y mettre l'export du calculateur maître (autres clés) casserait sa réouverture.

Configuration : .env (HUBSPOT_TOKEN=...), comme outils/hubspot/.

Usage :
    python hubspot_crm.py --test                          # clé, schéma, étapes du pipeline
    python hubspot_crm.py --export "FICHIER.json"         # rejoue l'étape CRM d'un devis exporté
    python hubspot_crm.py --fiche --page-id <id>          # fiche seule -> contact + transaction + note
    python hubspot_crm.py --description "NOM Prénom"      # ce que HubSpot sait du client (lecture)
    ... --appliquer                                       # écrit (sinon : simulation)

Lecture (outils de relance, groupage, reporting, inventaire) : `leads()`, `leads_depuis()`,
`chercher_lead()`, `historique_etapes()`, `pieces_jointes()` rendent les transactions au format
des opportunités noCRM, pour que chaque outil garde ses règles telles quelles.
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import nocrm                                    # noqa: E402  (aides pures : _tel, axe, corps…)

BASE = "https://api.hubapi.com"
NOMS_CLE = ("HUBSPOT_TOKEN", "HUBSPOT_ACCESS_TOKEN", "HUBSPOT_API_KEY", "HUBSPOT_SERVICE_KEY")
ENV = os.environ.get("HUBSPOT_ENV") or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

PIPELINE = "default"                            # « Devis déménagement »
ETAPE_QUALIF = "qualifiedtobuy"                 # Qualification / RDV
ETAPE_DEVIS_ENVOYE = "contractsent"             # Devis envoyé
ETAPE_GROUPAGE = "6187764973"                   # Demandes groupage (après Devis envoyé, D3)
ETAPE_REVISION = "6328945894"                   # Devis en révision (C-041), cible de la chaîne
ETAPES_CLOSES = ("closedwon", "closedlost")     # Signé, Perdu

# Types d'association HubSpot (HUBSPOT_DEFINED)
DEAL_CONTACT, NOTE_DEAL, TACHE_DEAL = 3, 214, 216

TITRE_NOTE = "Fiche client"                # format relu par la chaîne (fiche_hubspot.py, Karim 03/11/2026)
ANCIEN_TITRE_NOTE = "Fiche client (Notion)"  # copie du corps Notion pour un humain, ne se relit pas
PREFIXE_TACHE = "Relancer"
POSER_TACHE_RELANCE = False                     # Personne ne lit la tâche d'appel J+2 : 86 ouvertes, 1 faite (Karim, 03/11/2026)
HEURE_RELANCE = "09:00"
EMAIL_REPLI = "contact@samdemenage.fr"          # même repli que noCRM : compte principal
COMMERCIAL_COMPLET = {"christophe": "Christophe CAMPAGNE", "karim": "Karim BORDEAU",
                      "samuel": "Samuel COHEN", "sandrine": "Sandrine ARROUS"}
SANS_COMPTE = {"christophe": "contact@samdemenage.fr"}   # M3 : dossiers de Christophe à Samuel
AXE = {nocrm.TAG_ALLER: "Bordeaux vers Paris", nocrm.TAG_RETOUR: "Paris vers Bordeaux"}
# Couloirs de groupage (Karim, 21/10/2026) : un axe est la route depuis Bordeaux, pas une ville.
# Départements dans l'ordre de la route ; un tuple = un seul rang (l'Île-de-France compte pour
# une étape). Le sens se lit sur le rang : départ plus près de Bordeaux -> « Bordeaux vers X ».
COULOIRS = {
    "Paris": ("33", "17", "16", "79", "86", "37", "41", "45", "28", nocrm.DEPTS_IDF,
              "60", "80", "02", "62", "59"),
    "Marseille": ("33", "47", "82", "31", "11", "34", "30", "13", "83", "06"),
    "Lyon": ("33", "24", "19", "63", "42", "69", "01", "38", "73", "74"),
    "Bayonne": ("33", "40", "64"),
}
SEUIL_AUTRE_LD_H = 8.0   # hors couloir : « Autre longue distance » au-delà de 8 h A/R
DUREE_MM = {"2h": "2 h (300 € HT)", "demi": "Demi-journée (360 € HT)"}
MOTEUR = "calculateur maître · samdem.devis.export/1"
INTERDITES = {"sd_saisie_json"}


# --- Accès API -----------------------------------------------------------------------------

def charger_cle():
    for nom in NOMS_CLE:
        if os.environ.get(nom):
            return os.environ[nom].strip()
    if os.path.isfile(ENV):
        with open(ENV, encoding="utf-8-sig") as f:
            for ligne in f:
                cle, _, val = ligne.strip().partition("=")
                if cle.strip() in NOMS_CLE and val.strip():
                    return val.strip().strip('"').strip("'")
    return None


class HubSpot:
    """Client minimal. `ecrire=False` : toute écriture est refusée avant de partir."""

    def __init__(self, cle, ecrire=False):
        self.cle, self.ecrire = cle, ecrire

    def req(self, methode, chemin, corps=None):
        if methode != "GET" and not chemin.endswith(("/search", "/batch/read")) and not self.ecrire:
            raise RuntimeError("écriture refusée en simulation : %s %s" % (methode, chemin))
        data = json.dumps(corps).encode() if corps is not None else None
        for essai in range(5):
            r = urllib.request.Request(BASE + chemin, data=data, method=methode, headers={
                "Authorization": "Bearer " + self.cle, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(r, timeout=30) as rep:
                    texte = rep.read()
                return json.loads(texte) if texte else {}
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")
                if e.code in (429, 502, 503, 504) and essai < 4:
                    time.sleep(2 ** essai)
                    continue
                raise RuntimeError("%s %s -> HTTP %s %s" % (methode, chemin, e.code, msg[:400]))

    def deposer_fichier(self, chemin, dossier):
        """Dépose un fichier dans le gestionnaire de fichiers HubSpot (privé). Rend son id."""
        if not self.ecrire:
            raise RuntimeError("écriture refusée en simulation : dépôt de %s" % chemin)
        borne = "----samdem%d" % int(time.time() * 1000)
        nom = os.path.basename(chemin)
        champs = [("folderPath", dossier), ("fileName", nom),
                  ("options", json.dumps({"access": "PRIVATE", "overwrite": False,
                                          "duplicateValidationStrategy": "NONE"}))]
        corps = b"".join(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                          % (borne, k, v)).encode("utf-8") for k, v in champs)
        with open(chemin, "rb") as f:
            contenu = f.read()
        corps += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: application/pdf\r\n\r\n" % (borne, nom)).encode("utf-8")
        corps += contenu + ("\r\n--%s--\r\n" % borne).encode()
        r = urllib.request.Request(BASE + "/files/v3/files", data=corps, method="POST", headers={
            "Authorization": "Bearer " + self.cle, "Content-Type": "multipart/form-data; boundary=" + borne})
        try:
            with urllib.request.urlopen(r, timeout=120) as rep:
                return json.loads(rep.read())["id"]
        except urllib.error.HTTPError as e:
            raise RuntimeError("dépôt du fichier -> HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:400]))

    def chercher(self, objet, groupes, proprietes, limite=20):
        r = self.req("POST", "/crm/v3/objects/%s/search" % objet,
                     {"filterGroups": groupes, "properties": proprietes, "limit": limite})
        return r.get("results", [])

    def lire_lot(self, objet, ids, proprietes):
        if not ids:
            return []
        r = self.req("POST", "/crm/v3/objects/%s/batch/read" % objet,
                     {"properties": proprietes, "inputs": [{"id": str(i)} for i in ids]})
        return r.get("results", [])

    def associes(self, objet, id_, vers):
        r = self.req("GET", "/crm/v4/objects/%s/%s/associations/%s?limit=100" % (objet, id_, vers))
        return [str(x["toObjectId"]) for x in r.get("results", [])]


# --- Schéma : chaque valeur au format exact de sa propriété --------------------------------

def _plat(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _nombre(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = re.sub(r"[^\d,.\-]", "", str(v)).replace(",", ".")
        try:
            n = float(s)
        except ValueError:
            return None
    return int(n) if n.is_integer() else round(n, 2)


def tel_international(brut):
    """Format +33… ; None quand le numéro ne se lit pas sans deviner."""
    if not brut:
        return None
    s = str(brut).strip()
    chiffres = re.sub(r"\D", "", s)
    if s.startswith("+") and len(chiffres) >= 8:
        return "+" + chiffres
    if chiffres.startswith("0033"):
        return "+" + chiffres[2:]
    if len(chiffres) == 10 and chiffres.startswith("0"):
        return "+33" + chiffres[1:]
    if len(chiffres) == 9:
        return "+33" + chiffres
    return None


INFO_MANQUANTE = re.compile(r"information manquante|a confirmer|a completer|a renseigner|non communique|"
                            r"non renseigne|inconnu", re.I)


def info_manquante(v):
    """Valeur qui dit qu'une information manque (« 🟡 Information manquante », « à confirmer »…)."""
    return isinstance(v, str) and ("🟡" in v or bool(INFO_MANQUANTE.search(_plat(v))))


class Schema:
    """Propriétés réelles du portail, lues une fois par passage."""

    def __init__(self, hs):
        self.props, self.vides = {}, []
        for objet in ("deals", "contacts"):
            r = hs.req("GET", "/crm/v3/properties/%s?archived=false" % objet)
            self.props[objet] = {p["name"]: p for p in r.get("results", [])}

    def formater(self, objet, nom, v):
        """Rend (valeur prête à envoyer, None) ou (None, motif du refus)."""
        p = self.props[objet].get(nom)
        if nom in INTERDITES:
            return None, "propriété réservée à l'outil de devis de Ben"
        if p is None:
            return None, "propriété absente du portail"
        if (p.get("modificationMetadata") or {}).get("readOnlyValue") or p.get("calculated"):
            return None, "propriété en lecture seule"
        if p.get("hidden") and not p.get("hubspotDefined"):
            return None, "propriété masquée (doublon vide, D13)"
        t, champ = p.get("type"), p.get("fieldType")
        if t == "number":
            n = _nombre(v)
            return (n, None) if n is not None else (None, "%r n'est pas un nombre" % (v,))
        if t == "bool":
            if isinstance(v, str):
                v = _plat(v) in ("true", "oui", "1", "x", "vrai")
            return ("true" if v else "false"), None
        if t == "enumeration":
            options = p.get("options") or []
            for o in options:
                if str(v) == o["value"]:
                    return o["value"], None
            for o in options:
                if _plat(v) in (_plat(o["value"]), _plat(o["label"])):
                    return o["value"], None
            return None, "%r hors liste (%s)" % (v, " / ".join(o["label"] for o in options))
        if t == "date":
            m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
            return (m.group(1), None) if m else (None, "%r n'est pas une date" % (v,))
        if t == "datetime":
            return (str(v), None) if re.match(r"\d{4}-\d{2}-\d{2}", str(v)) else (None, "date-heure illisible")
        if champ == "phonenumber" or nom in ("phone", "mobilephone"):
            t_ = tel_international(v)
            return (t_, None) if t_ else (None, "téléphone %r illisible" % (v,))
        if nom == "email":
            s = email_valide(v)
            return (s, None) if s else (None, "e-mail %r invalide" % str(v).strip())
        s = str(v).strip()
        return (s[:65000], None) if s else (None, "vide")

    def nettoyer(self, objet, valeurs, refus):
        propres = {}
        for k, v in valeurs.items():
            if v is None or v == "":
                continue
            # Information manquante : la propriété reste vide, rien ne bloque (Karim, 09/10/2026) —
            # le manque reste lisible dans la note « Fiche client (Notion) ».
            if info_manquante(v):
                self.vides.append("%s.%s" % (objet[:-1], k))
                continue
            val, motif = self.formater(objet, k, v)
            if motif:
                refus.append("%s.%s : %s" % (objet[:-1], k, motif))
            else:
                propres[k] = val
        return propres


# --- Correspondance : export du calculateur + fiche -> propriétés HubSpot ------------------

def _ref_fiche(ligne):
    m = re.match(r"\s*(CLI-\d+)\b", str((ligne or {}).get("ref") or ""))
    return m.group(1) if m else None


def _page_id(page_id, ligne):
    if page_id:
        return str(page_id).replace("-", "")
    m = re.search(r"([0-9a-f]{32})\s*$", str((ligne or {}).get("notion_url") or ""))
    return m.group(1) if m else None


def _rang(couloir, dept):
    for n, etape in enumerate(couloir):
        if dept == etape or (isinstance(etape, tuple) and dept in etape):
            return n
    return None


def axe_groupage(depart, arrivee, heures_route_ar=None):
    """Valeur de sd_axe_groupage, dans le sens du trajet. Les deux bouts sur un même couloir,
    à des étapes différentes -> « Bordeaux vers X » / « X vers Bordeaux ». Hors couloir et plus
    de 8 h A/R -> « Autre longue distance ». Sinon (local, Gironde, inconnu) -> None."""
    d, a = nocrm._dept(depart), nocrm._dept(arrivee)
    if d and a:
        for ville, couloir in COULOIRS.items():
            rd, ra = _rang(couloir, d), _rang(couloir, a)
            if rd is not None and ra is not None and rd != ra:
                return ("Bordeaux vers %s" if rd < ra else "%s vers Bordeaux") % ville
    try:
        h = float(heures_route_ar)
    except (TypeError, ValueError):
        h = 0.0
    return "Autre longue distance" if h > SEUIL_AUTRE_LD_H else None


def email_valide(v):
    """E-mail normalisé, ou None : absent, « 🟡 information manquante », mal formé."""
    s = str(v or "").strip().lower()
    return s if re.fullmatch(r"[\w.+\-]+@[\w\-]+(\.[\w\-]+)+", s) else None


def proprietes_contact(ligne):
    """L'e-mail (Karim, 08/10/2026) et le téléphone (09/10/2026, cas ATIK) ne sont jamais
    bloquants : manquants, « 🟡 Information manquante » ou illisibles, ils sont omis, pas refusés —
    le contact part sans, et se complète au passage suivant."""
    l = ligne or {}
    nom = (l.get("client_nom") or "").strip()
    return {"lastname": nom.upper() or None, "firstname": (l.get("client_prenom") or "").strip() or None,
            "phone": tel_international(l.get("telephone")), "email": email_valide(l.get("email"))}


def proprietes_suivi(ligne, page_url=None):
    """Données de suivi (sans préfixe) : complétées, jamais écrasées."""
    l = ligne or {}
    commercial = (l.get("commercial") or "").strip()
    return {
        "adresse_depart": l.get("adresse_depart"),
        "adresse_arrivee": l.get("adresse_arrivee"),
        "date_demenagement": l.get("date_chargement"),
        "lien_fiche_notion": l.get("notion_url") or page_url,
        "sd_ref_dossier": _ref_fiche(l),
        "sd_commercial": COMMERCIAL_COMPLET.get(_plat(commercial).split(" ")[0], commercial) or None,
        "entite": "sam_demenage",          # la chaîne ne traite que du Sam'Déménage (09/09)
    }


def proprietes_chiffrage(ex, ligne):
    """Le chiffrage du devis retenu : réécrit à chaque export (le calculateur fait foi)."""
    import regles                               # import tardif : les clones de lib/ lisent sans lui
    ex = ex or {}
    i = ex.get("ex") or {}
    mis = ex.get("mission") or {}
    eq = ex.get("equipe") or {}
    ch = ex.get("champs_fiche") or {}
    mg = ex.get("marge") or {}
    ns = bool(mis.get("next_stories"))
    pct = mg.get("pct")
    ht = ch.get("total_ht")
    l = ligne or {}

    def portage(v):
        n = _nombre(v)
        return max(10, n) if n is not None else None       # 10 m au minimum (conventions)

    p = {
        "sd_total_ht": ht,
        "sd_total_ttc": ch.get("total_ttc"),
        "sd_transport_final": ch.get("transport_ht"),
        "sd_marge_estimee_pct": round(pct * 100, 1) if isinstance(pct, (int, float)) else None,
        "sd_marge_estimee_eur": mg.get("euro") if mg.get("euro") is not None else (
            round(pct * ht, 2) if isinstance(pct, (int, float)) and isinstance(ht, (int, float)) else None),
        "sd_marge_sous_seuil": (pct < regles.cible_marge(ns) - 1e-9) if isinstance(pct, (int, float)) else None,
        "validation_marge": "non",   # plus de plancher de marge (Karim, 03/11/2026)
        "sd_moteur_version": MOTEUR,
        "sd_volume_m3": mis.get("volume") or i.get("volume"),
        "sd_formule_tarifaire": mis.get("formule") or i.get("formule"),
        "sd_groupage": mis.get("groupage"),
        # Pose par pipeline.py --indicatif ; tout devis exporte sans lui est ferme.
        "sd_type_devis": "Indicatif" if (ex.get("fiche") or {}).get("indicatif") else "Ferme",
        "sd_next_stories": ns,
        "sd_mission_weekend": mis.get("weekend"),
        "sd_nb_demenageurs_depart": eq.get("intervenants_chargement") or i.get("nbDepart"),
        "sd_nb_demenageurs_arrivee": eq.get("intervenants_dechargement") or i.get("nbArrivee"),
        "sd_nb_camions": i.get("nbCamions"),
        "sd_nb_camions_location": i.get("nbCamionsLoc"),
        "sd_camion_location_ht": i.get("camionLocHT"),
        "sd_km_ar": i.get("kmAR"),
        "sd_heures_route_ar": i.get("heuresRouteAR"),
        "sd_peage_ar": i.get("peageAR"),
        "sd_axe_groupage": axe_groupage(l.get("adresse_depart") or l.get("commune_depart"),
                                        l.get("adresse_arrivee") or l.get("commune_arrivee"),
                                        i.get("heuresRouteAR")),
    }
    if ns:
        p["source_lead"] = "nextories"
    for cote, suffixe in (("Depart", "depart"), ("Arrivee", "arrivee")):
        p["sd_type_logement_%s" % suffixe] = i.get("tl" + cote)
        p["sd_etage_%s" % suffixe] = i.get("etage" + cote)
        p["sd_portage_%s_m" % suffixe] = portage(i.get("portage" + cote))
        if "asc" + cote in i:
            p["sd_ascenseur_%s" % suffixe] = bool(i.get("asc" + cote))
            p["sd_ascenseur_%s_petit" % suffixe] = bool(i.get("asc" + cote + "Petit"))
        if "mm" + cote in i:
            mm = i.get("mm" + cote) or ""
            p["sd_monte_meubles_%s" % suffixe] = bool(mm)
            p["sd_duree_monte_meubles_%s" % suffixe] = DUREE_MM.get(mm)
    return p


def montant_ht(ex, corps):
    """`amount` en HT (D1) = le devis le plus élevé de la fiche (règle du 10/09, D2).

    Rend (ht, ttc_retenu, tous les TTC). Le HT exact du devis courant quand c'est lui le plus
    cher ; sinon TTC ÷ 1,2, tout le devis étant à 20 %."""
    ch = (ex or {}).get("champs_fiche") or {}
    ttc_courant, ht_courant = ch.get("total_ttc"), ch.get("total_ht")
    tous = nocrm.montants_ttc(corps) if corps else []
    if isinstance(ttc_courant, (int, float)) and ttc_courant not in tous:
        tous.append(ttc_courant)
    if not tous:
        return None, None, []
    haut = max(tous)
    if isinstance(ttc_courant, (int, float)) and abs(haut - ttc_courant) < 0.01 and ht_courant:
        return ht_courant, haut, tous
    return round(haut / 1.2, 2), haut, tous


def note_html(titre, texte):
    texte = html.unescape(texte or "").replace("\xa0", " ")
    if len(texte) > 50000:                      # corps de note limité à 65 536 caractères
        texte = texte[:50000] + "\n[… tronqué]"
    corps = "<br>".join(html.escape(l) for l in texte.splitlines())
    return "<p><strong>%s</strong></p><p>%s</p>" % (html.escape(titre), corps)


def heure_paris(jour, heure=HEURE_RELANCE):
    d = datetime.date.fromisoformat(jour[:10])

    def dernier_dimanche(mois):
        x = datetime.date(d.year, mois, 31)
        return x - datetime.timedelta(days=(x.weekday() + 1) % 7)

    ete = dernier_dimanche(3) <= d < dernier_dimanche(10)
    return "%sT%s:00%s" % (d.isoformat(), heure, "+02:00" if ete else "+01:00")


# --- Rapprochement -------------------------------------------------------------------------

PROPS_DEAL = ["dealname", "dealstage", "pipeline", "hubspot_owner_id", "amount", "lien_fiche_notion",
              "sd_ref_dossier"]
PROPS_CONTACT = ["firstname", "lastname", "email", "phone", "mobilephone", "hubspot_owner_id"]


def _ouvertes(deals):
    return [d for d in deals if d["properties"].get("dealstage") not in ETAPES_CLOSES]


def trouver_contact(hs, tel, email):
    """Rend (contact|None, motif, ambigu). Téléphone d'abord, puis e-mail ; jamais le nom."""
    t9, mail = nocrm._tel(tel), email_valide(email)
    par_tel, par_mail = [], []
    if t9:
        par_tel = hs.chercher("contacts", [
            {"filters": [{"propertyName": "hs_searchable_calculated_phone_number", "operator": "EQ", "value": t9}]},
            {"filters": [{"propertyName": "hs_searchable_calculated_mobile_number", "operator": "EQ", "value": t9}]},
        ], PROPS_CONTACT)
    if mail:
        par_mail = hs.chercher("contacts", [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": mail}]}], PROPS_CONTACT)
    ids_tel, ids_mail = {c["id"] for c in par_tel}, {c["id"] for c in par_mail}
    if len(ids_tel) > 1:
        return None, "%d contacts avec ce téléphone" % len(ids_tel), True
    if ids_tel and ids_mail and ids_tel != ids_mail:
        return None, "le téléphone et l'e-mail désignent deux contacts différents", True
    if par_tel:
        return par_tel[0], "téléphone", False
    if len(ids_mail) > 1:
        return None, "%d contacts avec cet e-mail" % len(ids_mail), True
    if par_mail:
        return par_mail[0], "e-mail", False
    return None, "aucun contact", False


def transaction_orpheline(hs, nom, prenom):
    """Transactions ouvertes au nom du client et sans contact associé.

    Cas DUPRAT (09/10/2026) : une transaction saisie à la main depuis le formulaire n'a ni
    contact, ni lien Notion, ni référence ; sans ce repli, la finalisation en créait une
    seconde. Le nom seul ne suffit que pour une transaction orpheline.
    """
    mots = [m for m in re.split(r"[\s-]+", "%s %s" % (nom or "", prenom or "")) if len(m) > 1]
    if not mots:
        return []
    trouves = _ouvertes(hs.chercher("deals", [{"filters": [
        {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": m} for m in mots]}],
        PROPS_DEAL))
    return [d for d in trouves if not hs.associes("deals", d["id"], "contacts")]


def trouver_transaction(hs, page_id, ref, contact, nom=None, prenom=None):
    """Rend (transaction|None, motif, ambigu). Identifiant de transaction, fiche Notion, réf. CLI,
    contact, puis nom (transaction ouverte sans contact uniquement)."""
    if re.fullmatch(r"\d{6,}", page_id or ""):      # le dossier porte déjà son identifiant de transaction
        lus = hs.lire_lot("deals", [page_id], PROPS_DEAL)
        if lus:
            return lus[0], "identifiant de transaction", False
        page_id = None
    for libelle, groupes in (
            ("lien de la fiche Notion", page_id and [{"filters": [
                {"propertyName": "lien_fiche_notion", "operator": "CONTAINS_TOKEN", "value": "*" + page_id}]}]),
            ("référence %s" % ref, ref and [{"filters": [
                {"propertyName": "sd_ref_dossier", "operator": "EQ", "value": ref}]}])):
        if not groupes:
            continue
        trouves = hs.chercher("deals", groupes, PROPS_DEAL)
        if len(trouves) == 1:
            return trouves[0], libelle, False
        if len(trouves) > 1:
            ouvertes = _ouvertes(trouves)
            if len(ouvertes) == 1:
                return ouvertes[0], libelle + " (seule ouverte)", False
            return None, "%d transactions portent ce %s" % (len(trouves), libelle), True
    if contact:
        ids = hs.associes("contacts", contact["id"], "deals")
        ouvertes = _ouvertes(hs.lire_lot("deals", ids, PROPS_DEAL))
        if len(ouvertes) == 1:
            return ouvertes[0], "contact (seule transaction ouverte)", False
        if len(ouvertes) > 1:
            return None, "%d transactions ouvertes sur ce contact : %s" % (len(ouvertes), " · ".join(
                "%s (%s)" % (d["properties"].get("dealname"), d["id"]) for d in ouvertes[:5])), True
    orphelines = transaction_orpheline(hs, nom, prenom)
    if len(orphelines) == 1:
        return orphelines[0], "nom (transaction sans contact)", False
    if len(orphelines) > 1:
        return None, "%d transactions ouvertes sans contact à ce nom : %s" % (len(orphelines), " · ".join(
            "%s (%s)" % (d["properties"].get("dealname"), d["id"]) for d in orphelines[:5])), True
    return None, "aucune transaction ouverte", False


def marquer_type_devis(valeur, page_id=None, tel=None, email=None, nom=None, prenom=None, hs=None):
    """« Type de devis » posé dès la génération (pipeline.py --indicatif), sans attendre la
    finalisation. Même appariement que celle-ci ; ambiguïté ou rien trouvé : aucune écriture."""
    try:
        hs = hs or HubSpot(charger_cle(), ecrire=True)
        contact, motif, ambigu = trouver_contact(hs, tel, email)
        if ambigu:
            return False, "contact ambigu (%s), « Type de devis » non posé" % motif
        deal, motif, ambigu = trouver_transaction(hs, (page_id or "").replace("-", ""), None, contact,
                                                  nom, prenom)
        if ambigu or not deal:
            return False, "transaction introuvable ou ambiguë (%s), « Type de devis » non posé" % motif
        hs.req("PATCH", "/crm/v3/objects/deals/%s" % deal["id"], {"properties": {"sd_type_devis": valeur}})
        return True, "« Type de devis » = %s sur « %s » (%s, %s)" % (
            valeur, deal["properties"].get("dealname"), deal["id"], motif)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def lire_type_devis(page_id=None, tel=None, email=None, nom=None, prenom=None, hs=None):
    """« Type de devis » tel qu'il est sur la transaction, lu avant le message d'équipe : le label
    Indicatif peut être posé à la main plus tôt dans le process (Karim, 09/10/2026).
    Rend (valeur|None, explication) ; ne lève jamais."""
    try:
        hs = hs or HubSpot(charger_cle())
        contact, motif, ambigu = trouver_contact(hs, tel, email)
        if ambigu:
            return None, "contact ambigu (%s)" % motif
        deal, motif, ambigu = trouver_transaction(hs, (page_id or "").replace("-", ""), None, contact,
                                                  nom, prenom)
        if ambigu or not deal:
            return None, "transaction introuvable ou ambiguë (%s)" % motif
        valeur = hs.lire_lot("deals", [deal["id"]], ["sd_type_devis"])[0]["properties"].get("sd_type_devis")
        return valeur, "« %s » (%s)" % (deal["properties"].get("dealname"), deal["id"])
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def url_transaction(page_id=None, tel=None, email=None, nom=None, prenom=None, hs=None):
    """Lien de la transaction, pour le message d'équipe (Karim, 28/10/2026). Même appariement
    que la finalisation. Rend (url|None, explication) ; ne lève jamais.
    Une transaction créée à l'instant n'est pas encore dans l'index de recherche : sa mémoire passe
    d'abord."""
    try:
        cree = (_CREES.get((page_id or "").replace("-", "")) or {}).get("deal")
        if cree:
            return URL_DEAL % cree, "transaction créée à l'instant (%s)" % cree
        hs = hs or HubSpot(charger_cle())
        contact, motif, ambigu = trouver_contact(hs, tel, email)
        if ambigu:
            return None, "contact ambigu (%s)" % motif
        deal, motif, ambigu = trouver_transaction(hs, (page_id or "").replace("-", ""), None, contact,
                                                  nom, prenom)
        if ambigu or not deal:
            return None, "transaction introuvable ou ambiguë (%s)" % motif
        return URL_DEAL % deal["id"], "« %s » (%s)" % (deal["properties"].get("dealname"), deal["id"])
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def proprietaire(hs, commercial):
    """Rend (owner_id|None, explication). Même règle que noCRM : un mot commun suffit."""
    owners = hs.req("GET", "/crm/v3/owners?limit=100").get("results", [])
    cle = _plat(commercial).split(" ")[0] if commercial else ""
    if cle in SANS_COMPTE:
        mail = SANS_COMPTE[cle]
        o = next((o for o in owners if _plat(o.get("email")) == mail), None)
        if o:
            return o["id"], "%s sans compte HubSpot — affecté à %s (M3)" % (commercial, o.get("firstName"))
    if commercial:
        mots = set(_plat(commercial).split())
        for o in owners:
            if mots & set(_plat("%s %s" % (o.get("firstName"), o.get("lastName"))).split()):
                return o["id"], "commercial de la fiche : %s" % commercial
    o = next((o for o in owners if _plat(o.get("email")) == EMAIL_REPLI), None)
    motif = "aucun commercial sur la fiche" if not commercial else "« %s » sans compte HubSpot" % commercial
    return (o["id"] if o else None), "%s — affecté au compte principal" % motif


# --- Écritures -----------------------------------------------------------------------------

def completer(hs, objet, id_, existant, voulu):
    """N'écrit que les champs vides de l'objet existant."""
    vides = {k: v for k, v in voulu.items() if existant.get(k) in (None, "")}
    if vides:
        hs.req("PATCH", "/crm/v3/objects/%s/%s" % (objet, id_), {"properties": vides})
    return sorted(vides)


def titre_note(body):
    """Première ligne d'une note ; HubSpot réécrit le HTML, seul le texte est sûr."""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", body or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return next((l.strip() for l in s.splitlines() if l.strip()), "")


def est_note_fiche(body):
    return titre_note(body) in (TITRE_NOTE, ANCIEN_TITRE_NOTE)


def notes_fiche(notes):
    """Notes de fiche client, nouveau et ancien format, la plus récente d'abord."""
    return sorted((n for n in notes if est_note_fiche(n["properties"].get("hs_note_body"))),
                  key=lambda n: n["properties"].get("hs_timestamp") or "", reverse=True)


def poser_note(hs, deal_id, corps):
    """Note « Fiche client » : une seule par transaction. Absente, elle est créée ; présente, elle
    est modifiée, plusieurs fiches identiques ne font que polluer le fil (Karim, 04/11/2026).
    Une copie « Fiche client (Notion) » ne se relit pas : elle reste telle quelle."""
    body = note_html(TITRE_NOTE, corps)
    notes = hs.lire_lot("notes", hs.associes("deals", deal_id, "notes"), ["hs_note_body", "hs_timestamp"])
    fiches = [n for n in notes_fiche(notes) if titre_note(n["properties"].get("hs_note_body")) == TITRE_NOTE]
    if fiches:
        if texte_note(fiches[0]["properties"].get("hs_note_body")) == texte_note(body):
            return "note fiche client déjà à jour"
        hs.req("PATCH", "/crm/v3/objects/notes/%s" % fiches[0]["id"], {"properties": {"hs_note_body": body}})
        return "note fiche client modifiée"
    maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hs.req("POST", "/crm/v3/objects/notes", {
        "properties": {"hs_note_body": body, "hs_timestamp": maintenant},
        "associations": [{"to": {"id": deal_id}, "types": [
            {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_DEAL}]}]})
    return "note fiche client créée"


def poser_relance(hs, deal_id, titre, owner_id, jour):
    """Tâche « Relancer » à J+2 9 h : la tâche ouverte existante est déplacée, pas doublée."""
    quand = heure_paris(jour)
    taches = hs.lire_lot("tasks", hs.associes("deals", deal_id, "tasks"),
                         ["hs_task_subject", "hs_task_status", "hs_timestamp"])
    ouverte = next((t for t in taches if (t["properties"].get("hs_task_subject") or "").startswith(PREFIXE_TACHE)
                    and t["properties"].get("hs_task_status") != "COMPLETED"), None)
    if ouverte:
        hs.req("PATCH", "/crm/v3/objects/tasks/%s" % ouverte["id"], {"properties": {"hs_timestamp": quand}})
        return "relance déplacée au %s" % jour
    props = {"hs_timestamp": quand, "hs_task_subject": "%s %s" % (PREFIXE_TACHE, titre),
             "hs_task_status": "NOT_STARTED", "hs_task_type": "CALL"}
    if owner_id:
        props["hubspot_owner_id"] = owner_id
    hs.req("POST", "/crm/v3/objects/tasks", {"properties": props, "associations": [{"to": {"id": deal_id}, "types": [
        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": TACHE_DEAL}]}]})
    return "relance créée au %s" % jour


def choisir_etape(cible, etape_actuelle, existe, axe_idf):
    """(étape à écrire ou None, phrase du compte rendu ou None)."""
    if not cible:
        return None, None
    apres = " ; trajet Île-de-France : après l'envoi, la routine passera en « Demandes groupage »" if axe_idf else ""
    if etape_actuelle in ETAPES_CLOSES:
        return None, "laissée en « %s » (transaction close)" % _nom_etape(etape_actuelle)
    if etape_actuelle == cible:
        return None, "déjà en « %s »%s" % (_nom_etape(cible), apres)
    return cible, "« %s » → « %s »%s" % (_nom_etape(etape_actuelle) if existe else "création",
                                        _nom_etape(cible), apres)


def _nom_etape(id_):
    return {ETAPE_QUALIF: "Qualification / RDV", ETAPE_DEVIS_ENVOYE: "Devis envoyé",
            ETAPE_REVISION: "Devis en révision",
            ETAPE_GROUPAGE: "Demandes groupage", "closedwon": "Signé", "closedlost": "Perdu",
            "appointmentscheduled": "Demande reçue", "6187764972": "En attente d'infos",
            "presentationscheduled": "Inventaire réalisé", "decisionmakerboughtin": "Devis à produire",
            "5973046476": "Relance"}.get(id_, id_)


# --- Point d'entrée ------------------------------------------------------------------------

# Contacts et transactions créés pendant ce processus, par dossier. L'index de recherche
# HubSpot met quelques secondes à les voir : sans cette mémoire, une relance immédiate de
# finalisation.py (reprise.py) les recréerait.
_CREES = {}


def _cle_memo(pid, ligne):
    return pid or "%s|%s|%s" % (ligne.get("client_nom"), ligne.get("client_prenom"), ligne.get("telephone"))


def assurer_transaction(ligne, hs=None, page_id=None):
    """Contact et transaction du dossier, retrouvés ou créés, suivi complété, étape inchangée.
    Rend (id de transaction|None, compte rendu). Rien n'est écrit en cas d'ambiguïté."""
    hs = hs or HubSpot(charger_cle(), ecrire=True)
    ok, msg = avancer_dossier(ligne, appliquer=True, page_id=page_id, hs=hs)
    if not ok:
        return None, msg
    pid = _page_id(page_id, ligne)
    cree = (_CREES.get(_cle_memo(pid, ligne)) or {}).get("deal")
    if cree:
        return cree, msg
    contact, _, _ = trouver_contact(hs, ligne.get("telephone"), ligne.get("email"))
    deal, motif, ambigu = trouver_transaction(hs, pid, _ref_fiche(ligne), contact,
                                              ligne.get("client_nom"), ligne.get("client_prenom"))
    return (deal["id"], msg) if deal and not ambigu else (None, motif)


def avancer_dossier(ligne, appliquer=False, page_id=None, token=None, ex=None, hs=None):
    """Même contrat que nocrm.avancer_dossier : rend (ok, message), ne lève jamais.

    `ligne` = la ligne d'archive de finalisation.py ; `ex` = l'export du calculateur (sans
    lui, seules les données de suivi partent : cas de --fiche). Sans `appliquer`, rien n'est
    écrit et le message décrit ce qui le serait.
    """
    try:
        cle = charger_cle()
        if not cle:
            return False, "clé HubSpot absente (%s)" % ENV
        hs = hs or HubSpot(cle, ecrire=appliquer)
        schema = Schema(hs)
        l = ligne or {}
        pid = _page_id(page_id, l)
        refus, journal, ecarts = [], [], []

        corps = None
        if pid:
            try:
                corps = nocrm.corps_notion(pid, token)
            except Exception as e:
                ecarts.append("fiche illisible (%s: %s) — montant pris sur le seul devis courant"
                              % (type(e).__name__, e))

        memo = _CREES.setdefault(_cle_memo(pid, l), {})
        contact, motif_c, ambigu = trouver_contact(hs, l.get("telephone"), l.get("email"))
        if ambigu:
            return False, "contact ambigu, aucune écriture : %s" % motif_c
        if not contact and memo.get("contact"):
            contact = hs.lire_lot("contacts", [memo["contact"]], PROPS_CONTACT)[0]
            motif_c = "créé à l'essai précédent"
        deal, motif_d, ambigu = trouver_transaction(hs, pid, _ref_fiche(l), contact,
                                                    l.get("client_nom"), l.get("client_prenom"))
        if ambigu:
            return False, "transaction ambiguë, aucune écriture : %s" % motif_d
        if not deal and memo.get("deal"):
            deal = hs.lire_lot("deals", [memo["deal"]], PROPS_DEAL)[0]
            motif_d = "créée à l'essai précédent"

        p_contact = schema.nettoyer("contacts", proprietes_contact(l), refus)
        if "email" not in p_contact:
            journal.append("e-mail absent de la fiche, contact écrit sans")
        if "phone" not in p_contact:
            journal.append("téléphone absent ou illisible sur la fiche, contact écrit sans")
        suivi = schema.nettoyer("deals", proprietes_suivi(l, l.get("notion_url")), refus)
        chiffrage, ht, ttc, tous = {}, None, None, []
        if ex:
            chiffrage = schema.nettoyer("deals", proprietes_chiffrage(ex, l), refus)
            ht, ttc, tous = montant_ht(ex, corps)
            if ht is not None:
                chiffrage["amount"] = ht
        axe_idf = bool(nocrm.tag_axe(l.get("adresse_depart") or l.get("commune_depart"),
                                     l.get("adresse_arrivee") or l.get("commune_arrivee")))
        cible = ETAPE_REVISION if ex else None
        titre = ("%s %s" % ((l.get("client_nom") or "").upper(), l.get("client_prenom") or "")).strip()
        if not titre and not contact and not deal:
            return False, "ni nom, ni téléphone, ni e-mail : dossier non identifiable, rien créé"

        etape_actuelle = deal["properties"].get("dealstage") if deal else None
        cible, geste_etape = choisir_etape(cible, etape_actuelle, bool(deal), axe_idf)
        rappel = nocrm.date_rappel() if ex and POSER_TACHE_RELANCE else None

        if not appliquer:
            L = ["SIMULATION — rien n'est écrit",
                 "contact : %s" % ("%s (%s)" % (contact["id"], motif_c) if contact else "à créer"),
                 "transaction : %s" % ("%s « %s » (%s)" % (deal["id"], deal["properties"].get("dealname"), motif_d)
                                       if deal else "à créer « %s »" % titre)]
            if ex:
                L.append("montant HT : %s%s" % (ht, " (%d devis sur la fiche, le plus élevé)" % len(tous)
                                                 if len(tous) > 1 else ""))
            L.append("contact (si vides) : %s" % json.dumps(p_contact, ensure_ascii=False))
            L.append("suivi (si vides) : %s" % json.dumps(suivi, ensure_ascii=False))
            if chiffrage:
                L.append("chiffrage (réécrit) : %s" % json.dumps(chiffrage, ensure_ascii=False))
            if rappel:
                L.append("relance : %s %s" % (rappel, HEURE_RELANCE))
            if geste_etape:
                L.append("étape : %s" % geste_etape)
            if schema.vides:
                L.append("laissé vide (information manquante) : " + ", ".join(schema.vides))
            if refus:
                L.append("non écrit (format) : " + " ; ".join(refus))
            if ecarts:
                L.append("⚠ " + " ; ".join(ecarts))
            return True, "\n  ".join(L)

        # 1. Contact
        owner_id, motif_owner = proprietaire(hs, l.get("commercial"))
        if contact:
            faits = completer(hs, "contacts", contact["id"], contact["properties"], p_contact)
            if faits:
                journal.append("contact complété (%s)" % ", ".join(faits))
            cid = contact["id"]
        else:
            pc = dict(p_contact)
            if owner_id:
                pc["hubspot_owner_id"] = owner_id
            if not pc.get("lastname"):
                pc["lastname"] = titre or "Sans nom"
            cid = hs.req("POST", "/crm/v3/objects/contacts", {"properties": pc})["id"]
            memo["contact"] = cid
            journal.append("contact créé (%s)" % cid)

        # 2. Transaction : chiffrage réécrit, suivi complété ; l'étape vient en dernier
        if deal:
            did = deal["id"]
            actuel = hs.req("GET", "/crm/v3/objects/deals/%s?properties=%s" % (did, ",".join(
                list(suivi) + ["hubspot_owner_id"])))["properties"]
            faits = completer(hs, "deals", did, actuel, dict(suivi, **({"hubspot_owner_id": owner_id}
                                                                        if owner_id else {})))
            if chiffrage:
                hs.req("PATCH", "/crm/v3/objects/deals/%s" % did, {"properties": chiffrage})
                journal.append("chiffrage écrit (%d propriétés)" % len(chiffrage))
            if faits:
                journal.append("suivi complété (%s)" % ", ".join(faits))
            hs.req("PUT", "/crm/v4/objects/deals/%s/associations/default/contacts/%s" % (did, cid))
            owner_deal = actuel.get("hubspot_owner_id") or owner_id
        else:
            props = dict(suivi, **chiffrage)
            props.update({"dealname": titre or "Sans nom", "pipeline": PIPELINE,
                          "dealstage": cible or ETAPE_QUALIF})
            if owner_id:
                props["hubspot_owner_id"] = owner_id
            did = hs.req("POST", "/crm/v3/objects/deals", {"properties": props, "associations": [
                {"to": {"id": cid}, "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                               "associationTypeId": DEAL_CONTACT}]}]})["id"]
            memo["deal"] = did
            journal.append("transaction créée (%s, %s)" % (did, motif_owner))
            owner_deal = owner_id

        # 3. Relance. La note fiche client est écrite par la finalisation (fiche_hubspot.py).
        if rappel:
            journal.append(poser_relance(hs, did, titre or deal["properties"].get("dealname"), owner_deal, rappel))

        # 5. Étape
        if deal and cible:
            hs.req("PATCH", "/crm/v3/objects/deals/%s" % did, {"properties": {"pipeline": PIPELINE, "dealstage": cible}})
            relu = hs.req("GET", "/crm/v3/objects/deals/%s?properties=dealstage" % did)["properties"]
            if relu.get("dealstage") != cible:
                ecarts.append("étape non prise : relu « %s »" % _nom_etape(relu.get("dealstage")))
        if geste_etape:
            journal.append(geste_etape)
        if len(tous) > 1:
            journal.append("%d devis sur la fiche, le plus élevé retenu (%.0f € TTC)" % (len(tous), ttc))
        if schema.vides:
            journal.append("laissé vide (information manquante) : " + ", ".join(schema.vides))
        if refus:
            ecarts.append("non écrit (format) : " + " ; ".join(refus))

        texte = "transaction %s (%s) — %s" % (did, motif_d if deal else "nouvelle", " ; ".join(journal))
        if ecarts:
            return False, "%s ⚠ %s" % (texte, " ; ".join(ecarts))
        return True, texte
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


# --- Lecture : les transactions sous la forme d'une opportunité noCRM ------------------------
#
# Les outils de lecture (relances, gros dossiers, groupage, reporting, inventaire) savent lire
# une opportunité noCRM : `title`, `status`, `amount` TTC, `description` (en-tête contact,
# « --- », puis la fiche), `remind_date`, `updated_at`… Plutôt que de réécrire chacun, on leur
# rend une transaction HubSpot sous cette forme. Les règles métier de chaque outil ne bougent pas.

PORTAIL = "149055515"
URL_DEAL = "https://app-eu1.hubspot.com/contacts/%s/record/0-3/%%s" % PORTAIL
ETAPE_RELANCE = "5973046476"
COLONNES = {                                    # colonnes noCRM -> étapes HubSpot
    "devis_envoye": (ETAPE_DEVIS_ENVOYE, ETAPE_RELANCE),
    "axe_paris": (ETAPE_GROUPAGE,),
    "visites": (ETAPE_QUALIF,),
}
STATUT = {"closedwon": "won", "closedlost": "lost"}
TAG_AXE = {v: k for k, v in AXE.items()}
PROPS_LECTURE = ["dealname", "dealstage", "amount", "sd_total_ttc", "sd_axe_groupage", "createdate",
                 "closedate", "hs_lastmodifieddate", "hubspot_owner_id", "date_demenagement",
                 "lien_fiche_notion", "sd_volume_m3", "id_nocrm", "notes_last_updated",
                 "derniere_activite_nocrm", "hs_v2_date_entered_current_stage"]
# Jour de l'import noCRM -> HubSpot : chaque transaction y a été posée dans son étape.
# Une entrée d'étape ce jour-là ne dit rien de l'activité du dossier.
JOURS_IMPORT = ("2026-10-05",)


def derniere_activite(p):
    """Équivalent de `updated_at` noCRM : dernière activité réelle du dossier.

    max(dernière note/tâche/appel, dernière activité noCRM reprise, entrée dans l'étape
    actuelle hors jour d'import). Jamais `hs_lastmodifieddate` : toute opération en masse sur
    le portail (import du 05/10, reprise du 06/10) la remet à la date du jour."""
    dates = [p.get("notes_last_updated"), p.get("derniere_activite_nocrm")]
    etape = p.get("hs_v2_date_entered_current_stage") or ""
    if etape[:10] not in JOURS_IMPORT:
        dates.append(etape)
    dates = [d for d in dates if d]
    return max(dates) if dates else p.get("createdate")


def url_lead(id_):
    return URL_DEAL % id_


def texte_note(body):
    """Corps HTML d'une note -> texte, sans son titre en gras."""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", body or "")
    s = re.sub(r"(?is)^\s*<p>\s*<strong>[^<]*</strong>\s*</p>", "", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    lignes = [l.rstrip() for l in s.strip().splitlines()]
    if lignes and lignes[0].strip() in (TITRE_NOTE, ANCIEN_TITRE_NOTE):     # HubSpot réécrit le HTML : le titre survit au motif
        lignes = lignes[1:]
    return "\n".join(lignes).strip()


def _assoc_lot(hs, de, vers, ids):
    """{id: [ids associés]} en un appel par tranche de 100."""
    out = {}
    ids = [str(i) for i in ids]
    for k in range(0, len(ids), 100):
        r = hs.req("POST", "/crm/v4/associations/%s/%s/batch/read" % (de, vers),
                   {"inputs": [{"id": i} for i in ids[k:k + 100]]})
        for x in r.get("results", []):
            out[str(x["from"]["id"])] = [str(t["toObjectId"]) for t in x.get("to", [])]
    return out


def _lire_tout(hs, objet, ids, props):
    res = []
    ids = list(dict.fromkeys(str(i) for i in ids))
    for k in range(0, len(ids), 100):
        res += hs.lire_lot(objet, ids[k:k + 100], props)
    return {r["id"]: r for r in res}


def leads_compatibles(hs, deals, description=True, rappels=True):
    """Transactions HubSpot -> dicts au format des opportunités noCRM."""
    ids = [d["id"] for d in deals]
    contacts, notes, taches = {}, {}, {}
    if description and ids:
        d2c = _assoc_lot(hs, "deals", "contacts", ids)
        lus = _lire_tout(hs, "contacts", [c for v in d2c.values() for c in v[:1]], PROPS_CONTACT)
        contacts = {d: lus.get(v[0]) for d, v in d2c.items() if v}
        d2n = _assoc_lot(hs, "deals", "notes", ids)
        corps = _lire_tout(hs, "notes", [n for v in d2n.values() for n in v], ["hs_note_body", "hs_timestamp"])
        notes = {d: [corps[n] for n in v if n in corps] for d, v in d2n.items()}
    if rappels and ids:
        d2t = _assoc_lot(hs, "deals", "tasks", ids)
        lues = _lire_tout(hs, "tasks", [t for v in d2t.values() for t in v],
                          ["hs_task_status", "hs_timestamp", "hs_task_subject"])
        taches = {d: [lues[t] for t in v if t in lues] for d, v in d2t.items()}
    sortie = []
    for d in deals:
        p = d["properties"]
        c = (contacts.get(d["id"]) or {}).get("properties") or {}
        fiche = next((texte_note(n["properties"].get("hs_note_body"))
                      for n in notes_fiche(notes.get(d["id"], []))), "")
        autres = [texte_note(n["properties"].get("hs_note_body")) for n in notes.get(d["id"], [])
                  if not est_note_fiche(n["properties"].get("hs_note_body"))]
        entete = ["Prénom : %s" % c["firstname"] if c.get("firstname") else None,
                  "Nom : %s" % c["lastname"] if c.get("lastname") else None,
                  "Téléphone : %s" % (c.get("phone") or c.get("mobilephone"))
                  if c.get("phone") or c.get("mobilephone") else None,
                  "E-mail : %s" % c["email"] if c.get("email") else None,
                  # HubSpot fait foi (D7) : la date de la transaction passe devant le texte de la fiche
                  "Date souhaitée : %s" % "/".join(reversed(p["date_demenagement"][:10].split("-")))
                  if p.get("date_demenagement") else None]
        desc = "\n".join([l for l in entete if l] + ["---", fiche] + autres).strip()
        ouvertes = sorted((t["properties"].get("hs_timestamp") or "")[:10] for t in taches.get(d["id"], [])
                          if t["properties"].get("hs_task_status") != "COMPLETED"
                          and t["properties"].get("hs_timestamp"))
        ttc = _nombre(p.get("sd_total_ttc"))
        if ttc is None and _nombre(p.get("amount")) is not None:
            ttc = round(_nombre(p["amount"]) * 1.2, 2)     # amount est HT (D1), noCRM parlait TTC
        etape = p.get("dealstage")
        sortie.append({
            "id": d["id"], "crm": "hubspot", "url": url_lead(d["id"]),
            "title": p.get("dealname") or "", "step_id": etape, "step": _nom_etape(etape),
            "status": STATUT.get(etape, "todo"), "amount": ttc,
            "description": desc, "remind_date": ouvertes[0] if ouvertes else None,
            "created_at": p.get("createdate"), "updated_at": derniere_activite(p),
            "closed_at": p.get("closedate") if etape in ETAPES_CLOSES else None,
            "tags": [TAG_AXE[p["sd_axe_groupage"]]] if p.get("sd_axe_groupage") in TAG_AXE else [],
            "user_id": p.get("hubspot_owner_id"), "date_demenagement": p.get("date_demenagement"),
            "lien_fiche_notion": p.get("lien_fiche_notion"), "id_nocrm": p.get("id_nocrm"),
            "contact": {"prenom": c.get("firstname"), "nom": c.get("lastname"),
                        "tel": c.get("phone") or c.get("mobilephone"), "email": c.get("email")},
        })
    return sortie


def _chercher_tout(hs, groupes, props):
    res, apres = [], None
    while True:
        corps = {"filterGroups": groupes, "properties": props, "limit": 100}
        if apres:
            corps["after"] = apres
        r = hs.req("POST", "/crm/v3/objects/deals/search", corps)
        res += r.get("results", [])
        apres = (r.get("paging") or {}).get("next", {}).get("after")
        if not apres or len(res) >= 9900:       # la recherche HubSpot plafonne à 10 000
            return res


def _hs():
    cle = charger_cle()
    if not cle:
        raise RuntimeError("clé HubSpot absente (%s)" % ENV)
    return HubSpot(cle)


def leads(colonnes=("devis_envoye", "axe_paris"), statut=None, axe=False, description=True, hs=None):
    """Transactions des colonnes demandées. `statut="won"` + `axe=True` : les signées de l'axe
    Paris (le groupage les lit ainsi : dans HubSpot, une transaction signée quitte sa colonne)."""
    hs = hs or _hs()
    if statut == "won":
        filtres = [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]
        if axe:
            filtres.append({"propertyName": "sd_axe_groupage", "operator": "IN",
                            "values": list(TAG_AXE)})
    else:
        etapes = [e for c in colonnes for e in COLONNES[c]]
        filtres = [{"propertyName": "dealstage", "operator": "IN", "values": etapes}]
    filtres.append({"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE})
    return leads_compatibles(hs, _chercher_tout(hs, [{"filters": filtres}], PROPS_LECTURE), description)


def leads_depuis(jour, hs=None, description=False):
    """Toutes les transactions créées ou modifiées depuis `jour` (reporting)."""
    hs = hs or _hs()
    groupes = [{"filters": [{"propertyName": p, "operator": "GTE", "value": jour + "T00:00:00Z"},
                            {"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE}]}
               for p in ("createdate", "hs_lastmodifieddate")]
    vus = {d["id"]: d for d in _chercher_tout(hs, groupes, PROPS_LECTURE)}
    return leads_compatibles(hs, list(vus.values()), description, rappels=False)


def historique_etapes(deal_id, hs=None):
    """[(horodatage ISO, libellé d'étape)] dans l'ordre chronologique."""
    hs = hs or _hs()
    r = hs.req("GET", "/crm/v3/objects/deals/%s?propertiesWithHistory=dealstage" % deal_id)
    return sorted((h["timestamp"], _nom_etape(h["value"]))
                  for h in (r.get("propertiesWithHistory") or {}).get("dealstage", []))


def chercher_lead(nom=None, prenom=None, tel=None, email=None, hs=None, **_):
    """Même retour que nocrm.chercher_lead : (lead|None, candidats, balayés, rang).
    Rang 3 téléphone, 2 e-mail, 1 nom (jamais suffisant pour écrire)."""
    hs = hs or _hs()
    contact, motif, ambigu = trouver_contact(hs, tel, email) if (tel or email) else (None, "", False)
    if contact:
        rang = 3 if motif == "téléphone" else 2
        ids = hs.associes("contacts", contact["id"], "deals")
        deals = sorted(hs.lire_lot("deals", ids, PROPS_LECTURE),
                       key=lambda d: d["properties"].get("hs_lastmodifieddate") or "", reverse=True)
        ouvertes = _ouvertes(deals) or deals
        cands = leads_compatibles(hs, ouvertes[:5])
        if len(_ouvertes(deals)) > 1:
            return None, cands, len(deals), rang
        return (cands[0] if cands else None), cands, len(deals), rang
    mots = [m for m in re.split(r"\s+", "%s %s" % (nom or "", prenom or "")) if len(m) > 1]
    if not mots:
        return None, [], 0, 0
    trouves = hs.chercher("deals", [{"filters": [
        {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": m} for m in mots]}],
        PROPS_LECTURE, limite=10)
    cands = leads_compatibles(hs, trouves)
    return (cands[0] if len(cands) == 1 else None), cands, len(trouves), (1 if cands else 0)


def pieces_jointes(deal_id, hs=None):
    """[{id, name, url}] : fichiers joints aux notes de la transaction."""
    hs = hs or _hs()
    notes = hs.lire_lot("notes", hs.associes("deals", deal_id, "notes"), ["hs_attachment_ids"])
    ids = [i for n in notes for i in (n["properties"].get("hs_attachment_ids") or "").split(";") if i]
    sortie = []
    for i in ids:
        f = hs.req("GET", "/files/v3/files/%s" % i)
        nom_f = f.get("name") or str(i)
        if f.get("extension") and not nom_f.lower().endswith("." + f["extension"].lower()):
            nom_f += "." + f["extension"]
        sortie.append({"id": i, "name": nom_f})
    return sortie


def notes_libres(deal_id, hs=None):
    """Texte des notes saisies sur la transaction, hors note « Fiche client (Notion) »
    (équivalent de l'en-tête d'une description noCRM, au-dessus du « --- »)."""
    hs = hs or _hs()
    notes = hs.lire_lot("notes", hs.associes("deals", deal_id, "notes"), ["hs_note_body"])
    return "\n".join(texte_note(n["properties"].get("hs_note_body")) for n in notes
                     if not est_note_fiche(n["properties"].get("hs_note_body")))


def url_piece(file_id, hs=None):
    hs = hs or _hs()
    return hs.req("GET", "/files/v3/files/%s/signed-url" % file_id).get("url")


def ajouter_note(deal_id, texte, titre=None, hs=None):
    """Rend (statut, détail) — « fait », « deja » ou « echec ». Jamais de doublon."""
    try:
        hs = hs or HubSpot(charger_cle(), ecrire=True)
        notes = hs.lire_lot("notes", hs.associes("deals", deal_id, "notes"), ["hs_note_body"])
        plat = lambda s: re.sub(r"\s+", " ", texte_note(s)).strip().lower()  # noqa: E731
        if any(plat(texte) in plat(n["properties"].get("hs_note_body")) for n in notes):
            return "deja", "note identique déjà présente"
        body = note_html(titre, texte) if titre else "<p>%s</p>" % "<br>".join(
            html.escape(l) for l in texte.splitlines())
        maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        hs.req("POST", "/crm/v3/objects/notes", {
            "properties": {"hs_note_body": body, "hs_timestamp": maintenant},
            "associations": [{"to": {"id": str(deal_id)}, "types": [
                {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_DEAL}]}]})
        return "fait", "note inscrite sur la transaction %s" % deal_id
    except Exception as e:
        return "echec", "HubSpot a refusé la note : %s" % e


DOSSIER_INVENTAIRES = "/Inventaires clients"
DOSSIER_DEVIS = "/Devis clients"


def joindre_pdf(page_id, chemin, titre, tel=None, email=None, hs=None, dossier=DOSSIER_INVENTAIRES):
    """Joint un PDF à la transaction de la fiche, dans une note intitulée `titre`.

    Transaction retrouvée comme à la finalisation (lien de la fiche Notion, puis contact). `dossier` :
    gestionnaire de fichiers de HubSpot. Rend (statut, détail) — « fait », « deja » (même fichier déjà
    joint) ou « echec ». Ne lève jamais : le PDF reste en local, l'import se rejoue."""
    try:
        hs = hs or HubSpot(charger_cle(), ecrire=True)
        contact = None
        if tel or email:
            contact, motif, ambigu = trouver_contact(hs, tel, email)
            if ambigu:
                contact = None
        deal, motif, ambigu = trouver_transaction(hs, (page_id or "").replace("-", ""), None, contact)
        if ambigu or not deal:
            return "echec", "transaction introuvable ou ambiguë (%s) — PDF non joint" % motif
        nom = os.path.basename(chemin)
        notes = hs.lire_lot("notes", hs.associes("deals", deal["id"], "notes"), ["hs_note_body"])
        if any(html.escape(nom) in (n["properties"].get("hs_note_body") or "") for n in notes):
            return "deja", "%s déjà joint à la transaction %s" % (nom, deal["id"])
        fichier_id = hs.deposer_fichier(chemin, dossier)
        maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        hs.req("POST", "/crm/v3/objects/notes", {
            "properties": {"hs_note_body": note_html(titre, "Pièce jointe : %s" % nom),
                           "hs_timestamp": maintenant, "hs_attachment_ids": str(fichier_id)},
            "associations": [{"to": {"id": deal["id"]}, "types": [
                {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_DEAL}]}]})
        return "fait", "joint à la transaction %s « %s »" % (deal["id"], deal["properties"].get("dealname"))
    except Exception as e:
        return "echec", "%s: %s" % (type(e).__name__, e)


def description(nom):
    """Ce que le CRM sait d'un client sans fiche Notion (équivalent de nocrm.py --description)."""
    n, p = nocrm.separer_nom(nom)
    lead, cands, _, _ = chercher_lead(n, p)
    return [(c["title"], c["url"], c["description"]) for c in ([lead] if lead else cands)]


# --- CLI -----------------------------------------------------------------------------------

def _test():
    cle = charger_cle()
    if not cle:
        sys.exit("Clé absente : %s" % ENV)
    hs = HubSpot(cle)
    schema = Schema(hs)
    pipe = hs.req("GET", "/crm/v3/pipelines/deals/%s" % PIPELINE)
    ids = {s["id"]: s["label"] for s in pipe["stages"]}
    for e in (ETAPE_QUALIF, ETAPE_REVISION, ETAPE_DEVIS_ENVOYE, ETAPE_GROUPAGE) + ETAPES_CLOSES:
        print("%-12s %s" % (e, ids.get(e, "⚠ ABSENTE du pipeline")))
    essai = proprietes_chiffrage({"ex": {"ascDepart": False, "mmDepart": "2h", "ascArrivee": True,
                                         "mmArrivee": ""}, "mission": {"volume": 1}}, {})
    manquantes = [k for k in essai if k not in schema.props["deals"]]
    print("Propriétés du mapping absentes du portail : %s" % (manquantes or "aucune"))


def main():
    ap = argparse.ArgumentParser(description="Chaîne devis → HubSpot")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--export", help="JSON exporté par le calculateur")
    ap.add_argument("--fiche", action="store_true", help="fiche seule (sans devis)")
    ap.add_argument("--page-id")
    ap.add_argument("--description", metavar="NOM", help="ce que HubSpot sait d'un client (lecture)")
    ap.add_argument("--joindre-pdf", metavar="FICHIER", help="joint un PDF à la transaction de --page-id")
    ap.add_argument("--appliquer", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.test:
        return _test()
    if a.description:
        for titre, url, desc in description(a.description) or [("aucune transaction trouvée", "", "")]:
            print("== %s %s\n%s\n" % (titre, url, desc))
        return 0
    if a.joindre_pdf:
        if not a.page_id:
            ap.error("--joindre-pdf demande --page-id")
        statut, detail = joindre_pdf(a.page_id, a.joindre_pdf, "Inventaire de déménagement")
        print("HubSpot : %s — %s" % (statut, detail))
        return 0 if statut != "echec" else 1
    import fiche_notion as fn
    import finalisation as fz
    token = fn._token()
    if a.export:
        ex = fz.charger(a.export)
        tps = fz.temps_fiche(ex)
        pid = a.page_id or (ex.get("fiche") or {}).get("page_id")
        lg = fz.ligne_archive(ex, tps, pid, token)
        ok, msg = avancer_dossier(lg, appliquer=a.appliquer, page_id=pid, token=token, ex=ex)
    elif a.fiche and a.page_id:
        lg = fz.ligne_archive({}, {}, a.page_id, token)
        lg["ref"] = (lg.get("ref") or "").split(" · ")[0]
        ok, msg = avancer_dossier(lg, appliquer=a.appliquer, page_id=a.page_id, token=token)
    else:
        ap.error("--test, --export FICHIER ou --fiche --page-id ID")
    print("HubSpot : %s%s" % ("" if ok else "ÉCHEC — ", msg))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
