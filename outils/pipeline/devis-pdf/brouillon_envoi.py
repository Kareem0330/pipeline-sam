"""Prépare le brouillon d'envoi d'un devis, à partir de sa spec (generer_devis_pdf.py).

Usage : python brouillon_envoi.py <spec.json> [--signataire samuel|karim|sandrine] [--prenom X] [--a mail]
        python brouillon_envoi.py --nettoyer <numéro>

Modèle choisi par la spec : "indicatif": true → modeles-mail/devis-indicatif.html (sans RIB),
sinon devis-ferme.html (acompte et solde, RIB joint). Balises remplacées : prénom, montant
(fourchette si "total_ttc_max"), acompte, solde, signature. Pièces jointes : le PDF du devis
+ les documents de donnees/Docs Devis SamDem (mêmes fichiers que le dossier Drive).

Le brouillon se crée par le navigateur (Karim, 28/10/2026 : pas de CLI Google sur le compte
Sam'Déménage) : connecteur Gmail pour le corps, puis Chrome pour les pièces jointes. Le script
écrit brouillon.json (à, objet, html, texte) et copie les pièces jointes dans
outils/pipeline/livrables/pj-envoi/<numéro>/, seul endroit d'où Chrome peut les joindre ; --nettoyer
supprime ce dossier une fois les pièces jointes enregistrées dans le brouillon.
"""
import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

from generer_devis_pdf import SORTIE_DEFAUT, construire

ICI = Path(__file__).resolve().parent
MODELES = ICI / "modeles-mail"
DOCS = Path(__file__).resolve().parents[3] / "donnees" / "Docs Devis SamDem"
PJ_COMMUNES = ["CGV SARL SAM’DEMENAGE.pdf", "Déclaration de valeur Samdéménage.pdf", "Annexe__Grille_de_vétusté.pdf"]
RIB = "RIB SARL SAM’DÉMÉNAGE.PDF"
ENVOI = ICI.parent / "livrables" / "pj-envoi"
INVENTAIRES = Path(__file__).resolve().parents[3] / "donnees" / "Inventaires"
COPIE = ["secretariat@samdemenage.fr", "contact@samdemenage.fr"]


def euros(x):
    entier = abs(x - round(x)) < 0.005
    s = f"{round(x):,}" if entier else f"{x:,.2f}"
    return s.replace(",", " ").replace(".", ",") + " €"


def prenom_de(nom):
    mots = [m for m in nom.split() if not m.isupper()]
    return " ".join(mots) or nom


def signature(s):
    mail = "" if s["mail"] == "contact@samdemenage.fr" else f"<div>Mail : <a href=\"mailto:{s['mail']}\">{s['mail']}</a></div>"
    return (f"<div>{s['prenom']} – Le déménagement en conscience.</div><br>"
            f"<div>Interlocuteur : {s['nom']}</div><div>Société : SARL Sam’déménage</div>"
            "<div>SIRET : 92890392100049</div><div>N°TVA : FR36928903921</div>"
            "<div>Siège social : 77 rue Reinette, 33100 Bordeaux</div>"
            f"<div>Téléphone : {s['telephone']}</div>"
            f"{mail}<div>Mail contact : <a href=\"mailto:contact@samdemenage.fr\">contact@samdemenage.fr</a></div><br>"
            "<div>Sam’déménage</div><div>Artisan déménageur agréé par la Chambre des Métiers de Bordeaux.</div>")


def en_texte(h):
    t = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    t = re.sub(r"<br\s*/?>|</(tr|div|p)>", "\n", t)
    t = re.sub(r"</td>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = "\n".join(l.strip() for l in t.splitlines())
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def corps(spec, signataire, prenom):
    (_, _, ttc, acompte, solde), (_, _, ttc2, _, _) = construire(json.loads(json.dumps(spec)))
    indicatif = spec.get("indicatif", False)
    modele = (MODELES / ("devis-indicatif.html" if indicatif else "devis-ferme.html")).read_text(encoding="utf-8")
    montant = (f"{euros(ttc)} TTC" if abs(ttc - ttc2) < 0.005
               else f"entre {euros(ttc)} et {euros(ttc2)} TTC")
    if not indicatif and abs(ttc - ttc2) >= 0.005:
        sys.exit("Un devis ferme ne porte pas de fourchette : acompte et solde seraient ambigus.")
    if not prenom:
        modele = modele.replace("Bonjour {{prenom}},", "Bonjour,")
    valeurs = {"prenom": html.escape(prenom), "montant": montant, "acompte": euros(acompte),
               "solde": euros(solde), "signature": signature(signataire)}
    h = re.sub(r"\{\{(\w+)\}\}", lambda m: valeurs[m.group(1)], modele)
    return re.sub(r"<!--.*?-->\s*", "", h, count=1, flags=re.S), indicatif


def pieces_jointes(spec, indicatif):
    nom = spec["client"]["nom"].split()[0]
    devis = SORTIE_DEFAUT / f"Devis {spec['numero']} {nom}.pdf"
    inventaire = sorted(INVENTAIRES.glob(f"inventaire {spec['numero']} *.pdf"))[-1:]
    pj = [devis] + inventaire + [DOCS / f for f in PJ_COMMUNES] + ([] if indicatif else [DOCS / RIB])
    manquants = [str(p) for p in pj if not p.exists()]
    if manquants:
        sys.exit("Pièce jointe introuvable : " + ", ".join(manquants))
    return pj


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--signataire", default="samuel")
    ap.add_argument("--prenom")
    ap.add_argument("--a", help="destinataire, sinon l'e-mail de la spec")
    ap.add_argument("--nettoyer", metavar="NUMERO", help="supprime pj-envoi/<numéro>/ après l'envoi des pièces jointes")
    a = ap.parse_args()
    if a.nettoyer:
        dossier = ENVOI / a.nettoyer
        if dossier.parent != ENVOI or not dossier.is_dir():
            sys.exit(f"Rien à nettoyer : {dossier}")
        for f in dossier.iterdir():
            f.unlink()
        try:
            dossier.rmdir()
            print(f"Supprimé : {dossier}")
        except PermissionError:
            print(f"Fichiers supprimés ; dossier vide encore verrouillé (Chrome/OneDrive), sans gêne : {dossier}")
        return
    if not a.spec:
        ap.error("spec manquante")
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    signataires = json.loads((MODELES / "signataires.json").read_text(encoding="utf-8"))
    if a.signataire not in signataires:
        sys.exit(f"Signataire inconnu : {a.signataire} ({', '.join(signataires)})")
    prenom = prenom_de(spec["client"]["nom"]) if a.prenom is None else a.prenom.strip()
    h, indicatif = corps(spec, signataires[a.signataire], prenom)

    dossier = ENVOI / spec["numero"]
    dossier.mkdir(parents=True, exist_ok=True)
    pj = [Path(shutil.copy(p, dossier / p.name)) for p in pieces_jointes(spec, indicatif)]
    brouillon = {
        "a": a.a or spec["client"]["email"],
        "cc": COPIE,
        "objet": f"Votre devis {'indicatif ' if indicatif else ''}Sam'Déménage - {spec['numero']}",
        "html": h,
        "texte": en_texte(h),
        "pieces_jointes": [str(p) for p in pj],
    }
    (dossier / "brouillon.json").write_text(json.dumps(brouillon, ensure_ascii=False, indent=1), encoding="utf-8")
    print(dossier / "brouillon.json")
    print(f"À : {brouillon['a']} | Cc : {', '.join(COPIE)} | Objet : {brouillon['objet']}")
    print("Pièces jointes : " + ", ".join(p.name for p in pj))


if __name__ == "__main__":
    main()
