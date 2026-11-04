#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Devis PDF automatique (Karim, 02/11/2026) : à l'export, la chaîne produit le PDF du devis et le
garde en local (Karim, 03/11/2026). Samuel le vérifie, puis l'envoie au client.

Écrit la même spec que le skill devis-pdf-samdem (donnees/Devis SamDem\\specs\\), à partir de
l'export (montants, volume, équipe, matériel) et de la fiche Notion (client, adresses, date,
accès, options, inventaire), puis la confie à outils/pipeline/devis-pdf/generer_devis_pdf.py : une seule
mise en page. Ce script ne recalcule aucun prix, et brouillon_envoi.py relit la spec telle quelle.

Reste à la main, sans PDF, avec le motif dans le message : relivraison, étape intermédiaire,
chargement ou déchargement seul, montants qui ne retombent pas sur le total de l'export.

Les notes de la fiche sont internes (Karim, 02/11/2026) : aucune ne passe dans le PDF, qui reste
le modèle existant, sans consigne ni condition propre au dossier.

Dossier de Christophe (visite, inventaire manuscrit) : ni liste dans le devis, ni PDF
d'inventaire. L'inventaire reste une intervention humaine.

Usage (contrôle, rien n'est envoyé) :
    python devis_auto.py <export.json> [--sortie <dossier>]
"""

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.normpath(os.path.join(ICI, "..", ".."))
sys.path.insert(0, ICI)

import fiche_notion as fn                          # noqa: E402
import inventaire_auto as ia                       # noqa: E402
import regles                                      # noqa: E402

GENERATEUR = os.path.join(ICI, "devis-pdf", "generer_devis_pdf.py")
DOSSIER_DEVIS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "donnees", "Devis SamDem"))
EXPORTS = os.path.join(regles.DEVIS_GENERES, "exports")
ANNULATION = "J-14 avant la date du déménagement."
ECART_TRANSPORT_MAX = 1.0                           # € HT : l'arrondi du TTC, rien de plus
INVENTAIRE_MAX_LIGNES = 10

MATERIEL = [("standard", "carton standard", "cartons standards"),
            ("livres", "carton livres", "cartons livres"),
            ("vaisselle", "carton vaisselle", "cartons vaisselle"),
            ("bouteilles", "carton bouteilles", "cartons bouteilles"),
            ("penderies", "carton penderie", "cartons penderies"),
            ("informatiques", "carton informatique", "cartons informatiques"),
            ("tableaux", "carton tableaux", "cartons tableaux"),
            ("scotch", "rouleau de scotch", "rouleaux de scotch"),
            ("bulles", "rouleau de papier bulle (20 m)", "rouleaux de papier bulle (20 m)"),
            ("barrelAssiettes", "barrel assiettes", "barrels assiettes"),
            ("barrelVerres", "barrel verres", "barrels verres"),
            ("kraft", "rouleau de kraft", "rouleaux de kraft")]


class HorsAuto(Exception):
    """Dossier que le code ne sait pas mettre en page sans erreur : PDF fait à la main."""


def nombre(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _entier(v):
    return int(v) if float(v).is_integer() else v


# --- Fiche : ce que le parseur résume trop pour un devis ----------------------------------

def section(lignes, *mots):
    """Lignes sous le premier titre « ### » qui contient l'un des mots, jusqu'au titre suivant."""
    garde, dedans = [], False
    for l in lignes:
        s = l.strip()
        if s.startswith("###"):
            if dedans:
                break
            dedans = any(m in s.lower() for m in mots)
        elif dedans and s:
            garde.append(s)
    return garde


def _apres(ligne):
    return re.sub(r"\s+", " ", ligne.split(":", 1)[1]).strip() if ":" in ligne else ""


def _distance(v):
    return re.sub(r"<\s*", "< ", v)


def _etage(valeur):
    """« 1 (demi-étage au-dessus du RDC) » -> 1 ; « R+0 (plain-pied) — agence » -> RDC."""
    v = re.split(r"\s+—\s+|\s*\(", valeur)[0].strip()
    if re.fullmatch(r"r\+?0|rdc", v, re.I):
        return "RDC"
    return int(v) if v.isdigit() else v


def acces(lignes, intervenants):
    """Bloc Départ ou Arrivée de la spec, lu dans la section de la fiche."""
    a = {"intervenants": intervenants}
    logement, autre, rdc, taille, avec, sans = None, None, False, None, "", ""
    # « R+0 (plain-pied) — agence (local professionnel) » : la case cochée dit « Maison » faute de
    # mieux, la précision dit la vérité.
    precise = next((m.group(1).strip() for m in (re.search(r"\s—\s+(.*(?:local|agence|bureau|box|boutique).*)$", l, re.I)
                                                 for l in lignes) if m), None)
    for l in lignes:
        coche = re.match(r"^-\s*\[x\]\s*(.+)$", l, re.I)
        bas = l.lower()
        if coche:
            nom = coche.group(1).strip()
            if nom.lower() == "rdc":
                rdc = True
            elif nom.lower() in ("petit", "grand"):
                taille = nom.lower()
            elif not logement:
                logement = nom
        elif l.startswith("- [ ]"):
            continue
        elif "avec ascenseur" in bas:
            avec = _apres(l)
        elif "sans ascenseur" in bas:
            sans = _apres(l)
        elif "véhicule" in bas:
            a["portage_entree"] = _distance(_apres(l))
        elif "couloir" in bas:
            a["portage_interieur"] = _distance(_apres(l))
        elif re.match(r"^(box|garde-meuble|local|bureau|boutique|entrep)", l, re.I) and not autre:
            autre = l                               # « Box de stockage », sans case à cocher
    a["logement"] = (precise or logement or autre or "").strip()
    a["logement"] = a["logement"][:1].upper() + a["logement"][1:]
    if avec:
        e = _etage(avec)
        a["etage_ascenseur"] = "%s (%s ascenseur)" % (e, taille) if taille else e
    elif sans:
        a["etage_sans_ascenseur"] = _etage(sans)
    elif rdc:
        a["etage_sans_ascenseur"] = "RDC"
    return a


RE_DUREE = re.compile(r"\s*:?\s*\(?\d+\s*(h\s*\d*|min).*$", re.I)
# Trace de préparation sur une ligne de fiche : jamais sur un document client (Karim, 03/11/2026).
RE_VARIANTE = re.compile(r"\s*\([^)]*variante[^)]*\)", re.I)
RE_PREPARATION = re.compile(r"\s*[:(—-]*\s*(🟡|à chiffrer|\btemps\b|à confirmer|à estimer|à définir).*$", re.I)
LIBELLES_CARTON = {"vaisselle": "Mise en carton de la vaisselle",
                   "tout": "Mise en carton de tous les effets personnels"}


def options(lignes):
    """Options cochées sur la fiche, sans durée ni mention interne (jamais dans le devis).
    Rend (libellés à ajouter, lignes « non incluses » à retirer)."""
    plus, retirer = [], []

    def cochees(*mots):
        for l in section(lignes, *mots):
            m = re.match(r"^-\s*\[x\]\s*(.+)$", l, re.I)
            if m:
                yield RE_PREPARATION.sub("", RE_VARIANTE.sub("", RE_DUREE.sub("", m.group(1)))).strip(" :")

    demontage = list(cochees("démonter", "demonter"))
    if demontage:
        plus.append("Démontage et remontage : %s." % ", ".join(demontage))
        retirer.append("Démontage/remontage du mobilier.")
    for o in cochees("mise en carton"):
        plus.append(LIBELLES_CARTON.get(o.lower(), o[:1].upper() + o[1:]) + ".")
        if re.search(r"protection|penderie", o, re.I):   # protéger ou suspendre n'est pas mettre en carton
            continue
        retirer.append("Mise en carton des éléments fragiles." if re.search(r"fragile|vaisselle", o, re.I)
                       else "Mise en carton des effets personnels.")
    return plus, list(dict.fromkeys(retirer))


RE_INTERNE = re.compile(r"\b(samuel|christophe|karim|sandrine|ben)\b", re.I)


def lignes_inventaire(section_inv):
    """« Salon : Canapé x1 · Écrans x2 (⚠️ fragile) » -> ["Canapé : 1", "Écrans, fragile : 2"].
    Rend None si le texte est trop libre pour une liste propre : pas de liste, plutôt qu'une
    liste fausse dans un document que le client signe."""
    sortie = []
    if RE_INTERNE.search(" ".join(section_inv)):    # « Samuel n'en note qu'un » : note interne
        return None
    for l in section_inv:
        l = re.sub(r"^[^:·]{2,40}:\s+", "", l.strip())
        for morceau in l.split("·"):
            t = morceau.replace("⚠️", "").replace("⚠", "").strip()
            if not t:
                continue
            q = 1
            m = re.search(r"\s[x×](\d{1,3})\b", t)
            if m:
                q, t = int(m.group(1)), (t[:m.start()] + t[m.end():]).strip()
            else:
                m = re.match(r"^(\d{1,3})\s+(.+)$", t)
                if m:
                    q, t = int(m.group(1)), m.group(2)
            t = re.sub(r"\s*\(\s*fragile\s*\)", ", fragile", t, flags=re.I)
            t = re.sub(r"\(\s+", "(", t).strip()
            if not t or len(t) > 70:
                return None
            sortie.append("%s : %s" % (t[:1].upper() + t[1:], q))
    return sortie


def telephone(v):
    c = re.sub(r"\D", "", v or "")
    if c.startswith("33") and len(c) == 11:
        c = "0" + c[2:]
    return ".".join(c[i:i + 2] for i in range(0, 10, 2)) if len(c) == 10 else ""


def detail_materiel(ex):
    i, faits = ex.get("ex") or {}, []
    for cle, un, plusieurs in MATERIEL:
        q = nombre(i.get("qte_" + cle))
        if q:
            faits.append("%s %s" % (_entier(q), un if q == 1 else plusieurs))
    detail = [", ".join(faits)] if faits else []
    if any(p.get("libelle") == "Livraison matériel" and nombre(p.get("montant"))
           for p in ex.get("postes") or []):
        detail.append("Livraison du matériel comprise")
    return detail


# --- La spec -------------------------------------------------------------------------------

RE_DATE_NETTE = re.compile(r"^(idéalement )?(le \d{2}/\d{2}/\d{4}|entre le \d{2}/\d{2}(/\d{4})? et le \d{2}/\d{2}/\d{4})$")


def construire_spec(ex, dossier, lignes, numero, date):
    """Rend (spec, à vérifier). Lève HorsAuto pour un dossier à faire à la main."""
    ch, m, i, eq = (ex.get("champs_fiche") or {}, ex.get("mission") or {}, ex.get("ex") or {},
                    ex.get("equipe") or {})
    tps = ex.get("temps_min") or {}
    if ex.get("relivraison"):
        raise HorsAuto("relivraison")
    if any(i.get(k) for k in ("typeEtape", "typePoint2", "typePoint3")):
        raise HorsAuto("étape intermédiaire")
    if not nombre(tps.get("chargement")) or not nombre(tps.get("dechargement")):
        raise HorsAuto("chargement ou déchargement seul")

    c, dep, arr = dossier.get("client") or {}, dossier.get("depart") or {}, dossier.get("arrivee") or {}
    mis = dossier.get("mission") or {}
    # « 🟡 Pomerol (33500), adresse exacte à déterminer » reste une adresse : on la garde telle
    # quelle sur le devis (comme à la main), sans la pastille.
    adresse_dep = (dep.get("adresse_brute") or "").replace("🟡", "").strip()
    adresse_arr = (arr.get("adresse_brute") or "").replace("🟡", "").strip()
    if not c.get("nom") or not adresse_dep or not adresse_arr:
        raise HorsAuto("nom ou adresse absents de la fiche")
    a_verifier = []
    if "🟡" in (dep.get("adresse_brute") or "") + (arr.get("adresse_brute") or ""):
        a_verifier.append("adresse à confirmer")
    date_dem = ia._propre(mis.get("date_intervention") or "")
    if re.match(r"^\d", date_dem):
        date_dem = "le " + date_dem
    if not date_dem:
        date_dem = "date à définir ensemble"
        a_verifier.append("date absente de la fiche")
    elif not RE_DATE_NETTE.match(date_dem):
        a_verifier.append("date écrite telle que sur la fiche (« %s »)" % date_dem)
    tel = telephone(c.get("tel"))
    if not tel:
        a_verifier.append("téléphone absent de la fiche")
    if not c.get("email"):
        a_verifier.append("e-mail absent de la fiche")

    depart = acces(section(lignes, "départ"), eq.get("intervenants_chargement"))
    arrivee = acces(section(lignes, "arrivée"), eq.get("intervenants_dechargement"))
    if not depart["logement"] or not arrivee["logement"]:
        raise HorsAuto("type de logement absent de la fiche")
    # Une pastille 🟡 sur un accès est une question encore ouverte : le texte qu'elle porte
    # (« à confirmer à la visite ») n'a pas sa place sur un document que le client signe.
    if "🟡" in json.dumps([depart, arrivee], ensure_ascii=False):
        raise HorsAuto("accès encore à confirmer sur la fiche")

    volume = _entier(nombre(m.get("volume")))
    transport = {"type": "transport", "montant": 0, "ajuste": True}
    retirer = []
    if m.get("groupage"):
        transport["libelle"] = "Forfait transport groupage %s m3" % volume
        retirer.append("Tarif préférentiel (groupage).")
    formule_ht, manut_ht = nombre(ch.get("formule_ht")), nombre(ch.get("manut_ht"))
    # Confort sans aucune option facturée : le client signe un devis Standard (PEREGO, 30/10).
    formule = (m.get("formule") or "Standard") if formule_ht else "Standard"
    # Formule Standard : toujours 0 € sur le devis, son montant passe en manutention (Karim, 04/11/2026).
    if formule == "Standard":
        manut_ht, formule_ht = round(manut_ht + formule_ht, 2), 0.0
    postes = [transport,
              {"type": "manutention", "montant": manut_ht},
              {"type": "formule", "montant": formule_ht}]
    if nombre(ch.get("materiel_ht")):
        postes.append({"type": "autre", "libelle": "Matériel", "detail": detail_materiel(ex),
                       "montant": nombre(ch["materiel_ht"])})
    for cle, libelle in (("monte_charge_ht", "Monte-meubles"), ("piano_ht", "Transport de piano"),
                         ("autres_frais_ht", "Autres frais"), ("divers_ht", "Divers"),
                         ("deplacement_ht", "Frais de déplacement"), ("dossier_ht", "Frais de dossier")):
        if nombre(ch.get(cle)):
            postes.append({"type": "autre", "libelle": libelle, "montant": nombre(ch[cle])})

    # Le transport absorbe l'arrondi du TTC. Au-delà, un poste de l'export n'est pas sur le PDF.
    total_ttc = nombre(ch.get("total_ttc"))
    transport_pdf = total_ttc / 1.2 - sum(p["montant"] for p in postes)
    if abs(transport_pdf - nombre(ch.get("transport_ht"))) > ECART_TRANSPORT_MAX:
        raise HorsAuto("les montants ne retombent pas sur le total de l'export")

    spec = {"numero": numero, "date": date, "volume": volume, "formule": formule,
            "total_ttc": total_ttc,
            "client": {"nom": " ".join(x for x in (c.get("civilite"), c["nom"].upper(), c.get("prenom") or "") if x),
                       "adresse_depart": adresse_dep, "adresse_arrivee": adresse_arr,
                       "date_demenagement": date_dem,
                       "telephone": tel or "non communiqué",
                       "email": c.get("email") or "non communiqué"},
            "depart": depart, "arrivee": arrivee, "notes_manutention": [], "lignes": postes,
            "annulation": ANNULATION, "conditions": []}
    if (ex.get("fiche") or {}).get("indicatif"):
        spec["indicatif"] = True
    if nombre(ch.get("formule_ht")):
        plus, ret = options(lignes)
        if not plus:
            a_verifier.append("options de la formule non retrouvées sur la fiche")
        spec["formule_incluses_plus"] = plus
        retirer += ret
    if retirer:
        spec["formule_non_incluses_retirer"] = retirer

    meta = dossier.get("_meta") or {}
    if regles.dossier_christophe(mis.get("commercial"), mis.get("source_volume"), meta.get("notes")):
        spec["inventaire"] = []
        spec["note_transport"] = ["Volume estimé lors de notre visite : %s m3." % volume]
    else:
        brut = ia.section_inventaire(lignes)
        spec["inventaire"] = lignes_inventaire(brut) or []
        if not brut:
            # Case « Pas d'inventaire » de la fiche : le devis ne renvoie à rien (Karim, 04/11/2026).
            if any(re.match(r"^-\s*\[x\]\s*pas d.inventaire", l.strip(), re.I) for l in lignes):
                spec["sans_inventaire"] = True
            else:
                a_verifier.append("inventaire absent de la fiche")
    return spec, a_verifier


# --- Numéro, rendu, variantes --------------------------------------------------------------

def prochain_numero(aujourd_hui, dossier=DOSSIER_DEVIS):
    """Dernier numéro du dossier des devis + 1, suivi de la date (0820 + 02112026)."""
    plus_haut = 0
    for chemin in glob.glob(os.path.join(dossier, "*")) + glob.glob(os.path.join(dossier, "specs", "*")):
        m = re.match(r"^(?:Devis )?(\d{4})\d{8}", os.path.basename(chemin))
        if m:
            plus_haut = max(plus_haut, int(m.group(1)))
    return "%04d%s" % (plus_haut + 1, aujourd_hui.strftime("%d%m%Y"))


def rendre(spec, dossier=DOSSIER_DEVIS):
    """Écrit la spec, lance le générateur. Rend (chemin du PDF, inventaire listé dans le devis)."""
    specs = os.path.join(dossier, "specs")
    os.makedirs(specs, exist_ok=True)
    chemin_spec = os.path.join(specs, "%s %s.json" % (spec["numero"], spec["client"]["nom"]))
    with open(chemin_spec, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
    r = subprocess.run([sys.executable, "-I", GENERATEUR, chemin_spec, "--sortie", dossier],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if r.returncode != 0:
        raise RuntimeError("generer_devis_pdf.py : %s" % (r.stderr or r.stdout)[-400:])
    sortie = r.stdout.strip().splitlines()
    return sortie[0].strip(), any("inventaire court" in l for l in sortie)


def export_de_variante(page_id, nom, ttc):
    """Dernier export de cette fiche pour cette variante, au prix annoncé. None si absent."""
    page_id = page_id.replace("-", "")
    for chemin in sorted(glob.glob(os.path.join(EXPORTS, "2*.json")), reverse=True)[:400]:
        try:
            with open(chemin, encoding="utf-8") as fh:
                d = json.load(fh)
        except ValueError:
            continue
        if ((d.get("fiche") or {}).get("page_id") or "").replace("-", "") == page_id \
                and d.get("variante") == nom \
                and (ttc is None or nombre((d.get("champs_fiche") or {}).get("total_ttc")) == nombre(ttc)):
            return d
    return None


def produire(ex, page_id, token, variantes=None, dossier_sortie=DOSSIER_DEVIS, aujourd_hui=None, numeros=None):
    """Produit le PDF du devis, un par variante annoncée. Ne lève que sur panne technique.

    `numeros` (variante -> numéro) : devis pas encore validés, qui gardent leur numéro à la
    correction ; leur PDF est remplacé. Rend {pdfs: [{chemin, variante, numero, ttc}], numero,
    inventaire_dans_devis, christophe, a_verifier, raison}. `raison` dit pourquoi le PDF reste à
    faire à la main."""
    numeros = numeros or {}
    aujourd_hui = aujourd_hui or datetime.date.today()
    res = {"pdfs": [], "numero": None, "inventaire_dans_devis": False, "christophe": False,
           "a_verifier": [], "raison": None}
    dossier, _ = fn.lire_fiche(page_id, token)
    lignes = fn.lire_corps(page_id.replace("-", ""), token)
    mis, meta = dossier.get("mission") or {}, dossier.get("_meta") or {}
    res["christophe"] = regles.dossier_christophe(mis.get("commercial"), mis.get("source_volume"),
                                                  meta.get("notes"))
    a_faire = [(ex.get("variante"), ex)]
    if variantes and len(variantes) > 1:
        a_faire = []
        for nom in sorted(variantes):
            ttc = (variantes[nom] or {}).get("total_ttc")
            if nom == ex.get("variante"):
                a_faire.append((nom, ex))
                continue
            autre = export_de_variante(page_id, nom, ttc)
            if autre is None:
                res["raison"] = "export de la variante « %s » introuvable" % nom
                return res
            a_faire.append((nom, autre))
    try:
        # Tout est préparé avant le premier rendu : jamais la moitié des variantes en PDF.
        prets = []
        suivant = int(prochain_numero(aujourd_hui, dossier_sortie)[:4])
        date = aujourd_hui.strftime("%d/%m/%Y")
        for nom, e in a_faire:
            numero = numeros.get(nom or "")
            if not numero:
                numero = "%04d%s" % (suivant, aujourd_hui.strftime("%d%m%Y"))
                suivant += 1
            prets.append((nom, e, numero) + construire_spec(e, dossier, lignes, numero, date))
    except HorsAuto as h:
        res["raison"] = str(h)
        return res
    for nom, e, numero, spec, verifier in prets:
        chemin, court = rendre(spec, dossier_sortie)
        res["pdfs"].append({"chemin": chemin, "variante": nom, "numero": numero,
                            "ttc": nombre((e.get("champs_fiche") or {}).get("total_ttc"))})
        res["a_verifier"] += [v for v in verifier if v not in res["a_verifier"]]
        if e is ex:
            res["numero"], res["inventaire_dans_devis"] = numero, court
    return res


def main():
    ap = argparse.ArgumentParser(description="Devis PDF automatique, sans envoi (contrôle)")
    ap.add_argument("export", help="JSON du calculateur")
    ap.add_argument("--sortie", required=True, help="dossier de sortie du PDF et de la spec")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with open(a.export, encoding="utf-8") as fh:
        ex = json.load(fh)
    print(json.dumps(produire(ex, ex["fiche"]["page_id"], fn._token(), dossier_sortie=a.sortie),
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
