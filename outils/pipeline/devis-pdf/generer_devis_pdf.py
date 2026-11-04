"""Produit le PDF d'un devis Sam'Déménage, à la mise en page du devis MARSALLON (26/10/2026).

Usage : python generer_devis_pdf.py <spec.json> [--sortie <dossier>]

La spec décrit le client, les lignes et le total TTC annoncé. La ligne marquée
"ajuste": true (le transport) absorbe l'arrondi pour que HT + TVA = TTC au centime,
comme sur les devis envoyés. Acompte 30 % du TTC, solde le jour du déménagement.

Deux versions (Karim, 28/10/2026) : inventaire court listé sous le transport tant qu'il
tient en 10 lignes au plus et que le devis reste à 3 pages au plus ; sinon « Voir
inventaire <n°> » et inventaire séparé (skill inventaire-samdem).

Fourchette et indicatif (Karim, 28/10/2026) : "volume_max", "total_ttc_max" et
"montant_max" par ligne affichent « x à y » ; "indicatif": true retire acompte et solde.
"arrivee": null pour un chargement seul ; "note_transport" remplace le texte sous le transport.

Sections (Karim, 28/10/2026, 1er cas SAINT-MLEUX) : "sections": [{"titre", "detail", "lignes"}]
à la place de "lignes" ; chaque section a son sous-total HT, un seul total en bas. Par ligne :
"libelle" et "detail" (transport), "acces" [{"titre", ...}] (manutention). Formule : les options
choisies vont dans "formule_incluses_plus", celles qu'elles couvrent dans "formule_non_incluses_retirer".
"""
import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ICI = Path(__file__).resolve().parent
LOGO = ICI.parent / "Prod_inventaires" / "assets" / "logo.png"
POLICE = ICI / "fonts" / "Inter-latin.woff2"
SORTIE_DEFAUT = Path(__file__).resolve().parents[3] / "donnees" / "Devis SamDem"
NAVIGATEURS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
TVA = 0.20
ACOMPTE = 0.30
INVENTAIRE_MAX_LIGNES = 10
PAGES_MAX = 3

FORMULE_STANDARD = {
    "incluses": [
        "Protection des meubles (couvertures, film étirable, papier bulle).",
        "Restitution des effets dans toutes les pièces du logement d'arrivée.",
        "Débranchements et branchements des électroménagers : lave-linge, sèche-linge, réfrigérateur.",
        "Flexibilité de la date et de l'horaire.",
        "Assurance contractuelle gratuite :<br>650€/bien &nbsp;《》&nbsp; 6500€/chargement",
    ],
    "non_incluses": [
        "Démontage/remontage du mobilier.",
        "Mise en carton des effets personnels.",
        "Mise en carton des éléments fragiles.",
        "Mise en penderies des vêtements sur cintres.",
        "Déballage des cartons.",
        "Récupération des cartons vides (payant).",
        "Tarif préférentiel (groupage).",
        "Réservations de places de stationnement dans la ville de Bordeaux : inclus",
        "Réservations de place de stationnement hors de la ville de Bordeaux : à déterminer.",
        "Assurance dommage (valeurs réelles de vos biens sur déclaration de valeur).",
    ],
}


def eur(x, decimales=True):
    if not decimales and abs(x - round(x)) < 0.005:
        return f"{round(x):,}".replace(",", " ") + "€"
    s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
    return s + " €"


def e(s):
    return html.escape(str(s))


def bloc_acces(titre, a):
    lignes = [f"{titre} : {e(a['logement'])}"]
    if a.get("etage_ascenseur") is not None:
        lignes.append(f"Etage avec ascenseur : {e(a['etage_ascenseur'])}")
    if a.get("etage_sans_ascenseur") is not None:
        lignes.append(f"Etage sans ascenseur : {e(a['etage_sans_ascenseur'])}")
    if a.get("portage_entree") is not None:
        lignes.append(f"Distance de portage : Entrée (véhicule-porte) : {e(a['portage_entree'])}")
    if a.get("portage_interieur") is not None:
        lignes.append(f"Distance de portage : Intérieur (couloir-hall-cour) : {e(a['portage_interieur'])}")
    if a.get("intervenants") is not None:
        lignes.append(f"Nombre d'intervenants : {e(a['intervenants'])}")
    lignes += [e(x) for x in a.get("notes", [])]
    return "<p>" + "<br>".join(lignes) + "</p>"


def toutes_lignes(spec):
    if "sections" in spec:
        return [l for s in spec["sections"] for l in s["lignes"]]
    return spec["lignes"]


def plage(a, b, decimales=True):
    return eur(a, decimales) if abs(a - b) < 0.005 else f"{eur(a, decimales)} à {eur(b, decimales)}"


def construire_un(lignes, total_ttc, cle):
    ttc = round(total_ttc, 2)
    ht = round(ttc / (1 + TVA), 2)
    tva = round(ttc - ht, 2)
    fixe = sum(l[cle] for l in lignes if not l.get("ajuste"))
    for l in lignes:
        if l.get("ajuste"):
            l[cle] = round(ht - fixe, 2)
    if abs(sum(l[cle] for l in lignes) - ht) > 0.005:
        sys.exit("Lignes incohérentes avec le total : une ligne doit porter \"ajuste\": true.")
    acompte = round(ttc * ACOMPTE, 2)
    solde = round(ttc - acompte, 2)
    return ht, tva, ttc, acompte, solde


def construire(spec):
    lignes = toutes_lignes(spec)
    for l in lignes:
        l.setdefault("montant_max", l["montant"])
    bas = construire_un(lignes, spec["total_ttc"], "montant")
    haut = construire_un(lignes, spec.get("total_ttc_max", spec["total_ttc"]), "montant_max")
    return bas, haut


def rendu_ligne(l, spec):
    t = l["type"]
    if t == "transport":
        if l.get("detail"):
            corps = "".join(f"<p>{e(x)}</p>" for x in l["detail"])
        elif spec.get("note_transport"):
            corps = "".join(f"<p>{e(x)}</p>" for x in spec["note_transport"])
        elif spec.get("inventaire"):
            corps = "<p class='sous'>Inventaire :</p><ul>" + "".join(f"<li>{e(x)}</li>" for x in spec["inventaire"]) + "</ul>"
        else:
            corps = f"<p>Voir inventaire {e(spec['numero'])}.</p>"
        volume = spec["volume"] if spec.get("volume_max") in (None, spec["volume"]) else f"{spec['volume']} à {spec['volume_max']}"
        titre = e(l["libelle"]) if l.get("libelle") else f"Forfait transport {e(volume)} m3"
    elif t == "manutention":
        titre = "Forfait manutention"
        acces = l.get("acces") or [dict(spec["depart"], titre="Départ")] + (
            [dict(spec["arrivee"], titre="Arrivée")] if spec.get("arrivee") else [])
        corps = "".join(bloc_acces(a["titre"], a) for a in acces)
        for n in l.get("notes", spec.get("notes_manutention", [])):
            corps += f"<p>{e(n)}</p>"
        corps += "<p>Le nombre d'intervenants est noté à titre indicatif et n'a pas d'impact sur le prix.*</p>"
    elif t == "formule":
        f = FORMULE_STANDARD
        retirer = spec.get("formule_non_incluses_retirer", [])
        incluses = f["incluses"][:2] + [e(x) for x in spec.get("formule_incluses_plus", [])] + f["incluses"][2:]
        non_incluses = [x for x in f["non_incluses"] if x not in retirer]
        titre = f"Formule {e(spec.get('formule', 'Standard')).upper()}"
        corps = (
            "<p class='sous'>OPTIONS INCLUSES :</p><ul>" + "".join(f"<li>{x}</li>" for x in incluses) + "</ul>"
            "<p class='sous'>OPTIONS NON INCLUSES :</p><ul>" + "".join(f"<li>{x}</li>" for x in non_incluses) + "</ul>"
        )
    else:
        titre, corps = e(l["libelle"]), "".join(f"<p>{e(x)}</p>" for x in l.get("detail", []))
    m = plage(l["montant"], l["montant_max"]).replace(" à ", "<br>à ")
    return (
        f"<tr class='ligne'><td class='art'><div class='titre'>{titre}</div>{corps}</td>"
        f"<td class='num'>{m}</td><td class='qte'>1</td><td class='num'>{m}</td></tr>"
    )


def logo_rogne():
    from PIL import Image, ImageChops
    im = Image.open(LOGO).convert("RGBA")
    fond = Image.new("RGBA", im.size, (255, 255, 255, 255))
    plat = Image.alpha_composite(fond, im).convert("RGB")
    boite = ImageChops.difference(plat, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    buf = BytesIO()
    plat.crop(boite).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def html_devis(spec):
    (ht, tva, ttc, acompte, solde), (ht2, tva2, ttc2, acompte2, solde2) = construire(spec)
    total = plage(ttc, ttc2)
    if spec.get("indicatif"):
        paiement = ("<p>Devis indicatif établi sans visite ni inventaire : le montant n'est pas définitif. "
                    "Le devis définitif, avec le prix ferme et l'acompte, vous sera envoyé une fois le dossier complété.</p>")
    else:
        paiement = (f"<p>• Acompte {plage(acompte, acompte2, False)}<br>&nbsp;À la signature du devis</p>"
                    f"<p>• Solde restant {plage(solde, solde2, False)}<br>&nbsp;Le jour du déménagement</p>")
    logo = logo_rogne()
    police = base64.b64encode(POLICE.read_bytes()).decode()
    c = spec["client"]
    if "sections" in spec:
        lignes = ""
        for s in spec["sections"]:
            detail = "".join(f"<p>{e(x)}</p>" for x in s.get("detail", []))
            lignes += f"<tr class='section'><td colspan='4'><div class='titre-section'>{e(s['titre'])}</div>{detail}</td></tr>"
            lignes += "".join(rendu_ligne(l, spec) for l in s["lignes"])
            st = plage(sum(l["montant"] for l in s["lignes"]), sum(l["montant_max"] for l in s["lignes"]))
            lignes += f"<tr class='soustotal'><td colspan='3'>Sous-total HT : {e(s['titre'])}</td><td class='num'>{st}</td></tr>"
    else:
        lignes = "".join(rendu_ligne(l, spec) for l in spec["lignes"])
    conditions = "".join(f"<p>{e(x)}</p>" for x in spec.get("conditions", []))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Devis {e(spec['numero'])} {e(c['nom'])}</title>
<style>
@font-face {{ font-family: Inter; font-weight: 100 900; src: url(data:font/woff2;base64,{police}) format("woff2"); }}
@page {{ size: A4; margin: 16mm 15mm 16mm 15mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Inter, "Segoe UI", Arial, sans-serif; font-size: 9.5pt; color: #2b2b2b; margin: 0; line-height: 1.55; }}
p {{ margin: 0; }}
.entete {{ display: flex; align-items: flex-start; padding-bottom: 12px; border-bottom: 1px solid #d5dbe3; }}
.entete img {{ width: 122px; margin: 6px 22px 0 0; }}
thead {{ display: table-row-group; }}
.societe {{ flex: 1; }}
.societe h1 {{ font-size: 14pt; font-weight: 600; margin: 0 0 8px; }}
.societe p {{ margin-bottom: 3px; }}
.societe a {{ color: #2a6fdb; text-decoration: none; }}
.ident {{ text-align: right; }}
.ident .lab {{ font-size: 6.5pt; font-weight: 700; letter-spacing: .03em; margin-top: 8px; }}
.ident .lab:first-child {{ margin-top: 0; }}
.client {{ padding: 14px 0 10px; border-bottom: 1px solid #2b2b2b; }}
.client .lab {{ font-size: 6.5pt; font-weight: 700; letter-spacing: .03em; }}
.client h2 {{ font-size: 11pt; font-weight: 600; margin: 6px 0 4px; }}
.client p {{ margin-bottom: 3px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ font-size: 6.5pt; font-weight: 700; text-align: right; padding: 8px 0; border-bottom: 1px solid #2b2b2b; }}
th:first-child {{ text-align: left; }}
td {{ vertical-align: top; padding: 10px 0; }}
tr.ligne td {{ border-bottom: 1px dashed #c8c8c8; }}
tr.ligne {{ break-inside: avoid; }}
td.art {{ width: 72%; padding-right: 12px; }}
td.art p {{ margin-top: 0; }}
td.art p + p {{ margin-top: 6px; }}
.titre {{ font-weight: 600; }}
.sous {{ margin-top: 0 !important; }}
ul {{ margin: 0 0 4px; padding-left: 15px; }}
li {{ list-style: none; position: relative; }}
li::before {{ content: "•"; position: absolute; left: -13px; }}
td.num {{ text-align: right; white-space: nowrap; }}
td.qte {{ text-align: center; width: 45px; }}
tr.section td {{ padding: 16px 0 6px; border-bottom: 1px solid #2b2b2b; break-after: avoid; }}
.titre-section {{ font-size: 10.5pt; font-weight: 700; }}
tr.soustotal td {{ padding: 6px 0 14px; font-size: 8pt; font-weight: 600; text-align: right; }}
.totaux {{ width: 45%; margin: 12px 0 0 auto; }}
.totaux td {{ padding: 4px 0; font-size: 8pt; font-weight: 600; }}
.totaux td:last-child {{ text-align: right; }}
.totaux tr.total td {{ border-top: 1px solid #2b2b2b; padding-top: 8px; font-size: 9.5pt; font-weight: 400; }}
.conditions {{ margin-top: 24px; }}
.conditions p {{ margin-bottom: 26px; }}
.engagements {{ break-inside: avoid; }}
.engagements p {{ margin-bottom: 8px; }}
</style></head><body>
<div class="entete">
  <img src="data:image/png;base64,{logo}" alt="Sam'Déménage">
  <div class="societe">
    <h1>SARL Sam’déménage</h1>
    <p>SIRET : 92890392100049</p>
    <p><b>n° TVA</b> FR36928903921</p>
    <p>77 rue Reinette, 33100 Bordeaux</p>
    <p>Artisan déménageur</p>
    <p>Code APE : 4941A</p>
    <p><a href="https://www.samdemenage.fr">https://www.samdemenage.fr</a></p>
    <p>contact@samdemenage.fr</p>
  </div>
  <div class="ident">
    <p class="lab">DEVIS</p><p>{e(spec['numero'])}</p>
    <p class="lab">DATE</p><p>{e(spec['date'])}</p>
    <p class="lab">TOTAL</p><p>EUR {total}</p>
  </div>
</div>
<div class="client">
  <p class="lab">ADRESSE DE FACTURATION</p>
  <h2>{e(c['nom'])}</h2>
  <p>Adresse de départ : {e(c['adresse_depart'])}</p>
  <p>Adresse d'arrivée : {e(c['adresse_arrivee'])}</p>
  <p>Date de déménagement : {e(c['date_demenagement'])}</p>
  <p>Tél : {e(c['telephone'])}</p>
  <p>{e(c['email'])}</p>
</div>
<table>
  <thead><tr><th>ARTICLE</th><th>PRIX</th><th style="text-align:center">QTÉ</th><th>MONTANT</th></tr></thead>
  <tbody>{lignes}</tbody>
</table>
<table class="totaux">
  <tr><td>SOUS-TOTAL</td><td>{plage(ht, ht2)}</td></tr>
  <tr><td>TVA (20%)</td><td>{plage(tva, tva2)}</td></tr>
  <tr class="total"><td><b>TOTAL</b></td><td><b>EUR {total}</b></td></tr>
</table>
<div class="conditions">
  {conditions}
  <p>Règlement par virement bancaire.</p>
  <p>Date limite d'annulation sans frais : {e(spec['annulation'])}</p>
  {paiement}
</div>
<div class="engagements">
  <p>En signant ce devis, vous :</p>
  <p>■ Acceptez les CGV de Sam’déménage.<br>
  ■ Attestez avoir reçu une déclaration de valeur, avoir pris connaissance dans votre contrat ci-présent des limites de l'assurance contractuelle.<br>
  ■ Attestez que les informations que vous avez fournies pour établir le devis sont précises et complètes.¹<br>
  ■ Attestez que l'inventaire joint au présent contrat est complet, que les dimensions ou descriptions des éléments décrits sont exactes, et que les éléments à démonter/remonter sont annotés.²</p>
  <p>¹ : Toute information incomplète (étages, accès, distances de portage, inventaire, possibilités de parking) venant à rallonger le temps de la prestation de déménagement entraînera des coûts supplémentaires, notamment un forfait de révision de 72 € TTC en cas d'écart entre les conditions estimées et les conditions réelles constatées le jour de la mission.</p>
  <p>² : Le coût de l'option "Démontage/remontage des meubles" est calculée sur la base de la nature et du nombre des éléments indiqués. Aussi seuls les meubles dans la section "Démontage/remontage" seront pris en charge. À défaut, il y aura des coûts supplémentaires.</p>
  <p>* : Le nombre d'intervenant est noté à titre indicatif en fonction des éléments donnés pour l'édition de votre devis. Toutefois, en fonction de la situation en temps réel de nos équipes, celui-ci peut varier, sans que cela n'ait d'incidence sur le prix indiqué, ni à la hausse, ni à la baisse, ainsi que sur la nature des prestations.</p>
  <p>Signature (mention "Lu et approuvé", nom et prénom) :</p>
</div>
</body></html>"""


def imprimer(html_txt, pdf):
    nav = next((n for n in NAVIGATEURS if Path(n).exists()), None)
    if not nav:
        sys.exit("Ni Chrome ni Edge trouvé.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "devis.html"
        src.write_text(html_txt, encoding="utf-8")
        # Chrome garde en silence l'ancien PDF si le fichier est ouvert ailleurs : on imprime à
        # part, puis on copie, pour qu'un fichier verrouillé soit une erreur visible.
        provisoire = Path(tmp) / "devis.pdf"
        subprocess.run([nav, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={tmp}\\profil", f"--print-to-pdf={provisoire}", src.as_uri()],
                       check=True, capture_output=True, timeout=120)
        if not provisoire.exists():
            sys.exit("Le navigateur n'a pas produit de PDF.")
        try:
            shutil.copyfile(provisoire, pdf)
        except PermissionError:
            sys.exit(f"PDF ouvert dans une autre application, à fermer avant de relancer : {pdf}")


def nb_pages(pdf):
    from pypdf import PdfReader
    return len(PdfReader(pdf).pages)


def traces_de_preparation(spec):
    """Ce qui trahirait un devis préparé par une IA : ni pastille ni émoji sur tout le document,
    ni temps ni variante dans les options (Karim, 03/11/2026)."""
    traces = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]|à chiffrer", json.dumps(spec, ensure_ascii=False), re.I)
    return traces + [x for x in spec.get("formule_incluses_plus", [])
                     if re.search(r"\btemps\b|\bvariante\b", x, re.I)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    a = ap.parse_args()
    texte = Path(a.spec).read_text(encoding="utf-8")
    if "→" in texte:
        sys.exit("Flèche « → » dans la spec : écrire « Ville - Ville » (Karim, 28/10/2026).")
    spec = json.loads(texte)
    durees = [x for x in spec.get("formule_incluses_plus", []) if re.search(r"\d+\s*h", x)]
    if durees:
        sys.exit(f"Durée d'option dans la formule, à retirer (Karim, 28/10/2026) : {durees}")
    traces = traces_de_preparation(spec)
    if traces:
        sys.exit(f"Mention interne dans la spec, à retirer : le client ne doit voir aucune trace de préparation (Karim, 03/11/2026) : {traces}")
    sortie = Path(a.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    nom = spec["client"]["nom"].split()[0]
    pdf = sortie / f"Devis {spec['numero']} {nom}.pdf"
    inventaire = spec.get("inventaire") or []
    if len(inventaire) > INVENTAIRE_MAX_LIGNES:
        spec["inventaire"] = []
    imprimer(html_devis(spec), pdf)
    if spec.get("inventaire") and nb_pages(pdf) > PAGES_MAX:
        spec["inventaire"] = []
        imprimer(html_devis(spec), pdf)
    print(pdf)
    print(f"Pages : {nb_pages(pdf)}")
    if spec.get("note_transport"):
        print("Version : texte libre sous le transport (note_transport)")
    elif spec.get("inventaire"):
        print(f"Version : inventaire court ({len(inventaire)} lignes dans le devis)")
    else:
        print(f"Version : normale (« Voir inventaire {spec['numero']} »)")
        if inventaire:
            print("INVENTAIRE SÉPARÉ À PRODUIRE : skill inventaire-samdem, même numéro.")


if __name__ == "__main__":
    main()
