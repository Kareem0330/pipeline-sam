#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Range un devis validé dans références/, anonymisé (Karim, 04/11/2026).

La référence garde le format et les montants, jamais la personne : client, adresses, numéro et inventaire sont
remplacés, et l'écriture est refusée s'il reste une trace du client. Le PDF est refait depuis la spec anonyme.

    python reference_devis.py "<spec du devis>.json" "Standard + stockage + groupage"
"""

import argparse
import json
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
REFERENCES = os.path.join(ICI, "références")
GENERATEUR = os.path.join(ICI, "devis-pdf", "generer_devis_pdf.py")

CLIENT = {"nom": "CLIENT Exemple", "adresse_depart": "1 rue de l'Exemple, 33000 Bordeaux",
          "adresse_arrivee": "2 rue de l'Exemple, 75000 Paris", "telephone": "06.00.00.00.00",
          "email": "client@exemple.fr"}
PASSAGE = "3 rue de l'Exemple, 33000 Bordeaux"
NUMERO = "000000000000"
ARTICLES = ["Canapé", "Table basse", "Télévision", "Tapis", "Chaise", "Cartons", "Armoire", "Commode", "Bureau", "Lit",
            "Buffet", "Étagère"]


class TraceClient(ValueError):
    pass


def _article(n, ligne):
    """Même nombre de lignes et mêmes quantités : le format ne change pas, l'inventaire n'est plus celui du client."""
    m = re.search(r":\s*(.+)$", ligne)
    return "%s : %s" % (ARTICLES[n % len(ARTICLES)], m.group(1) if m else "1")


def traces(spec):
    """Ce qui permettrait de reconnaître le client dans la spec."""
    c = spec.get("client") or {}
    mots = [m for m in re.split(r"[\s'-]+", c.get("nom") or "") if len(m) >= 3]
    return mots + [v for v in (c.get("adresse_depart"), c.get("adresse_passage"), c.get("adresse_arrivee"),
                               c.get("telephone"), c.get("email"), spec.get("numero")) if v]


def anonymiser(spec):
    """Rend la spec anonyme. Lève TraceClient si une note ou un libellé cite encore le client."""
    a_retirer = traces(spec)
    sortie = dict(spec, numero=NUMERO, inventaire=[_article(n, l) for n, l in enumerate(spec.get("inventaire") or [])])
    sortie["client"] = dict(spec.get("client") or {}, **CLIENT)
    if sortie["client"].get("adresse_passage"):
        sortie["client"]["adresse_passage"] = PASSAGE
    texte = json.dumps(sortie, ensure_ascii=False).lower()
    restes = [t for t in a_retirer if t.lower() in texte]
    if restes:
        raise TraceClient("trace du client dans la référence : %s" % ", ".join(restes))
    return sortie


def ranger(chemin_spec, cas, dossier=REFERENCES):
    with open(chemin_spec, encoding="utf-8") as fh:
        spec = anonymiser(json.load(fh))
    cible = os.path.join(dossier, cas)
    os.makedirs(cible, exist_ok=True)
    chemin = os.path.join(cible, "%s.json" % cas)
    with open(chemin + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
    os.replace(chemin + ".tmp", chemin)
    r = subprocess.run([sys.executable, "-I", GENERATEUR, chemin, "--sortie", cible], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if r.returncode != 0:
        raise RuntimeError("generer_devis_pdf.py : %s" % (r.stderr or r.stdout)[-400:])
    pdf = os.path.join(cible, "%s.pdf" % cas)
    os.replace(r.stdout.strip().splitlines()[0].strip(), pdf)
    return pdf


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Range un devis validé dans références/, anonymisé")
    ap.add_argument("spec")
    ap.add_argument("cas", help="format « Formule + particularité », ex. Standard + stockage + groupage")
    a = ap.parse_args()
    print(ranger(a.spec, a.cas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
