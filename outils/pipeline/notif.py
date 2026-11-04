#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notifications sortantes de la chaine devis — WhatsApp via l'API locale de Beeper Desktop.

Pourquoi pas par le modele : Beeper Desktop ecoute sur http://localhost:23373. Un script peut
donc poster un message directement, en quelques millisecondes et **sans consommer un seul
token**. Faire reveiller un agent pour envoyer une ligne de texte couterait le chargement d'un
contexte entier (des dizaines de milliers de tokens) pour un appel qui tient en trois lignes.

Configuration — dans .env (meme fichier que NOTION_TOKEN) :

    BEEPER_ACCESS_TOKEN=<jeton cree dans Beeper Desktop : Settings > Developer / API>
    SAMDEM_WHATSAPP_CHAT=10          # « Devis/inventaire » ; vide = aucun envoi

Tant que ces deux cles ne sont pas renseignees, RIEN n'est envoye : le message part dans une
file d'attente lisible (.claude/scripts/whatsapp-file-attente.jsonl) et la chaine continue.
Une notification qui echoue ne doit jamais faire echouer une ecriture de fiche.

Usage :
    python notif.py --test                        # verifie le jeton et le chat
    python notif.py "Message a envoyer"           # envoie sur le chat configure
    python notif.py "Message" --chat 10
    python notif.py "Légende" --fichier "D:/.../inventaire X.pdf"   # fichier joint
    python notif.py --file-attente                # affiche ce qui n'a pas pu partir
    python notif.py --vider-file-attente          # tente de renvoyer la file, puis la vide
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import export                                     # noqa: E402  (lecture de .env)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BEEPER_API = "http://localhost:23373/v1"
RACINE = os.path.normpath(os.path.join(ICI, "..", ".."))
FILE_ATTENTE = os.path.join(RACINE, ".claude", "scripts", "whatsapp-file-attente.jsonl")

# Alertes d'incident : Slack (decision Samuel du 18/09/2026 — tout au meme endroit, boite mail
# degagee), via un webhook entrant (SAMDEM_SLACK_WEBHOOK). L'e-mail du 10/09/2026 ne sert plus
# que de repli quand Slack ne repond pas : il passe par la Web App Apps Script deja deployee
# pour le Google Sheet, qui tourne sous le compte Google de Samuel (MailApp, aucun mot de passe).
ALERTE_A_DEFAUT = "contact@samdemenage.fr"
JOURNAL_ALERTES = os.path.join(RACINE, ".claude", "scripts", "alertes.jsonl")


def _conf():
    c = export.config()
    return c.get("BEEPER_ACCESS_TOKEN"), c.get("SAMDEM_WHATSAPP_CHAT")


def _mettre_en_attente(texte, chat, raison):
    os.makedirs(os.path.dirname(FILE_ATTENTE), exist_ok=True)
    with open(FILE_ATTENTE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"chat": chat, "texte": texte, "raison": raison},
                            ensure_ascii=False) + "\n")


def envoyer(texte, chat=None, token=None):
    """Poste un message sur un chat Beeper. Rend (ok, detail).

    Ne leve jamais : l'appelant est en train de finaliser une fiche, une notification ratee
    ne doit pas casser son travail. Le message non parti est conserve dans la file d'attente.
    """
    tok_conf, chat_conf = _conf()
    token = token or tok_conf
    chat = chat or chat_conf
    if not token or "REMPLACER" in token:
        _mettre_en_attente(texte, chat, "BEEPER_ACCESS_TOKEN absent")
        return False, "BEEPER_ACCESS_TOKEN absent de %s — message mis en attente." % export.ENV
    if not chat:
        _mettre_en_attente(texte, chat, "SAMDEM_WHATSAPP_CHAT absent")
        return False, "SAMDEM_WHATSAPP_CHAT absent de %s — message mis en attente." % export.ENV

    url = "%s/chats/%s/messages" % (BEEPER_API, urllib.request.quote(str(chat), safe=""))
    req = urllib.request.Request(
        url, data=json.dumps({"text": texte}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, (json.loads(r.read().decode("utf-8")) or {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        _mettre_en_attente(texte, chat, "HTTP %s" % e.code)
        if e.code == 401:
            detail += " — jeton refusé (le régénérer dans Beeper Desktop)."
        return False, "HTTP %s : %s" % (e.code, detail)
    except Exception as e:                          # Beeper Desktop ferme, reseau, timeout
        _mettre_en_attente(texte, chat, str(e))
        return False, "%s — Beeper Desktop est-il ouvert ?" % e


def _deposer(chemin, token):
    """Depose un fichier chez Beeper Desktop (POST /assets/upload, multipart). Rend l'uploadID."""
    import mimetypes
    import uuid
    nom = os.path.basename(chemin)
    mime = mimetypes.guess_type(nom)[0] or "application/octet-stream"
    borne = "----samdem" + uuid.uuid4().hex
    with open(chemin, "rb") as fh:
        contenu = fh.read()
    corps = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
              "Content-Type: %s\r\n\r\n" % (borne, nom, mime)).encode("utf-8") + contenu
             + ("\r\n--%s\r\nContent-Disposition: form-data; name=\"fileName\"\r\n\r\n%s"
                "\r\n--%s--\r\n" % (borne, nom, borne)).encode("utf-8"))
    req = urllib.request.Request(
        BEEPER_API + "/assets/upload", data=corps, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + borne,
                 "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        rep = json.loads(r.read().decode("utf-8")) or {}
    if rep.get("error") or not rep.get("uploadID"):
        raise RuntimeError("dépôt refusé par Beeper : %s" % (rep.get("error") or rep))
    return rep["uploadID"], nom, rep.get("mimeType") or mime


def envoyer_fichier(chemin, texte="", chat=None, token=None):
    """Poste un fichier (avec un texte d'accompagnement) sur un chat Beeper. Rend (ok, detail).

    Meme contrat que `envoyer` : ne leve jamais, et un envoi rate part dans la file d'attente
    avec le chemin du fichier — `--vider-file-attente` le renverra tel quel.
    """
    tok_conf, chat_conf = _conf()
    token = token or tok_conf
    chat = chat or chat_conf

    def attente(raison):
        os.makedirs(os.path.dirname(FILE_ATTENTE), exist_ok=True)
        with open(FILE_ATTENTE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"chat": chat, "texte": texte, "fichier": chemin,
                                 "raison": raison}, ensure_ascii=False) + "\n")

    if not os.path.isfile(chemin):
        return False, "fichier introuvable : %s" % chemin
    if not token or "REMPLACER" in token or not chat:
        attente("BEEPER_ACCESS_TOKEN ou SAMDEM_WHATSAPP_CHAT absent")
        return False, "configuration Beeper incomplète dans %s — fichier mis en attente." % export.ENV
    try:
        upload_id, nom, mime = _deposer(chemin, token)
        url = "%s/chats/%s/messages" % (BEEPER_API, urllib.request.quote(str(chat), safe=""))
        charge = {"attachment": {"uploadID": upload_id, "fileName": nom, "mimeType": mime}}
        if texte:
            charge["text"] = texte
        req = urllib.request.Request(
            url, data=json.dumps(charge, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=60) as r:
            rep = json.loads(r.read().decode("utf-8")) or {}
        # Beeper rend un pendingMessageID : sans lui, rien ne prouve que le message est parti.
        if not rep.get("pendingMessageID"):
            attente("réponse sans pendingMessageID")
            return False, "Beeper n'a pas confirmé l'envoi : %s" % rep
        return True, rep
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        attente("HTTP %s" % e.code)
        return False, "HTTP %s : %s" % (e.code, detail)
    except Exception as e:
        attente(str(e))
        return False, "%s — Beeper Desktop est-il ouvert ?" % e


def _eur0(v):
    return "{:,.0f}".format(v).replace(",", " ")


def message_devis(ex, tps=None, variantes=None, pdfs=(), a_la_main=None, a_verifier=()):
    """Le message envoye a l'equipe quand une fiche vient d'etre remplie.

    `variantes` : ce que le journal de la fiche a retenu (nom -> montants). A plusieurs, on
    liste les prix au lieu d'en donner un seul — un client, un message.
    `pdfs` : les PDF du devis valides par Samuel et joints a la transaction (Karim, 03/11/2026) : le
    message n'en donne que le nom. `a_la_main` : le motif quand il reste a produire,
    `a_verifier` : ce qu'il faut controler avant d'envoyer.
    """
    ch = ex.get("champs_fiche") or {}
    fiche = ex.get("fiche") or {}
    m = ex.get("mission") or {}
    # Devis indicatif : titre distinct pour que Sandrine applique le bon modele d'e-mail
    # (Karim, 09/10/2026).
    titre = ("Devis ⚠️ INDICATIF ⚠️" if fiche.get("indicatif")
             else "Devis prêt à vérifier" if pdfs else "Devis prêt à produire")
    lignes =["%s — %s" % (titre, fiche.get("titre") or ex.get("client") or "client")]
    multi = variantes and len(variantes) > 1
    if m.get("volume") is not None:
        lignes.append("%s m³%s" % (m.get("volume"),
                                   "" if multi else " · " + (m.get("formule") or "")))
    if multi:
        largeur = max(len(v) for v in variantes)
        for nom in sorted(variantes):
            ttc = (variantes[nom] or {}).get("total_ttc")
            lignes.append("  %s  %s € TTC" % (nom.ljust(largeur),
                                              _eur0(ttc) if ttc is not None else "—"))
    elif ch.get("total_ttc") is not None:
        lignes.append("Total : %s € TTC" % _eur0(ch["total_ttc"]))
    if tps and not multi:
        lignes.append("Mission estimée : %dh%02d" % (tps["mission"] // 60, tps["mission"] % 60))
    if pdfs:
        lignes.append("PDF sur HubSpot, pas encore envoyé au client : %s." % ", ".join(pdfs))
    if a_la_main:
        lignes.append("PDF à produire à la main : %s." % a_la_main)
    if a_verifier:
        lignes.append("À vérifier avant envoi : %s." % ", ".join(a_verifier))
    # Pas de marge dans ce message : le groupe reunit des personnes qui n'ont pas a la voir
    # (decision Karim, 08/09/2026). Elle reste dans le calculateur, la fiche et le journal.
    # Le lien de la transaction HubSpot, plus celui de la fiche Notion (Karim, 03/11/2026). La
    # fiche Notion ne sert que de repli, quand la transaction est introuvable ou ambiguë.
    if fiche.get("hubspot_url"):
        lignes.append("Transaction HubSpot :")
        lignes.append(fiche["hubspot_url"])
    elif fiche.get("url"):
        lignes.append("Transaction HubSpot introuvable, fiche Notion :")
        lignes.append(fiche["url"])
    return "\n".join(lignes)


# --- Alertes d'incident (Slack, e-mail en repli) ---------------------------
#
# Ce que doit contenir une alerte, et rien d'autre : QUOI a echoue, OU, POURQUOI, et QUOI
# FAIRE. Une trace Python collee telle quelle n'apprend rien a qui lit son telephone entre
# deux chantiers — la cause y est traduite, la trace reste en bas pour le jour ou il faut
# creuser.

def _corps_alerte(quoi, ou, cause, dossier=None, faire=None, trace=None):
    import datetime
    bloc = [
        "Une étape de la chaîne devis a échoué. Le reste du traitement, lui, a continué :",
        "rien n'est perdu, mais ce point-là est à reprendre à la main.",
        "",
        "CE QUI A ÉCHOUÉ",
        "  %s" % quoi,
        "",
        "OÙ",
        "  %s" % ou,
    ]
    if dossier:
        bloc += ["", "DOSSIER", "  %s" % dossier]
    bloc += ["", "POURQUOI", "  %s" % cause]
    if faire:
        bloc += ["", "QUOI FAIRE", "  %s" % faire]
    if trace:
        bloc += ["", "DÉTAIL TECHNIQUE", "  " + str(trace).replace("\n", "\n  ")]
    bloc += ["", "--",
             "Message automatique de la chaîne devis Sam'Déménage (%s)."
             % datetime.datetime.now().strftime("%d/%m/%Y %H:%M")]
    return "\n".join(bloc)


def _journaliser_alerte(donnees):
    """Trace locale. Un incident dont la notification echoue reste lisible quelque part."""
    try:
        os.makedirs(os.path.dirname(JOURNAL_ALERTES), exist_ok=True)
        with open(JOURNAL_ALERTES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(donnees, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _mrkdwn(s):
    """Echappement Slack : sans lui, un `<` dans une trace casse la mise en forme."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blocs_slack(quoi, ou, cause, dossier=None, faire=None, trace=None):
    import datetime
    # Une section Slack plafonne a 3000 caracteres : au-dela, tout le message est refuse.
    sec = lambda t: {"type": "section", "text": {"type": "mrkdwn", "text": t[:2990]}}
    blocs = [
        {"type": "header", "text": {"type": "plain_text", "emoji": True,
                                    "text": ("🚨 Chaîne devis — échec")[:150]}},
        sec("*Ce qui a échoué*\n%s" % _mrkdwn(quoi)),
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": "*Dossier*\n%s" % _mrkdwn(dossier or "—")},
            {"type": "mrkdwn", "text": "*Où*\n%s" % _mrkdwn(ou)[:1900]}]},
        sec("*Pourquoi*\n%s" % _mrkdwn(cause)),
    ]
    if faire:
        blocs.append(sec("*Quoi faire*\n%s" % _mrkdwn(faire)))
    if trace:
        t = _mrkdwn(trace)
        if len(t) > 2800:
            t = "…" + t[-2800:]                 # la fin d'une trace porte l'erreur
        blocs.append(sec("*Détail technique*\n```%s```" % t))
    blocs.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
        "Le reste du traitement a continué — ce point-là est à reprendre à la main · %s"
        % datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}]})
    return blocs


def _envoyer_slack(webhook, quoi, ou, cause, dossier=None, faire=None, trace=None):
    """Poste l'alerte sur le webhook entrant. Rend (ok, detail) ; ne leve pas."""
    resume = "🚨 Échec chaîne devis — %s%s" % (quoi, " (%s)" % dossier if dossier else "")
    charge = {"text": resume,               # texte de la notification telephone
              "blocks": _blocs_slack(quoi, ou, cause, dossier, faire, trace)}
    req = urllib.request.Request(
        webhook, data=json.dumps(charge, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            corps = r.read().decode("utf-8", "replace").strip()
        # Un webhook Slack repond exactement « ok ». Tout autre corps = message non poste.
        return (True, "Slack") if corps == "ok" else (False, "Slack a répondu : %s" % corps[:200])
    except urllib.error.HTTPError as e:
        corps = e.read().decode("utf-8", "replace")[:200]
        if e.code in (403, 404, 410):
            corps += " — webhook révoqué ou canal archivé : en recréer un et mettre à jour " \
                     "SAMDEM_SLACK_WEBHOOK"
        return False, "Slack HTTP %s : %s" % (e.code, corps)
    except Exception as e:
        return False, "Slack injoignable : %s: %s" % (type(e).__name__, e)


def alerte(quoi, ou, cause, dossier=None, faire=None, trace=None, a=None, conf=None):
    """Previent Samuel sur Slack qu'une etape a echoue. Rend (ok, detail).

    Ne leve JAMAIS, et n'interrompt jamais l'appelant : une alerte qui ferait tomber la
    chaine transformerait un incident mineur en panne complete. Quatre filets, dans l'ordre :
    Slack, puis e-mail via la Web App Apps Script (seulement si Slack n'a pas pris l'alerte),
    puis file d'attente WhatsApp, puis journal local.
    """
    conf = conf or export.config()
    destinataire = a or conf.get("SAMDEM_ALERTE_EMAIL") or ALERTE_A_DEFAUT
    sujet = "[Sam'Déménage] Échec — %s%s" % (quoi, " (%s)" % dossier if dossier else "")
    texte = _corps_alerte(quoi, ou, cause, dossier, faire, trace)
    donnees = {"canal": None, "sujet": sujet, "quoi": quoi, "ou": ou, "cause": str(cause),
               "dossier": dossier, "envoye": False}

    webhook = conf.get("SAMDEM_SLACK_WEBHOOK")
    if webhook and webhook.startswith("https://hooks.slack.com/"):
        ok, detail_slack = _envoyer_slack(webhook, quoi, ou, cause, dossier, faire, trace)
        if ok:
            donnees.update(canal="slack", envoye=True)
            _journaliser_alerte(donnees)
            return True, "alerte postée sur Slack"
    else:
        detail_slack = "SAMDEM_SLACK_WEBHOOK absent de %s" % export.ENV
    donnees["slack"] = detail_slack

    # Repli e-mail : Slack n'a pas pris l'alerte, on ne la perd pas pour autant.
    donnees["a"] = destinataire
    url, jeton = conf.get("SAMDEM_SHEETS_URL"), conf.get("SAMDEM_SHEETS_TOKEN")
    detail = "SAMDEM_SHEETS_URL absente de %s" % export.ENV
    if url and jeton:
        try:
            ok, rep = export._post(url, {"jeton": jeton, "action": "alerte",
                                         "a": destinataire, "sujet": sujet, "texte": texte})
            # `alerte: true` est l'accuse de reception de la NOUVELLE version du script. On
            # ne se contente pas de `ok: true` : l'ancienne version ne connait pas l'action
            # « alerte », enregistre une ligne vide dans le Sheet et repond quand meme
            # `ok: true`. Sans ce controle, une alerte non envoyee passerait pour envoyee —
            # et c'est precisement le jour d'un incident qu'on s'en apercevrait.
            if ok and (rep or {}).get("ok") and (rep or {}).get("alerte"):
                donnees.update(canal="email", envoye=True)
                _journaliser_alerte(donnees)
                return True, "Slack KO (%s) — e-mail de repli envoyé à %s" % (detail_slack,
                                                                             destinataire)
            if ok and (rep or {}).get("ok"):
                detail = ("la Web App a répondu sans confirmer l'envoi — le script Apps "
                          "Script n'a probablement pas été redéployé depuis "
                          "apps_script_devis.gs")
            else:
                detail = "réponse de la Web App : %s" % rep
        except Exception as e:
            detail = "%s: %s" % (type(e).__name__, e)
    # Ni Slack ni l'e-mail : on bascule sur la file WhatsApp plutot que de perdre l'alerte.
    # Elle est relisible (notif.py --file-attente).
    _mettre_en_attente("%s\n\n%s" % (sujet, texte), _conf()[1],
                       "alerte : %s ; e-mail : %s" % (detail_slack, detail))
    _journaliser_alerte(donnees)
    return False, ("Slack KO (%s), e-mail non parti (%s) — alerte mise en file WhatsApp"
                   % (detail_slack, detail))


def main():
    ap = argparse.ArgumentParser(description="Notifications WhatsApp via Beeper Desktop")
    ap.add_argument("texte", nargs="?", help="message à envoyer")
    ap.add_argument("--chat", help="chatID Beeper (défaut : SAMDEM_WHATSAPP_CHAT)")
    ap.add_argument("--fichier", help="joindre ce fichier (le texte devient sa légende)")
    ap.add_argument("--alerte", action="store_true",
                    help="envoyer une alerte d'incident d'essai sur Slack (bout en bout)")
    ap.add_argument("--test", action="store_true", help="vérifier la configuration")
    ap.add_argument("--file-attente", action="store_true", help="afficher les messages en attente")
    ap.add_argument("--vider-file-attente", action="store_true",
                    help="tenter de renvoyer les messages en attente")
    a = ap.parse_args()

    token, chat = _conf()
    if a.test:
        print("Config : %s" % export.ENV)
        print("  BEEPER_ACCESS_TOKEN  %s" % ("défini" if token and "REMPLACER" not in token
                                             else "MANQUANT"))
        print("  SAMDEM_WHATSAPP_CHAT %s" % (chat or "MANQUANT"))
        wh = export.config().get("SAMDEM_SLACK_WEBHOOK") or ""
        print("  SAMDEM_SLACK_WEBHOOK %s" % ("défini" if wh.startswith("https://hooks.slack.com/")
                                             else "MANQUANT — alertes envoyées par e-mail"))
        if not token or not chat:
            print("\n→ Créer un jeton dans Beeper Desktop (Settings > Developer / API),")
            print("  puis renseigner les deux clés dans %s." % export.ENV)
            return 1
        req = urllib.request.Request(BEEPER_API + "/chats/" + str(chat),
                                     headers={"Authorization": "Bearer " + token})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.load(r)
            print("  Chat : OK — « %s »" % (d.get("title") or chat))
            return 0
        except Exception as e:
            print("  Chat : ÉCHEC — %s" % e)
            return 1

    if a.file_attente:
        if not os.path.exists(FILE_ATTENTE):
            print("File d'attente vide.")
            return 0
        print(open(FILE_ATTENTE, encoding="utf-8").read())
        return 0

    if a.vider_file_attente:
        if not os.path.exists(FILE_ATTENTE):
            print("File d'attente vide.")
            return 0
        lignes = [l for l in open(FILE_ATTENTE, encoding="utf-8").read().splitlines() if l.strip()]
        os.remove(FILE_ATTENTE)                 # les échecs se remettront en file tout seuls
        ok = 0
        for l in lignes:
            d = json.loads(l)
            if d.get("fichier"):
                envoye, _ = envoyer_fichier(d["fichier"], d.get("texte", ""), d.get("chat"))
            else:
                envoye, _ = envoyer(d["texte"], d.get("chat"))
            ok += 1 if envoye else 0
        print("%d/%d message(s) envoyé(s)." % (ok, len(lignes)))
        return 0 if ok == len(lignes) else 1

    if a.alerte:
        ok, detail = alerte(
            quoi=a.texte or "test d'alerte",
            ou="notif.py --alerte (essai manuel)",
            cause="aucune — vérification que le canal d'alerte fonctionne de bout en bout",
            faire="rien : si ce message est arrivé, les alertes d'incident arriveront aussi.")
        print("Alerte : %s — %s" % ("envoyée" if ok else "NON envoyée", detail))
        return 0 if ok else 1

    if a.fichier:
        envoye, detail = envoyer_fichier(a.fichier, a.texte or "", a.chat)
        print("WhatsApp : %s — %s" % ("fichier envoyé" if envoye else "NON envoyé", detail))
        return 0 if envoye else 1
    if not a.texte:
        ap.error("texte requis (ou --test / --alerte / --file-attente / --vider-file-attente)")
    envoye, detail = envoyer(a.texte, a.chat)
    print("WhatsApp : %s — %s" % ("envoyé" if envoye else "NON envoyé", detail))
    return 0 if envoye else 1


if __name__ == "__main__":
    sys.exit(main())
