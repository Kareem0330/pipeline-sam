#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fiche client sur la transaction HubSpot (Karim, 03/11/2026) : plus de fiche créée dans Notion.

La fiche est une seule note « Fiche client » sur la transaction, modifiée à chaque changement.
Son texte garde les lignes de fiche_notion.lire_corps (« ### Titre », « - [x] Case », lignes libres) :
parser_corps et ses règles n'ont pas changé, seule la source a changé.

Le dossier est identifié par l'identifiant de transaction, qui voyage là où voyageait l'identifiant
de page Notion (`fiche.page_id` de l'export). Un ancien dossier garde sa page Notion en lecture seule :
reprendre_notion() recopie son corps dans une note, une fois, puis le dossier ne connaît que HubSpot.

    python fiche_hubspot.py --creer corps.md --nom "NOM" --prenom "Prénom" --tel 06... --email x@y.fr \\
        --commercial Samuel --depart "..." --arrivee "..." --date 2026-11-20
    python fiche_hubspot.py --lire <id de transaction>
    python fiche_hubspot.py --chercher "NOM Prénom"
    python fiche_hubspot.py --reprendre <id de page Notion>
"""

import argparse
import json
import re
import sys

import fiche_notion as fn
import hubspot_crm as hc

RE_COMMERCIAL = re.compile(r"^\s*(?:- )?Commercial\s*:\s*(.+?)\s*$", re.I)
RE_CLIENT = re.compile(r"^\s*Client\s*:\s*(.+?)\s*$", re.I)
PROPS_FICHE = ["dealname", "createdate", "sd_commercial", "sd_ref_dossier", "sd_axe_groupage",
               "date_demenagement", "lien_fiche_notion"]
PROPS_CONTACT = ["firstname", "lastname", "phone", "email"]


class FicheAbsente(RuntimeError):
    """La transaction n'a pas de note « Fiche client » au format de la chaîne."""


def _hs(hs=None, ecrire=False):
    return hs or hc.HubSpot(hc.charger_cle(), ecrire=ecrire)


def _versions(hs, deal_id):
    notes = hs.lire_lot("notes", hs.associes("deals", str(deal_id), "notes"), ["hs_note_body", "hs_timestamp"])
    return [n for n in hc.notes_fiche(notes) if hc.titre_note(n["properties"].get("hs_note_body")) == hc.TITRE_NOTE]


def lire_lignes(deal_id, hs=None):
    """Dernière version de la fiche, en lignes au format de fiche_notion.lire_corps."""
    versions = _versions(_hs(hs), deal_id)
    if not versions:
        raise FicheAbsente("transaction %s sans note « %s »" % (deal_id, hc.TITRE_NOTE))
    return hc.texte_note(versions[0]["properties"].get("hs_note_body")).splitlines()


def ecrire(deal_id, lignes, hs=None):
    """Crée la note ou modifie celle qui existe, sans rien faire si le texte n'a pas changé."""
    return hc.poser_note(_hs(hs, ecrire=True), str(deal_id), "\n".join(lignes))


def avec_suivi(lignes, client=None, commercial=None):
    """Section « Suivi » de la note : ce que le corps ne porte pas et que la transaction porte mal (le
    contact d'un formulaire a souvent le nom complet dans « nom »). Le parseur l'ignore."""
    ajouts = []
    if client and not any(RE_CLIENT.match(l) for l in lignes):
        ajouts.append("Client : %s" % client)
    if commercial and not any(RE_COMMERCIAL.match(l) for l in lignes):
        ajouts.append("Commercial : %s" % commercial)
    return list(lignes) + (["### Suivi :"] + ajouts if ajouts else [])


def _premier(regex, lignes):
    return next((m.group(1) for m in map(regex.match, lignes) if m), None)


def _contact(hs, deal_id):
    ids = hs.associes("deals", str(deal_id), "contacts")
    lus = hs.lire_lot("contacts", ids[:1], PROPS_CONTACT) if ids else []
    return lus[0]["properties"] if lus else {}


def lire_fiche(deal_id, hs=None):
    """Même contrat que fiche_notion.lire_fiche : rend (dossier, lignes)."""
    hs = _hs(hs)
    deal_id = str(deal_id)
    lignes = lire_lignes(deal_id, hs)
    p = hs.lire_lot("deals", [deal_id], PROPS_FICHE)[0]["properties"]
    contact = _contact(hs, deal_id)
    dossier, meta = fn.parser_corps(lignes)

    # « Client : NOM Prénom » de la note fait foi, puis le contact : son « nom » peut contenir le prénom.
    client = dossier["client"]
    nom, prenom = fn._nom_prenom(_premier(RE_CLIENT, lignes) or "")
    prenom_c = contact.get("firstname") or ""
    nom_c = re.sub(r"\b%s\b" % re.escape(prenom_c), "", contact.get("lastname") or "", flags=re.I).strip() \
        if prenom_c else contact.get("lastname")
    nom_d, prenom_d = fn._nom_prenom(p.get("dealname") or "")
    client["nom"] = nom or client.get("nom") or nom_c or nom_d
    client["prenom"] = prenom or client.get("prenom") or prenom_c or prenom_d
    client["tel"] = client.get("tel") or contact.get("phone")
    client["email"] = client.get("email") or contact.get("email")

    # Le corps fait foi : les propriétés ne comblent que le contexte, comme sur l'ancienne fiche.
    mission = dossier["mission"]
    mission["commercial"] = _premier(RE_COMMERCIAL, lignes) or p.get("sd_commercial")
    mission["date_chargement"] = p.get("date_demenagement")
    mission["date_creation"] = (p.get("createdate") or "")[:10] or None
    mission["statut"] = None
    mission["ref"] = p.get("sd_ref_dossier")
    mission["axe_groupage"] = p.get("sd_axe_groupage")

    titre = " ".join(x for x in ((client.get("nom") or "").upper(), client.get("prenom") or "") if x)
    meta.update({"page_id": deal_id, "url": hc.URL_DEAL % deal_id, "titre": titre or p.get("dealname"),
                 "notion_id": fn.id_depuis_url(p.get("lien_fiche_notion")),
                 "divergences": [], "replis": [], "lignes_corps": len(lignes)})
    dossier["_meta"] = meta
    return dossier, lignes


def chercher(nom, hs=None):
    """(id de transaction, titre) du dossier qui a une fiche à ce nom ; None si aucun."""
    mots = [m for m in re.split(r"[\s-]+", nom or "") if len(m) > 1]
    if not mots or not (hs or hc.charger_cle()):
        return None
    hs = _hs(hs)
    trouves = hs.chercher("deals", [{"filters": [
        {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": m} for m in mots]}], hc.PROPS_DEAL)
    fiches = [d for d in trouves if _versions(hs, d["id"])]
    if not fiches:
        return None
    if len(fiches) > 1:
        ouvertes = hc._ouvertes(fiches)
        if len(ouvertes) != 1:
            raise SystemExit("%d fiches correspondent à %r :\n%s\nRelancer avec --page-id." % (
                len(fiches), nom, "\n".join("  %s — %s" % (d["properties"].get("dealname"), d["id"]) for d in fiches)))
        fiches = ouvertes
    return fiches[0]["id"], fiches[0]["properties"].get("dealname")


def ligne_client(nom, prenom=None, tel=None, email=None, commercial=None, depart=None, arrivee=None, date=None,
                 notion_url=None, ref=None):
    return {"client_nom": nom, "client_prenom": prenom, "telephone": tel, "email": email, "commercial": commercial,
            "adresse_depart": depart, "adresse_arrivee": arrivee, "date_chargement": date, "notion_url": notion_url,
            "ref": ref}


def creer(ligne, lignes, hs=None):
    """Retrouve ou crée contact et transaction, puis pose la fiche. Rend (id de transaction, compte rendu)."""
    hs = _hs(hs, ecrire=True)
    deal_id, motif = hc.assurer_transaction(ligne, hs)
    if not deal_id:
        return None, motif
    client = " ".join(x for x in ((ligne.get("client_nom") or "").upper(), ligne.get("client_prenom") or "") if x)
    lignes = avec_suivi(lignes, client, ligne.get("commercial"))
    return deal_id, "%s ; %s" % (motif, ecrire(deal_id, lignes, hs))


def reprendre_notion(page_id, token, hs=None):
    """Ancien dossier : recopie sa fiche Notion, lue sans y écrire, dans une note de sa transaction.

    Une seule fois : une transaction qui a déjà sa note la garde, elle est plus récente.
    Rend (id de transaction | None, explication)."""
    hs = _hs(hs, ecrire=True)
    page_id = page_id.replace("-", "")
    dossier, lignes = fn.lire_fiche(page_id, token)
    client, mission, meta = dossier["client"], dossier["mission"], dossier.get("_meta") or {}
    ligne = ligne_client(client.get("nom"), client.get("prenom"), client.get("tel"), client.get("email"),
                         mission.get("commercial"), date=mission.get("date_chargement"),
                         notion_url=meta.get("url"), ref=mission.get("ref"))
    deal_id, motif = hc.assurer_transaction(ligne, hs, page_id)
    if not deal_id:
        return None, motif
    if _versions(hs, deal_id):
        return deal_id, "fiche déjà sur la transaction %s" % deal_id
    client_note = " ".join(x for x in ((client.get("nom") or "").upper(), client.get("prenom") or "") if x)
    lignes = avec_suivi(lignes, client_note, mission.get("commercial"))
    return deal_id, "fiche Notion recopiée sur la transaction %s : %s" % (deal_id, ecrire(deal_id, lignes, hs))


def ids_du_dossier(page_id, hs=None):
    """Identifiants sous lesquels ce dossier a pu être exporté : sa transaction et son ancienne page."""
    ids = {str(page_id).replace("-", "").lower()}
    if fn.est_transaction(page_id):
        p = _hs(hs).lire_lot("deals", [str(page_id)], ["lien_fiche_notion"])
        notion = fn.id_depuis_url((p[0]["properties"] if p else {}).get("lien_fiche_notion"))
        if notion:
            ids.add(notion)
    return ids


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Fiche client sur la transaction HubSpot")
    ap.add_argument("--creer", metavar="FICHIER", help="corps de la fiche, en lignes")
    ap.add_argument("--lire", metavar="TRANSACTION")
    ap.add_argument("--chercher", metavar="NOM")
    ap.add_argument("--reprendre", metavar="PAGE_NOTION")
    ap.add_argument("--nom")
    ap.add_argument("--prenom")
    ap.add_argument("--tel")
    ap.add_argument("--email")
    ap.add_argument("--commercial")
    ap.add_argument("--depart")
    ap.add_argument("--arrivee")
    ap.add_argument("--date", help="date de déménagement, AAAA-MM-JJ, si elle est connue")
    a = ap.parse_args()
    if a.lire:
        dossier, lignes = lire_fiche(a.lire)
        print(json.dumps({"meta": dossier["_meta"], "client": dossier["client"], "lignes": lignes},
                         ensure_ascii=False, indent=1, default=str))
    elif a.chercher:
        print(json.dumps(chercher(a.chercher), ensure_ascii=False))
    elif a.reprendre:
        print(reprendre_notion(a.reprendre, fn._token()))
    elif a.creer:
        if not a.nom:
            ap.error("--nom requis")
        with open(a.creer, encoding="utf-8") as fh:
            lignes = fh.read().splitlines()
        deal_id, detail = creer(ligne_client(a.nom, a.prenom, a.tel, a.email, a.commercial, a.depart, a.arrivee, a.date),
                                lignes)
        print(json.dumps({"transaction": deal_id, "url": hc.URL_DEAL % deal_id if deal_id else None, "detail": detail},
                         ensure_ascii=False))
        return 0 if deal_id else 1
    else:
        ap.error("choisir --creer, --lire, --chercher ou --reprendre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
