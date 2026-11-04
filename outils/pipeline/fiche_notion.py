#!/usr/bin/env python3
"""
Lecture d'une fiche client Notion -> dossier.json, sans passer par le modele.

La fiche est un modele duplique : sa trame est fixe (### Depart :, "Etage avec ascenseur : 3",
cases - [x]). Elle est donc parsable. Ce script lit la page en HTTP direct (meme token que
export.py), parse le corps ET les proprietes, et rend le dossier.json attendu par pipeline.py.

Principe : LE CORPS FAIT FOI. Les proprietes ne servent que de repli quand le corps est muet,
et de controle : toute divergence corps/propriete est signalee dans _meta.divergences.
Raison : la saisie se fait dans le texte libre, la propriete n'est pas toujours reportee
(audit 08/09/2026 : 40 fiches sur 200 avec "Volume (m3)" vide et un volume dans le corps).

Aucune valeur n'est inventee : un champ illisible vaut null et alimente les manquants.

Usage :
    python fiche_notion.py "PLANCHAIS Benoit"          # dossier.json sur stdout
    python fiche_notion.py --page-id 3d4232705122817f810fdb8ec066dae3
    python fiche_notion.py --url https://www.notion.so/...-3d42327051228...
    python fiche_notion.py "PLANCHAIS" --texte         # corps normalise (debug)
    python fiche_notion.py --audit 200                 # corps vs proprietes sur N fiches
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.join(ICI, "itineraire"))
import export                                     # noqa: E402  (config + token Notion)
from calcul_itineraire import (SEUIL_SANS_PEAGE_H,      # noqa: E402  seuils metier, une seule source
                               SEUIL_LONGUE_DISTANCE_H)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


# --- Acces Notion ------------------------------------------------------------

def _entetes(token):
    return {"Authorization": "Bearer " + token, "Notion-Version": VERSION,
            "Content-Type": "application/json"}


def _appel(url, token, payload=None):
    donnees = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=donnees, headers=_entetes(token),
                                 method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _token():
    conf = export.config()
    token = conf.get("NOTION_TOKEN")
    # Notion ne sert plus qu'aux anciens dossiers, en lecture : sans jeton, la chaîne tourne sur HubSpot seul.
    return None if not token or "REMPLACER" in token else token


_ID_EN_FIN = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                        r"|[0-9a-fA-F]{32})$")


def est_transaction(id_):
    """Identifiant de transaction HubSpot (que des chiffres), et non de page Notion (Karim, 03/11/2026)."""
    return bool(re.fullmatch(r"\d{6,}", str(id_ or "").strip()))


def id_depuis_url(url):
    """Id Notion d'une URL : les 32 derniers hex du chemin, ou un UUID a tirets en fin de chemin.

    Ancre en fin, jamais apres retrait des tirets : « VIGNERON-Lucile-3d52…62eb » donnait
    « e3d52…62e » (le « e » de Lucile pris pour de l'hex), et « ?v= » porte l'id de la VUE.
    """
    chemin = re.split(r"[?#]", (url or "").strip(), maxsplit=1)[0].rstrip("/")
    m = _ID_EN_FIN.search(chemin)
    return m.group(1).replace("-", "").lower() if m else None


def chercher_fiche(nom, token, base=None):
    """Cherche une fiche par son titre. Rend (page_id, titre) ou leve une erreur lisible.

    La note HubSpot d'abord ; la base Notion ne sert plus qu'aux anciens dossiers."""
    if not base:
        import fiche_hubspot
        try:
            trouve = fiche_hubspot.chercher(nom)
        except Exception as e:      # HubSpot injoignable : un ancien dossier reste lisible
            print("HubSpot non interrogé (%s: %s)." % (type(e).__name__, e))
            trouve = None
        if trouve:
            return trouve
    if not token:
        raise SystemExit("Aucune fiche trouvée pour %r." % nom)
    base = base or export.BASE_FICHES_CLIENT
    rep = _appel("%s/databases/%s/query" % (API, base), token,
                 {"filter": {"property": "Nom client", "title": {"contains": nom}},
                  "page_size": 20,
                  "sorts": [{"timestamp": "created_time", "direction": "descending"}]})
    res = rep.get("results", [])
    if not res:
        raise SystemExit("Aucune fiche trouvée pour %r." % nom)
    titres = [(p["id"], _texte(p["properties"]["Nom client"]["title"])) for p in res]
    if len(titres) > 1:
        exact = [t for t in titres if t[1].lower().startswith(nom.lower())]
        if len(exact) == 1:
            return exact[0]
        listing = "\n".join("  %s — %s" % (t[1], t[0].replace("-", "")) for t in titres)
        raise SystemExit("%d fiches correspondent à %r :\n%s\n"
                         "Relancer avec --page-id." % (len(titres), nom, listing))
    return titres[0]


def _texte(rich):
    return "".join(x.get("plain_text", "") for x in (rich or []))


def lire_corps(page_id, token):
    """Rend le corps de la page en lignes normalisees (markdown minimal, cases explicites)."""
    if est_transaction(page_id):
        import fiche_hubspot
        return fiche_hubspot.lire_lignes(page_id)
    lignes = []

    def descendre(bloc_id, profondeur=0):
        curseur = None
        while True:
            url = "%s/blocks/%s/children?page_size=100" % (API, bloc_id)
            if curseur:
                url += "&start_cursor=" + curseur
            rep = _appel(url, token)
            for b in rep.get("results", []):
                type_ = b["type"]
                contenu = b.get(type_, {})
                texte = _texte(contenu.get("rich_text"))
                if type_ == "to_do":
                    prefixe = "- [x] " if contenu.get("checked") else "- [ ] "
                elif type_ in ("heading_1", "heading_2", "heading_3"):
                    prefixe = "### "
                elif type_ in ("bulleted_list_item", "numbered_list_item"):
                    prefixe = "- "
                elif type_ in ("paragraph", "quote", "callout", "toggle"):
                    prefixe = ""
                else:
                    prefixe = ""
                    texte = texte or "[%s]" % type_
                # Un bloc Notion peut contenir plusieurs lignes visuelles separees par des
                # sauts de ligne internes (Maj+Entree) : « Distance de portage :\nEntrée…
                # \nIntérieur… » est UN bloc. Sans ce decoupage, les trois lignes n'en font
                # qu'une et les valeurs qui suivent le premier « : » sont perdues.
                sous_lignes = texte.split("\n") or [""]
                for i, sous in enumerate(sous_lignes):
                    lignes.append("  " * profondeur + (prefixe if i == 0 else "") + sous)
                if b.get("has_children") and type_ != "child_database":
                    descendre(b["id"], profondeur + 1)
            if not rep.get("has_more"):
                break
            curseur = rep["next_cursor"]

    descendre(page_id)
    return lignes


# --- Petits analyseurs -------------------------------------------------------

def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def _nombres(s):
    """Tous les nombres d'une chaine, virgule decimale comprise."""
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", s)]


def _premier_nombre(s):
    n = _nombres(s)
    return n[0] if n else None


def nb_heures(s):
    """'4h30' -> 4.5 · '4h' -> 4.0 · '0h30' -> 0.5 · '0,5h' -> 0.5 · '2,25 heures' -> 2.25
    · '45 min' -> 0.75 · '' -> None. Une decimale avant le « h » exclut des minutes apres."""
    if not s:
        return None
    s = s.strip()
    m = re.search(r"(\d+)(?:[.,](\d+))?\s*h(?:eures?|rs?)?(?![^\W\d_])\s*(\d+)?", s, re.I)
    if m:
        if m.group(2):
            return float(m.group(1) + "." + m.group(2))
        return int(m.group(1)) + (int(m.group(3)) / 60.0 if m.group(3) else 0.0)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:min|mn|m\b)", s, re.I)
    if m:
        return float(m.group(1).replace(",", ".")) / 60.0
    return None


def nb_etage(s):
    """'RDC (plain-pied)' -> 0 · 'R+1' -> 1 · '2 (duplex)' -> 2 · '' -> None."""
    if s is None:
        return None
    brut = _sans_accents(s).strip()
    if not brut:
        return None
    m = re.match(r"\s*r\s*\+\s*(\d+)", brut)
    if m:
        return int(m.group(1))
    if re.match(r"\s*(rdc|rez|plain[- ]?pied|0\b)", brut):
        return 0
    m = re.search(r"\d+", brut)
    return int(m.group(0)) if m else None


_VOLUME = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*(?:3|³)", re.I)


def _lire_volume(texte):
    """Rend (volume, alerte). Un volume composite n'est jamais reduit a son premier nombre.

    « 7 m3 (mission directe) + 40 m3 (garde-meuble) = 47 m3 total » vaut 47, pas 7.
    Plusieurs volumes sans mention de total : on ne tranche pas, on rend None et on le dit.
    """
    trouves = [(m.start(), float(m.group(1).replace(",", "."))) for m in _VOLUME.finditer(texte)]
    if not trouves:
        return None, None
    if len(trouves) == 1:
        return trouves[0][1], None
    nu = _sans_accents(texte)
    reperes = [m.start() for m in re.finditer(r"total|=", nu)]
    if reperes:
        # le volume total est celui dont la position est la plus proche du mot « total »
        pos, valeur = min(trouves, key=lambda t: min(abs(t[0] - r) for r in reperes))
        return valeur, ("Volume composite dans la fiche (%s m³) — total retenu : %s m³."
                        % (" + ".join(str(v) for _, v in trouves), valeur))
    return None, ("Volume composite non tranché (%s m³) : aucun total indiqué dans la fiche."
                  % " / ".join(str(v) for _, v in trouves))


def _valeur_apres(ligne):
    """Partie a droite du premier ':'."""
    return ligne.split(":", 1)[1].strip() if ":" in ligne else ""


def _coche(ligne):
    return ligne.lstrip().startswith("- [x]")


def _libelle_case(ligne):
    return re.sub(r"^\s*-\s*\[[ x]\]\s*", "", ligne)


# --- Decoupage en sections ---------------------------------------------------

# Le corps suit toujours la meme trame. On la decoupe sur les titres pour qu'une phrase
# des Notes ("Depart : stationnement facile") ne soit jamais lue comme l'adresse de depart.
SECTIONS = [
    ("entete", None),
    ("offre", r"details? offre"),
    ("depart", r"^depart\b"),
    ("arrivee", r"^arrivee\b"),
    # « ### Étape : », « ### Étape 2 (dépose du lit) : »… — une section par arret, dans l'ordre
    # du trajet. Les titres restent dans la liste : c'est eux qui separent deux etapes.
    ("etape", r"^(etape|point [23])\b"),
    # « ### Relivraison : » — seconde operation du meme devis (sortie de garde-meuble, un autre
    # jour). Meme trame qu'un lieu pour l'adresse de relivraison (Karim, 14/10/2026).
    ("relivraison", r"^re-?livraison\b"),
    ("demontage", r"meubles? a demonter"),
    ("cartons", r"mise en cartons?"),
    ("materiel", r"materiel a livrer"),
    ("lourds", r"meubles? lourds?"),
    ("itineraire", r"itineraires?"),
]


def decouper(lignes):
    """Rend {nom_section: [lignes]}. La queue (Notes, chiffrage) va dans 'fin'."""
    sections = {nom: [] for nom, _ in SECTIONS}
    sections["fin"] = []
    courante = "entete"
    for ligne in lignes:
        if ligne.startswith("###"):
            titre = _sans_accents(ligne.lstrip("# ").strip())
            trouve = None
            for nom, motif in SECTIONS:
                if motif and re.search(motif, titre):
                    trouve = nom
                    break
            if trouve:
                courante = trouve
                sections[courante].append(ligne)
                continue
            courante = "fin"                      # titre hors trame : queue de fiche
        sections[courante].append(ligne)
    # Tout ce qui suit la section itineraire appartient a la queue (Notes, chiffrage).
    if sections["itineraire"]:
        garde, queue = [], []
        for ligne in sections["itineraire"]:
            cible = garde if not queue and not re.match(r"^\s*\[?divider|^Cr[ée]neaux", ligne) else queue
            cible.append(ligne)
        sections["itineraire"] = garde
        sections["fin"] = queue + sections["fin"]
    return sections


# --- Parsing du corps --------------------------------------------------------

FORMULES = {"standard": "Standard", "confort": "Confort",
            "premium": "Premium", "prestige": "Prestige"}

MATERIEL = [                                      # (motif dans le libelle, cle calculateur)
    (r"standards?", "standard"), (r"livres", "livres"), (r"vaisselle", "vaisselle"),
    (r"bouteilles", "bouteilles"), (r"penderies", "penderies"),
    (r"informatiques?", "informatiques"), (r"tableaux", "tableaux"),
    (r"scotch", "scotch"), (r"bulles", "bulles"),
    (r"barrel verres", "barrelVerres"), (r"barrel assiettes", "barrelAssiettes"),
    (r"kraft", "kraft"),
]

MOTS_SIGNAUX = [
    ("groupage", r"\bgroupage\b"),
    ("garde-meuble / étape", r"garde[- ]meuble|garde meuble|box de stockage|locabox|stockage interm"),
    ("monte-meuble", r"monte[- ](?:meuble|charge)"),
    ("déchetterie", r"dechetterie|encombrants|debarras"),
    ("piano", r"\bpiano\b"),
    ("week-end", r"week[- ]?end|samedi|dimanche"),
    ("Nextories", r"next\s?stories|nextories"),
    ("chargement ou déchargement seul (--chargement-seul / --dechargement-seul)",
     r"\b(?:de)?chargement seul|\b(?:que|uniquement) (?:le )?(?:de)?chargement\b"),
]


def _parse_adresse_zone(lignes, mot):
    """Adresse lue dans l'entete uniquement (jamais dans les Notes)."""
    motif = re.compile(r"^\s*%s\s*:" % mot, re.I)
    for ligne in lignes:
        if ligne.startswith("###"):
            continue
        if motif.match(_sans_accents(ligne).replace("depart", "depart")):
            valeur = _valeur_apres(ligne)
            if valeur:
                return valeur
    return None


def _parse_lieu(lignes):
    """Section Depart ou Arrivee -> dict du contrat dossier.json."""
    lieu = {"adresse_brute": None, "type_logement": None, "etage": None,
            "ascenseur": None, "ascenseur_petit": None, "rdc": False,
            "duplex": False, "portage_m": None, "monte_meuble": None}
    alertes = []
    portages, portage_total = [], None

    for ligne in lignes:
        nu = _sans_accents(ligne)
        if "duplex" in nu:                         # peut figurer sur l'étage OU le logement
            lieu["duplex"] = True
        if _coche(ligne):
            lib = _sans_accents(_libelle_case(ligne))
            if lib.startswith("maison"):
                lieu["type_logement"] = "maison"
            elif lib.startswith("appartement"):
                lieu["type_logement"] = "appartement"
            elif lib.startswith("rdc"):
                lieu["rdc"] = True
            elif lib.startswith("grand"):
                lieu["ascenseur"], lieu["ascenseur_petit"] = True, False
            elif lib.startswith("petit"):
                lieu["ascenseur"], lieu["ascenseur_petit"] = True, True
            continue

        if "etage avec ascenseur" in nu:
            lieu["ascenseur"] = True
            etage = nb_etage(_valeur_apres(ligne))
            if etage is not None:
                lieu["etage"] = etage
        elif "etage sans ascenseur" in nu:
            valeur = _valeur_apres(ligne)
            etage = nb_etage(valeur)
            if lieu["ascenseur"] is None:          # duplex : les deux lignes coexistent
                lieu["ascenseur"] = False
                if etage is not None:
                    lieu["etage"] = etage
        elif "monte-meuble" in nu or "monte meuble" in nu or "monte-charge" in nu:
            lieu["monte_meuble"] = "2h" if re.search(r"\b2\s*h", nu) else (
                "demi" if "demi" in nu else None)
        elif re.search(r"^\s*-?\s*(entree|interieur)\s*\(", nu):
            valeur = _valeur_apres(ligne)
            if "portage total" in _sans_accents(valeur):
                nombres = _nombres(valeur)
                if nombres:
                    portage_total = max(portage_total or 0, max(nombres))
            else:
                nombres = _nombres(valeur)
                portages.append(max(nombres) if nombres else None)
            if "🟡" in valeur:
                alertes.append(ligne.strip())
        elif nu.startswith("distance de portage") and _valeur_apres(ligne):
            nombres = _nombres(_valeur_apres(ligne))
            if nombres:
                portage_total = max(portage_total or 0, max(nombres))
        elif "🟡" in ligne:
            alertes.append(ligne.strip())

    if portage_total is not None:
        lieu["portage_m"] = portage_total          # deja un total : ne jamais additionner
    else:
        connus = [p for p in portages if p is not None]
        if connus:
            lieu["portage_m"] = sum(connus)
    if lieu["duplex"]:
        lieu["type_logement"] = lieu["type_logement"] or "appartement"

    # Un box / garde-meuble n'a pas de case « Maison / Appartement » a cocher : sans cette
    # regle, la section reste vide et le pipeline relance le client pour un etage qui n'existe
    # pas. Le depot Sam'Demenage de Saint-Loubes est en outre plain-pied par defaut (skill §2).
    if lieu["type_logement"] is None:
        texte = _sans_accents(" ".join(lignes))
        if re.search(r"garde[- ]meuble|box\b|depot|stockage|local ?box", texte):
            lieu["type_logement"] = "garde-meuble"
            if "saint-loubes" in texte or "saint loubes" in texte:
                lieu["rdc"], lieu["etage"] = True, 0
                lieu["ascenseur"] = False if lieu["ascenseur"] is None else lieu["ascenseur"]
    return lieu, alertes


def parser_relivraison(lignes):
    """Section « ### Relivraison » -> (dict, alertes).

    Le lieu de relivraison suit la trame d'un lieu (type coche, etage, ascenseur, portage) ;
    s'y ajoutent l'adresse, l'origine (garde-meuble de Saint-Loubes par defaut), le volume
    relivre (vide = volume depose) et, s'ils sont ecrits, les km / temps A/R du jour.
    """
    bloc = [l for l in lignes if not l.startswith("###")]
    origine = None
    lieu_lignes = []
    for ligne in bloc:
        if re.match(r"^\s*(depart|origine|depuis)\b", _sans_accents(ligne)):
            origine = _valeur_apres(ligne) or None     # hors lieu : « garde-meuble » y ferait
            continue                                    # lire l'arrivee comme un box
        lieu_lignes.append(ligne)
    lieu, alertes = _parse_lieu(lieu_lignes)
    reliv = {"origine": origine, "arrivee": lieu, "volume_m3": None,
             "km_ar": None, "heures_conduite_ar": None, "date": None}
    for ligne in lieu_lignes:
        nu = _sans_accents(ligne)
        if nu.startswith("adresse"):
            lieu["adresse_brute"] = _valeur_apres(ligne) or None
        elif nu.startswith("volume"):
            reliv["volume_m3"], _ = _lire_volume(_valeur_apres(ligne))
        elif nu.startswith("kilometres a/r"):
            reliv["km_ar"] = _premier_nombre(_valeur_apres(ligne))
        elif nu.startswith("temps a/r"):
            reliv["heures_conduite_ar"] = nb_heures(_valeur_apres(ligne))
        elif nu.startswith("date"):
            reliv["date"] = _valeur_apres(ligne) or None
    if not lieu["adresse_brute"]:
        alertes.append("adresse de relivraison absente : trajet du jour non calculé.")
    if lieu["etage"] is None and not lieu["rdc"]:
        alertes.append("étage de relivraison absent : RDC retenu.")
    return reliv, alertes


def parser_corps(lignes):
    """Corps de fiche -> (dossier partiel, meta). Le corps fait foi."""
    sections = decouper(lignes)
    alertes, signaux, non_parse = [], [], []

    client = {"nom": None, "prenom": None, "tel": None, "email": None}
    for ligne in sections["entete"]:
        nu = _sans_accents(ligne)
        if nu.startswith("telephone") or nu.startswith("tel "):
            client["tel"] = _valeur_apres(ligne) or None
        elif nu.startswith("mail") or nu.startswith("e-mail") or nu.startswith("email"):
            client["email"] = _valeur_apres(ligne) or None

    depart, al = _parse_lieu(sections["depart"])
    alertes += ["Départ — " + a for a in al]
    arrivee, al = _parse_lieu(sections["arrivee"])
    alertes += ["Arrivée — " + a for a in al]
    depart["adresse_brute"] = _parse_adresse_zone(sections["entete"], "depart")
    arrivee["adresse_brute"] = _parse_adresse_zone(sections["entete"], "arrivee")

    # Arrets intermediaires : une section « ### Étape » par arret, meme trame qu'un lieu (type,
    # etage, ascenseur, portage), plus l'adresse et les volumes deposes / charges sur place.
    titres, blocs = [], []
    for ligne in sections["etape"]:
        if ligne.startswith("###"):
            titres.append(ligne)
            blocs.append([])
        elif blocs:
            blocs[-1].append(ligne)
    etapes = []
    for n, (titre, bloc) in enumerate(zip(titres, blocs), 1):
        etape, al = _parse_lieu(bloc)
        alertes += ["Étape %d — %s" % (n, a) for a in al]
        etape["volume_charge_m3"] = etape["volume_decharge_m3"] = None
        for ligne in bloc:
            nu = _sans_accents(ligne)
            if nu.startswith("adresse"):
                etape["adresse_brute"] = _valeur_apres(ligne) or None
            elif re.match(r"^volume (depose|decharge)", nu):
                etape["volume_decharge_m3"], _ = _lire_volume(_valeur_apres(ligne))
            elif re.match(r"^volume charge", nu):
                etape["volume_charge_m3"], _ = _lire_volume(_valeur_apres(ligne))
        # Le titre et l'adresse du depot disent aussi le garde-meuble : sans eux, l'etape sortait
        # en « Adresse intermediaire », sans alerte, et le temps sur place etait faux (04/11/2026).
        if etape["type_logement"] is None:
            texte = _sans_accents("%s %s" % (titre, etape["adresse_brute"] or ""))
            depot = re.search(r"saint[- ]loubes", texte)
            if depot or re.search(r"garde[- ]meuble|box\b|depot|stockage", texte):
                etape["type_logement"] = "garde-meuble"
                if depot:
                    etape["rdc"], etape["etage"] = True, 0
        if not etape["adresse_brute"]:
            alertes.append("Étape %d — adresse absente : arrêt hors itinéraire." % n)
        if not (etape["volume_charge_m3"] or etape["volume_decharge_m3"]):
            alertes.append("Étape %d — aucun volume déposé ni chargé : manutention sur place "
                           "non chiffrée." % n)
        etapes.append(etape)

    relivraison = None
    if sections["relivraison"]:
        relivraison, al = parser_relivraison(sections["relivraison"])
        alertes += ["Relivraison — " + a for a in al]

    mission = {"volume_m3": None, "source_volume": None, "formule": None,
               "inventaire_fourni": None, "mise_en_carton": False, "demontage": False,
               "protection_fragile": False, "carton_h": None, "demontage_h": None, "demontage_elements": [],
               "fragile_h": None, "penderies": None, "peage_ht": None,
               "date_intervention": None, "reservation_parking": [],
               "materiel": {}, "materiel_total_ht": None, "objet_lourd": False}

    for ligne in sections["offre"]:
        nu = _sans_accents(ligne)
        if _coche(ligne):
            lib = _sans_accents(_libelle_case(ligne))
            for cle, nom in FORMULES.items():
                if "formule " + cle in lib:
                    mission["formule"] = nom
            if lib.startswith("inventaire"):
                mission["inventaire_fourni"] = True
            elif lib.startswith("pas d'inventaire") or lib.startswith("pas d inventaire"):
                mission["inventaire_fourni"] = False
            elif lib.startswith("au depart"):
                mission["reservation_parking"].append("départ")
            elif lib.startswith("a l'arrivee") or lib.startswith("a l arrivee"):
                mission["reservation_parking"].append("arrivée")
            continue
        if "volume de meuble" in nu:
            avant, _, apres = ligne.partition("|")
            corps_volume = re.sub(r"(?i)^.*volume de meuble\s*:", "", avant)
            mission["volume_m3"], alerte_vol = _lire_volume(corps_volume)
            if alerte_vol:
                alertes.append(alerte_vol)
            if "source" in _sans_accents(apres):
                mission["source_volume"] = _valeur_apres(apres) or None
            if "🟡" in ligne:
                alertes.append(ligne.strip())
        elif "date / heure" in nu or nu.startswith("date /"):
            mission["date_intervention"] = _valeur_apres(ligne) or None
            if "🟡" in ligne:
                alertes.append(ligne.strip())

    for ligne in sections["demontage"]:
        if ligne.startswith("###"):
            continue
        if _coche(ligne):
            mission["demontage"] = True
            # Une duree ecrite sur la ligne fait foi ; sinon l'element est chiffre au bareme
            # (demontage.py) par pipeline.py. Ici « 2m » est une longueur, jamais des minutes.
            fin = ligne.split("-")[-1]
            ecrite = re.search(r"\d\s*h(eures?|rs?)?(\b|\s*\d)|\d\s*(min|mn)\b|\(\s*\d+\s*m\s*\)",
                               fin, re.I)
            heures = nb_heures(fin) if ecrite else None
            if heures:
                mission["demontage_h"] = (mission["demontage_h"] or 0) + heures
            else:
                mission["demontage_elements"].append(_libelle_case(ligne).strip())
        elif "🟡" in ligne:
            alertes.append(ligne.strip())

    for ligne in sections["cartons"]:
        if ligne.startswith("###"):
            continue
        nu = _sans_accents(ligne)
        if _coche(ligne):
            if "penderie" in nu:
                nombres = _nombres(_libelle_case(ligne))
                mission["penderies"] = int(nombres[0]) if nombres else None
                # Regle du skill : 30 min pour 5 penderies, au prorata, dans cartonH.
                if mission["penderies"]:
                    heures = mission["penderies"] / 5.0 * 0.5
                    if "offert" in nu or "gratuit" in nu or "incluse" in nu:
                        signaux.append(
                            "Penderies notées offertes (%d) : %.2f h NON facturée — %s"
                            % (mission["penderies"], heures, ligne.strip()))
                    else:
                        mission["carton_h"] = (mission["carton_h"] or 0) + heures
                        signaux.append("%d penderies → %.2f h ajoutées à cartonH (30 min / 5)."
                                       % (mission["penderies"], heures))
            elif "fragile" in nu or "protection" in nu:
                # Protection du fragile : son propre poste (fragileH), pas la mise en carton
                # (erreur SAINT-MLEUX, 28/10/2026 : 2 h de protection comptees en carton).
                mission["protection_fragile"] = True
                heures = nb_heures(ligne)
                if heures:
                    mission["fragile_h"] = (mission["fragile_h"] or 0) + heures
            else:
                mission["mise_en_carton"] = True
                heures = nb_heures(ligne)
                if heures:
                    mission["carton_h"] = (mission["carton_h"] or 0) + heures
        elif "🟡" in ligne:
            alertes.append(ligne.strip())

    for ligne in sections["materiel"]:
        nu = _sans_accents(ligne)
        if nu.startswith("prix de l'article") or nu.startswith("prix de l article"):
            mission["materiel_total_ht"] = _premier_nombre(_valeur_apres(ligne))
            continue
        if not _coche(ligne):
            continue
        lib = _sans_accents(_libelle_case(ligne))
        cle = next((c for motif, c in MATERIEL if re.search(motif, lib)), None)
        quantite = _premier_nombre(_valeur_apres(ligne)) if ":" in ligne else None
        if cle:
            mission["materiel"][cle] = int(quantite) if quantite else None
        else:
            non_parse.append(ligne.strip())

    for ligne in sections["lourds"]:
        if ligne.startswith("###"):
            continue
        nu = _sans_accents(ligne).strip()
        if nu and not nu.startswith("(bois massif") and not nu.startswith("aucun"):
            mission["objet_lourd"] = True

    itineraire = {}
    for ligne in sections["itineraire"]:
        nu = _sans_accents(ligne)
        if nu.startswith("kilometres a/r"):
            itineraire["km_ar"] = _premier_nombre(_valeur_apres(ligne))
        elif nu.startswith("temps a/r"):
            itineraire["heures_conduite_ar"] = nb_heures(_valeur_apres(ligne))
        elif nu.startswith("peage ht"):
            valeur = _valeur_apres(ligne)
            if "🟡" in valeur:                    # « 🟡 Péage à renseigner (classe 3 ÷ 1,2) » n'est pas un montant
                alertes.append(ligne.strip())
            else:
                mission["peage_ht"] = _premier_nombre(valeur)
        elif "🟡" in ligne:
            alertes.append(ligne.strip())
    itineraire = {k: v for k, v in itineraire.items() if v is not None}
    if itineraire:
        itineraire["source"] = "corps de la fiche"
        # Les chiffres ecrits a la main n'emportent pas les drapeaux que le module calcule.
        # Sans cela, un A/R de 14 h relu dans le corps perdrait le taux conducteur a 20 EUR/h.
        heures = itineraire.get("heures_conduite_ar")
        if heures is not None:
            itineraire["longue_distance"] = heures > SEUIL_LONGUE_DISTANCE_H
            # Le « Temps A/R » d'une fiche peut etre celui de l'itineraire AVEC peage, deja passe
            # sous le seuil : seul le 🟡 de la ligne « Péage HT » dit alors qu'un peage est du.
            itineraire["peage_requis"] = heures > SEUIL_SANS_PEAGE_H or any(
                _sans_accents(a).startswith("peage ht") for a in alertes)
            itineraire["confiance"] = "ok"

    notes, dans_notes, deja_chiffre = [], False, False
    for ligne in sections["fin"]:
        nu = _sans_accents(ligne)
        if nu.startswith("notes"):
            dans_notes = True
            reste = _valeur_apres(ligne)
            if reste:
                notes.append(reste)
            continue
        if re.match(r"^\s*(temps de mission|temps de trajet|transport\s*:|rdv acompte|\[divider)", nu):
            dans_notes = False
        if re.match(r"^prix total\s*(ht)?\s*:", nu) and _nombres(ligne):
            deja_chiffre = True
        if dans_notes and ligne.strip():
            notes.append(ligne.strip())

    # Signaux : on repere une mention, on ne tranche pas. « pas de stockage intermediaire »
    # contient le mot mais dit le contraire — les tournures negatives sont donc ecartees.
    negation = re.compile(r"\b(pas de|pas d'|aucun|aucune|sans|hors|ni)\b")
    for nom, motif in MOTS_SIGNAUX:
        for ligne in lignes:
            nu = _sans_accents(ligne)
            m = re.search(motif, nu)
            if not m:
                continue
            if negation.search(nu[max(0, m.start() - 40):m.start()]):
                continue
            signaux.append("%s — mentionné : « %s »" % (nom, ligne.strip()[:160]))
            break

    alertes += [l.strip() for l in notes if "🟡" in l]

    dossier = {"client": client, "depart": depart, "arrivee": arrivee, "etapes": etapes,
               "mission": mission, "itineraire": itineraire, "relivraison": relivraison}
    meta = {"alertes": sorted(set(alertes)), "signaux": signaux,
            "non_parse": non_parse, "notes": notes, "deja_chiffre": deja_chiffre}
    return dossier, meta


# --- Proprietes : repli et controle ------------------------------------------

def valeur_propriete(prop):
    """Rend la valeur Python d'une propriete Notion, ou None si vide."""
    if not prop:
        return None
    type_ = prop.get("type")
    brut = prop.get(type_)
    if type_ in ("rich_text", "title"):
        return _texte(brut) or None
    if type_ == "number":
        return brut
    if type_ == "checkbox":
        return brut
    if type_ == "select":
        return brut.get("name") if brut else None
    if type_ == "date":
        return brut.get("start") if brut else None
    if type_ in ("email", "url", "phone_number"):
        return brut or None
    if type_ == "unique_id":
        return ("%s-%s" % (brut.get("prefix"), brut.get("number"))
                if brut and brut.get("prefix") else (brut or {}).get("number"))
    return None


def _jetons(s):
    """Mots significatifs d'une chaine, pour comparer deux ecritures d'une meme adresse."""
    return {j for j in re.split(r"[^a-z0-9]+", _sans_accents(str(s)))
            if len(j) > 2 and j not in ("rue", "avenue", "allee", "route", "boulevard",
                                        "chemin", "place", "impasse", "bis", "appt",
                                        "livraison", "sur")}


def _comparables(a, b, mode=""):
    """Deux valeurs disent-elles la meme chose ?

    mode 'adresse' : meme jeu de mots, quel que soit l'ordre (« Cenon (33150) — 20 Av. X »
                     et « 20 Av. X, 33150 Cenon » ne sont pas une divergence).
    mode 'somme'   : le corps porte un total, la propriete ses composantes.
    """
    if a is None or b is None or mode == "libre":
        return True
    if mode == "adresse":
        ja, jb = _jetons(a), _jetons(b)
        if not ja or not jb:
            return True
        return len(ja & jb) >= 0.7 * min(len(ja), len(jb))
    if mode == "portage":
        # La propriete est de la prose libre : tantot les deux composantes, tantot une seule
        # (« < 10 mètres »), tantot un total. Elle n'est comparable que quand elle porte
        # les deux distances ou dit « total » — sinon on ne compare pas ce qui n'est pas
        # de meme nature, sous peine d'un detecteur qui crie a chaque fiche.
        nb = _nombres(str(b))
        if len(nb) < 2 and "total" not in _sans_accents(str(b)):
            return True
        na = _nombres(str(a))
        if not na or not nb:
            return True
        return abs(sum(na) - sum(nb)) < 0.01 or abs(max(na) - max(nb)) < 0.01
    if mode == "inclus":
        # Le corps porte souvent la valeur ET son commentaire (« 🟡 x@y.fr — à confirmer »).
        # Tant que l'un contient l'autre, les deux disent la meme chose.
        pa = _sans_accents(str(a)).replace("🟡", "").strip()
        pb = _sans_accents(str(b)).replace("🟡", "").strip()
        if mode == "inclus" and "@" not in pa and "@" not in pb:
            pa, pb = re.sub(r"\D", "", pa), re.sub(r"\D", "", pb)   # téléphone : les chiffres
        if not pa or not pb:
            return True
        return pa in pb or pb in pa
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.01
    na, nb = _premier_nombre(str(a)), _premier_nombre(str(b))
    if na is not None and nb is not None:
        return abs(na - nb) < 0.01
    # La pastille 🟡 est une annotation, pas une valeur : « 🟡 x@y.fr » et « x@y.fr » disent
    # la meme chose. On la retire avant de comparer, comme la ponctuation de bord.
    propre = lambda s: _sans_accents(str(s)).replace("🟡", "").strip(" .,;—-").strip()
    return propre(a) == propre(b)


# Champs lisibles des deux cotes : (chemin dossier, nom de propriete, libelle, mode).
# « Temps de trajet total » n'y figure pas : c'est une sortie de devis, pas une entree —
# la comparer au « Temps A/R » du corps serait une erreur de categorie.
CROISES = [
    ("mission.volume_m3", "Volume (m3)", "volume", ""),
    ("mission.formule", "Formule (offre choisie)", "formule", ""),
    ("mission.inventaire_fourni", "Inventaire fourni", "inventaire", ""),
    # « Source volume » est de la prose des deux cotes et n'entre dans aucun calcul :
    # repli utile, mais la comparer ne produirait que du bruit.
    ("mission.source_volume", "Source volume", "source du volume", "libre"),
    ("depart.adresse_brute", "Adresse départ", "adresse de départ", "adresse"),
    ("arrivee.adresse_brute", "Adresse arrivée", "adresse d'arrivée", "adresse"),
    ("depart.type_logement", "Départ - type logement", "type de logement départ", ""),
    ("arrivee.type_logement", "Arrivée - type logement", "type de logement arrivée", ""),
    ("depart.rdc", "Départ - RDC", "RDC départ", ""),
    ("arrivee.rdc", "Arrivée - RDC", "RDC arrivée", ""),
    # Le portage est un TOTAL cote corps (entree + interieur) et de la prose libre cote
    # propriete (« entrée → ascenseur : 5 m ; ascenseur → lieu de vie : 0 m », « 10-20 m +
    # 3 marches »). Les deux ne sont pas de meme nature : les comparer criait sur une fiche
    # sur deux sans jamais rien apprendre. Repli seul.
    ("depart.portage_m", "Départ - distance portage", "portage départ", "libre"),
    ("arrivee.portage_m", "Arrivée - distance portage", "portage arrivée", "libre"),
    ("client.tel", "Téléphone", "téléphone", "inclus"),
    ("client.email", "Email", "email", "inclus"),
]


def _get(d, chemin):
    cur = d
    for part in chemin.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set(d, chemin, valeur):
    parts = chemin.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = valeur


def croiser(dossier, proprietes):
    """Complete le dossier avec les proprietes (repli) et liste les divergences.

    Le corps l'emporte toujours : une propriete n'ecrase jamais une valeur lue dans le texte.
    """
    divergences, replis = [], []
    for chemin, nom_prop, libelle, mode in CROISES:
        valeur_corps = _get(dossier, chemin)
        valeur_prop = valeur_propriete(proprietes.get(nom_prop))
        if valeur_prop in (None, "", []):
            continue
        if valeur_corps in (None, "", []):
            if chemin.endswith("type_logement"):
                valeur_prop = str(valeur_prop).lower()
            if chemin.endswith("portage_m"):
                nombres = _nombres(str(valeur_prop))
                valeur_prop = sum(nombres) if nombres else None
            if valeur_prop is not None:
                _set(dossier, chemin, valeur_prop)
                replis.append("%s : absent du corps, repris de la propriété (%s)"
                              % (libelle, valeur_prop))
            continue
        if not _comparables(valeur_corps, valeur_prop, mode):
            divergences.append({"champ": libelle, "corps": valeur_corps,
                                "propriete": valeur_prop, "retenu": "corps"})
    return divergences, replis


def _nom_prenom(titre):
    """'DE STEFANO Katia 09/06' -> ('DE STEFANO', 'Katia')."""
    titre = re.sub(r"\s*\d{2}/\d{2}(/\d{2,4})?\s*$", "", titre or "").strip()
    mots = titre.split()
    nom = [m for m in mots if m.isupper() or (m.upper() == m and len(m) > 1)]
    prise = 0
    for m in mots:
        if m == m.upper() and any(c.isalpha() for c in m):
            prise += 1
        else:
            break
    nom = " ".join(mots[:prise]) or (mots[0] if mots else None)
    prenom = " ".join(mots[prise:]) or None
    return nom, prenom


# --- Assemblage --------------------------------------------------------------

def lire_fiche(page_id, token):
    if est_transaction(page_id):
        import fiche_hubspot
        return fiche_hubspot.lire_fiche(page_id)
    page = _appel("%s/pages/%s" % (API, page_id.replace("-", "")), token)
    proprietes = page.get("properties", {})
    lignes = lire_corps(page_id, token)
    dossier, meta = parser_corps(lignes)

    titre = valeur_propriete(proprietes.get("Nom client")) or ""
    nom, prenom = _nom_prenom(titre)
    dossier["client"]["nom"] = dossier["client"]["nom"] or nom
    dossier["client"]["prenom"] = dossier["client"]["prenom"] or prenom

    divergences, replis = croiser(dossier, proprietes)

    mission = dossier["mission"]
    mission["commercial"] = valeur_propriete(proprietes.get("Commercial"))
    mission["date_chargement"] = valeur_propriete(proprietes.get("Date de chargement"))
    mission["date_creation"] = valeur_propriete(proprietes.get("Date de création"))
    mission["statut"] = valeur_propriete(proprietes.get("Statut"))
    mission["ref"] = valeur_propriete(proprietes.get("Réf"))
    mission["axe_groupage"] = valeur_propriete(proprietes.get("Axe groupage"))
    # Les proprietes ne comblent ici que des champs de contexte (commercial, dates, statut,
    # ref, axe) : aucune ne recouvre une valeur lue dans le corps.

    meta.update({"page_id": page.get("id"), "url": page.get("url"), "titre": titre,
                 "divergences": divergences, "replis": replis,
                 "lignes_corps": len(lignes)})
    dossier["_meta"] = meta
    return dossier, lignes


# --- Audit corps vs proprietes ----------------------------------------------

def auditer(nombre, token, base=None):
    """Mesure, sur N fiches, quelles proprietes divergent du corps ou sont vides."""
    base = base or export.BASE_FICHES_CLIENT
    pages, curseur = [], None
    while len(pages) < nombre:
        payload = {"page_size": min(100, nombre - len(pages)),
                   "sorts": [{"timestamp": "created_time", "direction": "descending"}]}
        if curseur:
            payload["start_cursor"] = curseur
        rep = _appel("%s/databases/%s/query" % (API, base), token, payload)
        pages += rep.get("results", [])
        if not rep.get("has_more"):
            break
        curseur = rep["next_cursor"]

    stats = {libelle: {"accord": 0, "divergence": 0, "prop_vide": 0, "corps_vide": 0,
                       "exemples": []} for _, _, libelle, _m in CROISES}
    erreurs = 0
    for page in pages:
        try:
            lignes = lire_corps(page["id"], token)
            dossier, _ = parser_corps(lignes)
        except Exception as e:                      # fiche atypique : on la compte a part
            erreurs += 1
            continue
        titre = valeur_propriete(page["properties"].get("Nom client")) or "?"
        for chemin, nom_prop, libelle, mode in CROISES:
            corps = _get(dossier, chemin)
            prop = valeur_propriete(page["properties"].get(nom_prop))
            s = stats[libelle]
            if corps in (None, "", []) and prop in (None, "", []):
                s["prop_vide"] += 1
                s["corps_vide"] += 1
            elif prop in (None, "", []):
                s["prop_vide"] += 1
            elif corps in (None, "", []):
                s["corps_vide"] += 1
            elif _comparables(corps, prop, mode):
                s["accord"] += 1
            else:
                s["divergence"] += 1
                if len(s["exemples"]) < 3:
                    s["exemples"].append("%s : corps=%r / propriété=%r" % (titre, corps, prop))
    return {"fiches": len(pages), "erreurs": erreurs, "champs": stats}


def _rapport_audit(a):
    lignes = ["Audit corps vs propriétés — %d fiches (%d illisibles)"
              % (a["fiches"], a["erreurs"]), ""]
    lignes.append("%-26s %7s %11s %10s %10s" % ("champ", "accord", "divergence",
                                                "prop.vide", "corps vide"))
    for libelle, s in a["champs"].items():
        lignes.append("%-26s %7d %11d %10d %10d"
                      % (libelle, s["accord"], s["divergence"], s["prop_vide"], s["corps_vide"]))
    lignes.append("")
    for libelle, s in a["champs"].items():
        for ex in s["exemples"]:
            lignes.append("  [%s] %s" % (libelle, ex))
    return "\n".join(lignes)


# --- CLI ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Fiche client Notion -> dossier.json")
    ap.add_argument("nom", nargs="?", help="nom du client (recherche dans la base)")
    ap.add_argument("--page-id")
    ap.add_argument("--url", help="URL Notion de la fiche")
    ap.add_argument("--texte", action="store_true", help="corps normalisé au lieu du JSON")
    ap.add_argument("--sortie", help="écrire le dossier.json dans ce fichier")
    ap.add_argument("--audit", type=int, metavar="N",
                    help="comparer corps et propriétés sur les N dernières fiches")
    a = ap.parse_args()

    token = _token()

    if a.audit:
        print(_rapport_audit(auditer(a.audit, token)))
        return 0

    page_id = a.page_id or (id_depuis_url(a.url) if a.url else None)
    if not page_id:
        if not a.nom:
            ap.error("donner un nom, --page-id ou --url")
        page_id, _ = chercher_fiche(a.nom, token)

    dossier, lignes = lire_fiche(page_id, token)

    if a.texte:
        print("\n".join(lignes))
        return 0

    sortie = json.dumps(dossier, ensure_ascii=False, indent=2)
    if a.sortie:
        with open(a.sortie, "w", encoding="utf-8") as fh:
            fh.write(sortie)
        print(a.sortie)
    else:
        print(sortie)
    return 0


if __name__ == "__main__":
    sys.exit(main())
