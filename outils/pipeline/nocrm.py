#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Derniere etape de la chaine devis : enrichir le dossier, puis le faire avancer dans noCRM.

    devis exporte -> fiche Notion remplie -> Google Sheet -> WhatsApp -> noCRM

Quatre gestes sur l'opportunite, DANS CET ORDRE (Karim, 10/09/2026) :
  1. DESCRIPTION — le corps de la fiche Notion est recopie dans le texte de l'opportunite.
     Le CRM cesse d'etre une coquille : le commercial y lit le dossier complet, chiffrage
     compris, sans ouvrir Notion. L'en-tete contact de noCRM (avant le « --- ») est
     conserve ; tout ce qui suit est remplace. Rejouer un export ne duplique donc rien.
  2. MONTANT — `amount` recoit le TTC. Quand la fiche porte plusieurs devis (variantes),
     c'est le PLUS ELEVE qui est retenu (Karim, 10/09/2026) : le CRM porte le potentiel du
     dossier, l'arbitrage entre variantes se fait a la signature.
  3. RAPPEL — statut « En attente », echeance a J+2, note « a relancer ». Un J+2 qui tombe
     un samedi ou un dimanche est REPORTE AU LUNDI : personne ne relance le week-end, et un
     rappel pose un samedi est un rappel perdu.
  4. COLONNE — le deplacement, et lui seul, reste la derniere etape.

Opportunite introuvable : elle est CREEE (titre, corps Notion, montant, commercial de la
fiche) puis suit les memes etapes. Un dossier chiffre ne doit pas rester hors du CRM.

Deux destinations, une seule regle :
  · « Devis envoye » par defaut ;
  · « Trajets Axe Paris » quand le demenagement touche l'Ile-de-France — cette colonne est
    APRES « Devis envoye » dans le tunnel, elle ne remplace donc pas l'information, elle la
    precise : le dossier a bien recu son devis, et il attend un appariement de groupage.

NB recherche : l'API v2 de noCRM n'a PAS de recherche serveur. `?query=`, `?search=` et `?q=`
sont acceptes puis ignores — ils renvoient les leads les plus recents, ce qui donnerait un
faux positif silencieux si on faisait confiance au premier resultat. On pagine donc et on
filtre en local, en s'arretant des qu'on trouve.

NB appariement : par TELEPHONE d'abord (un numero ne ment pas), puis e-mail, puis nom. Trois
garde-fous, parce qu'une opportunite deplacee au hasard coute plus cher qu'un dossier oublie :
  · en automatique, le NOM SEUL ne suffit pas — le dossier est signale, pas deplace ;
  · plusieurs candidats de meme rang = aucun deplacement, on rend la liste ;
  · apres le PUT, on RELIT le lead : « fait » n'est dit que si la colonne et le tag y sont.

NB filtres : `?step=<id ou nom>` fonctionne, `?step_id=` est IGNORE (200 + les leads les plus
recents). Verifier qu'un filtre a filtre, jamais se fier au code retour.

Configuration : ~/.claude/nocrm.env (ou outils/pipeline/nocrm.env)
    NOCRM_BASE_URL=https://samdemenage.nocrm.io/api/v2
    NOCRM_API_KEY=...

Usage :
    python nocrm.py --etapes                                   # colonnes du pipeline
    python nocrm.py --chercher "VIGNERON Lucile" --tel 06...   # trouve, n'ecrit rien
    python nocrm.py --corps --page-id <id>                     # ce qui SERAIT recopie
    python nocrm.py --devis-envoye "VIGNERON Lucile" --tel 06... --page-id <id> --appliquer
    python nocrm.py --devis-envoye "NOM Prenom" --axe-paris --appliquer
    python nocrm.py --lead 39484016 --etape 638965 --appliquer  # deplacement direct

Par defaut le script AFFICHE ce qu'il ferait et ne touche a rien : il faut --appliquer.
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ICI = os.path.dirname(os.path.abspath(__file__))
ENV_CANDIDATS = [
    os.environ.get("NOCRM_ENV"),
    os.path.join(ICI, "nocrm.env"),
    os.path.join(os.path.expanduser("~"), ".claude", "nocrm.env"),
]

PIPELINE = 121697                      # « Tunnel de vente », le seul pipeline
ETAPE_DEVIS_ENVOYE = 638965
ETAPE_AXE_PARIS = 730698

# Ile-de-France. Un demenagement qui touche l'un de ces departements est sur l'axe Paris :
# Sam'Demenage part de Bordeaux, il n'y a pas d'autre lecture possible.
DEPTS_IDF = ("75", "77", "78", "91", "92", "93", "94", "95")

# Les deux seuls tags de groupage en usage sur noCRM (convention Samuel). Le sens compte :
# une tournee ne se remplit pas de la meme facon a l'aller et au retour.
TAG_ALLER = "groupage:bordeaux-paris"      # depart hors IdF -> arrivee en IdF
TAG_RETOUR = "groupage:paris-bordeaux"     # depart en IdF -> arrivee hors IdF

# Colonnes depuis lesquelles on ne fait PAS reculer un dossier : elles sont apres « Devis
# envoye » dans le tunnel. Envoyer un avenant ne doit pas ramener en arriere un dossier
# deja en negociation.
ETAPES_AVAL = (ETAPE_AXE_PARIS, 638966)          # Trajets Axe Paris, Negociation

PAGES_MAX = 10                         # 10 x 100 = 1 000 leads au pire (691 au 05/10/2026)
PAR_PAGE = 100

# Colonne d'atterrissage d'une opportunite creee par le pipeline. Elle est ensuite deplacee
# comme les autres — la creation ne court-circuite pas la regle de colonne.
ETAPE_CREATION = ETAPE_DEVIS_ENVOYE

# Repli d'affectation quand la fiche Notion ne nomme pas de commercial, ou qu'il n'a pas de
# compte noCRM : le compte principal, resolu par son e-mail (l'id peut changer, pas l'adresse).
EMAIL_REPLI = "contact@samdemenage.fr"

# Enrichissement de la description : le corps Notion remplace tout ce qui suit cette ligne,
# l'en-tete contact genere par noCRM (« Prenom / Nom / Telephone / E-mail ») est conserve.
SEPARATEUR = "---"

# Rappel de relance pose sur l'opportunite.
JOURS_RAPPEL = 2
NOTE_RAPPEL = "à relancer"

# Rangs d'appariement, du plus sur au moins sur.
RANG_TEL, RANG_EMAIL, RANG_NOM = 3, 2, 1
# En automatique, on n'accepte QUE le telephone ou l'e-mail : un homonyme ne doit jamais
# faire bouger une opportunite. Le nom seul remonte un candidat, il ne declenche rien.
RANG_MINIMUM_AUTO = RANG_EMAIL


# --- Configuration -----------------------------------------------------------

def chemin_env():
    for c in ENV_CANDIDATS:
        if c and os.path.exists(c):
            return c
    return ENV_CANDIDATS[-1]


ENV = chemin_env()


def config():
    conf = {}
    if ENV and os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                k, v = ligne.split("=", 1)
                conf[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("NOCRM_BASE_URL", "NOCRM_API_KEY", "NOCRM_SUBDOMAIN"):
        if os.environ.get(k):
            conf[k] = os.environ[k]
    if not conf.get("NOCRM_BASE_URL") and conf.get("NOCRM_SUBDOMAIN"):
        conf["NOCRM_BASE_URL"] = "https://%s.nocrm.io/api/v2" % conf["NOCRM_SUBDOMAIN"]
    return conf


# --- Acces HTTP --------------------------------------------------------------

def _appel(chemin, params=None, data=None, methode="GET", conf=None):
    """Rend (ok, contenu). Ne leve jamais : l'appelant decide quoi faire d'un echec."""
    conf = conf or config()
    base, cle = conf.get("NOCRM_BASE_URL"), conf.get("NOCRM_API_KEY")
    if not base or not cle:
        return False, {"erreur": "NOCRM_BASE_URL ou NOCRM_API_KEY absent de %s" % ENV}
    url = base.rstrip("/") + "/" + chemin.lstrip("/")
    if params:
        url += "?" + urllib.parse.urlencode(params)
    corps = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=corps, method=methode,
                                 headers={"X-API-Key": cle, "Accept": "application/json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            texte = r.read().decode("utf-8")
            try:
                return True, json.loads(texte)
            except ValueError:
                return True, {"reponse": texte[:500]}
    except urllib.error.HTTPError as e:
        return False, {"http": e.code, "corps": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return False, {"erreur": str(e)}


def lots_leads(params=None, lots_max=PAGES_MAX, conf=None):
    """Parcourt /leads par lots de PAR_PAGE : rend (ok, lot) a chaque tour, `lot` sans doublon.
    Un echec est rendu une fois (ok False), puis le parcours s'arrete.

    noCRM IGNORE `page` (meme lot a chaque appel, code 200 — constate le 05/10/2026) : seul
    `offset` pagine. Garde-fous contre une boucle qui viderait le quota (2 000 requetes/jour) :
    `lots_max`, lot court, ou lot sans aucun id nouveau.
    """
    vus = set()
    for n in range(lots_max):
        ok, lot = _appel("/leads", dict(params or {}, limit=PAR_PAGE, offset=n * PAR_PAGE),
                         conf=conf)
        if not ok:
            yield False, lot
            return
        if not isinstance(lot, list):
            return
        neufs = [l for l in lot if l.get("id") not in vus]
        if not neufs:
            return
        vus.update(l.get("id") for l in neufs)
        yield True, neufs
        if len(lot) < PAR_PAGE:
            return


def etapes(pipeline_id=PIPELINE, conf=None):
    ok, rep = _appel("/steps", {"pipeline_id": pipeline_id}, conf=conf)
    return rep if ok and isinstance(rep, list) else []


# --- Normalisation -----------------------------------------------------------

def _plat(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def _tel(s):
    """« 06.22.36.18.60 », « +33 6 22 36 18 60 » -> « 622361860 » (les 9 chiffres utiles)."""
    chiffres = re.sub(r"\D", "", s or "")
    if not chiffres:
        return None
    return chiffres[-9:] if len(chiffres) >= 9 else None


def _mots(s):
    return {m for m in re.split(r"[^a-z0-9]+", _plat(s)) if len(m) > 1}


def separer_nom(nom, prenom=None):
    """« VIGNERON Lucile » en un seul argument : le mot en majuscules est le nom."""
    if prenom or " " not in (nom or ""):
        return nom, prenom
    bouts = nom.split()
    majs = [b for b in bouts if b.isupper() and len(b) > 1]
    if not majs:
        return nom, prenom
    return " ".join(majs), " ".join(b for b in bouts if b not in majs)


def _dept(adresse):
    """Departement d'une adresse francaise, d'apres son code postal. « Paris » sans code
    postal est reconnu a part : les fiches l'ecrivent souvent sans les 5 chiffres."""
    m = re.search(r"\b(\d{5})\b", adresse or "")
    if m:
        return m.group(1)[:2]
    if re.search(r"\bparis\b", _plat(adresse)):
        return "75"
    return None


# --- Recherche du lead -------------------------------------------------------

def _score(lead, tel, email, mots_nom):
    """Rang d'appariement : 3 telephone, 2 e-mail, 1 nom complet. 0 = pas ce lead.

    Le telephone et l'e-mail vivent dans la description du lead (« Téléphone: 06... »),
    pas dans un champ dedie : on cherche donc dans le texte entier.
    """
    texte = " ".join(str(lead.get(k) or "") for k in ("title", "description"))
    if tel and tel in re.sub(r"\D", "", texte):
        return 3
    if email and email in _plat(texte):
        return 2
    if mots_nom and mots_nom <= _mots(lead.get("title")):
        return 1
    return 0


def chercher_lead(nom=None, prenom=None, tel=None, email=None, pages=PAGES_MAX, conf=None):
    """Rend (lead, candidats, balayes, rang). `lead` est None si rien ou si c'est ambigu.

    `rang` dit SUR QUOI l'appariement a tenu : 3 telephone, 2 e-mail, 1 nom. L'appelant
    decide ce qu'il en fait — l'automatique refuse le rang 1.

    On trie par date de mise a jour decroissante : le dossier qu'on vient de chiffrer a
    forcement bouge recemment, il sort donc en general des la premiere page.
    """
    conf = conf or config()
    tel_n = _tel(tel)
    email_n = _plat(email) if email else None
    mots_nom = _mots(" ".join(x for x in (nom, prenom) if x))
    meilleurs, rang, balayes = [], 0, 0
    for ok, lot in lots_leads({"sort_by": "updated_at", "sort_order": "desc"}, pages, conf):
        if not ok:
            break
        balayes += len(lot)
        for lead in lot:
            s = _score(lead, tel_n, email_n, mots_nom)
            if s > rang:
                meilleurs, rang = [lead], s
            elif s and s == rang and lead["id"] not in [x["id"] for x in meilleurs]:
                meilleurs.append(lead)
        if rang == 3:                    # apparie par telephone : inutile de continuer
            break
    if len(meilleurs) == 1:
        return meilleurs[0], meilleurs, balayes, rang
    return None, meilleurs, balayes, rang


# --- Le corps de la fiche Notion, tel qu'on le colle dans le CRM --------------

def corps_notion(page_id, token=None):
    """Le corps de la fiche, rendu comme le donnerait un copier-coller depuis Notion.

    `lire_corps` produit du markdown minimal (« ### », « - ») utile aux parseurs ; ici on
    vise un humain qui lit une opportunite. On retire donc la syntaxe et on garde les cases
    (« [x] Formule confort »), qui portent une information.

    Texte brut, titres de section en « ━━ 𝗗𝗘́𝗣𝗔𝗥𝗧 ━━ » : c'est lui qu'on lit pour les montants et
    qu'on fusionne avec l'en-tete. La mise en page (espaces, bandeaux) est ajoutee a l'ecriture
    par `en_html`.
    """
    import fiche_notion as fn
    token = token or fn._token()
    trait = "_" * 30
    sortie = []
    for ligne in fn.lire_corps(str(page_id).replace("-", ""), token):
        t = ligne.strip()
        if t.startswith("### "):
            libelle = t[4:].strip().rstrip(" :")
            if libelle:
                sortie.append("━━ %s ━━" % gras(libelle.upper()))
            continue
        if t.startswith("- ["):                   # « - [x] ... » -> « [x] ... »
            t = t[2:]
        elif t.startswith("- "):
            t = t[2:]
        if t == "[divider]":
            # Rendu « --- », le trait couperait la description au mauvais endroit au prochain
            # passage (fusionner_description coupe sur cette ligne) : trait bas a la place.
            sortie.append(trait)
            continue
        # Les blocs Notion contiennent souvent des espaces doubles invisibles a l'ecran :
        # on les reduit, faute de quoi le texte du CRM differe d'un copier-coller humain.
        t = re.sub(r"[ \t\u00a0]{2,}", " ", t)
        if t:
            sortie.append(t)
    return "\n".join(sortie)


def gras(texte):
    """« DÉPART » -> « 𝗗𝗘́𝗣𝗔𝗥𝗧 » : lettres et chiffres en gras Unicode sans empattement.

    noCRM n'interprete aucune mise en forme dans une description : le gras doit etre porte par
    les caracteres eux-memes. Les accents deviennent des diacritiques combinants, les autres
    signes restent tels quels.
    """
    sortie = []
    for c in unicodedata.normalize("NFD", texte):
        if "A" <= c <= "Z":
            sortie.append(chr(0x1D5D4 + ord(c) - ord("A")))
        elif "a" <= c <= "z":
            sortie.append(chr(0x1D5EE + ord(c) - ord("a")))
        elif "0" <= c <= "9":
            sortie.append(chr(0x1D7EC + ord(c) - ord("0")))
        else:
            sortie.append(c)
    return "".join(sortie)


RE_TITRE = re.compile(r"^━━ (.+) ━━$")
BANDEAU = "━" * 23


def en_html(texte):
    """La description telle que noCRM l'affiche avec des espaces (Karim, 16/09/2026).

    Envoyee en texte brut, la description est rendue sans aucun saut de paragraphe. noCRM
    accepte du HTML dans `description` (verifie le 16/09/2026) — c'est ce que produit un
    copier-coller depuis Google Docs. Chaque titre de section devient un bandeau precede d'un
    paragraphe vide ; les lignes d'un meme bloc restent groupees.
    """
    blocs, courant = [], []

    def clore():
        if courant:
            blocs.append("<p>%s</p>" % "<br>".join(courant))
            courant.clear()

    for ligne in (texte or "").split("\n"):
        t = ligne.strip()
        m = RE_TITRE.match(t)
        if m:
            clore()
            blocs.append("<p>&nbsp;</p><p><strong>%s<br>━━ %s ━━<br>%s</strong></p>"
                         % (BANDEAU, html.escape(m.group(1)), BANDEAU))
        elif t == SEPARATEUR or (t and set(t) == {"_"}):
            clore()
            blocs.append("<p>%s</p>" % t)
        elif not t:
            clore()
        else:
            courant.append(_ligne_html(t))
    clore()
    return "".join(blocs)


def _ligne_html(t):
    """« Étage : 4 » -> libelle en gras, comme les tableaux colles a la main."""
    libelle, sep, valeur = t.partition(" :")
    if sep and 0 < len(libelle) <= 40 and not libelle.startswith("["):
        return "<strong>%s :</strong>%s" % (html.escape(libelle), html.escape(valeur))
    return html.escape(t)


def fusionner_description(existante, corps):
    """Garde l'en-tete de l'opportunite, remplace ce qui suit le premier « --- ».

    Trois cas, un seul comportement stable :
      · description avec « --- » (cas courant, l'en-tete contact vient du formulaire noCRM) :
        l'en-tete est garde tel quel, la suite est remplacee — donc idempotent ;
      · description sans « --- » : elle est gardee ENTIEREMENT et le corps s'ajoute dessous,
        derriere un « --- ». On ne detruit pas une note tapee a la main par un commercial ;
      · description vide : le corps seul.
    """
    tete = ""
    if existante and existante.strip():
        lignes = existante.split("\n")
        coupe = next((i for i, l in enumerate(lignes) if l.strip() == SEPARATEUR), None)
        # Sans « --- » mais avec nos titres de section : c'est une opportunite creee par le
        # pipeline, tout le texte vient de Notion — on le remplace au lieu de l'empiler.
        if coupe is None and any(RE_TITRE.match(l.strip()) for l in lignes):
            return corps
        tete ="\n".join(lignes[:coupe] if coupe is not None else lignes).rstrip()
    if not tete:
        return corps
    return "%s\n%s\n%s" % (tete, SEPARATEUR, corps)


def completer_entete(existante, tel=None, email=None):
    """Ajoute a l'en-tete contact le telephone / l'e-mail de la fiche qu'il ne porte pas.

    Sert apres un appariement par le NOM valide a la main : la fiche porte d'autres
    coordonnees que le lead, et sans elles le passage suivant retomberait sur le nom seul.
    Les lignes vont AVANT le « --- », que `fusionner_description` conserve.
    """
    texte = existante or ""
    ajouts = []
    if _tel(tel) and _tel(tel) not in re.sub(r"\D", "", texte):
        ajouts.append("Téléphone (fiche Notion): %s" % tel.strip())
    if email and _plat(email) not in _plat(texte):
        ajouts.append("E-mail (fiche Notion): %s" % email.strip())
    if not ajouts:
        return existante, []
    lignes = texte.split("\n")
    coupe = next((i for i, l in enumerate(lignes) if l.strip() == SEPARATEUR), None)
    if coupe is None:
        return (texte.rstrip() + "\n" if texte.strip() else "") + "\n".join(ajouts), ajouts
    return "\n".join(lignes[:coupe] + ajouts + lignes[coupe:]), ajouts


def commande_rattrapage(ligne, page_id=None):
    """La commande qui rejoue TOUT l'avancement (description, montant, rappel, colonne) sur
    un lead apparie par le nom seul. `--lead/--etape` ne ferait que deplacer la colonne."""
    l = ligne or {}
    args = ['python outils/pipeline/nocrm.py --devis-envoye "%s"' % (l.get("client_nom") or "")]
    for opt, cle in (("--prenom", "client_prenom"), ("--tel", "telephone"),
                     ("--email", "email"), ("--depart", "adresse_depart"),
                     ("--arrivee", "adresse_arrivee"), ("--commercial", "commercial")):
        v = l.get(cle)
        if v:
            args.append('%s "%s"' % (opt, str(v).replace('"', "'")))
    if page_id:
        args.append("--page-id %s" % page_id)
    args.append("--sur-le-nom --appliquer")
    return " ".join(args)


# « Prix Total : 2 995,00 € TTC ». Le « HT » de la ligne au-dessus (« Prix Total HT : ... »)
# ne peut pas etre confondu : le deux-points doit suivre « Total » immediatement.
RE_TTC = re.compile(r"Prix\s+Total\s*:\s*([0-9][0-9\s  .,]*)\s*€\s*TTC", re.I)


def montants_ttc(corps):
    """Tous les totaux TTC ecrits dans le corps, dans l'ordre. Un par bloc de chiffrage."""
    trouves = []
    for m in RE_TTC.finditer(corps or ""):
        brut = re.sub(r"[^0-9,.]", "", m.group(1))
        # Format francais : le point separe les milliers, la virgule les decimales.
        brut = brut.replace(".", "").replace(",", ".")
        try:
            v = round(float(brut), 2)
        except ValueError:
            continue
        if v > 0:
            trouves.append(v)
    return trouves


def montant_retenu(corps):
    """Le TTC a poser dans l'opportunite : le PLUS ELEVE des devis de la fiche.

    Regle changee par Samuel le 10/09/2026 (elle etait au plus faible le matin meme).

    Rend (montant, tous). `tous` sert au message : « 3 devis, le plus élevé retenu » se lit,
    « 2 995 € » tout seul laisse croire qu'il n'y en avait qu'un.
    """
    tous = montants_ttc(corps)
    return (max(tous) if tous else None), tous


# --- Rappel de relance -------------------------------------------------------

def date_rappel(depuis=None, jours=JOURS_RAPPEL):
    """J+`jours`, reporte au lundi si l'echeance tombe un samedi ou un dimanche.

    On ne relance pas le week-end : un rappel pose un samedi est vu le lundi au mieux, et
    perdu au pire. Le report vaut pour le seul week-end — les jours feries ne sont pas
    traites, faute de calendrier fiable et parce qu'ils ne coutent qu'un jour de decalage.
    """
    d = (depuis or datetime.date.today()) + datetime.timedelta(days=jours)
    if d.weekday() >= 5:                      # 5 = samedi, 6 = dimanche
        d += datetime.timedelta(days=7 - d.weekday())
    return d.isoformat()


# --- Ecriture sur l'opportunite ----------------------------------------------

def _norme(s):
    """Compare deux textes sans se laisser piquer par les espaces : noCRM re-rend la
    description (insecables, retours a la ligne) et un octet d'ecart ne prouve rien."""
    # Les bandeaux « ━━━ » n'existent que dans la version HTML : on les ignore des deux cotes.
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ").replace("━", "")).strip()


def enrichir(lead_id, description=None, montant=None, rappel=None, conf=None):
    """Ecrit description / montant / rappel sur l'opportunite, PUIS relit pour confirmer.

    La relecture n'est pas une precaution de style : noCRM repond 200 a un champ qu'il ne
    connait pas et l'ignore en silence (verifie le 10/09/2026). Sans relecture, une faute de
    frappe dans un nom de champ passerait pour un succes a chaque dossier.

    Rend (ok, faits, ecarts) — `faits` et `ecarts` sont des listes de messages courts.
    """
    charge = {}
    if description is not None:
        charge["description"] = en_html(description)
    if montant is not None:
        charge["amount"] = float(montant)
    if rappel:
        charge["status"] = "standby"          # « En attente » : le statut qui porte un rappel
        charge["remind_date"] = rappel
        charge["reminder_note"] = NOTE_RAPPEL
    if not charge:
        return True, [], []

    ok, rep = _appel("/leads/%s" % lead_id, data=charge, methode="PUT", conf=conf)
    if not ok:
        return False, [], ["écriture refusée — %s" % rep]

    ok2, relu = _appel("/leads/%s" % lead_id, conf=conf)
    if not ok2 or not isinstance(relu, dict):
        return True, ["écrit (non relu : %s)" % rep], []

    faits, ecarts = [], []
    if description is not None:
        if _norme(relu.get("description")) == _norme(description):
            faits.append("description reprise de Notion (%d caractères)" % len(description))
        else:
            ecarts.append("description non confirmée à la relecture "
                          "(%d caractères envoyés, %d relus)"
                          % (len(description), len(relu.get("description") or "")))
    if montant is not None:
        if abs((relu.get("amount") or 0) - float(montant)) < 0.01:
            faits.append("montant %s € TTC" % ("%.2f" % float(montant)).replace(".", ","))
        else:
            ecarts.append("montant non enregistré (relu : %s)" % relu.get("amount"))
    if rappel:
        heure = relu.get("remind_time")
        if relu.get("remind_date") != rappel and heure:
            # Un rappel deja pose AVEC une heure (par un commercial) fige sa date : noCRM ignore
            # une nouvelle remind_date envoyee seule, et repond 200 (verifie le 21/09/2026). Il
            # l'accepte si l'heure l'accompagne : on renvoie la date avec l'heure existante.
            _appel("/leads/%s" % lead_id, methode="PUT", conf=conf,
                   data={"status": "standby", "remind_date": rappel, "remind_time": heure,
                         "reminder_note": NOTE_RAPPEL})
            ok3, relu3 = _appel("/leads/%s" % lead_id, conf=conf)
            if ok3 and isinstance(relu3, dict):
                relu = relu3
        if relu.get("remind_date") == rappel and relu.get("status") == "standby":
            faits.append("rappel « %s » le %s%s" % (
                NOTE_RAPPEL, rappel,
                " à %s (heure du rappel existant)" % heure if heure else ""))
        else:
            ecarts.append("rappel non posé (relu : statut %s, date %s)"
                          % (relu.get("status"), relu.get("remind_date")))
    return not ecarts, faits, ecarts


def utilisateur_pour(commercial, conf=None):
    """Id noCRM du commercial nomme sur la fiche Notion. Repli sur le compte principal.

    Rend (user_id, explication). Un id None laisse noCRM affecter par defaut plutot que de
    faire echouer une creation : mieux vaut une opportunite mal affectee qu'aucune.
    """
    ok, us = _appel("/users", conf=conf)
    if not ok or not isinstance(us, list) or not us:
        return None, "liste des utilisateurs noCRM illisible"
    actifs = [u for u in us if not u.get("is_disabled")]
    if commercial:
        cible = _mots(commercial)
        for u in actifs:
            nom = _mots("%s %s" % (u.get("firstname") or "", u.get("lastname") or ""))
            # Un mot commun suffit : les fiches ecrivent « Samuel », « Cohen » ou « S. Cohen ».
            if cible & nom:
                return u.get("id"), "commercial de la fiche : %s" % (commercial or "")
    for u in actifs:
        if _plat(u.get("email")) == _plat(EMAIL_REPLI):
            motif = ("aucun commercial sur la fiche" if not commercial
                     else "« %s » sans compte noCRM" % commercial)
            return u.get("id"), "%s — affecté au compte principal" % motif
    return None, "aucun utilisateur retenu — affectation laissée à noCRM"


def creer_lead(titre, description=None, montant=None, user_id=None,
               step_id=ETAPE_CREATION, conf=None):
    """Cree l'opportunite absente du CRM, puis la relit. Rend (lead, message).

    Le titre suit la convention des opportunites existantes : « NOM Prenom ».
    """
    charge = {"title": titre, "pipeline_id": PIPELINE, "step_id": step_id}
    if description is not None:
        charge["description"] = en_html(description)
    if montant is not None:
        charge["amount"] = float(montant)
    if user_id:
        charge["user_id"] = user_id
    ok, rep = _appel("/leads", data=charge, methode="POST", conf=conf)
    if not ok or not isinstance(rep, dict) or not rep.get("id"):
        return None, "création refusée — %s" % rep
    ok2, relu = _appel("/leads/%s" % rep["id"], conf=conf)
    return (relu if ok2 and isinstance(relu, dict) else rep), "créée (lead %s)" % rep["id"]


# --- Regle de colonne --------------------------------------------------------

def axe_paris(depart, arrivee):
    """Vrai quand un bout du trajet est en Ile-de-France et l'autre non."""
    d, a = _dept(depart), _dept(arrivee)
    if not d or not a:
        return False
    return (d in DEPTS_IDF) != (a in DEPTS_IDF)


def tag_axe(depart, arrivee):
    """Le tag de groupage, dans le sens du trajet. None hors axe Paris."""
    if not axe_paris(depart, arrivee):
        return None
    return TAG_RETOUR if _dept(depart) in DEPTS_IDF else TAG_ALLER


def etape_cible(depart=None, arrivee=None):
    """Rend (step_id, motif, tag). Le tag n'existe que sur l'axe Paris."""
    tag = tag_axe(depart, arrivee)
    if tag:
        return ETAPE_AXE_PARIS, "trajet Bordeaux ↔ Île-de-France — groupage axe Paris", tag
    return ETAPE_DEVIS_ENVOYE, "devis envoyé", None


# --- Deplacement -------------------------------------------------------------

def _tags(lead):
    """Les tags d'un lead, en chaines. L'API les rend en liste de chaines, mais on ne parie
    pas la-dessus : un objet {name: ...} ne doit pas se transformer en tag illisible."""
    sortie = []
    for t in (lead or {}).get("tags") or []:
        nom = t if isinstance(t, str) else (t.get("name") or t.get("tag") if isinstance(t, dict) else None)
        if nom:
            sortie.append(nom)
    return sortie


def deplacer(lead_id, step_id, tag=None, conf=None):
    """Deplace le lead, pose le tag, puis RELIT pour confirmer.

    Le tag est ajoute aux tags existants, jamais substitue : l'API remplace la liste
    entiere, envoyer le seul tag de groupage effacerait les autres.
    """
    charge = {"step_id": step_id}
    avant = {}
    if tag:
        ok0, avant = _appel("/leads/%s" % lead_id, conf=conf)
        anciens = _tags(avant if ok0 else {})
        if tag not in anciens:
            charge["tags"] = anciens + [tag]
    ok, rep = _appel("/leads/%s" % lead_id, data=charge, methode="PUT", conf=conf)
    if not ok:
        return False, rep
    ok2, relu = _appel("/leads/%s" % lead_id, conf=conf)
    if not ok2 or not isinstance(relu, dict):
        return True, rep                       # ecrit, mais pas relu : on ne surinterprete pas
    if relu.get("step_id") != step_id:
        return False, {"erreur": "le lead est resté en « %s »" % relu.get("step")}
    if tag and tag not in _tags(relu):
        return False, {"erreur": "colonne changée mais tag « %s » non posé" % tag,
                       "tags": _tags(relu)}
    return True, relu


def avancer_dossier(ligne, appliquer=False, conf=None, rang_minimum=RANG_MINIMUM_AUTO,
                    page_id=None, token=None):
    """Point d'entree de la chaine devis. `ligne` = la ligne d'archive de finalisation.py
    (client_nom, client_prenom, telephone, email, commercial, adresse_depart/arrivee).

    `page_id` (+ `token`) donne acces au corps de la fiche Notion : sans lui, l'opportunite
    est seulement deplacee, comme avant. Avec lui, elle est d'abord enrichie — description,
    montant, rappel — puis deplacee.

    Rend (ok, message). Ne leve jamais : le devis est parti, la fiche est ecrite — un CRM
    injoignable ne doit pas transformer une finalisation reussie en echec.
    """
    try:
        l = ligne or {}
        conf = conf or config()
        if not conf.get("NOCRM_API_KEY"):
            return False, "config noCRM absente (%s)" % ENV
        nom, prenom = l.get("client_nom") or "", l.get("client_prenom") or ""
        cible, motif, tag = etape_cible(l.get("adresse_depart") or l.get("commune_depart"),
                                        l.get("adresse_arrivee") or l.get("commune_arrivee"))

        # Le corps de la fiche est lu UNE fois : il porte a la fois le texte a recopier et
        # les totaux TTC. Illisible, il ne bloque rien — le deplacement garde tout son sens.
        corps, ttc, tous, souci = None, None, [], None
        if page_id:
            try:
                corps = corps_notion(page_id, token)
                ttc, tous = montant_retenu(corps)
                if not tous:
                    souci = "aucun « Prix Total : … € TTC » dans la fiche — montant non écrit"
            except Exception as e:
                souci = "corps Notion illisible (%s: %s) — description et montant non écrits" \
                        % (type(e).__name__, e)

        lead, candidats, balayes, rang = chercher_lead(
            nom, prenom, l.get("telephone"), l.get("email"), conf=conf)

        # Garde-fous d'appariement : aucun ne doit conduire a ECRIRE sur le mauvais dossier.
        # Un homonyme enrichi avec le devis d'un autre client est pire qu'un dossier oublie.
        if lead is not None and rang < rang_minimum:
            return False, ("« %s » (lead %s) trouvé sur le NOM seul — non touché. "
                           "Vérifier que c'est le même client, puis : %s"
                           % (lead.get("title"), lead["id"], commande_rattrapage(l, page_id)))
        if lead is None and candidats:
            return False, ("%d leads correspondent, aucune écriture : %s"
                           % (len(candidats),
                              " · ".join("%s (%s)" % (c.get("title"), c.get("id"))
                                         for c in candidats[:5])))

        rappel = date_rappel()
        journal = []
        cree = False

        if lead is None:
            # Zero candidat : le dossier n'existe pas au CRM, on l'y fait entrer.
            titre = ("%s %s" % (nom, prenom)).strip() or (l.get("client_nom") or "Sans nom")
            if not appliquer:
                return True, ("à créer : « %s » en « %s »%s (%d leads balayés)"
                              % (titre, _nom_etape(cible, conf),
                                 ", %s € TTC" % ttc if ttc else "", balayes))
            uid, motif_uid = utilisateur_pour(l.get("commercial"), conf=conf)
            lead, msg = creer_lead(titre, corps, ttc, uid, conf=conf)
            if lead is None:
                return False, "aucun lead trouvé pour « %s » et %s" % (titre, msg)
            cree, journal = True, ["opportunité créée (%s)" % motif_uid]
            if corps:
                journal.append("description reprise de Notion (%d caractères)" % len(corps))
            if ttc:
                journal.append("montant %s € TTC" % ("%.2f" % ttc).replace(".", ","))

        appariement = ("créée" if cree
                       else {RANG_TEL: "téléphone", RANG_EMAIL: "e-mail"}.get(rang, "nom"))

        if not appliquer:
            gestes = [g for g in ("description" if corps else None,
                                  "montant %s € TTC" % ttc if ttc else None,
                                  "rappel du %s" % rappel) if g]
            return True, ("à enrichir (%s) puis « %s » → « %s » (%s) — lead %s, apparié par %s"
                          % (", ".join(gestes), lead.get("step"), _nom_etape(cible, conf),
                             motif, lead["id"], appariement))

        # Apparie par le nom (valide a la main) : l'en-tete recoit les coordonnees de la fiche,
        # pour que le prochain passage retrouve le lead par telephone ou e-mail.
        existante, ajouts = lead.get("description"), []
        if rang == RANG_NOM and not cree and corps:
            existante, ajouts = completer_entete(existante, l.get("telephone"), l.get("email"))

        # 1-3. Enrichissement. Une opportunite qu'on vient de creer porte deja description et
        # montant : on ne lui repasse que le rappel, qui n'existe pas a la creation.
        ok_e, faits, ecarts = enrichir(
            lead["id"],
            description=None if cree else (fusionner_description(existante, corps)
                                           if corps else None),
            montant=None if cree else ttc,
            rappel=rappel, conf=conf)
        journal += faits
        if ajouts and any(f.startswith("description") for f in faits):
            journal.append("en-tête complété (%s)" % " ; ".join(ajouts))
        if souci:
            ecarts = [souci] + ecarts

        # 4. Colonne — derniere etape, inchangee.
        if lead.get("step_id") == cible and not cree:
            journal.append("déjà en « %s »" % lead.get("step"))
        elif lead.get("step_id") in ETAPES_AVAL and cible == ETAPE_DEVIS_ENVOYE:
            journal.append("laissé en « %s » (colonne en aval de « Devis envoyé »)"
                           % lead.get("step"))
        else:
            ok_d, rep = deplacer(lead["id"], cible, tag=tag, conf=conf)
            if ok_d:
                journal.append("« %s » → « %s » (%s%s)"
                               % (lead.get("step"), _nom_etape(cible, conf), motif,
                                  ", tag « %s »" % tag if tag else ""))
            else:
                ecarts.append("déplacement refusé — %s" % rep)

        if len(tous) > 1:
            journal.append("%d devis sur la fiche, le plus élevé retenu (%s)"
                           % (len(tous), " / ".join("%.0f" % t for t in sorted(tous))))
        entete = "lead %s, apparié par %s" % (lead["id"], appariement)
        texte = "%s — %s" % (entete, " ; ".join(journal) or "rien à faire")
        if ecarts:
            return False, "%s ⚠ %s" % (texte, " ; ".join(ecarts))
        return True, texte
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def _nom_etape(step_id, conf=None):
    for e in etapes(conf=conf):
        if e.get("id") == step_id:
            return e.get("name")
    return str(step_id)


# --- CLI ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Pipeline noCRM — avancement d'un dossier")
    ap.add_argument("--etapes", action="store_true", help="lister les colonnes du pipeline")
    ap.add_argument("--chercher", metavar="NOM", help="trouver le lead, sans rien écrire")
    ap.add_argument("--description", metavar="NOM",
                    help="afficher la description du lead : source d'une fiche Notion à créer")
    ap.add_argument("--devis-envoye", metavar="NOM", help="déplacer après envoi du devis")
    ap.add_argument("--prenom")
    ap.add_argument("--tel")
    ap.add_argument("--email")
    ap.add_argument("--depart", help="adresse de départ (détection de l'axe Paris)")
    ap.add_argument("--arrivee", help="adresse d'arrivée (détection de l'axe Paris)")
    ap.add_argument("--axe-paris", action="store_true", help="forcer la colonne axe Paris")
    ap.add_argument("--tag", help="tag à poser en plus (ajouté, jamais substitué)")
    ap.add_argument("--sur-le-nom", action="store_true",
                    help="accepter un appariement par le nom seul (refusé en automatique)")
    ap.add_argument("--lead", type=int, help="déplacement direct : id du lead")
    ap.add_argument("--etape", type=int, help="déplacement direct : id de la colonne")
    ap.add_argument("--page-id", help="fiche Notion à recopier dans l'opportunité")
    ap.add_argument("--commercial", help="commercial de la fiche (affectation à la création)")
    ap.add_argument("--corps", action="store_true",
                    help="afficher le corps Notion et les TTC lus, sans rien écrire")
    ap.add_argument("--appliquer", action="store_true", help="écrire dans noCRM")
    a = ap.parse_args()

    conf = config()
    if not conf.get("NOCRM_API_KEY"):
        print("Config noCRM absente : %s" % ENV)
        return 1

    if a.etapes:
        for e in etapes(conf=conf):
            print("%8s  %s" % (e.get("id"), e.get("name")))
        return 0

    if a.corps:
        # Voie de controle : voir ce qui SERAIT recopie, et quel TTC serait retenu.
        if not a.page_id:
            ap.error("--corps demande --page-id")
        corps = corps_notion(a.page_id)
        retenu, tous = montant_retenu(corps)
        print(corps)
        print("\n--- %d ligne(s), %d caractère(s)" % (len(corps.splitlines()), len(corps)))
        print("TTC lus : %s" % (" / ".join("%.2f" % t for t in tous) or "aucun"))
        print("TTC retenu : %s" % (retenu if retenu is not None else "aucun"))
        print("Rappel qui serait posé : %s (« %s »)" % (date_rappel(), NOTE_RAPPEL))
        return 0

    if a.lead and a.etape:
        # Voie manuelle : l'humain a designe le lead, on ne cherche rien et on ne devine rien.
        tag = a.tag or (TAG_ALLER if a.axe_paris else None)
        if not a.appliquer:
            print("Déplacerait le lead %s vers « %s »%s."
                  % (a.lead, _nom_etape(a.etape, conf), " + tag « %s »" % tag if tag else ""))
            return 0
        ok, rep = deplacer(a.lead, a.etape, tag=tag, conf=conf)
        if ok:
            print("Déplacement : OK — lead %s en « %s »%s"
                  % (a.lead, rep.get("step") if isinstance(rep, dict) else a.etape,
                     ", tags %s" % _tags(rep) if tag else ""))
        else:
            print("Déplacement : ÉCHEC — %s" % rep)
        return 0 if ok else 1

    if a.description:
        # Fiche Notion absente : la description de l'opportunite est la source de la fiche a
        # creer (/creer-fiche-client-samdem). Lecture seule : le nom seul suffit a apparier.
        nom, prenom = separer_nom(a.description, a.prenom)
        lead, candidats, _, _ = chercher_lead(nom, prenom, a.tel, a.email, conf=conf)
        if lead is None:
            for c in candidats:
                print("  ? %s (%s) — %s" % (c.get("title"), c.get("id"), c.get("step")))
            print("Aucun lead retenu%s." % (" (ambigu)" if candidats else ""))
            return 1
        ok, detail = _appel("/leads/%s" % lead["id"], conf=conf)
        detail = detail if ok and isinstance(detail, dict) else lead
        user = detail.get("user") or {}
        print("Lead : %s (%s) — colonne « %s » — commercial : %s — créé le %s"
              % (detail.get("title"), detail.get("id"), detail.get("step"),
                 " ".join(x for x in (user.get("firstname"), user.get("lastname")) if x)
                 or "non renseigné", (detail.get("created_at") or "")[:10]))
        print("---")
        print(detail.get("description") or "(description vide)")
        return 0

    nom = a.chercher or a.devis_envoye
    if not nom:
        ap.error("--etapes, --chercher, --description, --devis-envoye ou --lead/--etape requis")

    nom, prenom = separer_nom(nom, a.prenom)

    lead, candidats, balayes, rang = chercher_lead(nom, prenom, a.tel, a.email, conf=conf)
    print("%d leads balayés." % balayes)
    if lead is None:
        for c in candidats:
            print("  ? %s (%s) — %s" % (c.get("title"), c.get("id"), c.get("step")))
        print("Aucun lead retenu%s." % (" (ambigu)" if candidats else ""))
        # Un dossier absent du CRM n'est plus une impasse : avancer_dossier() le cree. On ne
        # sort ici que si l'appariement est AMBIGU (creer serait fabriquer un doublon) ou si
        # l'appel ne demandait qu'une recherche.
        if candidats or a.chercher:
            return 1
    else:
        print("Lead : %s (%s) — colonne « %s », apparié par %s"
              % (lead.get("title"), lead["id"], lead.get("step"),
                 {RANG_TEL: "téléphone", RANG_EMAIL: "e-mail"}.get(rang, "nom seul")))
        if a.chercher:
            return 0

    ligne = {"client_nom": nom, "client_prenom": prenom, "telephone": a.tel, "email": a.email,
             "adresse_depart": a.depart, "adresse_arrivee": a.arrivee,
             "commercial": a.commercial}
    if a.axe_paris and lead:
        tag = tag_axe(a.depart, a.arrivee) or TAG_ALLER
        if not a.appliquer:
            print("noCRM : à déplacer vers « %s » + tag « %s » (forcé)"
                  % (_nom_etape(ETAPE_AXE_PARIS, conf), tag))
            return 0
        ok, rep = deplacer(lead["id"], ETAPE_AXE_PARIS, tag=tag, conf=conf)
        print("noCRM : %s%s" % ("OK — axe Paris, tag « %s »" % tag if ok else "ÉCHEC — ",
                                "" if ok else rep))
        return 0 if ok else 1
    # --sur-le-nom : l'humain a vu le candidat et l'assume ; l'automatique, lui, refuse.
    ok, msg = avancer_dossier(ligne, appliquer=a.appliquer, conf=conf,
                              rang_minimum=RANG_NOM if a.sur_le_nom else RANG_MINIMUM_AUTO,
                              page_id=a.page_id)
    print("noCRM : %s" % msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
