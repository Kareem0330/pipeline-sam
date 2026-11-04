"""Génère un inventaire Sam'Déménage en PDF, à l'identique du modèle maison.

    python generer_inventaire.py dossier.json [--sortie DOSSIER] [--fige] [--html] [--ouvrir] [--remplacer]

dossier.json : voir SKILL.md (section « Format du dossier »).
Par défaut le PDF porte des champs modifiables (n°, date d'établissement, client,
date de déménagement, adresses) ; --fige produit un PDF sans champs.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import pymupdf

ICI = Path(__file__).resolve().parent
ASSETS = ICI / "assets"
SORTIE_DEFAUT = Path(__file__).resolve().parents[3] / "donnees" / "Inventaires"

NAVIGATEURS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# Barème couvertures selon le volume total (m³)
BAREME_COUVERTURES = [(20, "30 à 40"), (30, "30 à 50"), (40, "50 à 70"), (50, "70 à 90")]
COUVERTURES_AU_DELA = "60 à 90"

MATERIEL_DEFAUT = [
    ("Couvertures de protection", None, 0.200),
    ("Penderies plastiques / cartons", "0 à 10", 0.300),
    ("Sangles d'arrimage", "10 à 30", 0.005),
    ("Film / papier bulle", "0 à 5", 0.050),
]

NAVY = (28 / 255, 63 / 255, 102 / 255)
GRIS = (70 / 255, 88 / 255, 110 / 255)
BLANC = (1, 1, 1)

# nom du champ -> (police, taille, couleur, alignement, espacement des lettres)
# DVB / DV = DejaVu Sans Bold / Regular, embarquées dans le formulaire PDF
CHAMPS = {
    "numero": ("DVB", 10.5, BLANC, "droite", 0),
    "etabli_le": ("DVB", 7.3, BLANC, "gauche", 0.365),
    "client": ("DVB", 10.0, NAVY, "gauche", 0),
    "date_demenagement": ("DVB", 10.0, NAVY, "gauche", 0),
    "adresse_depart": ("DVB", 10.0, NAVY, "gauche", 0),
    "adresse_arrivee": ("DVB", 10.0, NAVY, "gauche", 0),
    "numero_note": ("DV", 7.8, GRIS, "gauche", 0),
    "etabli_le_note": ("DV", 7.8, GRIS, "gauche", 0),
}
# Les champs de la note sont des répliques de ceux du bandeau : un seul champ PDF,
# deux emplacements — modifier l'un met l'autre à jour.
NOM_PDF = {"numero_note": "numero", "etabli_le_note": "etabli_le"}
POLICES = {"DV": "DejaVuSans.ttf", "DVB": "DejaVuSans-Bold.ttf"}
# DejaVu Sans : ascendante 0,928 em, descendante 0,236 em ; interligne CSS 1,35
ASCENDANTE, DESCENDANTE, INTERLIGNE = 0.928, 0.236, 1.35


def fr(x, dec=3):
    return f"{x:.{dec}f}".replace(".", ",")


def couvertures(volume_total):
    for seuil, q in BAREME_COUVERTURES:
        if volume_total <= seuil:
            return q
    return COUVERTURES_AU_DELA


def preparer(d):
    d = dict(d)
    d.setdefault("numero", "")
    d.setdefault("etabli_le", dt.date.today().strftime("%d/%m/%Y"))
    for k in ("client", "date_demenagement", "adresse_depart", "adresse_arrivee"):
        d.setdefault(k, "")
    if d.get("nom"):
        d["client"] = nom_client(d["nom"], d.get("prenom", ""))
    vol_total = float(d["volume_total"])

    if "materiel" not in d:
        d["materiel"] = [
            {"nature": n, "quantite": q or couvertures(vol_total), "volume": v}
            for n, q, v in MATERIEL_DEFAUT
        ]
    for m in d["materiel"]:
        m["volume_txt"] = fr(float(m["volume"]))
    vol_mat = sum(float(m["volume"]) for m in d["materiel"])

    for p in d["pieces"]:
        p["nom"] = p["nom"].upper()
        for a in p["articles"]:
            a.setdefault("qte", 1)
            a.setdefault("dims", "")
            a.setdefault("fragile", False)

    d["vol_materiel_txt"] = fr(vol_mat)
    d["vol_mobilier_txt"] = fr(vol_total - vol_mat)
    d["vol_total_txt"] = str(int(vol_total)) if vol_total == int(vol_total) else fr(vol_total, 1)

    if "note_precisions" not in d:
        textes = [d["adresse_depart"], d["adresse_arrivee"]] + [
            str(a["qte"]) + " " + a["dims"] for p in d["pieces"] for a in p["articles"]]
        d["note_precisions"] = any(("préciser" in t or "confirmer" in t) for t in textes)
    d.setdefault("note_maj", False)
    return d


def marqueurs():
    return {nom: f"rgb(254, 1, {10 + 20 * i})" for i, nom in enumerate(CHAMPS)}


def rendre_html(d, mode):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ICI)), autoescape=True)
    return env.get_template("template_inventaire.html").render(
        d=d, mode=mode, marqueurs=marqueurs(), assets=ASSETS.as_uri())


def navigateur():
    for n in NAVIGATEURS:
        if os.path.exists(n):
            return n
    raise RuntimeError("Chrome ou Edge introuvable.")


def imprimer(html, pdf, tmp):
    src = Path(tmp) / f"{pdf.stem}.html"
    src.write_text(html, encoding="utf-8")
    subprocess.run(
        [navigateur(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--user-data-dir={Path(tmp) / 'profil'}", "--run-all-compositor-stages-before-draw",
         "--virtual-time-budget=5000", f"--print-to-pdf={pdf}", src.as_uri()],
        check=True, capture_output=True, timeout=120)
    if not pdf.exists():
        raise RuntimeError("Échec de l'impression PDF.")


def mesurer(pdf):
    """Repère les champs dans la passe « mesure » grâce à leur couleur de fond."""
    couleurs = {}
    for nom, css in marqueurs().items():
        r, g, b = (int(x) for x in css[4:-1].split(","))
        couleurs[(r, g, b)] = nom
    zones = {}
    with pymupdf.open(pdf) as doc:
        for pno, page in enumerate(doc):
            for dr in page.get_drawings():
                if not dr.get("fill"):
                    continue
                rgb = tuple(round(c * 255) for c in dr["fill"])
                if rgb in couleurs:
                    nom = couleurs[rgb]
                    r = dr["rect"]
                    if nom in zones and zones[nom][0] == pno:
                        r = zones[nom][1] | r
                    zones[nom] = (pno, r)
    return zones


def police_pdf(doc, fichier):
    """Police TrueType simple (WinAnsi) embarquée, utilisable par les champs de formulaire."""
    brut = (ASSETS / "fonts" / fichier).read_bytes()
    police = pymupdf.Font(fontbuffer=brut)
    try:
        import io
        import logging
        from fontTools import subset, ttLib
        logging.getLogger("fontTools").setLevel(logging.ERROR)
        tt = ttLib.TTFont(io.BytesIO(brut))
        sub = subset.Subsetter(subset.Options())
        sub.populate(unicodes=[ord(bytes([c]).decode("cp1252", "ignore") or " ") for c in range(32, 256)])
        sub.subset(tt)
        tampon = io.BytesIO()
        tt.save(tampon)
        brut = tampon.getvalue()
    except ImportError:
        pass
    largeurs = []
    for c in range(32, 256):
        ch = bytes([c]).decode("cp1252", "ignore")
        largeurs.append(str(round(police.glyph_advance(ord(ch)) * 1000)) if ch else "0")
    nom = police.name.replace(" ", "")
    flux = doc.get_new_xref()
    doc.update_object(flux, "<<>>")
    doc.update_stream(flux, brut)
    doc.xref_set_key(flux, "Length1", str(len(brut)))
    desc = doc.get_new_xref()
    doc.update_object(desc, f"<</Type/FontDescriptor/FontName/{nom}/Flags 32/FontBBox[-1069 -415 1975 1174]"
                            f"/ItalicAngle 0/Ascent 928/Descent -236/CapHeight 729/StemV 80/FontFile2 {flux} 0 R>>")
    xref = doc.get_new_xref()
    doc.update_object(xref, f"<</Type/Font/Subtype/TrueType/BaseFont/{nom}/FirstChar 32/LastChar 255"
                            f"/Widths[{' '.join(largeurs)}]/Encoding/WinAnsiEncoding/FontDescriptor {desc} 0 R>>")
    return xref, police


def chaine_pdf(texte):
    b = texte.encode("cp1252", "replace")
    return "(" + "".join(chr(x) if 32 <= x < 127 and chr(x) not in "()\\" else f"\\{x:03o}" for x in b) + ")"


def texte_pdf(texte):
    return "<FEFF" + texte.encode("utf-16-be").hex().upper() + ">"


def couleur_pdf(c):
    return " ".join(f"{x:.4g}" for x in c) + " rg"


def couper(texte, mesure, largeur):
    """Retour à la ligne mot à mot, comme le navigateur."""
    lignes, courante = [], ""
    for mot in texte.split(" "):
        essai = f"{courante} {mot}" if courante else mot
        if courante and mesure(essai) > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    return lignes + [courante]


def poser_champs(pdf_final, zones, d):
    with pymupdf.open(pdf_final) as doc:
        polices = {cle: police_pdf(doc, f) for cle, f in POLICES.items()}
        champs = {}
        for nom, (pno, rect) in zones.items():
            cle, taille, couleur, align, tc = CHAMPS[nom]
            nom_pdf = NOM_PDF.get(nom, nom)
            valeur = str(d.get(nom_pdf, ""))
            fxref, police = polices[cle]
            hauteur_ligne = INTERLIGNE * taille
            multiligne = rect.height > 1.5 * hauteur_ligne
            mesure = lambda t: police.text_length(t, fontsize=taille) + tc * len(t)
            lignes = couper(valeur, mesure, rect.width + 0.5) if multiligne else [valeur]
            if not multiligne and mesure(valeur) > rect.width + 0.5:
                taille = taille * rect.width / mesure(valeur)
            w = pymupdf.Widget()
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.field_name = nom_pdf
            w.field_value = valeur
            w.rect = rect
            w.border_width = 0
            w.border_color = None
            w.fill_color = None
            annot = doc[pno].add_widget(w)
            x = annot.xref
            # Apparence : même ligne de base que le texte HTML (interligne 1,35)
            base = (INTERLIGNE - ASCENDANTE - DESCENDANTE) / 2 * taille + ASCENDANTE * taille
            texte = ""
            for i, ligne in enumerate(lignes):
                largeur = police.text_length(ligne, fontsize=taille) + tc * len(ligne)
                tx = rect.width - largeur if align == "droite" else 0
                ty = rect.height - base - i * INTERLIGNE * taille
                texte += f"1 0 0 1 {tx:.3f} {ty:.3f} Tm {chaine_pdf(ligne)} Tj "
            contenu = (f"/Tx BMC q BT /{cle} {taille:.3f} Tf {couleur_pdf(couleur)} {tc} Tc "
                       f"{texte}ET Q EMC")
            ap = doc.get_new_xref()
            doc.update_object(ap, f"<</Type/XObject/Subtype/Form/BBox[0 0 {rect.width:.3f} {rect.height:.3f}]"
                                  f"/Resources<</Font<</{cle} {fxref} 0 R>>>>>>")
            doc.update_stream(ap, contenu.encode("latin-1"))
            doc.xref_set_key(x, "AP", f"<</N {ap} 0 R>>")
            doc.xref_set_key(x, "DA", f"({couleur_pdf(couleur)} /{cle} {taille:.3f} Tf)")
            doc.xref_set_key(x, "Q", "2" if align == "droite" else "0")
            doc.xref_set_key(x, "V", texte_pdf(valeur))
            doc.xref_set_key(x, "MK", "null")
            if multiligne:
                doc.xref_set_key(x, "Ff", "4096")
            champs.setdefault(nom_pdf, []).append(x)

        racines = []
        for nom_pdf, widgets in champs.items():
            if len(widgets) == 1:
                racines.append(widgets[0])
                continue
            parent = doc.get_new_xref()
            kids = " ".join(f"{k} 0 R" for k in widgets)
            doc.update_object(parent, f"<</FT/Tx/T{texte_pdf(nom_pdf)}/V{texte_pdf(str(d.get(nom_pdf, '')))}"
                                      f"/Kids[{kids}]>>")
            for k in widgets:
                for cle in ("T", "FT", "V", "Ff"):
                    doc.xref_set_key(k, cle, "null")
                doc.xref_set_key(k, "Parent", f"{parent} 0 R")
            racines.append(parent)
        cat = doc.pdf_catalog()
        dr = " ".join(f"/{cle} {fx} 0 R" for cle, (fx, _) in polices.items())
        doc.xref_set_key(cat, "AcroForm", f"<</Fields[{' '.join(f'{r} 0 R' for r in racines)}]"
                                          f"/DR<</Font<<{dr}>>>>/DA(/DV 10 Tf 0 g)>>")
        tmp = pdf_final.with_suffix(".tmp.pdf")
        doc.save(tmp, garbage=3, deflate=True)
    os.replace(tmp, pdf_final)


def nom_client(nom, prenom):
    """« NOM Prénom » : nom de famille en capitales, prénom avec majuscule initiale (Marie-Hélène)."""
    prenom = "-".join(" ".join(m[:1].upper() + m[1:].lower() for m in p.split()) for p in prenom.split("-"))
    return " ".join(x for x in (nom.strip().upper(), prenom.strip()) if x)


def nom_fichier(d):
    """« inventaire <n°> NOM Prénom », ou « inventaire NOM Prénom » sans n°.
    Dossier indicatif : « inventaire indicatif … » (Karim, 12/10/2026)."""
    client = d["client"] or "client du " + d["etabli_le"].replace("/", "-")
    base = " ".join(x for x in ("inventaire", "indicatif" if d.get("indicatif") else "",
                                d["numero"], client) if x)
    return "".join(c for c in base if c not in '<>:"/\\|?*') + ".pdf"


def generer(dossier, sortie=SORTIE_DEFAUT, fige=False, remplacer=False, html=False):
    """Dossier (dict) -> PDF. Rend (chemin, nombre de pages). Lève RuntimeError en cas d'échec.

    Point d'entrée commun à la ligne de commande et à la chaîne devis
    (outils/pipeline/inventaire_auto.py) : un seul chemin de rendu, donc un seul rendu.
    """
    d = preparer(dossier)
    sortie = Path(sortie).resolve()
    sortie.mkdir(parents=True, exist_ok=True)
    final = sortie / nom_fichier(d)
    n = 2
    while final.exists() and not remplacer:  # ne jamais écraser un inventaire existant
        final = sortie / f"{Path(nom_fichier(d)).stem} ({n}).pdf"
        n += 1

    with tempfile.TemporaryDirectory() as tmp:
        if fige:
            imprimer(rendre_html(d, "fige"), final, tmp)
        else:
            mesure = Path(tmp) / "mesure.pdf"
            imprimer(rendre_html(d, "mesure"), mesure, tmp)
            zones = mesurer(mesure)
            manquants = set(CHAMPS) - set(zones)
            if manquants:
                raise RuntimeError(f"Champs non repérés : {sorted(manquants)}")
            imprimer(rendre_html(d, "champs"), final, tmp)
            poser_champs(final, zones, d)
        if html:
            (sortie / (final.stem + ".html")).write_text(rendre_html(d, "fige"), encoding="utf-8")

    with pymupdf.open(final) as doc:
        return final, len(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier")
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    ap.add_argument("--fige", action="store_true", help="PDF sans champs modifiables")
    ap.add_argument("--html", action="store_true", help="conserve aussi le HTML final")
    ap.add_argument("--ouvrir", action="store_true", help="ouvre le PDF produit")
    ap.add_argument("--remplacer", action="store_true", help="écrase le PDF du même nom (itérations)")
    a = ap.parse_args()

    try:
        final, pages = generer(json.loads(Path(a.dossier).read_text(encoding="utf-8")),
                               a.sortie, a.fige, a.remplacer, a.html)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"OK  {final}  ({pages} page{'s' if pages > 1 else ''})")
    if a.ouvrir:
        os.startfile(final)


if __name__ == "__main__":
    main()
