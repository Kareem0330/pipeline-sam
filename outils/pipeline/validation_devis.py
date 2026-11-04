#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relecture et validation du devis PDF (Karim, 03/11/2026).

L'export du calculateur fait foi : il produit le PDF, qui attend ici la relecture de Samuel. Le
veilleur tourne sans modèle ; ce fichier tient donc l'état de chaque dossier, et Claude, dans sa
session, l'attend, présente le PDF et pose la question. Rien ne part avant --valider : ni le devis
et l'inventaire vers HubSpot, ni le message et l'inventaire vers l'équipe sur WhatsApp.

Usage :
    python validation_devis.py --attendre                 # rend la main au prochain export prêt
    python validation_devis.py --liste                    # devis qui attendent une relecture
    python validation_devis.py --afficher --page-id <id>
    python validation_devis.py --valider --page-id <id> [--variante "Standard"]
    python validation_devis.py --refuser --page-id <id> [--motif "..."]
    python validation_devis.py --ajouter-pdf <pdf> --page-id <id> [--variante "X"] [--ttc 1800]
"""

import argparse
import contextlib
import datetime
import glob
import json
import os
import re
import sys
import tempfile
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import regles                                       # noqa: E402

DOSSIER = os.path.join(regles.DEVIS_GENERES, "validation")
JOURNAUX = os.path.join(regles.DEVIS_GENERES, "exports")
A_RELIRE, A_CORRIGER, VALIDE = "a_relire", "a_corriger", "valide"
DELAI_EXPORT = 4 * 3600                             # secondes d'attente d'un export
DELAI_INVENTAIRE = 180                              # une mise en forme par le modèle prend une minute
PAS = 3


def _id(page_id):
    return (page_id or "").replace("-", "")


def _chemin(page_id):
    return os.path.join(DOSSIER, "%s.json" % _id(page_id))


def _maintenant():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def lire(page_id):
    try:
        with open(_chemin(page_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _ecrire(etat):
    """Écriture atomique : le veilleur et l'inventaire peuvent lire pendant ce temps."""
    os.makedirs(DOSSIER, exist_ok=True)
    cible = _chemin(etat["page_id"])
    fd, tmp = tempfile.mkstemp(dir=DOSSIER, prefix=".etat-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(etat, fh, ensure_ascii=False, indent=2)
    for essai in range(5):
        try:
            os.replace(tmp, cible)
            return
        except PermissionError:                     # lecteur en cours, OneDrive : passager
            if essai == 4:
                raise
            time.sleep(0.3)


@contextlib.contextmanager
def _verrou(page_id):
    """L'inventaire, détaché, peut finir au moment où Samuel valide."""
    os.makedirs(DOSSIER, exist_ok=True)
    chemin = _chemin(page_id) + ".verrou"
    fin = time.time() + 10
    while True:
        try:
            os.close(os.open(chemin, os.O_CREAT | os.O_EXCL))
            break
        except FileExistsError:
            if time.time() > fin:                   # verrou orphelin : on passe
                break
            time.sleep(0.1)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(chemin)


# --- Ce qu'écrit la finalisation ----------------------------------------------------------

def numeros_en_cours(page_id):
    """Variante -> numéro des devis pas encore validés : une correction garde son numéro et
    remplace son PDF. Après validation, un nouveau devis prend un nouveau numéro."""
    etat = lire(page_id)
    if not etat or etat.get("statut") == VALIDE:
        return {}
    return {p.get("variante") or "": p["numero"] for p in etat.get("pdfs") or [] if p.get("numero")}


def enregistrer(page_id, ex, pdf, ligne=None, tps=None, variantes=None):
    """Note le résultat d'un export : le dernier export d'une variante remplace le précédent. Garde
    de quoi composer le message d'équipe, qui part à la validation."""
    fiche, ligne = ex.get("fiche") or {}, ligne or {}
    mission, champs = ex.get("mission") or {}, ex.get("champs_fiche") or {}
    with _verrou(page_id):
        etat = lire(page_id)
        if not etat or etat.get("statut") == VALIDE:
            etat = {"page_id": _id(page_id), "pdfs": [], "importes": (etat or {}).get("importes") or []}
        neufs = {p.get("variante") for p in pdf.get("pdfs") or []} | {ex.get("variante")}
        maintenant = _maintenant()
        # Un nouvel export repart de la fiche : les corrections de texte du PDF remplacé sont à refaire.
        etat["corrections_perdues"] = [c for p in etat["pdfs"] if p.get("variante") in neufs
                                       for c in p.get("corrections") or []]
        etat.update(client=fiche.get("titre") or ex.get("client"), statut=A_RELIRE,
                    export_le=maintenant, maj_le=maintenant, hubspot_url=fiche.get("hubspot_url"),
                    notion_url=fiche.get("url"), tel=ligne.get("telephone"), email=ligne.get("email"),
                    indicatif=bool(fiche.get("indicatif")), a_la_main=pdf.get("raison"),
                    a_verifier=pdf.get("a_verifier") or [], inventaire={"statut": "en_cours"},
                    marge={k: (ex.get("marge") or {}).get(k) for k in ("pct", "cible")},
                    message={"ex": {"client": ex.get("client"), "variante": ex.get("variante"), "fiche": fiche,
                                    "mission": {"volume": mission.get("volume"), "formule": mission.get("formule")},
                                    "champs_fiche": {"total_ttc": champs.get("total_ttc")}},
                             "tps": {"mission": tps["mission"]} if tps and tps.get("mission") is not None else None,
                             "variantes": variantes or None},
                    pdfs=[p for p in etat["pdfs"] if p.get("variante") not in neufs] + (pdf.get("pdfs") or []))
        _ecrire(etat)


def noter_inventaire(page_id, statut, chemin=None, motif=None, envoi=None):
    """statut : pret, aucun, sans_objet ou erreur. Rend True si un devis attend sa validation :
    l'inventaire partira avec lui. False : dossier déjà validé ou sans relecture en cours, à
    l'appelant de l'envoyer tout de suite. `envoi` : sa ligne du registre des envois, quand il doit
    encore partir sur WhatsApp."""
    with _verrou(page_id):
        etat = lire(page_id)
        if not etat or etat.get("statut") == VALIDE:
            return False
        etat["inventaire"] = {"statut": statut, "chemin": chemin, "motif": motif, "envoi": envoi}
        etat["maj_le"] = _maintenant()
        _ecrire(etat)
    return True


# --- Ce que voit Samuel --------------------------------------------------------------------

def controle_pdf(chemin, ttc=None, numero=None):
    """Le PDF porte-t-il bien le TTC de l'export et son numéro ? Rend (conforme, détail) ;
    conforme vaut None quand le fichier n'a pas pu être lu."""
    if not chemin or not os.path.isfile(chemin):
        return False, "fichier introuvable"
    try:
        import pymupdf
        with pymupdf.open(chemin) as doc:
            plat = re.sub(r"\s", "", "".join(p.get_text() for p in doc))
    except Exception as e:
        return None, "PDF non contrôlé (%s)" % type(e).__name__
    manques = []
    if numero and numero not in plat:
        manques.append("numéro %s" % numero)
    if ttc is not None and ("%.2f" % float(ttc)).replace(".", ",") not in plat:
        manques.append("TTC %.2f €" % float(ttc))
    if manques:
        return False, "absent du PDF : %s" % ", ".join(manques)
    return True, "conforme à l'export" if ttc is not None else "numéro présent, TTC non comparé"


def spec_du_pdf(p):
    """Spec dont le PDF est issu : specs/<numéro> NOM Prénom.json, à côté du PDF. None si absente."""
    if not p.get("chemin") or not p.get("numero"):
        return None
    trouvees = glob.glob(os.path.join(glob.escape(os.path.dirname(p["chemin"])), "specs", "%s *.json" % p["numero"]))
    return trouvees[0] if len(trouvees) == 1 else None


def presenter(etat):
    sortie = {k: etat.get(k) for k in ("page_id", "client", "statut", "export_le", "hubspot_url", "indicatif",
                                       "a_la_main", "a_verifier", "inventaire", "motif", "marge",
                                       "corrections_perdues")}
    sortie["pdfs"] = []
    for p in etat.get("pdfs") or []:
        conforme, detail = controle_pdf(p.get("chemin"), p.get("ttc"), p.get("numero"))
        sortie["pdfs"].append(dict(p, conforme=conforme, controle=detail, spec=spec_du_pdf(p)))
    return sortie


def en_attente():
    etats = []
    for f in glob.glob(os.path.join(DOSSIER, "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                e = json.load(fh)
        except (OSError, ValueError):
            continue
        if e.get("statut") in (A_RELIRE, A_CORRIGER):
            etats.append(e)
    return sorted(etats, key=lambda e: e.get("export_le") or "")


def attendre(page_id=None, delai=DELAI_EXPORT, delai_inventaire=DELAI_INVENTAIRE, pas=PAS):
    """Bloque jusqu'à un export postérieur à l'appel, inventaire compris s'il est en préparation.
    Rend l'état, ou None au bout du délai."""
    depuis, fin = _maintenant(), time.time() + delai
    while time.time() < fin:
        for etat in ([lire(page_id)] if page_id else en_attente()):
            if not etat or etat.get("statut") != A_RELIRE or (etat.get("export_le") or "") < depuis:
                continue
            if (etat.get("inventaire") or {}).get("statut") == "en_cours":
                ecoule = datetime.datetime.now() - datetime.datetime.fromisoformat(etat["export_le"])
                if ecoule.total_seconds() < delai_inventaire:
                    continue
            return etat
        time.sleep(pas)
    return None


# --- Décision de Samuel --------------------------------------------------------------------

def ajouter_pdf(page_id, chemin, variante=None, ttc=None):
    """PDF produit à la main (skill devis-pdf-samdem) : il suit la même relecture."""
    m = re.search(r"(\d{12})", os.path.basename(chemin))
    with _verrou(page_id):
        etat = lire(page_id) or {"page_id": _id(page_id), "pdfs": [], "importes": [],
                                 "inventaire": {"statut": "sans_objet"}}
        maintenant = _maintenant()
        etat["pdfs"] = [p for p in etat["pdfs"] if p.get("variante") != variante] + [
            {"chemin": chemin, "variante": variante, "numero": m.group(1) if m else None, "ttc": ttc}]
        etat.update(statut=A_RELIRE, a_la_main=None, export_le=maintenant, maj_le=maintenant)
        _ecrire(etat)
    return lire(page_id)


def regenerer(page_id, variante=None, motif=None):
    """Correction de texte (Karim, 03/11/2026) : refait le PDF depuis sa spec corrigée, même numéro, sans
    repasser par le calculateur. Rend (ok, détail) ; un PDF qui ne porte plus le TTC de l'export n'est pas ok."""
    import devis_auto
    etat = lire(page_id)
    if not etat:
        return False, "aucun devis enregistré pour cette fiche"
    if etat.get("statut") == VALIDE:
        return False, "devis déjà validé et importé : une correction passe par un nouvel export, avec un nouveau numéro"
    pdfs = [p for p in etat.get("pdfs") or [] if not variante or p.get("variante") == variante]
    if len(pdfs) != 1:
        return False, "%d PDF correspondent : préciser --variante" % len(pdfs)
    spec = spec_du_pdf(pdfs[0])
    if not spec:
        return False, "spec introuvable pour le devis %s" % pdfs[0].get("numero")
    try:
        with open(spec, encoding="utf-8") as fh:
            contenu = json.load(fh)
        chemin, _ = devis_auto.rendre(contenu, os.path.dirname(pdfs[0]["chemin"]))
    except Exception as e:
        return False, "PDF non refait, l'ancien reste en place. %s : %s" % (type(e).__name__, e)
    with _verrou(page_id):
        etat = lire(page_id)
        for p in etat["pdfs"]:
            if p.get("numero") == pdfs[0].get("numero"):
                p["chemin"] = chemin
                p["corrections"] = (p.get("corrections") or []) + ([motif] if motif else [])
        etat.update(statut=A_RELIRE, motif=None, maj_le=_maintenant())
        _ecrire(etat)
    conforme, detail = controle_pdf(chemin, pdfs[0].get("ttc"), pdfs[0].get("numero"))
    if conforme is False:
        return False, "%s : %s. Un changement de prix passe par le calculateur." % (os.path.basename(chemin), detail)
    return True, "%s refait : %s" % (os.path.basename(chemin), detail)


def refuser(page_id, motif=None):
    with _verrou(page_id):
        etat = lire(page_id)
        if not etat:
            return False, "aucun devis enregistré pour cette fiche"
        etat.update(statut=A_CORRIGER, motif=motif, maj_le=_maintenant())
        _ecrire(etat)
    return True, "rien n'est importé, le numéro est gardé pour la correction"


def _prevenir_equipe(page_id, etat, pdfs, retenues=None):
    """Message d'équipe, puis inventaire, sur la même conversation. Rend le compte rendu. Beeper
    fermé : tout attend dans la file WhatsApp, avec une alerte ; la validation reste acquise."""
    import hubspot_crm
    import inventaire_auto
    import notif
    client = etat.get("client") or ""
    ctx = etat.get("message") or {}
    ex = dict(ctx.get("ex") or {"client": client, "fiche": {"titre": client, "url": etat.get("notion_url")}})
    tps, noms = ctx.get("tps"), ctx.get("variantes")
    if retenues and noms:
        noms = {n: v for n, v in noms.items() if n in retenues}
    if len(pdfs) == 1:                              # le PDF retenu n'est pas forcément le dernier exporté
        if pdfs[0].get("ttc") is not None:
            ex["champs_fiche"] = {"total_ttc": pdfs[0]["ttc"]}
        if pdfs[0].get("variante") != ex.get("variante"):
            ex["mission"] = {"volume": (ex.get("mission") or {}).get("volume")}
            tps = None
    if not (ex.get("fiche") or {}).get("hubspot_url"):
        url, _ = hubspot_crm.url_transaction(page_id=page_id, tel=etat.get("tel"), email=etat.get("email"))
        if url:
            ex["fiche"] = dict(ex.get("fiche") or {}, hubspot_url=url)
    texte = notif.message_devis(ex, tps, noms, pdfs=[os.path.basename(p["chemin"]) for p in pdfs],
                                a_verifier=etat.get("a_verifier") or [])
    ok, detail = notif.envoyer(texte)
    compte_rendu = ["Message d'équipe : %s." % ("envoyé" if ok else "en file d'attente, Beeper n'a pas répondu")]
    inv = etat.get("inventaire") or {}
    if inv.get("envoi") and inv.get("chemin"):
        ok_inv, detail_inv = notif.envoyer_fichier(inv["chemin"], "Inventaire — %s" % client)
        inventaire_auto.inscrire(dict(inv["envoi"], envoye=ok_inv, attend_validation=False))
        compte_rendu.append("Inventaire sur WhatsApp : %s." % ("envoyé" if ok_inv else "en file d'attente"))
        ok = ok and ok_inv
        if not ok_inv:
            detail = detail_inv
    if not ok:
        notif.alerte(quoi="le message du devis validé n'est pas parti sur WhatsApp",
                     ou="validation_devis.py → Beeper Desktop (notif.envoyer)",
                     cause="Beeper Desktop n'a pas répondu : %s" % str(detail)[:200], dossier=client,
                     faire="Rien n'est perdu : tout attend dans la file. Ouvrir Beeper puis lancer "
                           "python outils/pipeline/notif.py --vider-file-attente")
    return compte_rendu


def valider(page_id, variantes=None, forcer=False):
    """Importe le PDF du devis et l'inventaire sur la transaction, puis prévient l'équipe sur
    WhatsApp. Rend (ok, compte rendu). Rejouable : un fichier déjà joint n'est pas joint deux fois,
    et le message ne part qu'une fois l'import réussi."""
    import crm
    import hubspot_crm
    import notif
    if crm.actif() not in ("hubspot", "les-deux"):
        return False, "HubSpot n'est pas le CRM actif : rien n'est importé"
    etat = lire(page_id)
    if not etat:
        return False, "aucun devis enregistré pour cette fiche"
    if etat.get("statut") == VALIDE:
        return True, "déjà validé et importé le %s" % etat.get("valide_le")
    pdfs = [p for p in etat.get("pdfs") or [] if not variantes or p.get("variante") in variantes]
    if not pdfs:
        return False, "aucun PDF à importer%s" % (" : %s" % etat["a_la_main"] if etat.get("a_la_main") else "")
    for p in pdfs:
        conforme, detail = controle_pdf(p.get("chemin"), p.get("ttc"), p.get("numero"))
        if conforme is False and not forcer:
            return False, "%s : %s. Rien n'est importé." % (os.path.basename(p.get("chemin") or "?"), detail)

    client, tel, email = etat.get("client") or "", etat.get("tel"), etat.get("email")
    a_joindre = [(p["chemin"], "Devis %s — %s" % (p.get("numero") or "", client), hubspot_crm.DOSSIER_DEVIS)
                 for p in pdfs]
    inv = etat.get("inventaire") or {}
    if inv.get("statut") == "pret" and inv.get("chemin"):
        a_joindre.append((inv["chemin"], "Inventaire de déménagement — %s" % client,
                          hubspot_crm.DOSSIER_INVENTAIRES))
    compte_rendu, echecs = [], []
    for chemin, titre, dossier in a_joindre:
        statut, detail = hubspot_crm.joindre_pdf(page_id, chemin, titre, tel=tel, email=email, dossier=dossier)
        compte_rendu.append("%s : %s" % (os.path.basename(chemin), detail))
        if statut == "echec":
            echecs.append("%s : %s" % (os.path.basename(chemin), detail))
    if echecs:
        notif.alerte(quoi="le devis validé n'a pas été entièrement importé sur HubSpot",
                     ou="validation_devis.py → HubSpot (hubspot_crm.joindre_pdf)",
                     cause=" ; ".join(echecs), dossier=client,
                     faire="Régler la cause, puis rejouer : python outils/pipeline/validation_devis.py "
                           "--valider --page-id %s (ce qui est déjà joint ne le sera pas deux fois)." % _id(page_id))
        return False, "\n".join(compte_rendu)
    if inv.get("statut") == "en_cours":
        compte_rendu.append("Inventaire encore en préparation : il sera joint dès qu'il sera prêt.")
    with _verrou(page_id):
        etat = lire(page_id)
        etat["importes"] = (etat.get("importes") or []) + [
            {"chemin": c, "le": _maintenant()} for c, _, _ in a_joindre]
        etat.update(statut=VALIDE, valide_le=_maintenant(), maj_le=_maintenant())
        _ecrire(etat)
    # L'inventaire a pu finir pendant l'import : il n'aurait plus personne pour l'envoyer.
    tardif = etat.get("inventaire") or {}
    if tardif.get("statut") == "pret" and tardif.get("chemin") not in [c for c, _, _ in a_joindre]:
        _, detail = hubspot_crm.joindre_pdf(page_id, tardif["chemin"], "Inventaire de déménagement — %s" % client,
                                            tel=tel, email=email, dossier=hubspot_crm.DOSSIER_INVENTAIRES)
        compte_rendu.append("%s : %s" % (os.path.basename(tardif["chemin"]), detail))
    compte_rendu += _prevenir_equipe(page_id, etat, pdfs, variantes)
    with contextlib.suppress(OSError):              # client soldé : le prochain devis repart à zéro
        os.remove(os.path.join(JOURNAUX, "%s.variantes.json" % _id(page_id)))
    return True, "\n".join(compte_rendu)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Relecture et validation du devis PDF")
    ap.add_argument("--attendre", action="store_true")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--afficher", action="store_true")
    ap.add_argument("--valider", action="store_true")
    ap.add_argument("--refuser", action="store_true")
    ap.add_argument("--regenerer", action="store_true", help="refaire le PDF depuis sa spec corrigée")
    ap.add_argument("--ajouter-pdf", metavar="PDF")
    ap.add_argument("--page-id")
    ap.add_argument("--variante", action="append", help="à répéter ; défaut : tous les PDF du dossier")
    ap.add_argument("--ttc", type=float)
    ap.add_argument("--motif")
    ap.add_argument("--delai", type=int, default=DELAI_EXPORT, help="secondes d'attente d'un export")
    ap.add_argument("--forcer", action="store_true", help="importer malgré un contrôle du PDF en échec")
    a = ap.parse_args()

    def afficher(valeur):
        print(json.dumps(valeur, ensure_ascii=False, indent=1))

    if a.attendre:
        etat = attendre(a.page_id, a.delai)
        afficher(presenter(etat) if etat else {"statut": "aucun_export"})
        return 0
    if a.liste:
        afficher([presenter(e) for e in en_attente()])
        return 0
    if not a.page_id:
        ap.error("--page-id requis")
    if a.afficher:
        etat = lire(a.page_id)
        afficher(presenter(etat) if etat else {"statut": "aucun_devis"})
        return 0
    if a.ajouter_pdf:
        variante = a.variante[0] if a.variante else None
        afficher(presenter(ajouter_pdf(a.page_id, os.path.abspath(a.ajouter_pdf), variante, a.ttc)))
        return 0
    if a.refuser:
        ok, msg = refuser(a.page_id, a.motif)
    elif a.regenerer:
        ok, msg = regenerer(a.page_id, a.variante[0] if a.variante else None, a.motif)
    elif a.valider:
        ok, msg = valider(a.page_id, a.variante, a.forcer)
    else:
        ap.error("choisir --attendre, --liste, --afficher, --valider, --refuser, --regenerer ou --ajouter-pdf")
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
