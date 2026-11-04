#!/usr/bin/env python3
"""
Pipeline dossier -> itineraire -> completude -> devis pre-rempli.

Prend un dossier.json (produit par le modele en lisant la fiche Notion) et execute en
local tout ce qui est deterministe :
  1. calcul de l'itineraire (module outils/pipeline/itineraire)
  2. deduction des parametres metier (effectifs, taux, camions — voir regles.py)
  3. score de completude : GO / GO_AVEC_RESERVES / STOP, avec relance redigee si STOP
  4. devis pre-rempli : copie du calculateur maitre, dossier injecte, ouverte au navigateur

Usage :
    python pipeline.py dossier.json                  # rapport lisible
    python pipeline.py dossier.json --json           # sortie machine
    python pipeline.py dossier.json --devis           # + devis HTML rempli, ouvert (apres controle)
    python pipeline.py dossier.json --devis --prefill # + JSON pour le calculateur en ligne
    python pipeline.py --exemple > dossier.json       # squelette de dossier

--devis copie le calculateur maitre, y injecte le dossier (const PREFILL) et ouvre le fichier :
le formulaire est rempli des l'ouverture, aucun collage. Le calcul reste celui du calculateur,
c'est le meme fichier — pas un document reconstruit. --prefill garde la voie « artefact en
ligne » : JSON au presse-papier, bouton « Charger un dossier ».

Controle d'abord (Karim, 04/11/2026) : sans --devis, le pipeline affiche ce qui partira dans le
calculateur et n'ouvre rien. --devis ne genere que ces valeurs-la, avec les memes options ; une
fiche ou une option changee impose un nouveau controle. Code de sortie 4 : generation refusee.

Aucune valeur n'est inventee : un champ absent reste absent et alimente les manquants.

Fiche introuvable (--fiche) : statut FICHE_A_CREER, code de sortie 3. Le pipeline cherche
l'opportunite du CRM et renvoie vers /creer-fiche-client-samdem. Aucun devis ne part d'une
opportunite sans fiche : finalisation.py n'aurait aucune fiche ou ecrire.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "itineraire"))
import regles                                     # noqa: E402
import demontage                                  # noqa: E402
import calcul_itineraire as itin                  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MAITRE = os.path.join(RACINE, "outils", "pipeline", "calculateurs", "calculateur-devis.html")
SORTIE = regles.DEVIS_GENERES
CALCULATEUR_URL = "outils/pipeline/calculateurs/calculateur-devis.html"
# Variante « atelier » : meme calculateur, plus une file de dossiers alimentee par Claude
# (capacite db). C'est la chaine de production ; le maitre reste partageable par lien.
CALCULATEUR_ATELIER_URL = "outils/pipeline/calculateurs/calculateur-devis-atelier.html"


# --- Completude --------------------------------------------------------------

# Un champ bloquant absent empeche le calculateur de produire un chiffre defendable.
# Chaque entree porte la question a poser au client, pour que le STOP rende une relance
# prete a envoyer plutot qu'un message d'erreur.
BLOQUANTS = [
    ("mission.volume_m3", "le volume estimé en m³ (ou un inventaire pour qu'on le calcule)"),
    ("depart.adresse_brute", "l'adresse complète de départ"),
    ("arrivee.adresse_brute", "l'adresse complète d'arrivée"),
    ("depart.etage", "l'étage du logement de départ (et s'il y a un ascenseur)"),
    ("arrivee.etage", "l'étage du logement d'arrivée (et s'il y a un ascenseur)"),
    ("mission.formule", "la formule souhaitée (Standard, Confort ou Premium)"),
]


def _get(dossier, chemin):
    cur = dossier
    for part in chemin.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _etage_connu(bloc):
    """Un RDC coche vaut un etage connu (0), meme si le champ etage est vide."""
    if not isinstance(bloc, dict):
        return False
    if bloc.get("rdc"):
        return True
    return bloc.get("etage") is not None


def evaluer_completude(dossier):
    manquants, jaunes = [], []

    for chemin, question in BLOQUANTS:
        if chemin.endswith(".etage"):
            if not _etage_connu(_get(dossier, chemin.rsplit(".", 1)[0])):
                manquants.append((chemin, question))
            continue
        if _get(dossier, chemin) in (None, "", []):
            manquants.append((chemin, question))

    itineraire = dossier.get("itineraire") or {}
    confiance = itineraire.get("confiance")
    longue_distance = itineraire.get("longue_distance")

    if confiance == "echec" and longue_distance is not False:
        manquants.append(("itineraire",
                          "les kilomètres et le temps de trajet (calcul automatique indisponible)"))
    elif confiance == "degrade":
        jaunes.append("Itinéraire calculé en mode dégradé — vérifier les alertes du module.")
    for alerte in itineraire.get("alertes", []):
        if alerte.startswith("⚠"):
            jaunes.append(alerte)
    if itineraire.get("peage_requis"):
        jaunes.append("Péage à relever manuellement (classe 3 ÷ 1,2) : A/R au-delà du seuil.")

    mission = dossier.get("mission") or {}
    if mission.get("volume_m3") is not None and not mission.get("inventaire_fourni"):
        jaunes.append("Volume annoncé sans inventaire — source : %s."
                      % (mission.get("source_volume") or "non précisée"))
    for pb in regles.coherence_formule(
            mission.get("formule"),
            mise_en_carton=bool(mission.get("mise_en_carton")),
            demontage=bool(mission.get("demontage")),
            protection_fragile=bool(mission.get("protection_fragile"))):
        jaunes.append("Incohérence : " + pb)

    volume = mission.get("volume_m3")
    if volume is not None and volume > 30:
        jaunes.append("Volume %s m³ : %s attendus, à confirmer."
                      % (volume, regles.gabarit_camion(volume)))

    # Un volume absent alors qu'un inventaire existe n'est pas une question a poser au
    # client : c'est une estimation a faire nous-memes (skill /estimer-volume-samdem).
    actions = []
    a_inventaire = bool(mission.get("inventaire_fourni") or mission.get("inventaire_texte")
                        or mission.get("inventaire_fichiers"))
    if a_inventaire:
        restant = []
        for chemin, question in manquants:
            if chemin == "mission.volume_m3":
                actions.append(
                    "Volume absent mais inventaire disponible → estimer avec "
                    "/estimer-volume-samdem (retenir le volume CONSERVATEUR), "
                    "plutôt que de le demander au client.")
            else:
                restant.append((chemin, question))
        manquants = restant

    if manquants:
        statut = "STOP"
    elif actions:
        statut = "ESTIMATION_REQUISE"
    elif jaunes:
        statut = "GO_AVEC_RESERVES"
    else:
        statut = "GO"

    return {"statut": statut,
            "manquants": [c for c, _ in manquants],
            "jaunes": jaunes,
            "actions": actions,
            "relance": _relance(dossier, manquants) if manquants else None}


def _relance(dossier, manquants):
    """Un STOP doit rendre un message pret a copier, pas une erreur."""
    client = dossier.get("client") or {}
    prenom = client.get("prenom") or ""
    lignes = ["Bonjour %s," % prenom if prenom else "Bonjour,", "",
              "Pour finaliser votre devis de déménagement, il me manque :"]
    lignes += ["– %s" % question for _, question in manquants]
    lignes += ["", "Merci d'avance,", "Sam'Déménage"]
    return "\n".join(lignes)


# --- Deduction des parametres du calculateur ---------------------------------

def deduire(dossier):
    """Parametres metier deduits : effectifs, taux, camions. Rien d'invente."""
    mission = dossier.get("mission") or {}
    depart = dossier.get("depart") or {}
    arrivee = dossier.get("arrivee") or {}
    itineraire = dossier.get("itineraire") or {}
    volume = mission.get("volume_m3")

    # Un etage ecrit prime sur la case Rdc : une maison « Rdc + R+1 » se chiffre au R+1.
    etage_dep = depart.get("etage") if depart.get("etage") is not None else (0 if depart.get("rdc") else None)
    etage_arr = arrivee.get("etage") if arrivee.get("etage") is not None else (0 if arrivee.get("rdc") else None)

    camions, a_confirmer = regles.nb_camions(volume)
    longue_distance = bool(itineraire.get("longue_distance"))

    return {
        "nb_depart": regles.nb_demenageurs(volume, etage_dep, bool(depart.get("ascenseur"))),
        "nb_arrivee": regles.nb_demenageurs(volume, etage_arr, bool(arrivee.get("ascenseur"))),
        "taux": regles.TAUX_MANUTENTION,
        "nb_camions": mission.get("nb_camions") or camions,
        "camions_a_confirmer": a_confirmer and not mission.get("nb_camions"),
        "longue_distance": longue_distance,
        "taux_conducteur": regles.TAUX_LONGUE_DISTANCE if longue_distance else "",
        "gabarit": regles.gabarit_camion(volume),
        "etage_depart": etage_dep,
        "etage_arrivee": etage_arr,
    }


# --- Objet EX du calculateur -------------------------------------------------

def construire_ex(dossier, d):
    mission = dossier.get("mission") or {}
    depart = dossier.get("depart") or {}
    arrivee = dossier.get("arrivee") or {}
    itineraire = dossier.get("itineraire") or {}
    client = dossier.get("client") or {}

    km = itineraire.get("km_ar")
    heures = itineraire.get("heures_conduite_ar")

    ex = {
        "clientNom": " ".join(x for x in [client.get("prenom"), client.get("nom")] if x),
        "volume": mission.get("volume_m3") or 0,
        "formule": mission.get("formule") or "Standard",
        "jaille": mission.get("jaille") or "Faible (< 50%)",
        "dateCreation": date.today().isoformat(),
        "groupage": bool(mission.get("groupage")),
        "weekend": bool(mission.get("weekend")),
        "nextStories": bool(mission.get("next_stories")),

        "tlDepart": regles.type_logement(depart.get("type_logement"), depart.get("duplex")) or "Maison",
        "etageDepart": d["etage_depart"] or 0,
        "portageDepart": regles.portage(depart.get("portage_m")),
        "nbDepart": d["nb_depart"] or 2,
        "tauxDepart": d["taux"],
        "ascDepart": bool(depart.get("ascenseur")),
        "ascDepartPetit": bool(depart.get("ascenseur_petit")),
        "mmDepart": depart.get("monte_meuble") or "",

        "tlArrivee": regles.type_logement(arrivee.get("type_logement"), arrivee.get("duplex")) or "Maison",
        "etageArrivee": d["etage_arrivee"] or 0,
        "portageArrivee": regles.portage(arrivee.get("portage_m")),
        "nbArrivee": d["nb_arrivee"] or 2,
        "tauxArrivee": d["taux"],
        "ascArrivee": bool(arrivee.get("ascenseur")),
        "ascArriveePetit": bool(arrivee.get("ascenseur_petit")),
        "mmArrivee": arrivee.get("monte_meuble") or "",

        # Priorite stricte : un kilometrage connu exclut le forfait de deplacement.
        "kmAR": km or 0,
        "heuresRouteAR": heures if heures is not None else 0.5,
        "coutDeplManuel": 0,   # vide : km x 0,60 si connus, sinon repli moteur 20 EUR HT/camion (Karim, 20/10/2026)
        "nbCamions": d["nb_camions"] or 1,
        "peageAR": mission.get("peage_ht") or 0,
        # En groupage, le moteur gere seul la route : ces deux champs longue distance restent vides.
        "tauxConducteur": "" if mission.get("groupage") else d["taux_conducteur"],
        "trajetAR2h": False if mission.get("groupage") else bool(d["longue_distance"]),

        "volDechetterie": mission.get("dechetterie_m3") or 0,
        "coutMateriel": mission.get("cout_materiel") or 0,
        "piano": bool(mission.get("piano")),
        "objetLourd": bool(mission.get("objet_lourd")),
        "cartonH": mission.get("carton_h") or 0,
        "demontageH": mission.get("demontage_h") or 0,
        "fragileH": mission.get("fragile_h") or 0,
    }

    # Arrets intermediaires -> sections « Étape », « Point 2 », « Point 3 » du calculateur, dans
    # l'ordre du trajet. Le moteur calcule seul la manutention sur place a partir du volume, de
    # l'etage et du portage. Au-dela de trois arrets le calculateur n'a plus de section :
    # traiter() le signale, les arrets en trop ne sont pas chiffres.
    for etape, cle in zip(dossier.get("etapes") or [], ("Etape", "Point2", "Point3")):
        ex["type" + cle] = ("Box / Garde-meuble" if etape.get("type_logement") == "garde-meuble"
                            else "Adresse intermédiaire")
        ex["etage" + cle] = etape.get("etage") or 0
        ex["vol" + cle + "Charge"] = etape.get("volume_charge_m3") or 0
        ex["vol" + cle + "Decharge"] = etape.get("volume_decharge_m3") or 0
        ex["portage" + cle] = regles.portage(etape.get("portage_m"))
        ex["asc" + cle] = bool(etape.get("ascenseur"))
        ex["asc" + cle + "Petit"] = bool(etape.get("ascenseur_petit"))

    if dossier.get("relivraison"):
        ex.update(relivraison_ex(dossier["relivraison"], mission))

    # Materiel de conditionnement : les cases cochees de la fiche deviennent mat_<cle>/qte_<cle>.
    # Une case cochee sans quantite reste cochee a 0 : c'est la fiche qui est incomplete,
    # on ne devine pas un nombre de cartons.
    for cle, quantite in (mission.get("materiel") or {}).items():
        ex["mat_%s" % cle] = True
        ex["qte_%s" % cle] = quantite or 0
    # Livraison (30 € HT, D4 du 05/10/2026) des qu'un article payant est commande : les
    # cartons penderies, pretes, ne la declenchent pas.
    ex["matLivraison"] = any(cle != "penderies" for cle in (mission.get("materiel") or {}))

    return {k: v for k, v in ex.items() if v is not None}


def relivraison_ex(rel, mission):
    """Section « Relivraison » du calculateur (Karim, 14/10/2026) : seconde operation du devis,
    du garde-meuble (box RDC) a l'adresse de relivraison. Effectifs au tableau volume x etage,
    trajet du jour calcule par traiter() ; sans km connu, le moteur compte 20 EUR HT par camion."""
    arr = rel.get("arrivee") or {}
    volume = rel.get("volume_m3") or mission.get("volume_m3") or 0
    etage = arr.get("etage") if arr.get("etage") is not None else 0
    km = rel.get("km_ar")
    heures = rel.get("heures_conduite_ar")
    camions, _ = regles.nb_camions(volume)
    return {
        "relivActif": True,
        "relivVolume": rel.get("volume_m3") or "",
        "relivTlDepart": "Box", "relivEtageDepart": 0, "relivPortageDepart": 20,
        "relivTlArrivee": regles.type_logement(arr.get("type_logement"), arr.get("duplex")) or "Appartement",
        "relivEtageArrivee": etage,
        "relivPortageArrivee": regles.portage(arr.get("portage_m")),
        "relivAscArrivee": bool(arr.get("ascenseur")),
        "relivAscArriveePetit": bool(arr.get("ascenseur_petit")),
        "relivMmArrivee": arr.get("monte_meuble") or "",
        "relivNbDepart": regles.nb_demenageurs(volume, 0, False) or 2,
        "relivNbArrivee": regles.nb_demenageurs(volume, etage, bool(arr.get("ascenseur"))) or 2,
        "relivTaux": regles.TAUX_MANUTENTION,
        "relivKmAR": km or 0,
        "relivHeuresRouteAR": heures if heures is not None else 0.5,
        "relivNbCamions": camions or 1,
    }


def _js(valeur):
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, (int, float)):
        return repr(valeur)
    return json.dumps(str(valeur), ensure_ascii=False)


def _presse_papier(texte):
    """Depose le pre-remplissage dans le presse-papier. Echec silencieux : le fichier
    reste la, on ne fait pas echouer un pipeline pour un presse-papier indisponible."""
    import subprocess
    try:
        if sys.platform.startswith("win"):
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        elif sys.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        else:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        p.communicate(texte.encode("utf-8"))
        return p.returncode == 0
    except Exception:
        return False


def construire_paquet(dossier, ex):
    """Le dossier tel que le calculateur l'attend : parametres, fiche cible, bandeau.

    Un seul objet pour les deux sorties — le JSON a coller dans l'artefact en ligne et la
    copie HTML pre-remplie. Les deux portent donc exactement la meme chose, la fiche Notion
    comprise : la finalisation n'a plus personne a qui demander « quelle fiche ? ».
    """
    depart = (dossier.get("depart") or {}).get("adresse_brute") or "?"
    arrivee = (dossier.get("arrivee") or {}).get("adresse_brute") or "?"
    meta = dossier.get("_meta") or {}
    generation = dossier.get("_generation") or {}
    page_id = (meta.get("page_id") or "").replace("-", "") or None
    arrets = [e.get("adresse_brute") for e in dossier.get("etapes") or [] if e.get("adresse_brute")]
    trajet = " → ".join([depart] + arrets + [arrivee])
    banniere = "Dossier pré-rempli — %s, %s, %s m³." % (
        ex.get("clientNom") or "client", trajet, ex.get("volume"))
    if generation.get("variante"):
        banniere += " Variante « %s »." % generation["variante"]
    if generation.get("indicatif"):
        banniere += " DEVIS INDICATIF."
    a_saisir = list(generation.get("manques") or [])
    if ((dossier.get("itineraire") or {}).get("peage_requis")
            and not (dossier.get("mission") or {}).get("peage_ht")):
        a_saisir.append("le péage A/R (classe 3 ÷ 1,2)")
    if a_saisir:
        banniere += " ⚠ À saisir avant export : %s." % " ; ".join(a_saisir)
    return {
        "schema": "samdem.devis.prefill/1",
        "genere_le": date.today().isoformat(),
        "calculateur": CALCULATEUR_URL,
        # « indicatif » voyage dans l'en-tete fiche, que le calculateur recopie tel quel dans
        # son export : la finalisation le lit pour la propriete HubSpot « Type de devis ».
        "fiche": {"page_id": page_id, "titre": meta.get("titre"), "url": meta.get("url"),
                  "indicatif": bool(generation.get("indicatif"))},
        "banniere": banniere,
        # Nom de variante pose d'avance (--variante) et noms deja finalises pour cette fiche :
        # le calculateur bloque l'export d'un doublon, qui ecraserait la variante precedente.
        "variante": generation.get("variante"),
        "variantes_existantes": variantes_existantes(page_id),
        "ex": ex,
    }


def variantes_existantes(page_id):
    """Noms de variante deja finalises pour cette fiche, d'apres le journal de finalisation.py."""
    if not page_id:
        return []
    chemin = os.path.join(SORTIE, "exports", "%s.variantes.json" % page_id)
    try:
        with open(chemin, encoding="utf-8") as fh:
            return sorted(json.load(fh).keys())
    except (OSError, ValueError, AttributeError):
        return []


def _cible(dossier, dossier_sortie, motif):
    client = dossier.get("client") or {}
    nom = (client.get("nom") or "CLIENT").upper().replace(" ", "-")
    prenom = (client.get("prenom") or "").replace(" ", "-")
    # Deux variantes d'un meme client ne doivent pas s'ecraser sur disque : le nom de la
    # variante entre dans le nom du fichier.
    variante = (dossier.get("_generation") or {}).get("variante")
    if variante:
        prenom += "_" + _slug(variante)
    os.makedirs(dossier_sortie, exist_ok=True)
    return os.path.join(dossier_sortie, motif % (nom, prenom))


def _slug(s):
    import re
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "variante"


def ouvrir(chemin):
    """Ouvre le devis dans le navigateur par defaut. Echec silencieux : le fichier reste la."""
    chemin = os.path.abspath(chemin)              # startfile echoue sur un chemin relatif
    try:
        if sys.platform.startswith("win"):
            os.startfile(chemin)                  # noqa: S606  (chemin produit par nous)
        else:
            import webbrowser
            webbrowser.open("file://" + chemin)
        return True
    except Exception:
        return False


def generer_prefill(dossier, ex, dossier_sortie=SORTIE):
    """Ecrit le JSON de pre-remplissage du calculateur EN LIGNE et le met au presse-papier.

    Voie « artefact » : on colle ce JSON dans « Charger un dossier ». La voie par defaut
    (--devis) n'en a pas besoin, elle ouvre une copie deja remplie.
    """
    cible = _cible(dossier, dossier_sortie, "Prefill_%s_%s.json")
    texte = json.dumps(construire_paquet(dossier, ex), ensure_ascii=False, indent=2)
    with open(cible, "w", encoding="utf-8") as fh:
        fh.write(texte)
    return cible, _presse_papier(texte)


# Chargement seul / dechargement seul (Karim, 28/10/2026) : le temps de manutention de la
# phase absente est force a 0 dans la copie. Le calculateur remet ses ajustements a zero en
# chargeant PREFILL : le forcage se place donc juste apres ce chargement.
ANCRE_CHARGEMENT = "if (PREFILL) chargerDossier(JSON.stringify(PREFILL));"
PHASE_A_ZERO = {"chargement": "dechargeMin", "dechargement": "chargeMin"}


def generer_devis(dossier, ex, chemin_maitre=MAITRE, dossier_sortie=SORTIE, phase_seule=None):
    """Copie le calculateur maitre et y injecte le dossier : le formulaire est rempli des
    l'ouverture, sans « Charger un dossier » ni collage. Le maitre n'est jamais modifie.

    phase_seule = "chargement" ou "dechargement" : l'autre phase est mise a 0 min."""
    cible = _cible(dossier, dossier_sortie, "Devis_%s_%s.html")
    shutil.copyfile(chemin_maitre, cible)

    with open(cible, encoding="utf-8") as fh:
        html = fh.read()

    # Substitution litterale, pas de regex : le JSON contient des antislashs et des accents
    # qui n'ont aucune raison de passer par un moteur d'expressions rationnelles. « </ » est
    # neutralise, sinon une adresse contenant « </script> » fermerait le script de la page.
    paquet = json.dumps(construire_paquet(dossier, ex), ensure_ascii=False, indent=2)
    ancre = "const PREFILL = null;"
    if ancre not in html:
        raise RuntimeError("ancre « const PREFILL = null; » introuvable dans %s — "
                           "le calculateur maitre est trop ancien." % chemin_maitre)
    html = html.replace(ancre, "const PREFILL = %s;" % paquet.replace("</", "<\\/"), 1)

    if phase_seule:
        if ANCRE_CHARGEMENT not in html:
            raise RuntimeError("ancre « %s » introuvable dans %s — impossible de mettre une "
                               "phase a 0." % (ANCRE_CHARGEMENT, chemin_maitre))
        html = html.replace(ANCRE_CHARGEMENT,
                            "if (PREFILL) { chargerDossier(JSON.stringify(PREFILL)); "
                            "overrides.%s = 0; render(); }" % PHASE_A_ZERO[phase_seule], 1)

    with open(cible, "w", encoding="utf-8") as fh:
        fh.write(html)
    return cible


# --- Controle avant generation ------------------------------------------------

# Le generateur ouvre un onglet que Samuel peut exporter : il ne part que sur des valeurs deja
# relues. Sinon un second lancement laisse deux versions ouvertes (LE TRIVIDIC, 04/11/2026).
CODE_REFUS = 4
REGISTRE_CONTROLES = os.path.join(tempfile.gettempdir(), "samdem-controles-devis.json")


def points_a_trancher(dossier, groupage_tranche=False, phase_tranchee=False):
    """Ce que le code ne chiffrerait qu'en se trompant en silence : le devis attend la reponse."""
    points = []
    for n, etape in enumerate(dossier.get("etapes") or [], 1):
        if not etape.get("type_logement"):
            points.append("Étape %d : type inconnu. Cocher le logement ou écrire "
                          "« Lieu : garde-meuble » dans la section." % n)
        if not etape.get("adresse_brute"):
            points.append("Étape %d : adresse absente." % n)
        if not (etape.get("volume_charge_m3") or etape.get("volume_decharge_m3")):
            points.append("Étape %d : aucun volume déposé ni chargé." % n)
    signaux = (dossier.get("_meta") or {}).get("signaux") or []
    if (not groupage_tranche and not (dossier.get("mission") or {}).get("groupage")
            and any(s.startswith("groupage") for s in signaux)):
        points.append("Groupage mentionné sur la fiche : relancer avec --groupage ou --sans-groupage.")
    if not phase_tranchee and any(s.startswith("chargement ou déchargement seul") for s in signaux):
        points.append("Une seule phase mentionnée sur la fiche : relancer avec --chargement-seul, "
                      "--dechargement-seul ou --deux-phases.")
    return points


def empreinte(dossier, ex, phase_seule=None):
    """Ce qui fait le devis genere. La date du jour n'en est pas : le fond ne change pas avec elle."""
    generation = dossier.get("_generation") or {}
    contenu = {"ex": {k: v for k, v in ex.items() if k != "dateCreation"}, "phase": phase_seule,
               "variante": generation.get("variante"), "indicatif": generation.get("indicatif"),
               "manques": generation.get("manques")}
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _lire_controles(registre):
    try:
        with open(registre, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _ecrire_controles(controles, registre):
    with open(registre + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(controles, fh)
    os.replace(registre + ".tmp", registre)


def noter_controle(cle, valeur, registre):
    controles = _lire_controles(registre)
    controles[cle] = valeur
    _ecrire_controles(controles, registre)


def consommer_controle(cle, valeur, registre):
    """Vrai si ces valeurs viennent d'etre controlees. Un controle vaut pour une generation."""
    controles = _lire_controles(registre)
    if controles.get(cle) != valeur:
        return False
    del controles[cle]
    _ecrire_controles(controles, registre)
    return True


def rapport_controle(ex, d):
    """Les valeurs telles qu'elles partiront dans le calculateur, pas telles que la fiche les dit."""
    def lieu(cle, nb):
        asc = "ascenseur" if ex.get("asc" + cle) else "sans ascenseur"
        return "%s, étage %s, %s, portage %s m, %s déménageurs" % (
            ex.get("tl" + cle), ex.get("etage" + cle), asc, ex.get("portage" + cle), nb)
    lignes = ["Mission : %s m³ · %s · groupage %s · %s camion(s)"
              % (ex.get("volume"), ex.get("formule"), "oui" if ex.get("groupage") else "non", ex.get("nbCamions")),
              "Départ : " + lieu("Depart", ex.get("nbDepart"))]
    for n, cle in enumerate(("Etape", "Point2", "Point3"), 1):
        if ex.get("type" + cle):
            lignes.append("Étape %d : %s, étage %s, déposé %s m³, chargé %s m³, portage %s m"
                          % (n, ex["type" + cle], ex.get("etage" + cle), ex.get("vol" + cle + "Decharge"),
                             ex.get("vol" + cle + "Charge"), ex.get("portage" + cle)))
    lignes += ["Arrivée : " + lieu("Arrivee", ex.get("nbArrivee")),
               "Trajet : %s km, %s h A/R, péage %s € HT%s"
               % (ex.get("kmAR"), ex.get("heuresRouteAR"), ex.get("peageAR"),
                  " · longue distance" if ex.get("trajetAR2h") else ""),
               "Options : carton %s h, démontage %s h, fragile %s h, autre matériel %s € HT, "
               "déchetterie %s m³, piano %s"
               % (ex.get("cartonH"), ex.get("demontageH"), ex.get("fragileH"), ex.get("coutMateriel"),
                  ex.get("volDechetterie"), "oui" if ex.get("piano") else "non")]
    materiel = ["%s x%s" % (k[4:], ex.get("qte_" + k[4:])) for k in ex if k.startswith("mat_")]
    if materiel:
        lignes.append("Matériel : " + ", ".join(materiel))
    if ex.get("relivActif"):
        lignes.append("Relivraison : %s, étage %s" % (ex.get("relivTlArrivee"), ex.get("relivEtageArrivee")))
    return lignes


def commande_devis(a, existe=False, generer=True):
    """La commande de generation (ou de controle), avec les memes options."""
    cible = '--page-id "%s"' % a.page_id if a.page_id else '--fiche "%s"' % a.fiche if a.fiche else '"%s"' % a.dossier
    options = ["--" + o.replace("_", "-") for o in ("groupage", "sans_groupage", "chargement_seul",
               "dechargement_seul", "deux_phases", "indicatif", "malgre_manques", "sans_etapes",
               "sans_itineraire", "prefill", "pas_ouvrir") if getattr(a, o)]
    if a.variante:
        options.append('--variante "%s"' % a.variante)
    if existe:
        options.append("--remplacer")
    return 'python "outils/pipeline/pipeline.py" %s%s%s' % (
        cible, " --devis" if generer else "", "".join(" " + o for o in options))


def sur_hubspot(page_id, token):
    """Ancien dossier : sa fiche Notion, lue sans y ecrire, rejoint sa transaction avant le devis.
    Rend l'id de transaction. Echec : la page Notion, la finalisation reessaiera et alertera."""
    import crm
    import fiche_notion
    if fiche_notion.est_transaction(page_id) or crm.actif() not in ("hubspot", "les-deux"):
        return page_id
    import fiche_hubspot
    try:
        deal_id, motif = fiche_hubspot.reprendre_notion(page_id, token)
    except Exception as e:
        deal_id, motif = None, "%s: %s" % (type(e).__name__, e)
    print("Ancien dossier : %s" % motif)
    return deal_id or page_id


def traiter_lot(noms, avec_itineraire=True):
    """Traite plusieurs dossiers d'affilee et rend une ligne de resultat par client.

    Chaque dossier est independant : un STOP ou une fiche introuvable n'interrompt pas le
    lot, il ressort dans le compte rendu. C'est le mode « voici les devis a faire ».
    """
    import fiche_notion
    token = fiche_notion._token()
    resultats = []
    for nom in noms:
        ligne = {"nom": nom, "statut": None, "devis": None, "prefill": None, "erreur": None,
                 "titre": None, "url": None, "manquants": [], "jaunes": []}
        try:
            page_id, titre = fiche_notion.chercher_fiche(nom, token)
            ligne["titre"] = titre
            dossier, _ = fiche_notion.lire_fiche(sur_hubspot(page_id, token), token)
            dossier, d, c = traiter(dossier, avec_itineraire=avec_itineraire)
            ligne["statut"] = c["statut"]
            ligne["manquants"] = c["manquants"]
            ligne["jaunes"] = c["jaunes"]
            ligne["relance"] = c["relance"]
            ligne["url"] = (dossier.get("_meta") or {}).get("url")
            ligne["a_trancher"] = points_a_trancher(dossier)
            if c["statut"] not in ("STOP", "ESTIMATION_REQUISE") and not ligne["a_trancher"]:
                ex = construire_ex(dossier, d)
                ligne["devis"] = generer_devis(dossier, ex)
                ligne["prefill"], _ = generer_prefill(dossier, ex)
        except SystemExit as ex:            # fiche introuvable ou ambigue
            ligne["erreur"] = str(ex)
            if str(ex).startswith("Aucune fiche"):
                ligne["statut"] = STATUT_FICHE_A_CREER
                lead, _ = opportunite_nocrm(nom)
                if lead:
                    ligne["erreur"] += (" Opportunité CRM %s (« %s ») : créer la fiche "
                                        "avant le devis." % (lead["id"], lead.get("step")))
        except Exception as ex:             # rien ne doit faire tomber le lot entier
            ligne["erreur"] = "%s : %s" % (type(ex).__name__, ex)
        resultats.append(ligne)
    return resultats


# --- Fiche absente -----------------------------------------------------------

STATUT_FICHE_A_CREER = "FICHE_A_CREER"
CODE_FICHE_A_CREER = 3


def opportunite_nocrm(nom):
    """Fiche introuvable : rend (lead, candidats) cote CRM, sans rien ecrire.

    Le devis ne part jamais de l'opportunite : la fiche est creee d'abord (decision Karim
    11/09/2026), sinon finalisation.py n'a aucune fiche ou reporter le devis.
    """
    try:
        import crm
        import nocrm
        source = nocrm
        if crm.lecture() == "hubspot":
            import hubspot_crm as source
        nom_seul, prenom = nocrm.separer_nom(nom)
        lead, candidats, _, _ = source.chercher_lead(nom_seul, prenom)
        return lead, candidats
    except Exception:
        return None, []


def fiche_a_creer(nom, erreur, en_json=False):
    lead, candidats = opportunite_nocrm(nom)
    import crm
    source = 'python "outils/pipeline/%s" --description "%s"' % (
        "hubspot_crm.py" if crm.lecture() == "hubspot" else "nocrm.py", nom)
    if en_json:
        print(json.dumps({"completude": {"statut": STATUT_FICHE_A_CREER, "erreur": erreur},
                          "nocrm": ({"id": lead["id"], "titre": lead.get("title"),
                                     "colonne": lead.get("step")} if lead else None),
                          "candidats": [{"id": c["id"], "titre": c.get("title")}
                                        for c in candidats if not lead],
                          "source_fiche": source if lead else None},
                         ensure_ascii=False, indent=2))
        return CODE_FICHE_A_CREER
    print("Statut : %s — %s" % (STATUT_FICHE_A_CREER, erreur))
    if lead:
        print("Opportunité CRM : %s (%s) — colonne « %s »"
              % (lead.get("title"), lead["id"], lead.get("step")))
        print("  → créer la fiche AVANT le devis (/creer-fiche-client-samdem)")
        print("    source : %s" % source)
        print('  → puis contrôler : python "outils/pipeline/pipeline.py" --fiche "%s"' % nom)
    elif candidats:
        print("Opportunités CRM ambiguës — désigner la bonne avant de créer la fiche :")
        for c in candidats:
            print("  ? %s (%s) — %s" % (c.get("title"), c["id"], c.get("step")))
    else:
        print("Aucune opportunité CRM non plus : créer la fiche depuis la prise de contact.")
    return CODE_FICHE_A_CREER


# --- Orchestration -----------------------------------------------------------

def _adresse_routable(adresse):
    """« Bordeaux — 🟡 adresse à compléter » -> « Bordeaux ».

    Une fiche accole souvent une mention d'attente a l'adresse. Envoyee telle quelle au
    geocodeur, elle fait echouer l'itineraire entier : on ne garde que ce qui la precede.
    """
    if not adresse:
        return None
    propre = re.split(r"\s+[—–]\s+|🟡", adresse)[0].strip(" ,;-")
    return propre or None


def traiter(dossier, avec_itineraire=True, sans_etapes=False):
    if sans_etapes and dossier.get("etapes"):
        # Variante directe d'une fiche qui porte des arrets : l'itineraire et le peage ecrits
        # dans la fiche sont ceux du trajet AVEC arrets. On les ecarte, la boucle est recalculee.
        dossier["etapes"] = []
        dossier["itineraire"] = {}
        (dossier.get("mission") or {})["peage_ht"] = None
    if avec_itineraire and not (dossier.get("itineraire") or {}).get("km_ar"):
        dep = _adresse_routable((dossier.get("depart") or {}).get("adresse_brute"))
        arr = _adresse_routable((dossier.get("arrivee") or {}).get("adresse_brute"))
        if dep and arr:
            etapes = [a for a in (_adresse_routable(e.get("adresse_brute"))
                                  for e in dossier.get("etapes") or []) if a]
            dossier["itineraire"] = itin.calculer(dep, arr, etapes)

    rel = dossier.get("relivraison")
    reserves_reliv = []
    if rel:
        origine = rel.get("origine") or itin.DEPOT
        if "loub" not in origine.lower():
            reserves_reliv.append("Relivraison — départ hors du garde-meuble de Saint-Loubès (« %s ») : "
                                  "chiffré comme un box au RDC, à vérifier." % origine)
        arr_r = _adresse_routable((rel.get("arrivee") or {}).get("adresse_brute"))
        if avec_itineraire and not rel.get("km_ar") and arr_r:
            it = itin.calculer(_adresse_routable(origine) or itin.DEPOT, arr_r)
            rel["itineraire"] = it
            if it.get("confiance") in ("ok", "degrade"):
                rel["km_ar"], rel["heures_conduite_ar"] = it.get("km_ar"), it.get("heures_conduite_ar")
                reserves_reliv += ["Relivraison — " + a for a in it.get("alertes") or []]
            else:
                reserves_reliv.append("Relivraison — trajet du jour non calculé : à saisir dans le calculateur.")
        elif not rel.get("km_ar"):
            reserves_reliv.append("Relivraison — trajet du jour inconnu : à saisir dans le calculateur.")

    deductions = deduire(dossier)
    est = estimer_demontage(dossier, deductions)
    completude = evaluer_completude(dossier)
    if reserves_reliv:
        completude["jaunes"] += reserves_reliv
        if completude["statut"] == "GO":
            completude["statut"] = "GO_AVEC_RESERVES"
    if est:
        reserves = (["Démontage — « %s » : hors barème, temps non compté." % l
                     for l in est["non_reconnues"]]
                    + ["Démontage — « %s » : au barème sans temps, non compté." % l
                       for l in est["sans_temps"]])
        completude["jaunes"] += reserves
        if reserves and completude["statut"] == "GO":
            completude["statut"] = "GO_AVEC_RESERVES"
    if len(dossier.get("etapes") or []) > 3:
        completude["jaunes"].append("⚠ %d arrêts intermédiaires : le calculateur n'en chiffre "
                                    "que 3." % len(dossier["etapes"]))
        if completude["statut"] == "GO":
            completude["statut"] = "GO_AVEC_RESERVES"
    dossier["completude"] = completude
    return dossier, deductions, completude


def estimer_demontage(dossier, d):
    """Lignes de démontage sans durée écrite -> temps du barème, saisi tel quel.

    Le barème (demontage.py) et le calculateur comptent 2 personnes au démontage, quel que
    soit l'effectif (Karim, 06/10/2026). Une durée écrite dans la fiche reste prioritaire.
    """
    mission = dossier.get("mission") or {}
    elements = mission.get("demontage_elements") or []
    if not elements:
        return None
    est = demontage.estimer(elements)
    mission["demontage_h"] = round((mission.get("demontage_h") or 0) + est["heures"], 2)
    dossier["mission"] = mission
    dossier["demontage"] = est
    return est


EXEMPLE = {
    "client": {"nom": "DUPONT", "prenom": "Marie", "tel": None, "email": None},
    "depart": {"adresse_brute": "12 rue de Bazeilles, 33400 Talence",
               "type_logement": "appartement", "etage": 3, "ascenseur": False,
               "rdc": False, "duplex": False, "portage_m": None},
    "arrivee": {"adresse_brute": "5 rue de Rivoli, 75004 Paris",
                "type_logement": "appartement", "etage": 2, "ascenseur": True,
                "rdc": False, "duplex": False, "portage_m": None},
    "etapes": [],
    "mission": {"volume_m3": 22, "source_volume": "inventaire client", "formule": "Confort",
                "inventaire_fourni": True, "demontage": True, "commercial": "Christophe"},
    "itineraire": {},
}


def main():
    ap = argparse.ArgumentParser(description="Pipeline dossier -> devis Sam'Demenage")
    ap.add_argument("dossier", nargs="?", help="chemin du dossier.json ('-' = stdin)")
    ap.add_argument("--fiche", metavar="NOM",
                    help="lire directement la fiche de ce client : note HubSpot, ou ancienne page Notion")
    ap.add_argument("--fiches", nargs="+", metavar="NOM",
                    help="traiter plusieurs dossiers d'affilee (implique --devis)")
    ap.add_argument("--page-id", help="id de la transaction (ou d'une ancienne page Notion), si le nom est ambigu")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--devis", action="store_true",
                    help="copie HTML du calculateur deja remplie, ouverte dans le navigateur")
    ap.add_argument("--copie-html", action="store_true",
                    help=argparse.SUPPRESS)          # ancien nom de --devis
    ap.add_argument("--prefill", action="store_true",
                    help="en plus : JSON a coller dans le calculateur en ligne (presse-papier)")
    ap.add_argument("--pas-ouvrir", action="store_true",
                    help="generer le devis sans l'ouvrir")
    ap.add_argument("--sans-itineraire", action="store_true")
    ap.add_argument("--variante", metavar="NOM",
                    help="nom de la variante : pre-rempli dans le calculateur et repris dans "
                         "le nom du fichier (deux variantes d'un client ne s'ecrasent plus)")
    ap.add_argument("--sans-etapes", action="store_true",
                    help="ignorer les arrets de la fiche (variante directe) et recalculer "
                         "l'itineraire sans eux")
    ap.add_argument("--malgre-manques", action="store_true",
                    help="generer le devis meme si un champ bloquant manque (sauf le volume) : "
                         "le bandeau du calculateur liste ce qui reste a saisir")
    ap.add_argument("--indicatif", action="store_true",
                    help="devis indicatif : « Type de devis » = Indicatif sur la transaction HubSpot "
                         "a la finalisation (sinon Ferme)")
    groupage = ap.add_mutually_exclusive_group()
    groupage.add_argument("--groupage", action="store_true",
                          help="cocher « Groupage » : la fiche le signale, le modele tranche")
    groupage.add_argument("--sans-groupage", action="store_true",
                          help="la fiche mentionne le groupage, mais ce devis n'en est pas un")
    ap.add_argument("--remplacer", action="store_true",
                    help="regenerer un devis deja genere : l'ancien onglet reste a fermer")
    seule = ap.add_mutually_exclusive_group()
    seule.add_argument("--chargement-seul", action="store_true",
                       help="on ne fait que le chargement : temps de dechargement mis a 0")
    seule.add_argument("--dechargement-seul", action="store_true",
                       help="on ne fait que le dechargement : temps de chargement mis a 0")
    seule.add_argument("--deux-phases", action="store_true",
                       help="la fiche mentionne une seule phase, mais les deux sont a chiffrer")
    ap.add_argument("--exemple", action="store_true", help="afficher un dossier.json type")
    a = ap.parse_args()
    phase_seule = ("chargement" if a.chargement_seul
                   else "dechargement" if a.dechargement_seul else None)

    if a.exemple:
        print(json.dumps(EXEMPLE, ensure_ascii=False, indent=2))
        return 0

    if a.fiches:
        res = traiter_lot(a.fiches, avec_itineraire=not a.sans_itineraire)
        if a.json:
            print(json.dumps({"lot": res, "calculateur": CALCULATEUR_URL},
                             ensure_ascii=False, indent=2))
            return 0
        pret = 0
        for r in res:
            if r["erreur"]:
                print("✗ %-28s %s" % (r["nom"], r["erreur"].splitlines()[0]))
            elif r.get("a_trancher"):
                print("⏸ %-28s à trancher : %s" % (r["titre"] or r["nom"], " ".join(r["a_trancher"])))
            elif r["devis"]:
                pret += 1
                print("✓ %-28s %-18s %s" % (r["titre"], r["statut"], r["devis"]))
                for j in r["jaunes"]:
                    print("    🟡 %s" % j[:150])
            else:
                print("⏸ %-28s %-18s manque : %s"
                      % (r["titre"] or r["nom"], r["statut"], ", ".join(r["manquants"]) or "—"))
        print("\n%d dossier(s) prêts sur %d — chaque fichier s'ouvre déjà rempli." % (pret, len(res)))
        print("Vérifier la marge, puis « Exporter JSON ».")
        return 0

    if a.fiche or a.page_id:
        import fiche_notion
        token = fiche_notion._token()
        page_id = a.page_id
        if not page_id:
            try:
                page_id = fiche_notion.chercher_fiche(a.fiche, token)[0]
            except SystemExit as ex:
                if not str(ex).startswith("Aucune fiche"):
                    raise
                return fiche_a_creer(a.fiche, str(ex), a.json)
        if a.devis or a.copie_html or a.prefill:
            page_id = sur_hubspot(page_id, token)
        dossier, _ = fiche_notion.lire_fiche(page_id, token)
    elif a.dossier == "-":
        dossier = json.load(sys.stdin)
    elif a.dossier:
        with open(a.dossier, encoding="utf-8") as fh:
            dossier = json.load(fh)
    else:
        ap.error("dossier.json, --fiche ou --page-id requis (ou --exemple)")

    dossier, d, c = traiter(dossier, avec_itineraire=not a.sans_itineraire,
                            sans_etapes=a.sans_etapes)
    dossier["_generation"] = {"variante": (a.variante or "").strip() or None, "manques": [],
                              "indicatif": a.indicatif}
    if a.groupage:
        dossier.setdefault("mission", {})["groupage"] = True
    # --malgre-manques : Samuel saisit lui-meme une hypothese dans le calculateur. Jamais sans
    # volume ni itineraire — un devis a 0 m3 ou a 0 km n'est pas une hypothese, c'est un
    # chiffre faux.
    forcer = (a.malgre_manques and c["statut"] == "STOP"
              and not {"mission.volume_m3", "itineraire"} & set(c["manquants"]))
    if forcer:
        libelles = dict(BLOQUANTS)
        dossier["_generation"]["manques"] = [libelles.get(m, m) for m in c["manquants"]]

    fichier, prefill, colle, ouvert = None, None, False, None
    veut_devis = a.devis or a.copie_html
    veut_generer = veut_devis or a.prefill
    a_trancher = points_a_trancher(dossier, a.groupage or a.sans_groupage,
                                   bool(phase_seule) or a.deux_phases)
    chiffrable = (forcer or c["statut"] not in ("STOP", "ESTIMATION_REQUISE")) and not a_trancher
    ex = construire_ex(dossier, d) if chiffrable else None
    existe = bool(ex) and os.path.exists(_cible(dossier, SORTIE, "Devis_%s_%s.html"))
    refus = None
    if ex:
        marque = empreinte(dossier, ex, phase_seule)
        cle_controle = os.path.basename(_cible(dossier, SORTIE, "%s_%s"))
        if not veut_generer:
            noter_controle(cle_controle, marque, REGISTRE_CONTROLES)
        elif veut_devis and existe and not a.remplacer:
            refus = ("ce devis a déjà été généré. Relancer le contrôle, puis générer avec --remplacer "
                     "et faire fermer l'ancien onglet, qui porte l'ancienne version.")
        elif not consommer_controle(cle_controle, marque, REGISTRE_CONTROLES):
            refus = "valeurs non contrôlées, ou fiche et options changées depuis le contrôle."
    elif veut_generer and a_trancher:
        refus = "des points restent à trancher."
    if ex and veut_generer and not refus:
        if veut_devis:
            fichier = generer_devis(dossier, ex, dossier_sortie=SORTIE, phase_seule=phase_seule)
            ouvert = None if a.pas_ouvrir else ouvrir(fichier)
        if a.prefill:
            prefill, colle = generer_prefill(dossier, ex)
        # Devis indicatif : la transaction est marquee tout de suite (Karim, 09/10/2026) ; la
        # finalisation le reecrit ensuite a partir de l'export.
        import crm
        if a.indicatif and crm.actif() in ("hubspot", "les-deux"):
            import hubspot_crm
            cl = dossier.get("client") or {}
            ok, msg = hubspot_crm.marquer_type_devis(
                "Indicatif", page_id=(dossier.get("_meta") or {}).get("page_id"), tel=cl.get("tel"),
                email=cl.get("email"), nom=cl.get("nom"), prenom=cl.get("prenom"))
            print("HubSpot : %s%s" % ("" if ok else "⚠ ", msg))

    meta = dossier.get("_meta") or {}

    if a.json:
        print(json.dumps({"completude": c, "deductions": d, "a_trancher": a_trancher,
                          "controle": rapport_controle(ex, d) if ex else None, "refus": refus,
                          "itineraire": dossier.get("itineraire"), "devis": fichier,
                          "demontage": dossier.get("demontage"),
                          "ouvert": ouvert, "prefill": prefill, "calculateur": CALCULATEUR_URL,
                          "fiche": meta},
                         ensure_ascii=False, indent=2))
        return CODE_REFUS if refus else 0

    if meta.get("titre"):
        print("Fiche : %s (%s lignes lues)" % (meta["titre"], meta.get("lignes_corps", "?")))
    print("Statut : %s" % c["statut"])
    it = dossier.get("itineraire") or {}
    if it.get("km_ar"):
        # Un itineraire relu dans le corps de la fiche n'a pas de variante ni de source
        # calculee : il ne porte que les chiffres ecrits par Samuel.
        detail = it.get("variante", it.get("source", "")).replace("_", " ")
        print("Itinéraire : %s km A/R, %s h de conduite%s%s"
              % (it["km_ar"], it.get("heures_conduite_ar"),
                 ", " + detail if detail else "",
                 " — longue distance" if it.get("longue_distance") else ""))
    q = lambda v: "?" if v is None else v          # champ non deductible : jamais invente
    print("Effectifs : %s au chargement, %s au déchargement · %s · manutention %s €/h%s"
          % (q(d["nb_depart"]), q(d["nb_arrivee"]), q(d["gabarit"]), d["taux"],
             " · conducteur %s €/h" % d["taux_conducteur"] if d["longue_distance"] else ""))
    if d["camions_a_confirmer"]:
        print("  ⚠ nombre de camions à confirmer (volume > 30 m³)")
    rel = dossier.get("relivraison")
    if rel:
        rex = relivraison_ex(rel, dossier.get("mission") or {})
        print("Relivraison : %s m³ → %s %s, %s au chargement / %s au déchargement · %s km A/R, %s h"
              % (rex["relivVolume"] or "volume déposé", rex["relivTlArrivee"].lower(),
                 "RDC" if not rex["relivEtageArrivee"] else "étage %s" % rex["relivEtageArrivee"],
                 rex["relivNbDepart"], rex["relivNbArrivee"], rex["relivKmAR"] or "?",
                 rex["relivHeuresRouteAR"]))
    if dossier.get("demontage"):
        print(demontage.rapport(dossier["demontage"]))
    for j in c["jaunes"]:
        print("  %s" % j if j.startswith("⚠") else "  🟡 %s" % j)
    for act in c.get("actions", []):
        print("  → %s" % act)

    # Ce que la fiche a dit et que le code ne tranche pas : divergences corps/propriétés,
    # mentions à arbitrer, pastilles 🟡. C'est la seule part qui appelle une lecture humaine.
    for div in meta.get("divergences", []):
        print("  ⚠ %s : corps « %s » ≠ propriété « %s » → le corps fait foi."
              % (div["champ"], div["corps"], div["propriete"]))
    for repli in meta.get("replis", []):
        print("  · %s" % repli)
    for sig in meta.get("signaux", []):
        print("  ? %s" % sig)
    if meta.get("non_parse"):
        print("  ? lignes non reconnues : %s" % " | ".join(meta["non_parse"][:5]))
    alertes = meta.get("alertes") or []
    if alertes:
        print("  🟡 %d point(s) 🟡 dans la fiche :" % len(alertes))
        for al in alertes[:8]:
            print("     %s" % al[:160])
    if meta.get("deja_chiffre"):
        print("  · la fiche porte déjà un chiffrage (devis antérieur).")
    if c["statut"] == "STOP":
        print("\nManque : %s" % ", ".join(c["manquants"]))
        if forcer:
            print("  → devis généré malgré tout (--malgre-manques) : à saisir dans le calculateur.")
        else:
            print("\n--- Relance à envoyer ---\n%s" % c["relance"])
    if a_trancher:
        print("\nÀ trancher avant de générer :")
        for point in a_trancher:
            print("  ⏸ %s" % point)
    if ex and not fichier and not a.prefill or refus:
        if ex:
            print("\nCe qui partira dans le calculateur :")
            for ligne in rapport_controle(ex, d):
                print("  %s" % ligne)
        if refus:
            print("\nGénération refusée : %s" % refus)
            if ex:
                print("  → contrôler : %s" % commande_devis(a, generer=False))
            return CODE_REFUS
        print("\nContrôle noté. Vérifier ces valeurs, puis générer une seule fois :")
        print("  %s" % commande_devis(a, existe))
        if existe:
            print("  ⚠ Un devis existe déjà : faire fermer son onglet, il porte l'ancienne version.")
    if fichier:
        print("\nDevis pré-rempli : %s" % fichier)
        if phase_seule:
            print("  → %s" % ("Chargement seul : temps de déchargement mis à 0 min."
                              if phase_seule == "chargement"
                              else "Déchargement seul : temps de chargement mis à 0 min."))
        if ouvert is True:
            print("  → ouvert dans le navigateur, formulaire déjà rempli.")
        elif ouvert is False:
            print("  → à ouvrir à la main : l'ouverture automatique a échoué.")
        _ns = bool((dossier.get("mission") or {}).get("next_stories"))
        print("  → vérifier la marge (cible %g %%%s), puis « Exporter JSON »"
              % (regles.cible_marge(_ns) * 100,
                 " · Next Stories, marge calée automatiquement" if _ns else ""))
        print("    puis : python finalisation.py --presse-papier --fiche \"%s\"" %
              ((dossier.get("client") or {}).get("nom") or "NOM"))
    if prefill:
        print("\nPré-remplissage (calculateur en ligne) : %s%s"
              % (prefill, "  (copié dans le presse-papier)" if colle else ""))
        print("  → atelier : %s   ou partagé : %s" % (CALCULATEUR_ATELIER_URL, CALCULATEUR_URL))
        print("    puis « Charger un dossier » → coller → « Remplir le formulaire ».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
