#!/usr/bin/env python3
"""
Regles metier Sam'Demenage, sous forme de donnees et de fonctions pures.

Ce fichier ne fait aucun appel reseau et n'ecrit rien : il ne contient que ce qui etait
jusqu'ici re-deduit par le modele a chaque dossier (table des demenageurs, taux, nombre
de camions, sections de formule). Le coder une fois evite de le refaire raisonner.

Source : skill /calcul-devis-samdem (sections 4, 5, 7, 8) + arbitrages Samuel du 08/09/2026.
"""

# --- Taux (decision Karim 08/09/2026) ----------------------------------------

TAUX_MANUTENTION = 28          # EUR/h, partout (Karim, 23/09/2026 ; 30 du 08/09 au 22/09)
TAUX_LONGUE_DISTANCE = 20      # EUR/h par personne du camion, des que A/R > 2 h
SEUIL_LONGUE_DISTANCE_H = 2.0  # D6, Karim 05/10/2026 : regle des calculateurs (5h59 perime)
COUT_DEPL_FORFAIT = 20         # EUR HT par camion, si aucun kilometrage connu

# Copies du calculateur, exports et relectures : des livrables qui s'accumulent, gardes hors du coffre
# (Karim, 04/11/2026), a cote des PDF de donnees/Devis SamDem.
DEVIS_GENERES = __import__("os").path.normpath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "..", "donnees", "Devis générés"))

# --- Marge (decision Karim 08/09/2026, cible relevee le 09/09/2026) ----------

MARGE_CIBLE = 0.35                 # cible commerciale affichee par le calculateur (etait 0.32)
# Plus aucun blocage d'envoi sur la marge (Karim, 03/11/2026) : le plancher de 30,5 % est retire,
# la marge reste une indication et Samuel relit chaque devis avant qu'il parte.

# Next Stories (Karim, 10/09/2026) : cocher la case dans le calculateur ramene la marge a
# 21 % une fois tous les autres calculs faits. Sur ces dossiers, 21 % est la cible.
MARGE_NEXT_STORIES = 0.21

TVA = 0.20

# Commission retiree des devis Sam'Demenage le 09/09/2026 (Samuel) : plus aucune
# commission n'est ajoutee au prix, devis Next Stories compris (la case ne joue plus
# que sur les frais de dossier). Une seule exception, portee par le taux que le
# calculateur ecrit dans le JSON export (commission.taux), jamais par ce defaut :
#   - Acces Demenagement -> 0.07 (calculateur-devis-acces-demenagement.html)
# Attention : la commission n'est PAS la marge. La marge proxy vaut
# transport + 15 % des options (25 % en Premium) + marge de la prime de dimanche ;
# la manutention n'y entre jamais.
# Base commissionnable quand elle s'applique : transport + toute la manutention
# + toute la masse salariale de route + options. Rien d'autre.
COMMISSION_TAUX = 0.0

# --- Inventaire (Karim, 24/09/2026 ; seuil de 6 m3 du 22/09/2026 releve a 10) ------
# Sous 10 m3, l'inventaire est ecrit directement sur le devis : pas de PDF annexe, donc
# ni production ni envoi automatique. A 10 m3 pile, l'inventaire part.
SEUIL_INVENTAIRE_PDF_M3 = 10


def inventaire_pdf_requis(volume_m3):
    """Faut-il produire et envoyer le PDF d'inventaire ? Volume inconnu : oui."""
    try:
        return float(volume_m3) >= SEUIL_INVENTAIRE_PDF_M3
    except (TypeError, ValueError):
        return True


def dossier_christophe(commercial=None, source_volume=None, notes=()):
    """Dossier de Christophe : visite, inventaire manuscrit (Karim, 02/11/2026). La chaîne ne
    génère ni n'envoie d'inventaire : c'est une intervention humaine."""
    if "christophe" in " ".join(str(x or "") for x in (commercial, source_volume)).lower():
        return True
    return any("visite de christophe" in str(n).lower() for n in notes or ())


def cible_marge(next_stories=False):
    """Cible commerciale de ce devis : 21 % sur un dossier Next Stories, 35 % sinon."""
    return MARGE_NEXT_STORIES if next_stories else MARGE_CIBLE


# --- Table des demenageurs (skill section 4) ---------------------------------
# Colonnes : RDC, 1er, 2e, 3e, 4e, 5e, 6e. Plafond absolu de 4 deja applique.

_TABLE = [
    (3,  [2, 2, 2, 2, 2, 2, 2]),
    (7,  [2, 2, 2, 2, 2, 2, 2]),
    (11, [2, 2, 2, 3, 3, 3, 3]),
    (14, [3, 3, 3, 3, 3, 3, 3]),
    (19, [3, 3, 3, 3, 4, 4, 4]),
    (23, [3, 3, 3, 4, 4, 4, 4]),
    (27, [3, 4, 4, 4, 4, 4, 4]),
    (31, [4, 4, 4, 4, 4, 4, 4]),
    (60, [4, 4, 4, 4, 4, 4, 4]),
]

PLAFOND_DEMENAGEURS = 4


def nb_demenageurs(volume_m3, etage, ascenseur):
    """Effectif d'une phase (chargement OU dechargement), croise volume x etage.

    - Avec ascenseur : l'etage est divise par 2 (arrondi au plus proche).
    - Passage automatique a 4 si etage >= 1 ET ascenseur ET volume >= 35 m3.
    - Plafond absolu : 4.
    """
    if volume_m3 is None or etage is None:
        return None
    etage_eff = int(round(etage / 2.0)) if ascenseur else int(etage)
    col = max(0, min(6, etage_eff))
    ligne = next((v for seuil, v in _TABLE if volume_m3 <= seuil), _TABLE[-1][1])
    nb = ligne[col]
    if etage >= 1 and ascenseur and volume_m3 >= 35:
        nb = PLAFOND_DEMENAGEURS
    return min(nb, PLAFOND_DEMENAGEURS)


def nb_camions(volume_m3):
    """<= 30 m3 -> 1 camion sans demander. Au-dela, l'effectif reste a confirmer."""
    if volume_m3 is None:
        return None, False
    if volume_m3 <= 30:
        return 1, False
    return 2, True          # True = a confirmer avec Samuel


def gabarit_camion(volume_m3):
    """Coherence volume / gabarit attendue par la checklist du skill fiche."""
    if volume_m3 is None:
        return None
    if volume_m3 < 20:
        return "1 camion 20 m3"
    if volume_m3 <= 30:
        return "1 camion 30 m3"
    return "2 camions"


# --- Formules ----------------------------------------------------------------

FORMULES = ("Standard", "Confort", "Premium")


def coherence_formule(formule, mise_en_carton=False, demontage=False, protection_fragile=False):
    """Retourne la liste des incoherences formule/options (vide si tout va bien).

    Standard = aucune option (la mise en penderie est incluse, jamais une incoherence).
    Confort  = au moins une option. Premium = mise en carton complete ET demontage.
    """
    pbs = []
    if formule not in FORMULES:
        return ["Formule absente ou invalide : %r" % (formule,)]
    if formule == "Standard":
        if demontage:
            pbs.append("Standard + demontage/remontage : le demontage est une option "
                       "Confort ou Premium.")
        if mise_en_carton:
            pbs.append("Standard + mise en carton : la mise en carton est une option "
                       "Confort ou Premium.")
        if protection_fragile:
            pbs.append("Standard + protection du fragile : option Confort ou Premium.")
    if formule == "Premium" and not (mise_en_carton and demontage):
        pbs.append("Premium sans mise en carton complete ni demontage/remontage : "
                   "Premium exige les deux.")
    return pbs


# --- Portage -----------------------------------------------------------------

PORTAGE_MINIMUM_M = 10


def portage(valeur):
    """Minimum 10 m toujours applique, sans pastille. Une valeur inferieure est remontee
    a 10 ; une valeur superieure est conservee telle quelle."""
    if valeur is None:
        return PORTAGE_MINIMUM_M
    return max(PORTAGE_MINIMUM_M, int(valeur))


# --- Types de logement -> champs du calculateur ------------------------------

TYPES_LOGEMENT = {
    "maison": "Maison",
    "appartement": "Appartement",
    "duplex": "Duplex",          # le moteur applique seul la majoration d'etage
    "box": "Box",                # etape en box de stockage
    "garde-meuble": "Box",
}


def type_logement(valeur, duplex=False):
    if duplex:
        return "Duplex"
    if not valeur:
        return None
    return TYPES_LOGEMENT.get(str(valeur).strip().lower())
