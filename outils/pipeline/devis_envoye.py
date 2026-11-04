#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Routine « devis envoyé Hubspot » (Karim, 03/11/2026) : suit les envois de devis aux clients.

Un mail de Sandrine (secretariat@) avec Samuel en copie, ou de Samuel avec Sandrine en copie, adressé
hors de l'entreprise, avec un PDF « Devis … » joint, prouve que le devis est parti. La transaction
du client quitte alors « Devis en révision » pour :
  - « Demandes groupage » si le trajet touche l'Île-de-France ou si la case Groupage est cochée ;
  - « Devis envoyé » sinon.

Le connecteur Gmail n'est accessible qu'au modèle : la tâche planifiée
(~/.claude/scheduled-tasks/devis-envoye-hubspot) lit les mails et les passe à ce script, qui porte
toutes les règles.

Rapprochement : adresse du destinataire -> contact -> transactions ; sinon nom du PDF
(« Devis 082103112026 Pujo François .pdf ») -> nom de la transaction. Plusieurs candidates en
révision, ou aucune transaction : rien ne bouge, alerte Slack. Une transaction déjà passée
ne génère rien. Un mail antérieur à l'entrée en révision ne compte pas : le dossier est revenu en
révision pour une nouvelle version, qui n'est pas encore partie.

Registre .claude/scripts/devis-envoye-hubspot.jsonl : un mail n'est traité et signalé qu'une fois.

Usage :
    python devis_envoye.py --preparer                  # requête Gmail + messages déjà traités
    python devis_envoye.py --mails F.json              # simulation (« - » : entrée standard)
    python devis_envoye.py --mails F.json --appliquer  # déplace, journalise, alerte
    python devis_envoye.py --panne "texte"             # alerte Slack (connecteur Gmail en panne)
"""

import argparse
import datetime
import json
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import hubspot_crm as hc                        # noqa: E402
import nocrm                                    # noqa: E402

RACINE = os.path.dirname(os.path.dirname(ICI))
REGISTRE = os.path.join(RACINE, ".claude", "scripts", "devis-envoye-hubspot.jsonl")

SANDRINE = "secretariat@samdemenage.fr"
KARIM = "contact@samdemenage.fr"   # Samuel, dans ce dossier
COPIE_ATTENDUE = {SANDRINE: KARIM, KARIM: SANDRINE}
DOMAINE_INTERNE = "@samdemenage.fr"
PREMIER_PASSAGE_JOURS = 7

ETAPES_APRES = (hc.ETAPE_DEVIS_ENVOYE, hc.ETAPE_GROUPAGE, hc.ETAPE_RELANCE) + hc.ETAPES_CLOSES
MOTS_HORS_NOM = {"devis", "indicatif", "standard", "confort", "premium", "eco", "economique",
                 "formule", "variante", "pdf", "version"}
PROPS = hc.PROPS_DEAL + ["adresse_depart", "adresse_arrivee", "sd_groupage"]


# --- Règles (sans réseau) ------------------------------------------------------------------

def mots(texte):
    return set(re.findall(r"[a-z]+", hc._plat(texte)))


def mots_du_pdf(fichier):
    """Le client dans le nom du fichier : sans « Devis », numéro, formule ni extension."""
    return {m for m in mots(re.sub(r"\.pdf\s*$", "", fichier, flags=re.I)) if m not in MOTS_HORS_NOM}


def pdf_de_devis(pieces):
    return [p for p in pieces or [] if p.lower().rstrip().endswith(".pdf") and "devis" in mots(p)]


def est_envoi_de_devis(mail):
    """Le destinataire doit être hors de l'entreprise : un PDF transmis en interne ne prouve rien."""
    copie = COPIE_ATTENDUE.get((mail.get("de") or "").lower())
    return bool(copie) and copie in [c.lower() for c in mail.get("cc") or []] \
        and any(not a.lower().endswith(DOMAINE_INTERNE) for a in mail.get("a") or []) \
        and bool(pdf_de_devis(mail.get("pieces")))


def meme_nom(pieces, nom_transaction):
    """Tous les mots du PDF sont dans le nom de la transaction, ou l'inverse. Un simple mot commun
    ne suffit pas : « Martin Paul » ne doit pas désigner « DURAND Paul »."""
    transaction = mots(nom_transaction)
    for piece in pdf_de_devis(pieces):
        fichier = mots_du_pdf(piece)
        if fichier and transaction and (fichier <= transaction or transaction <= fichier):
            return True
    return False


def destinataires_clients(mail):
    return [a.lower() for a in (mail.get("a") or []) + (mail.get("cc") or [])
            if not a.lower().endswith(DOMAINE_INTERNE)]


def etape_cible(proprietes):
    groupage = proprietes.get("sd_groupage") == "true"
    idf = nocrm.tag_axe(proprietes.get("adresse_depart"), proprietes.get("adresse_arrivee"))
    return hc.ETAPE_GROUPAGE if groupage or idf else hc.ETAPE_DEVIS_ENVOYE


def _instant(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def decider(mail, candidates, entree_revision):
    """Rend (issue, transaction|None, motif). `candidates` : transactions du client, toutes étapes.
    `entree_revision(id)` : horodatage ISO de la dernière entrée en révision."""
    if not candidates:
        return "alerte", None, "aucune transaction retrouvée"
    en_revision = [d for d in candidates if d["properties"].get("dealstage") == hc.ETAPE_REVISION]
    if len(en_revision) > 1:
        noms = " · ".join("%s (%s)" % (d["properties"].get("dealname"), d["id"]) for d in en_revision)
        return "alerte", None, "%d transactions en révision : %s" % (len(en_revision), noms)
    if en_revision:
        deal = en_revision[0]
        entree = entree_revision(deal["id"])
        if entree and _instant(mail["date"]) < _instant(entree):
            return "ancien", deal, "mail antérieur à l'entrée en révision"
        return "deplacer", deal, None
    if any(d["properties"].get("dealstage") in ETAPES_APRES for d in candidates):
        return "deja", candidates[0], "étape déjà passée"
    etapes = " · ".join("%s (%s)" % (d["properties"].get("dealname"),
                                     hc._nom_etape(d["properties"].get("dealstage"))) for d in candidates)
    return "alerte", None, "devis parti, transaction pas encore en révision : %s" % etapes


# --- HubSpot -------------------------------------------------------------------------------

def _du_pipeline(deals):
    return [d for d in deals if d["properties"].get("pipeline") == hc.PIPELINE]


def par_adresse(hs, mail):
    ids = set()
    for adresse in destinataires_clients(mail):
        contacts = hs.chercher("contacts", [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": adresse}]}], ["email"])
        for contact in contacts:
            ids.update(hs.associes("contacts", contact["id"], "deals"))
    return _du_pipeline(hs.lire_lot("deals", sorted(ids), PROPS))


def par_nom(hs, mail):
    """Relue après la recherche : l'index de recherche HubSpot peut retarder sur l'étape."""
    jetons = sorted({m for p in pdf_de_devis(mail.get("pieces")) for m in mots_du_pdf(p) if len(m) > 2})[:5]
    if not jetons:
        return []
    trouves = hs.chercher("deals", [{"filters": [
        {"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": j}]} for j in jetons],
        ["dealname"], limite=100)
    retenus = [d["id"] for d in trouves if meme_nom(mail.get("pieces"), d["properties"].get("dealname"))]
    return _du_pipeline(hs.lire_lot("deals", retenus, PROPS))


def candidates_du_mail(hs, mail):
    return par_adresse(hs, mail) or par_nom(hs, mail)


def entree_en_revision(hs, deal_id):
    r = hs.req("GET", "/crm/v3/objects/deals/%s?propertiesWithHistory=dealstage" % deal_id)
    dates = [h["timestamp"] for h in (r.get("propertiesWithHistory") or {}).get("dealstage", [])
             if h["value"] == hc.ETAPE_REVISION]
    return max(dates) if dates else None


def deplacer(hs, deal_id, cible):
    """Écrit l'étape puis la relit : un PATCH accepté n'est tenu pour fait qu'une fois relu."""
    hs.req("PATCH", "/crm/v3/objects/deals/%s" % deal_id, {"properties": {"dealstage": cible}})
    relue = hs.lire_lot("deals", [deal_id], ["dealstage"])[0]["properties"].get("dealstage")
    if relue != cible:
        raise RuntimeError("étape relue « %s » au lieu de « %s »" % (hc._nom_etape(relue), hc._nom_etape(cible)))


# --- Registre ------------------------------------------------------------------------------

def lire_registre(chemin=REGISTRE):
    if not os.path.isfile(chemin):
        return []
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def journaliser(ligne, chemin=REGISTRE):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def preparer(lignes, aujourd_hui):
    """Requête Gmail depuis la veille du dernier passage réussi, messages déjà traités à sauter."""
    passages = [l["quand"] for l in lignes if l.get("type") == "passage"]
    depuis = (_instant(max(passages)).date() - datetime.timedelta(days=1)) if passages \
        else aujourd_hui - datetime.timedelta(days=PREMIER_PASSAGE_JOURS)
    return {"requete_gmail": "{(from:%s cc:%s) (from:%s cc:%s)} filename:devis after:%s"
                             % (SANDRINE, KARIM, KARIM, SANDRINE, depuis.strftime("%Y/%m/%d")),
            "expediteurs": [SANDRINE, KARIM],
            "deja_traites": sorted(l["id"] for l in lignes if l.get("type") == "mail"
                                   and (l.get("date") or "9")[:10] >= depuis.isoformat())}


# --- Passage -------------------------------------------------------------------------------

def _alerter(mail, motif):
    import notif                                # import tardif : la simulation n'en a pas besoin
    pdf = ", ".join(pdf_de_devis(mail.get("pieces")))
    notif.alerte("Devis envoyé au client, transaction non déplacée", "devis_envoye.py (routine 8 h et 14 h)",
                 motif, dossier=pdf or mail.get("objet"),
                 faire="Mail de %s du %s à %s : déplacer la transaction à la main si besoin."
                       % (mail.get("de"), mail.get("date", "")[:10], ", ".join(mail.get("a") or [])))


def traiter(hs, mails, appliquer, connus=()):
    bilan, faits = [], set()
    for mail in sorted(mails, key=lambda m: m.get("date") or ""):
        if mail.get("id") in connus or not est_envoi_de_devis(mail):
            continue
        issue, deal, motif = decider(mail, candidates_du_mail(hs, mail), lambda i: entree_en_revision(hs, i))
        cible = None
        if issue == "deplacer" and deal["id"] in faits:
            issue, motif = "deja", "déplacée par un mail précédent de ce passage"
        if issue == "deplacer":
            cible = etape_cible(deal["properties"])
            if appliquer:
                deplacer(hs, deal["id"], cible)
                faits.add(deal["id"])
        nom = deal["properties"].get("dealname") if deal else None
        bilan.append({"type": "mail", "id": mail.get("id"), "date": mail.get("date"), "de": mail.get("de"), "issue": issue,
                      "deal": deal["id"] if deal else None, "nom": nom,
                      "vers": hc._nom_etape(cible) if cible else None, "motif": motif,
                      "pdf": pdf_de_devis(mail.get("pieces"))})
        if appliquer:
            if issue == "alerte":
                _alerter(mail, motif)
            journaliser(dict(bilan[-1], quand=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return bilan


def _lire_mails(chemin):
    if chemin == "-":
        return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    with open(chemin, encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preparer", action="store_true")
    ap.add_argument("--mails")
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--panne")
    a = ap.parse_args()

    if a.panne:
        import notif
        notif.alerte("Routine devis envoyé Hubspot", "tâche planifiée devis-envoye-hubspot", a.panne,
                     faire="Le passage suivant reprend les mails non traités.")
        return 0
    if a.preparer:
        print(json.dumps(preparer(lire_registre(), datetime.date.today()), ensure_ascii=False))
        return 0
    if not a.mails:
        ap.error("--preparer, --mails ou --panne")

    try:
        cle = hc.charger_cle()
        if not cle:
            raise RuntimeError("clé HubSpot absente (%s)" % hc.ENV)
        lignes = lire_registre()
        connus = {l["id"] for l in lignes if l.get("type") == "mail"}
        bilan = traiter(hc.HubSpot(cle, ecrire=a.appliquer), _lire_mails(a.mails), a.appliquer, connus)
        if a.appliquer:
            journaliser({"type": "passage", "quand": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    except Exception as e:
        if a.appliquer:
            import notif
            notif.alerte("Routine devis envoyé Hubspot", "devis_envoye.py", "%s: %s" % (type(e).__name__, e),
                         faire="Le passage suivant reprend les mails non traités.")
        print("ÉCHEC — %s: %s" % (type(e).__name__, e))
        return 1

    if not a.appliquer:
        print("SIMULATION — rien n'est écrit")
    for l in bilan:
        print("%s | %s | %s%s%s" % (l["issue"], (l["date"] or "")[:16], l["nom"] or ", ".join(l["pdf"]),
                                    " -> %s" % l["vers"] if l["vers"] else "",
                                    " | %s" % l["motif"] if l["motif"] else ""))
    print("%d mail(s) examiné(s)" % len(bilan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
