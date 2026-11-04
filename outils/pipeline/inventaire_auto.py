#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventaire automatique — dernier maillon de la chaîne devis (décision Karim, 18/09/2026).

Lancé par finalisation.py, en arrière-plan, juste après le message WhatsApp du devis.
Cherche un inventaire client, le met au propre avec le skill Prod_inventaires et
le garde pour la relecture : il rejoint HubSpot et la conversation WhatsApp quand Samuel valide le
devis (validation_devis.py, Karim 03/11/2026). Sans relecture en cours, il part tout de suite.

Ordre de recherche — le premier qui répond l'emporte :
  1. fiche Notion : section « Inventaire… » du corps de la fiche, puis fichiers (PDF,
     tableur, document) rangés sous cette section ou dont le nom parle d'inventaire ;
  2. noCRM : pièces jointes de l'opportunité (documents ; images seulement si leur nom parle
     d'inventaire), puis texte saisi en tête de description (au-dessus du « --- »).
  Rien trouvé : on s'arrête sans bruit, la chaîne a déjà fini son travail.

Mise en forme : le format structuré « Pièce : article dims xN · … » (celui qu'écrivent nos
skills) est lu par un parseur codé — zéro token. Tout le reste (texte libre, PDF, tableur)
passe par le modèle, en mode non interactif, avec les règles de rédaction du SKILL.md de
Prod_inventaires, puis est validé ici avant tout rendu.

Garanties :
  · un même inventaire n'est jamais renvoyé deux fois (registre par fiche + empreinte de la
    source) ; un inventaire modifié repart, marqué « met à jour et remplace » ;
  · aucune étape ne fait échouer la chaîne devis : tout incident part en alerte Slack
    (notif.alerte) et le PDF non envoyé attend dans la file WhatsApp ;
  · données du PDF (client, adresses, date / créneau, volume) lues dans la fiche et l'export
    du devis — jamais inventées ; ce qui manque reste un champ vide, modifiable dans le PDF.

Usage :
    python inventaire_auto.py --page-id <id> [--volume 16] [--sans-envoi] [--forcer]
    python inventaire_auto.py --page-id <id> --chercher      # dit seulement ce qu'il trouve
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.normpath(os.path.join(ICI, "..", ".."))
PROD = os.path.join(ICI, "Prod_inventaires")
sys.path.insert(0, ICI)
sys.path.insert(0, PROD)

import fiche_notion as fn                          # noqa: E402
import crm                                          # noqa: E402
import nocrm                                        # noqa: E402
import notif                                        # noqa: E402
import regles                                       # noqa: E402
import validation_devis                             # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

JOURNAL = os.path.join(RACINE, ".claude", "scripts", "inventaires-auto.log")
REGISTRE = os.path.join(RACINE, ".claude", "scripts", "inventaires-envoyes.jsonl")
SKILL_MD = os.path.join(PROD, "SKILL.md")
CLAUDE_EXE = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
MODELE = "sonnet"
DELAI_MODELE = 600                                  # secondes

EXT_DOCS = {".pdf", ".docx", ".odt", ".xlsx", ".xls", ".ods", ".csv", ".txt"}
EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
RE_INVENTAIRE = re.compile(r"inventaire|inventory|liste\s+(du\s+|des\s+)?(mobilier|meubles)", re.I)
# Pièces jointes qui ne sont jamais un inventaire : pas la peine de les faire lire au modèle.
RE_HORS_SUJET = re.compile(r"devis|facture|cgv|condition|contrat|d[ée]claration|valeur|"
                           r"attestation|assurance|bon[\s_-]de|lettre[\s_-]de[\s_-]voiture", re.I)
APPELS_MODELE_MAX = 3                               # par dossier : borne le coût d'un CRM chargé


def log(msg):
    ligne = "[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(ligne)
    try:
        os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8") as fh:
            fh.write(ligne + "\n")
    except Exception:
        pass


# --- Registre : un inventaire donné n'est envoyé qu'une fois ---------------------------

def empreinte(*morceaux):
    h = hashlib.sha1()
    for m in morceaux:
        h.update(m if isinstance(m, bytes) else str(m).encode("utf-8"))
    return h.hexdigest()


def registre(page_id):
    if not os.path.exists(REGISTRE):
        return []
    lignes = []
    with open(REGISTRE, encoding="utf-8") as fh:
        for l in fh:
            try:
                d = json.loads(l)
            except ValueError:
                continue
            if d.get("page_id") == page_id:
                lignes.append(d)
    return lignes


def inscrire(entree):
    os.makedirs(os.path.dirname(REGISTRE), exist_ok=True)
    with open(REGISTRE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entree, ensure_ascii=False) + "\n")


# --- Notion : corps + fichiers, en une seule descente ----------------------------------

def lire_page(page_id, token):
    """Rend (lignes, fichiers). Lignes au format de fiche_notion.lire_corps ; fichiers :
    [{nom, url, section}] où `section` est le dernier titre rencontré au-dessus du fichier."""
    lignes, fichiers = [], []
    titre = [""]

    def descendre(bloc_id, profondeur=0):
        curseur = None
        while True:
            url = "%s/blocks/%s/children?page_size=100" % (fn.API, bloc_id)
            if curseur:
                url += "&start_cursor=" + curseur
            rep = fn._appel(url, token)
            for b in rep.get("results", []):
                t = b["type"]
                c = b.get(t, {})
                texte = fn._texte(c.get("rich_text"))
                if t in ("file", "pdf", "image"):
                    src = c.get(c.get("type") or "file") or {}
                    nom = c.get("name") or fn._texte(c.get("caption")) \
                        or os.path.basename((src.get("url") or "").split("?")[0])
                    if src.get("url"):
                        fichiers.append({"nom": nom, "url": src["url"], "section": titre[0]})
                    lignes.append("  " * profondeur + "[%s] %s" % (t, nom))
                    continue
                if t in ("heading_1", "heading_2", "heading_3"):
                    prefixe = "### "
                    titre[0] = texte
                elif t == "to_do":
                    prefixe = "- [x] " if c.get("checked") else "- [ ] "
                elif t in ("bulleted_list_item", "numbered_list_item"):
                    prefixe = "- "
                elif t in ("paragraph", "quote", "callout", "toggle"):
                    prefixe = ""
                else:
                    prefixe, texte = "", texte or "[%s]" % t
                for i, sous in enumerate(texte.split("\n") or [""]):
                    lignes.append("  " * profondeur + (prefixe if i == 0 else "") + sous)
                if b.get("has_children") and t != "child_database":
                    descendre(b["id"], profondeur + 1)
            if not rep.get("has_more"):
                break
            curseur = rep["next_cursor"]

    descendre(page_id)
    return lignes, fichiers


def section_inventaire(lignes):
    """Lignes de la (des) section(s) dont le titre parle d'inventaire. Vide si rien d'utile."""
    garde, dedans = [], False
    for l in lignes:
        s = l.strip()
        if s.startswith("###"):
            dedans = bool(RE_INVENTAIRE.search(s))
            continue
        if s.startswith("[divider]"):
            dedans = False
            continue
        if dedans and s and not s.startswith("["):
            garde.append(s)
    # Une section qui ne dit que « à demander » / « aucun » n'est pas un inventaire.
    utiles = [l for l in garde
              if not re.search(r"^\W*(🟡)?\s*(à demander|en attente|aucun|néant|pas d'inventaire)",
                               l, re.I)]
    return utiles


# --- Parseur du format structuré « Pièce : article dims xN · … » ------------------------

_DIM = r"[LPHØlph]?\s?\d+(?:[.,]\d+)?"
RE_DIMS = re.compile(r"^(?P<avant>.*?)\s+(?P<dims>%s(?:\s*[×x*]\s*%s)+(?:\s*cm)?)$" % (_DIM, _DIM))
RE_QTE = re.compile(r"^(?P<avant>.*?)\s+[x×](?P<q>\d{1,3})$")
RE_NON_PRECISE = re.compile(r"^(?P<avant>.*?)\s*\((?P<note>nombre non pr[ée]cis[ée]|quantit[ée] [àa] pr[ée]ciser)\)$", re.I)
RE_FRAGILE = re.compile(r"^(?P<avant>.*?)\s*\((?:fragile)\)$", re.I)
RE_LIGNE = re.compile(r"^-?\s*(?P<piece>[^:·]{2,40}?)\s*:\s*(?P<articles>.+)$")


def lire_article(texte):
    t = texte.strip()
    a = {"qte": 1}
    m = RE_QTE.match(t)
    if m:
        a["qte"], t = int(m.group("q")), m.group("avant").strip()
    m = RE_NON_PRECISE.match(t)
    if m:
        a["qte"], a["dims"], t = "à préciser", "nombre non précisé", m.group("avant").strip()
    m = RE_DIMS.match(t)
    if m:
        a["dims"], t = m.group("dims").replace("*", "×").strip(), m.group("avant").strip()
    m = RE_FRAGILE.match(t)
    if m:
        a["fragile"], t = True, m.group("avant").strip()
    if not t or not re.search(r"[A-Za-zÀ-ÿ]", t):
        return None
    a["nom"] = t[:1].upper() + t[1:]
    return a


def parser_structure(lignes):
    """Rend la liste des pièces si CHAQUE ligne suit le format, sinon None (-> modèle)."""
    pieces = []
    for l in lignes:
        m = RE_LIGNE.match(l)
        if not m:
            return None
        # Un nom de pièce est court et sans ponctuation de phrase : « Bonjour, voici notre
        # liste : … » n'est pas une pièce, c'est du texte libre (-> modèle).
        piece = m.group("piece").strip()
        if re.search(r"[,.!?;]", piece) or len(piece.split()) > 5:
            return None
        articles = []
        for morceau in m.group("articles").split("·"):
            if not morceau.strip():
                continue
            # Une énumération à virgules ou une phrase dans un article = texte libre.
            if re.search(r",\s|\.\s|[.!?]$", morceau.strip()):
                return None
            a = lire_article(morceau)
            if a is None:
                return None
            articles.append(a)
        if not articles:
            return None
        pieces.append({"nom": m.group("piece").strip(), "articles": articles})
    return pieces or None


# --- noCRM ---------------------------------------------------------------------------

def lead_du_client(dossier):
    c = dossier.get("client") or {}
    source = nocrm
    if crm.lecture() == "hubspot":
        import hubspot_crm as source
    lead, candidats, _, rang = source.chercher_lead(nom=c.get("nom"), prenom=c.get("prenom"),
                                                    tel=c.get("tel"), email=c.get("email"))
    # Lire l'inventaire d'un autre client serait pire que ne rien trouver : un appariement
    # sur le seul nom (rang 1) ne suffit pas, comme pour les écritures dans le CRM.
    if lead and rang >= 2:
        return lead
    if candidats:
        log(crm.nom() + " : appariement insuffisant (rang %s, %d candidat(s)) — CRM ignoré."
            % (rang, len(candidats)))
    return None


def pieces_jointes_nocrm(lead_id):
    if crm.lecture() == "hubspot":
        import hubspot_crm
        ok, lst = True, hubspot_crm.pieces_jointes(lead_id)
    else:
        ok, lst = nocrm._appel("/leads/%s/attachments" % lead_id)
    if not ok or not isinstance(lst, list):
        raise RuntimeError("liste des pièces jointes noCRM illisible : %s" % lst)
    retenues = []
    for pj in lst:
        nom = pj.get("name") or ""
        if RE_HORS_SUJET.search(nom) and not RE_INVENTAIRE.search(nom):
            continue
        ext = os.path.splitext(nom.lower())[1]
        if ext in EXT_DOCS or (ext in EXT_IMAGES and RE_INVENTAIRE.search(nom)):
            retenues.append(pj)
    # Les documents qui se disent « inventaire » passent devant les autres.
    retenues.sort(key=lambda pj: 0 if RE_INVENTAIRE.search(pj.get("name") or "") else 1)
    return retenues


def telecharger_nocrm(lead_id, pj, dossier_tmp):
    if crm.lecture() == "hubspot":
        import hubspot_crm
        ok, rep = True, {"url": hubspot_crm.url_piece(pj["id"])}
    else:
        ok, rep = nocrm._appel("/leads/%s/attachments/%s" % (lead_id, pj["id"]))
    if not ok or not (rep or {}).get("url"):
        raise RuntimeError("URL de téléchargement noCRM absente : %s" % rep)
    return telecharger(rep["url"], pj.get("name") or str(pj["id"]), dossier_tmp)


def en_tete_nocrm(lead_id):
    """Texte saisi au-dessus du « --- » (le reste est la copie de la fiche Notion).
    HubSpot : les notes de la transaction, hors note « Fiche client (Notion) »."""
    if crm.lecture() == "hubspot":
        import hubspot_crm
        ok, lead = True, {"description": hubspot_crm.notes_libres(lead_id)}
    else:
        ok, lead = nocrm._appel("/leads/%s" % lead_id)
    if not ok:
        return []
    desc = (lead or {}).get("description") or ""
    lignes = desc.split("\n")
    coupe = next((i for i, l in enumerate(lignes) if l.strip() == nocrm.SEPARATEUR), None)
    if coupe is None and any(nocrm.RE_TITRE.match(l.strip()) for l in lignes):
        return []                                   # description entièrement issue de Notion
    tete = lignes[:coupe] if coupe is not None else lignes
    contact = re.compile(r"^\s*(pr[ée]nom|nom|t[ée]l[ée]phone|e-?mail|mail|adresse)\s*:", re.I)
    return [l.strip() for l in tete if l.strip() and not contact.match(l)]


# --- Fichiers ---------------------------------------------------------------------------

def telecharger(url, nom, dossier_tmp):
    nom = re.sub(r'[<>:"/\\|?*]', "-", nom) or "piece-jointe"
    chemin = os.path.join(dossier_tmp, nom)
    # Le CDN de HubSpot répond 403 à un client sans User-Agent de navigateur (06/10/2026).
    requete = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (samdem-inventaire)"})
    with urllib.request.urlopen(requete, timeout=60) as r:
        contenu = r.read()
        type_ = r.headers.get("Content-Type") or ""
    # Une page web à la place du fichier (lien de session expiré, page de connexion noCRM)
    # répond 200 : sans ce contrôle, elle passerait pour la pièce jointe.
    if "text/html" in type_ or contenu[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise RuntimeError("téléchargement de « %s » : page web reçue au lieu du fichier" % nom)
    with open(chemin, "wb") as fh:
        fh.write(contenu)
    return chemin


def extraire_texte(chemin):
    """Texte des formats que le modèle ne lit pas directement (tableurs, docx, csv, txt)."""
    ext = os.path.splitext(chemin.lower())[1]
    if ext == ".pdf":
        # PDF texte : on lit le texte (parseur ou modèle sur du texte, moins cher). PDF scanné
        # (pas de texte) : None, le modèle lira le fichier lui-même.
        import pymupdf
        with pymupdf.open(chemin) as doc:
            texte = "\n".join(p.get_text() for p in doc)
        return texte if len(texte.strip()) >= 40 else None
    if ext in (".txt", ".csv"):
        return open(chemin, encoding="utf-8", errors="replace").read()
    if ext in (".xlsx", ".xls", ".ods"):
        import pandas as pd
        feuilles = pd.read_excel(chemin, sheet_name=None, header=None)
        return "\n\n".join("# %s\n%s" % (n, f.fillna("").to_csv(sep=";", index=False, header=False))
                           for n, f in feuilles.items())
    if ext in (".docx", ".odt"):
        import zipfile
        xml = zipfile.ZipFile(chemin).read("word/document.xml" if ext == ".docx" else "content.xml")
        texte = re.sub(r"</w:p>|</text:p>", "\n", xml.decode("utf-8", "replace"))
        return re.sub(r"<[^>]+>", "", texte)
    return None                                     # PDF, images : lus par le modèle


# --- Le modèle, pour ce qui n'est pas codable ------------------------------------------

def regles_redaction():
    """Règles de rédaction des pièces et articles, lues dans le SKILL.md (source unique)."""
    texte = open(SKILL_MD, encoding="utf-8").read()
    debut = texte.find("**Pièces**")
    fin = texte.find("\n## ", debut)                # jusqu'au titre de section suivant
    if debut < 0 or fin < 0:
        raise RuntimeError("règles introuvables dans %s (paragraphe « **Pièces** » de la "
                           "section 3)" % SKILL_MD)
    return texte[debut:fin].strip()


CONSIGNE = """Tu mets au propre l'inventaire d'un client de déménagement pour Sam'Déménage.

Réponds UNIQUEMENT par un objet JSON, sans texte autour, de la forme :
{"pieces": [{"nom": "Cuisine", "articles": [{"nom": "Assiettes", "qte": 1, "dims": "", "fragile": true}]}]}

- `qte` : entier, ou la chaîne "à préciser" si le nombre n'est pas donné.
- `dims` : chaîne, vide si aucune dimension.
- Si la source n'est PAS un inventaire de mobilier (photos de pièces, devis, facture,
  échange sans liste d'objets…), réponds exactement {"pieces": []}.
- N'invente rien : chaque article vient de la source.

Règles de rédaction (skill Prod_inventaires) :
%s
"""


def structurer_par_modele(texte=None, fichiers=(), dossier_tmp=None):
    """Rend la liste des pièces ([] = pas un inventaire). Lève en cas d'échec."""
    if not os.path.exists(CLAUDE_EXE):
        raise RuntimeError("Claude Code introuvable : %s" % CLAUDE_EXE)
    consigne = CONSIGNE % regles_redaction()
    if texte:
        consigne += "\n\nSOURCE (texte) :\n<<<\n%s\n>>>\n" % texte
    if fichiers:
        consigne += ("\n\nSOURCE (fichiers à lire avec l'outil Read) :\n"
                     + "\n".join("- %s" % f for f in fichiers))
    cmd = [CLAUDE_EXE, "-p", "--model", MODELE, "--output-format", "json",
           "--allowedTools", "Read", "--strict-mcp-config", "--no-session-persistence",
           "--disable-slash-commands"]
    if dossier_tmp:
        cmd += ["--add-dir", dossier_tmp]
    # Répertoire temporaire comme dossier courant : le CLAUDE.md du coffre (volumineux) n'est
    # pas chargé — le modèle n'a besoin que de la consigne et de la source.
    r = subprocess.run(cmd, input=consigne, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=DELAI_MODELE, cwd=dossier_tmp or tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError("claude -p a échoué (code %s) : %s" % (r.returncode, (r.stderr or r.stdout)[-500:]))
    try:
        enveloppe = json.loads(r.stdout)
        reponse = enveloppe.get("result") or ""
        if enveloppe.get("is_error"):
            raise RuntimeError("le modèle signale une erreur : %s" % reponse[:300])
    except ValueError:
        reponse = r.stdout
    m = re.search(r"\{.*\}", reponse, re.S)
    if not m:
        raise RuntimeError("réponse du modèle sans JSON : %s" % reponse[:300])
    return valider(json.loads(m.group(0)))


def valider(donnees):
    """Contrôle strict de la forme rendue par le modèle, avant tout rendu."""
    pieces = (donnees or {}).get("pieces")
    if not isinstance(pieces, list):
        raise RuntimeError("JSON du modèle sans liste « pieces »")
    propres = []
    for p in pieces:
        nom = str((p or {}).get("nom") or "").strip()
        arts = (p or {}).get("articles")
        if not nom or not isinstance(arts, list):
            raise RuntimeError("pièce mal formée : %s" % p)
        garde = []
        for a in arts:
            n = str((a or {}).get("nom") or "").strip()
            if not n:
                raise RuntimeError("article sans nom dans « %s »" % nom)
            q = a.get("qte", 1)
            if isinstance(q, float) and q.is_integer():
                q = int(q)
            if not (isinstance(q, int) and q > 0) and q != "à préciser":
                raise RuntimeError("quantité invalide pour « %s » : %r" % (n, q))
            garde.append({"nom": n, "qte": q, "dims": str(a.get("dims") or "").strip(),
                          "fragile": bool(a.get("fragile"))})
        if garde:
            propres.append({"nom": nom, "articles": garde})
    return propres


# --- Recherche, dans l'ordre voulu par Samuel -------------------------------------------

class Deja(Exception):
    """L'inventaire trouvé a déjà été produit et envoyé : on s'arrête avant tout coût."""


class Recherche:
    """Porte l'état d'une recherche : registre, budget d'appels au modèle, erreurs locales.

    Une pièce jointe illisible ne doit pas empêcher de regarder la suivante : ses erreurs
    sont notées, et ne remontent (en alerte) que si rien n'a finalement été trouvé.
    """

    def __init__(self, deja, forcer, tmp):
        self.cles_connues = {d.get("cle") for d in deja}
        self.forcer, self.tmp = forcer, tmp
        self.appels, self.erreurs = 0, []

    def verifier(self, cle, source):
        if cle in self.cles_connues and not self.forcer:
            raise Deja(source, cle)

    def modele(self, texte=None, fichiers=()):
        if self.appels >= APPELS_MODELE_MAX:
            raise RuntimeError("budget de %d appels au modèle atteint" % APPELS_MODELE_MAX)
        self.appels += 1
        return structurer_par_modele(texte=texte, fichiers=fichiers, dossier_tmp=self.tmp)

    def depuis_texte(self, lignes, cle, source):
        self.verifier(cle, source)
        return parser_structure(lignes) or self.modele(texte="\n".join(lignes))

    def depuis_fichier(self, chemin, source):
        cle = empreinte("fichier", open(chemin, "rb").read())
        self.verifier(cle, source)
        texte = extraire_texte(chemin)
        if texte is not None:
            lignes = [l.strip() for l in texte.splitlines() if l.strip()]
            return parser_structure(lignes) or self.modele(texte=texte), cle
        return self.modele(fichiers=[chemin]), cle

    def essayer(self, source, action):
        try:
            return action()
        except Deja:
            raise
        except Exception as e:
            self.erreurs.append("%s : %s: %s" % (source, type(e).__name__, e))
            log("  ⚠ %s illisible — %s: %s" % (source, type(e).__name__, e))
            return None


def trouver_inventaire(r, dossier, lignes, fichiers_notion):
    """Rend (pieces, source, cle) ou (None, raison, None). Lève Deja si déjà envoyé."""
    # 1. Notion — texte de la section Inventaire
    texte = section_inventaire(lignes)
    if texte:
        src = "fiche Notion (section Inventaire)"
        cle = empreinte("notion-texte", "\n".join(texte))
        pieces = r.essayer(src, lambda: r.depuis_texte(texte, cle, src))
        if pieces:
            return pieces, src, cle
        log("Section Inventaire de la fiche : pas d'inventaire exploitable.")

    # 1 bis. Notion — fichiers rangés sous la section ou nommés « inventaire »
    for f in fichiers_notion:
        ext = os.path.splitext(f["nom"].lower())[1]
        if not (RE_INVENTAIRE.search(f["section"] or "") or RE_INVENTAIRE.search(f["nom"])):
            continue
        if ext not in EXT_DOCS and not (ext in EXT_IMAGES and RE_INVENTAIRE.search(f["nom"])):
            continue
        src = "fiche Notion (fichier « %s »)" % f["nom"]
        res = r.essayer(src, lambda: r.depuis_fichier(telecharger(f["url"], f["nom"], r.tmp), src))
        if res and res[0]:
            return res[0], src, res[1]

    # 2. noCRM — pièces jointes puis en-tête de description
    lead = r.essayer(crm.nom() + " (recherche de l'opportunité)", lambda: lead_du_client(dossier))
    if not lead:
        return None, "aucun inventaire sur la fiche, opportunité %s non appariée" % crm.nom(), None
    pjs = r.essayer(crm.nom() + " (liste des pièces jointes)", lambda: pieces_jointes_nocrm(lead["id"])) or []
    for pj in pjs:
        src = "%s (pièce jointe « %s »)" % (crm.nom(), pj.get("name"))
        res = r.essayer(src, lambda: r.depuis_fichier(telecharger_nocrm(lead["id"], pj, r.tmp), src))
        if res and res[0]:
            return res[0], src, res[1]
    tete = r.essayer(crm.nom() + " (description)", lambda: en_tete_nocrm(lead["id"])) or []
    if len(tete) >= 3 or any(RE_INVENTAIRE.search(l) for l in tete):
        src = crm.nom() + " (description de l'opportunité)"
        cle = empreinte("nocrm-texte", "\n".join(tete))
        pieces = r.essayer(src, lambda: r.depuis_texte(tete, cle, src))
        if pieces:
            return pieces, src, cle
    return None, "aucun inventaire trouvé (fiche Notion ni %s)" % crm.nom(), None


# --- Données du PDF, lues dans la fiche --------------------------------------------------

def _propre(valeur):
    """Coupe les mentions d'attente accolées (« — 🟡 à compléter ») ; vide si rien d'utile."""
    v = re.split(r"\s+—\s+|🟡", valeur or "", maxsplit=1)[0].strip(" :-")
    return "" if re.fullmatch(r"(à|a) (compléter|préciser|définir|confirmer)?\.?", v, re.I) else v


MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def date_et_creneau(dossier, lignes):
    m = dossier.get("mission") or {}
    date = _propre(m.get("date_intervention") or "")
    if not date and m.get("date_chargement"):
        brut = str(m["date_chargement"])[:10]
        try:
            j = datetime.date.fromisoformat(brut)
            date = "%d %s %d" % (j.day, MOIS[j.month - 1], j.year)
        except ValueError:
            date = brut
    creneau = ""
    for i, l in enumerate(lignes):
        if re.match(r"^\s*cr[ée]neau", l, re.I):
            apres = l.split(":", 1)[1].strip() if ":" in l else ""
            if not apres and i + 1 < len(lignes):
                apres = lignes[i + 1].strip()
            if re.search(r"\d{1,2}\s*h", apres):
                creneau = _propre(apres)
                break
    if date and creneau:
        return "%s — %s" % (date, creneau)
    return date or creneau


def dossier_pdf(dossier, lignes, pieces, volume, maj, indicatif=False, numero=""):
    c = dossier.get("client") or {}
    return {
        "indicatif": indicatif,
        "numero": numero,
        "nom": c.get("nom") or "",
        "prenom": c.get("prenom") or "",
        "date_demenagement": date_et_creneau(dossier, lignes),
        "adresse_depart": _propre((dossier.get("depart") or {}).get("adresse_brute")),
        "adresse_arrivee": _propre((dossier.get("arrivee") or {}).get("adresse_brute")),
        "volume_total": volume,
        "note_maj": maj,
        "pieces": pieces,
    }


# --- Chef d'orchestre ---------------------------------------------------------------------

def lire_dossier(page_id, token):
    """Une seule descente dans la page : corps (pour la fiche) + fichiers (pour la recherche).
    Transaction HubSpot : la fiche est sa note ; une ancienne page Notion n'apporte plus que ses fichiers."""
    if fn.est_transaction(page_id):
        dossier, lignes = fn.lire_fiche(page_id, token)
        fichiers, notion_id = [], (dossier.get("_meta") or {}).get("notion_id")
        if notion_id:
            try:
                fichiers = lire_page(notion_id, token)[1]
            except Exception as e:
                log("page Notion %s illisible, fichiers ignorés — %s: %s" % (notion_id, type(e).__name__, e))
        return dossier, lignes, fichiers
    lignes, fichiers = lire_page(page_id, token)
    dossier, _ = fn.parser_corps(lignes)
    props = fn._appel("%s/pages/%s" % (fn.API, page_id), token).get("properties", {})
    nom, prenom = fn._nom_prenom(fn.valeur_propriete(props.get("Nom client")) or "")
    dossier["client"]["nom"] = dossier["client"].get("nom") or nom
    dossier["client"]["prenom"] = dossier["client"].get("prenom") or prenom
    dossier["mission"]["date_chargement"] = fn.valeur_propriete(props.get("Date de chargement"))
    dossier["mission"]["commercial"] = fn.valeur_propriete(props.get("Commercial"))
    return dossier, lignes, fichiers


def joindre_au_crm(page_id, pdf, client, contact):
    """Copie du PDF sur la transaction HubSpot (Karim, 06/10/2026). Seulement quand HubSpot est
    écrit (interrupteur outils/crm.env sur hubspot ou les-deux) ; noCRM n'a jamais reçu le PDF.
    Un échec n'annule rien : le PDF est produit et parti sur WhatsApp."""
    if crm.actif() not in ("hubspot", "les-deux"):
        return
    import hubspot_crm
    statut, detail = hubspot_crm.joindre_pdf(page_id, str(pdf), "Inventaire de déménagement — %s" % client,
                                             tel=contact.get("tel"), email=contact.get("email"))
    log("%s : HubSpot — %s" % (client, detail))
    if statut == "echec":
        notif.alerte(quoi="l'inventaire PDF n'a pas été joint à la transaction HubSpot",
                     ou="inventaire_auto.py → HubSpot (hubspot_crm.joindre_pdf)",
                     cause=detail, dossier=client,
                     faire="Le PDF est prêt. Corriger la cause (un 403 = "
                           "droit « files » à ajouter à la clé HubSpot), puis le joindre seul : "
                           "python outils/pipeline/hubspot_crm.py --joindre-pdf \"%s\" --page-id %s"
                           % (pdf, page_id))


def traiter(page_id, volume=None, envoyer=True, forcer=False, chercher=False, sortie=None,
            indicatif=False, numero=""):
    page_id = page_id.replace("-", "")
    token = fn._token()
    dossier, lignes, fichiers = lire_dossier(page_id, token)
    c = dossier["client"]
    client = " ".join(x for x in ((c.get("nom") or "").upper(), c.get("prenom") or "") if x) or page_id

    def etat(statut, chemin=None, motif=None, envoi=None):
        """Dit à la relecture où en est l'inventaire. True : il attend la validation de Samuel."""
        if chercher or not envoyer:
            return False
        try:
            return validation_devis.noter_inventaire(page_id, statut, chemin, motif, envoi)
        except Exception as e:
            log("%s : état de relecture non écrit — %s: %s" % (client, type(e).__name__, e))
            return False

    # Visites de Christophe (Karim, 02/11/2026) : inventaire manuscrit, intervention humaine.
    # --forcer reste possible quand Samuel le demande.
    m = dossier["mission"]
    if not forcer and regles.dossier_christophe(m.get("commercial"), m.get("source_volume"),
                                                (dossier.get("_meta") or {}).get("notes")):
        log("%s : dossier de Christophe — inventaire laissé à la main." % client)
        etat("sans_objet", motif="dossier de Christophe, laissé à la main")
        return 0
    deja = registre(page_id)

    with tempfile.TemporaryDirectory(prefix="samdem-inv-") as tmp:
        r = Recherche(deja, forcer or chercher, tmp)
        try:
            pieces, source, cle = trouver_inventaire(r, dossier, lignes, fichiers)
        except Deja as d:
            log("%s : inventaire inchangé depuis le dernier envoi (%s) — rien à faire." % (client, d.args[0]))
            # Pas de nouveau PDF, mais celui déjà produit doit rejoindre HubSpot à la validation, et
            # l'équipe s'il ne lui est pas encore parti.
            connu = next((x for x in reversed(deja) if x.get("cle") == d.args[1]), {})
            produit = connu.get("fichier")
            if produit and os.path.isfile(produit):
                etat("pret", produit, envoi=connu if connu.get("attend_validation") else None)
            else:
                etat("erreur", motif="PDF déjà envoyé introuvable sur le disque")
            return 0
        if not pieces:
            log("%s : %s — rien à faire." % (client, source))
            if not r.erreurs:
                etat("aucun", motif=source)
            if r.erreurs:
                raise RuntimeError("aucun inventaire exploitable, et %d source(s) illisible(s) : %s"
                                   % (len(r.erreurs), " | ".join(r.erreurs)))
            return 0
        n_art = sum(len(p["articles"]) for p in pieces)
        log("%s : inventaire trouvé — %s (%d pièce(s), %d article(s), %d appel(s) au modèle)."
            % (client, source, len(pieces), n_art, r.appels))
        if chercher:
            print(json.dumps(pieces, ensure_ascii=False, indent=1))
            return 0

        volume = volume or (dossier.get("mission") or {}).get("volume_m3")
        if not volume:
            raise RuntimeError("volume inconnu (ni export du devis, ni fiche) : PDF impossible")

        import generer_inventaire as gi
        pdf, pages = gi.generer(dossier_pdf(dossier, lignes, pieces, volume, bool(deja), indicatif, numero),
                                sortie or gi.SORTIE_DEFAUT)
        log("%s : PDF produit — %s (%d page(s))." % (client, pdf, pages))

    entree = {"page_id": page_id, "cle": cle, "source": source, "fichier": str(pdf),
              "date": datetime.datetime.now().isoformat(timespec="seconds"), "envoye": False}
    if not envoyer:
        log("%s : envoi WhatsApp désactivé (--sans-envoi) — registre non modifié." % client)
        return 0
    if indicatif:
        # Devis indicatif (Karim, 12/10/2026) : l'inventaire va sur HubSpot seulement, jamais
        # sur la conversation WhatsApp de l'équipe.
        entree["indicatif"] = True
    # Une relecture en cours : HubSpot et l'équipe attendent la validation (Karim, 03/11/2026).
    attente = dict(entree, attend_validation=True)
    if etat("pret", str(pdf), envoi=None if indicatif else attente):
        inscrire(attente)
        log("%s : le PDF attend la validation du devis." % client)
        return 0
    if indicatif:
        inscrire(entree)
        joindre_au_crm(page_id, pdf, client, c)
        log("%s : devis indicatif — PDF joint à HubSpot seulement, pas d'envoi WhatsApp." % client)
        return 0
    ok, detail = notif.envoyer_fichier(str(pdf), "Inventaire — %s" % client)
    entree["envoye"] = ok
    # Inscrit même en échec : le PDF attend dans la file WhatsApp, le renvoyer à chaque export
    # du devis le dupliquerait.
    inscrire(entree)
    joindre_au_crm(page_id, pdf, client, c)
    if ok:
        log("%s : PDF envoyé sur WhatsApp." % client)
        return 0
    log("%s : envoi WhatsApp en échec — %s" % (client, detail))
    notif.alerte(quoi="l'inventaire PDF n'est pas parti sur WhatsApp",
                 ou="inventaire_auto.py → Beeper Desktop (notif.envoyer_fichier)",
                 cause="Beeper Desktop n'a pas accepté le fichier : %s" % detail,
                 dossier=client,
                 faire="Le PDF est prêt (%s) et attend dans la file. Ouvrir Beeper puis "
                       "lancer python outils/pipeline/notif.py --vider-file-attente" % pdf)
    return 1


def main():
    ap = argparse.ArgumentParser(description="Inventaire automatique après validation du devis")
    ap.add_argument("--page-id", required=True, help="fiche client Notion")
    ap.add_argument("--volume", type=float, help="volume du devis (m³) ; défaut : celui de la fiche")
    ap.add_argument("--sans-envoi", action="store_true", help="produire le PDF sans l'envoyer")
    ap.add_argument("--forcer", action="store_true", help="ignorer le registre des envois")
    ap.add_argument("--chercher", action="store_true", help="dire seulement ce qui est trouvé")
    ap.add_argument("--sortie", help="dossier du PDF (défaut : celui de Prod_inventaires)")
    ap.add_argument("--indicatif", action="store_true",
                    help="devis indicatif : « indicatif » dans le nom du PDF, joint à HubSpot "
                         "seulement, pas d'envoi WhatsApp")
    ap.add_argument("--numero", default="", help="numéro du devis, repris sur l'inventaire")
    a = ap.parse_args()
    try:
        return traiter(a.page_id, a.volume, not a.sans_envoi, a.forcer, a.chercher, a.sortie,
                       a.indicatif, a.numero)
    except Exception as e:
        trace = traceback.format_exc()
        log("ÉCHEC %s : %s: %s" % (a.page_id, type(e).__name__, e))
        print(trace, file=sys.stderr)
        if not (a.chercher or a.sans_envoi):
            try:
                validation_devis.noter_inventaire(a.page_id, "erreur", motif="%s: %s" % (type(e).__name__, e))
            except Exception:
                pass
        notif.alerte(quoi="l'inventaire automatique n'a pas pu être produit",
                     ou="inventaire_auto.py (après validation du devis)",
                     cause="%s : %s. Le devis, la fiche, le CRM et le message d'équipe sont "
                           "déjà faits — seul l'inventaire manque." % (type(e).__name__, e),
                     dossier=a.page_id,
                     faire="Relancer à la main : python outils/pipeline/inventaire_auto.py "
                           "--page-id %s — ou produire l'inventaire avec /inventaire-samdem."
                           % a.page_id,
                     trace=trace)
        return 3


if __name__ == "__main__":
    sys.exit(main())
