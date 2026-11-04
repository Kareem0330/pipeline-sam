#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dit ce qui est prêt et ce qui manque, avec le guide à suivre. N'écrit rien sur HubSpot et n'envoie rien.

    python verifier_installation.py                  # tout vérifier
    python verifier_installation.py --conversations  # numéros des conversations Beeper (guide 3)
    python verifier_installation.py --essai-slack    # envoie un message d'essai sur Slack (guide 4)
"""

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(ICI, "outils", "pipeline")
sys.path.insert(0, PIPE)
ENV = os.path.join(ICI, ".env")
MODULES = {"pymupdf": "pymupdf", "PIL": "pillow", "pypdf": "pypdf", "jinja2": "jinja2", "fontTools": "fonttools",
           "pandas": "pandas", "openpyxl": "openpyxl"}
NAVIGATEURS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
afaire = []


def ligne(ok, texte, guide=None, facultatif=False):
    print("  %-9s %s" % ("OK" if ok else ("Facultatif" if facultatif else "À FAIRE"), texte))
    if not ok and guide and not facultatif:
        afaire.append(guide)
    return ok


def conf():
    valeurs = {}
    if os.path.isfile(ENV):
        with open(ENV, encoding="utf-8-sig") as fh:
            for l in fh:
                k, _, v = l.strip().partition("=")
                if k and not k.startswith("#") and v.strip():
                    valeurs[k.strip()] = v.strip().strip('"\'')
    return valeurs


def logiciels():
    print("Logiciels")
    ligne(sys.version_info >= (3, 10), "Python %d.%d" % sys.version_info[:2], "01-installer-le-dossier.md")
    manquants = []
    for module, paquet in MODULES.items():
        try:
            importlib.import_module(module)
        except ImportError:
            manquants.append(paquet)
    ligne(not manquants, "modules Python" + (" : manquent %s" % ", ".join(manquants) if manquants else ""), "01-installer-le-dossier.md")
    ligne(any(os.path.exists(n) for n in NAVIGATEURS), "Chrome ou Edge, pour les PDF", "01-installer-le-dossier.md")
    claude = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    ligne(os.path.exists(claude), "commande claude, pour les inventaires en texte libre", facultatif=True)


def dossier():
    print("Dossier")
    ligne(os.path.isfile(ENV), "fichier .env", "01-installer-le-dossier.md")
    ligne("onedrive" not in ICI.lower() and "google drive" not in ICI.lower(), "hors de OneDrive et de Google Drive", "01-installer-le-dossier.md")
    ligne(ICI.isascii(), "chemin sans accent", "01-installer-le-dossier.md")
    ligne(os.path.isfile(os.path.join(PIPE, "calculateurs", "calculateur-devis.html")), "calculateur de devis", "01-installer-le-dossier.md")
    docs = os.path.join(ICI, "donnees", "Docs Devis SamDem")
    ligne(os.path.isdir(docs) and len(os.listdir(docs)) >= 4, "documents d'envoi (CGV, RIB…)", "01-installer-le-dossier.md")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'watch-devis-export' } | Measure-Object).Count"],
                           capture_output=True, text=True, timeout=30)
        ligne(int((r.stdout or "0").strip() or 0) >= 1, "veilleur du presse-papier lancé", "01-installer-le-dossier.md")
    except Exception as e:
        ligne(False, "veilleur non contrôlé (%s)" % type(e).__name__, "01-installer-le-dossier.md")


def pdf_essai():
    print("PDF")
    spec = os.path.join(ICI, "references", "exemple-spec.json")
    with tempfile.TemporaryDirectory(prefix="samdem-essai-") as tmp:
        r = subprocess.run([sys.executable, "-I", os.path.join(PIPE, "devis-pdf", "generer_devis_pdf.py"), spec, "--sortie", tmp],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        produits = [f for f in os.listdir(tmp) if f.lower().endswith(".pdf")]
    ligne(r.returncode == 0 and bool(produits), "devis d'essai généré" + ("" if produits else " : %s" % (r.stderr or r.stdout)[-200:]), "08-depannage.md")


def hubspot(c):
    print("HubSpot")
    if not ligne(bool(c.get("HUBSPOT_TOKEN")), "clé dans .env", "02-cle-hubspot.md"):
        return
    os.environ.setdefault("HUBSPOT_TOKEN", c["HUBSPOT_TOKEN"])
    import hubspot_crm as hc
    hs = hc.HubSpot(hc.charger_cle())
    for libelle, chemin in (("transactions et étapes", "/crm/v3/pipelines/deals/%s" % hc.PIPELINE),
                            ("commerciaux", "/crm/v3/owners?limit=1"),
                            ("contacts", "/crm/v3/objects/contacts?limit=1"),
                            ("fichiers", "/files/v3/files/search?limit=1")):
        try:
            hs.req("GET", chemin)
            ligne(True, libelle, "02-cle-hubspot.md")
        except Exception as e:
            ligne(False, "%s : %s" % (libelle, str(e)[:110]), "02-cle-hubspot.md")


def _chats(token, limite=200):
    tout, curseur = [], None
    while len(tout) < limite:
        url = "http://localhost:23373/v1/chats?limit=50" + ("&cursor=%s&direction=before" % curseur if curseur else "")
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        tout += d.get("items") or []
        curseur = d.get("oldestCursor")
        if not d.get("hasMore") or not curseur:
            break
    return tout


def beeper(c):
    print("WhatsApp (Beeper)")
    if not ligne(bool(c.get("BEEPER_ACCESS_TOKEN")), "jeton dans .env", "03-whatsapp-beeper.md"):
        return
    try:
        chats = _chats(c["BEEPER_ACCESS_TOKEN"])
    except Exception as e:
        ligne(False, "Beeper ne répond pas : ouvre-le (%s)" % type(e).__name__, "03-whatsapp-beeper.md")
        return
    ligne(True, "Beeper répond", "03-whatsapp-beeper.md")
    chat = c.get("SAMDEM_WHATSAPP_CHAT")
    trouve = next((x for x in chats if chat in (x.get("localChatID"), x.get("id"))), None)
    ligne(bool(trouve), "conversation : %s" % (trouve.get("title") if trouve else "à choisir (--conversations)"), "03-whatsapp-beeper.md")


def facultatifs(c):
    print("Le reste")
    ligne(bool(c.get("SAMDEM_SLACK_WEBHOOK")), "alertes Slack (guide 4)", facultatif=True)
    ligne(bool(c.get("NOTION_TOKEN")), "anciens dossiers Notion (guide 5)", facultatif=True)


def conversations(c):
    if not c.get("BEEPER_ACCESS_TOKEN"):
        raise SystemExit("Écris d'abord BEEPER_ACCESS_TOKEN dans .env (guide 3).")
    for x in _chats(c["BEEPER_ACCESS_TOKEN"]):
        print("%-8s %-10s %s" % (x.get("localChatID"), x.get("network") or "", x.get("title") or ""))


def essai_slack(c):
    if not c.get("SAMDEM_SLACK_WEBHOOK"):
        raise SystemExit("Écris d'abord SAMDEM_SLACK_WEBHOOK dans .env (guide 4).")
    req = urllib.request.Request(c["SAMDEM_SLACK_WEBHOOK"], method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"text": "Essai des alertes de la chaîne de devis : tout fonctionne."}).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=15) as r:
        print("Message envoyé." if r.status == 200 else "Slack a répondu %s." % r.status)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Vérifie l'installation de la chaîne de devis")
    ap.add_argument("--conversations", action="store_true")
    ap.add_argument("--essai-slack", action="store_true")
    a = ap.parse_args()
    c = conf()
    if a.conversations:
        conversations(c)
        return 0
    if a.essai_slack:
        essai_slack(c)
        return 0
    logiciels()
    dossier()
    pdf_essai()
    hubspot(c)
    beeper(c)
    facultatifs(c)
    print()
    if afaire:
        print("Reste à faire : suis %s, dans le dossier guides." % ", ".join(dict.fromkeys(afaire)))
        return 1
    print("Tout est prêt. Prochaine étape : guides/07-premier-devis.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
