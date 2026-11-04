"""Relance immediate d'une etape de la finalisation (Karim, 09/10/2026).

Une etape qui echoue sur une panne passagere (reseau, delai depasse, 5xx, 429) est relancee
tout de suite, RELANCES fois au plus, sans delai : Samuel est en train de preparer un devis, il
n'attend pas. Une erreur de donnees (contact ambigu, URL de Web App changee, refus de format)
echouerait pareil : elle n'est pas relancee, elle part au rapport.

Chaque etape relancee doit etre rejouable sans doublon — c'est le contrat de F1
(reprise-auto/plan-projet.md). Le WhatsApp et l'inventaire ne passent jamais par ici.
"""
import os
import re

RELANCES = 2

# Ce qui signe une panne passagere, dans les messages que rendent nos etapes : exceptions
# reseau de urllib, codes HTTP 5xx / 429 (formats HubSpot « HTTP 503 », Sheet / noCRM
# {'http': 503}, urllib « HTTP Error 503 »).
_PASSAGER = re.compile(
    r"timed? ?out|timeout|urlerror|urlopen error|connection(reset|aborted|refused)?error"
    r"|connection (reset|aborted|refused)|remotedisconnected|remote end closed|incompleteread"
    r"|temporar|getaddrinfo|name resolution|ssl|eof occurred|broken pipe"
    r"|http( error)? ?(5\d\d|429)\b|'http': (5\d\d|429)\b",
    re.I)


def passager(detail):
    return bool(_PASSAGER.search(str(detail or "")))


def executer(nom, fn):
    """Lance `fn()` -> (ok, detail) ; une exception (SystemExit comprise) vaut un echec.

    Rend (ok, detail, essais). Relance immediatement tant que l'echec est passager, RELANCES
    fois au plus. Une reprise reussie se dit dans le terminal, sans alerte.
    """
    essais = 0
    while True:
        essais += 1
        try:
            ok, detail = fn()
        except (Exception, SystemExit) as e:
            ok, detail = False, "%s: %s" % (type(e).__name__, e)
        if ok:
            if essais > 1:
                print("  ↻ %s : réussi au %de essai" % (nom, essais))
            return True, detail, essais
        if essais > RELANCES or not passager(detail):
            return False, detail, essais
        print("  ↻ %s : échec passager (%s) — relance %d/%d"
              % (nom, str(detail)[:120], essais, RELANCES))


def bilan(essais):
    """Ce que le rapport dit des essais faits."""
    if essais <= 1:
        return "Pas de relance : l'erreur ne vient pas d'une panne passagère, elle reviendrait à l'identique."
    return "%d essais faits, dont %d relance(s) immédiate(s), sans succès." % (essais, essais - 1)


def commande(fichier, etapes=None):
    """Commande pour rejouer ces etapes seules, depuis l'export enregistre. None sans fichier.

    Sans `etapes` : toute la finalisation, message d'equipe compris — pour un arret survenu
    avant que rien ne parte a l'equipe."""
    if not fichier or fichier in ("-", "--presse-papier") or not os.path.isfile(fichier):
        return None
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finalisation.py")
    suite = "--seulement " + ",".join(etapes) if etapes else "--whatsapp"
    return 'python "%s" "%s" --appliquer %s' % (script, os.path.abspath(fichier), suite)
