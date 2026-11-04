#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interrupteur CRM général de tous les outils (Karim, 06/10/2026) : noCRM ou HubSpot.

Une seule ligne décide pour toute la boîte à outils, dans le fichier général outils/crm.env :

    SAMDEM_CRM=hubspot      # ou nocrm (retour arrière), ou les-deux (transition)

Aucun fichier propre à un outil n'entre en jeu : un réglage d'outil ne doit pas pouvoir
changer le CRM des autres. Seule la variable d'environnement SAMDEM_CRM passe devant (essais
ponctuels). Fichier absent ou valeur inconnue : noCRM, le comportement d'avant la migration.

Écritures (finalisation) : « les-deux » écrit dans les deux CRM.
Lectures (relances, gros dossiers, groupage, reporting…) : HubSpot seulement sur « hubspot » ;
« les-deux » lit encore noCRM, qui reste la référence tant que la bascule n'est pas faite.
"""

import os

ICI = os.path.dirname(os.path.abspath(__file__))
CRMS = ("nocrm", "hubspot", "les-deux")
CLE = "SAMDEM_CRM"


def fichier():
    """outils/crm.env, retrouvé en remontant jusqu'au dossier « outils »."""
    d = ICI
    while True:
        if os.path.basename(d) == "outils":
            return os.path.join(d, "crm.env")
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _lire(chemin):
    if not chemin or not os.path.isfile(chemin):
        return None
    with open(chemin, encoding="utf-8-sig") as f:
        for ligne in f:
            k, _, v = ligne.strip().partition("=")
            if k.strip() == CLE and v.strip():
                return v.strip().strip('"').strip("'")
    return None


def actif(choix=None):
    v = (choix or os.environ.get(CLE) or _lire(fichier()) or "nocrm").strip().lower()
    return v if v in CRMS else "nocrm"


def lecture(choix=None):
    return "hubspot" if actif(choix) == "hubspot" else "nocrm"


def nom(choix=None):
    return "HubSpot" if lecture(choix) == "hubspot" else "noCRM"


if __name__ == "__main__":
    print("CRM : %s (écritures) — lectures sur %s — réglé dans %s" % (actif(), nom(), fichier()))
