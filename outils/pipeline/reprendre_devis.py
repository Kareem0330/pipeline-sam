#!/usr/bin/env python3
"""
Reprise d'un devis deja exporte, pour le modifier.

Retrouve le dernier export « Exporter JSON » d'une fiche (regles.DEVIS_GENERES, dossier exports), copie le
calculateur maitre et y injecte les valeurs de cet export (const PREFILL), puis ouvre le
fichier. Le moteur est celui du maitre du jour. Les reglages faits a la main a l'envoi — temps
de chargement / dechargement retouches, puis « TTC cible » — sont reappliques dans la copie
(Karim, 12/10/2026) : elle rouvre au prix envoye, pas au bareme du jour. Le maitre n'est pas
touche : le code de reprise n'est injecte que dans la copie.

Usage :
    python reprendre_devis.py "NOM Prénom"
    python reprendre_devis.py "NOM Prénom" --variante "Direct"
    python reprendre_devis.py --page-id <id>
    python reprendre_devis.py "NOM" --liste          # exports trouves, sans rien generer
"""
import argparse
import glob
import json
import os
import sys

import pipeline

EXPORTS = os.path.join(pipeline.SORTIE, "exports")


def _norme(page_id):
    return (page_id or "").replace("-", "").lower()


def resoudre_fiche(nom=None, page_id=None):
    """(identifiant du dossier, titre). Titre None : garder le nom de l'export (une transaction porte
    souvent « Prénom NOM », une page Notion « NOM Prénom »)."""
    if page_id:
        return _norme(page_id), None
    import fiche_notion
    pid, titre = fiche_notion.chercher_fiche(nom, fiche_notion._token())
    return _norme(pid), None if fiche_notion.est_transaction(pid) else titre


def exports_de(page_id):
    # Un dossier repris de Notion a des exports sous les deux identifiants.
    import fiche_hubspot
    ids = fiche_hubspot.ids_du_dossier(page_id)
    trouves = []
    for chemin in glob.glob(os.path.join(EXPORTS, "*.json")):
        if chemin.endswith(".variantes.json"):
            continue
        try:
            with open(chemin, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if d.get("schema") != "samdem.devis.export/1":
            continue
        if _norme((d.get("fiche") or {}).get("page_id")) in ids:
            trouves.append((d.get("genere_le") or "", chemin, d))
    return sorted(trouves, key=lambda t: t[0])


def _euros(x):
    return ("%s €" % format(round(x), ",d")).replace(",", " ")


def _duree(minutes):
    h, m = divmod(int(round(minutes)), 60)
    return "%dh%02d" % (h, m)


def paquet_reprise(export, titre=None):
    ex = dict(export["ex"])
    if titre:                                    # fiche renommee depuis l'envoi
        nom, _, prenom = titre.partition(" ")
        ex["clientNom"] = ("%s %s" % (prenom, nom)).strip()
    cf = export.get("champs_fiche") or {}
    marge = export.get("marge") or {}
    envoye = (export.get("genere_le") or "")[:10]
    banniere = "Reprise du devis exporté le %s — %s, %s m³, variante « %s ». Envoyé à %s TTC (marge %.1f %%)" % (
        "/".join(reversed(envoye.split("-"))), ex.get("clientNom"), ex.get("volume"),
        export.get("variante") or "—", _euros(cf.get("total_ttc") or 0), 100 * (marge.get("pct") or 0))
    # Les temps retouches a la main ne sont pas dans « ex » : la copie les reapplique, puis le
    # TTC cible (dans cet ordre — le TTC cible se calcule sur les temps).
    ajustes = export.get("temps_ajustes_a_la_main") or {}
    temps = export.get("temps_min") or {}
    reprise = {"chargeMin" if phase == "chargement" else "dechargeMin": temps[phase]
               for phase in ("chargement", "dechargement") if ajustes.get(phase) and temps.get(phase)}
    tr = temps.get("relivraison") or {}
    for phase, cle in (("chargement", "relivChargeMin"), ("dechargement", "relivDechargeMin")):
        if ajustes.get("relivraison_" + phase) and tr.get(phase):
            reprise[cle] = tr[phase]
    if marge.get("ajuste_sur_ttc"):
        reprise["ttc"] = marge["ajuste_sur_ttc"]
    remis = ["chargement %s" % _duree(reprise["chargeMin"])] if "chargeMin" in reprise else []
    remis += ["déchargement %s" % _duree(reprise["dechargeMin"])] if "dechargeMin" in reprise else []
    remis += ["relivraison chargement %s" % _duree(reprise["relivChargeMin"])] if "relivChargeMin" in reprise else []
    remis += ["relivraison déchargement %s" % _duree(reprise["relivDechargeMin"])] if "relivDechargeMin" in reprise else []
    remis += ["TTC cible %s" % _euros(reprise["ttc"])] if "ttc" in reprise else []
    banniere += (". Réglages manuels de l'envoi réappliqués : %s." % " · ".join(remis)) if remis else ", au barème."
    fiche = dict(export.get("fiche") or {})
    if titre:
        fiche["titre"] = titre
    return {
        "schema": "samdem.devis.prefill/1",
        "calculateur": pipeline.CALCULATEUR_URL,
        "fiche": fiche,
        "banniere": banniere,
        "variante": export.get("variante"),
        "variantes_existantes": sorted(set(pipeline.variantes_existantes(fiche.get("page_id"))
                                           + ([export["variante"]] if export.get("variante") else []))),
        "ex": ex,
        "reprise": reprise,
    }


# Injecte dans la copie seulement : reapplique temps retouches puis TTC cible apres chargement.
ANCRE_CHARGEMENT = "if (PREFILL) chargerDossier(JSON.stringify(PREFILL));"
CODE_REPRISE = """
if (PREFILL && PREFILL.reprise) {
  const R = PREFILL.reprise;
  if (R.chargeMin != null) overrides.chargeMin = R.chargeMin;
  if (R.dechargeMin != null) overrides.dechargeMin = R.dechargeMin;
  if (R.relivChargeMin != null) overrides.relivChargeMin = R.relivChargeMin;
  if (R.relivDechargeMin != null) overrides.relivDechargeMin = R.relivDechargeMin;
  if (R.ttc) { $("#ttcTargetNum").value = R.ttc; applyTtcTarget(R.ttc); } else render();
}"""


def generer(paquet):
    fiche = paquet["fiche"]
    titre = (fiche.get("titre") or paquet["ex"].get("clientNom") or "CLIENT").replace(" ", "_")
    variante = paquet.get("variante")
    nom = "Devis_%s%s_reprise.html" % (titre, "_" + pipeline._slug(variante) if variante else "")
    cible = os.path.join(pipeline.SORTIE, nom)
    with open(pipeline.MAITRE, encoding="utf-8") as fh:
        html = fh.read()
    ancre = "const PREFILL = null;"
    if ancre not in html:
        raise SystemExit("ancre « %s » introuvable dans le calculateur maître." % ancre)
    texte = json.dumps(paquet, ensure_ascii=False, indent=2).replace("</", "<\\/")
    if ANCRE_CHARGEMENT not in html:
        raise SystemExit("ancre « %s » introuvable dans le calculateur maître." % ANCRE_CHARGEMENT)
    html = html.replace(ancre, "const PREFILL = %s;" % texte, 1)
    html = html.replace(ANCRE_CHARGEMENT, ANCRE_CHARGEMENT + CODE_REPRISE, 1)
    with open(cible, "w", encoding="utf-8") as fh:
        fh.write(html)
    return cible


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nom", nargs="?")
    ap.add_argument("--page-id")
    ap.add_argument("--variante", help="reprendre cette variante (défaut : le dernier export)")
    ap.add_argument("--liste", action="store_true")
    a = ap.parse_args()
    if not a.nom and not a.page_id:
        ap.error("donner un nom ou --page-id")

    page_id, titre = resoudre_fiche(a.nom, a.page_id)
    trouves = exports_de(page_id)
    if a.variante:
        trouves = [t for t in trouves if (t[2].get("variante") or "").lower() == a.variante.lower()]
    if not trouves:
        sys.exit("Aucun export pour la fiche %s%s dans %s." % (
            titre or page_id, " (variante %s)" % a.variante if a.variante else "", EXPORTS))

    if a.liste or not a.variante:
        for date, chemin, d in trouves:
            cf = d.get("champs_fiche") or {}
            print("  %s  variante « %s »  %s TTC  — %s" % (
                date[:16].replace("T", " "), d.get("variante"), _euros(cf.get("total_ttc") or 0),
                os.path.basename(chemin)))
        if a.liste:
            return

    _, chemin, export = trouves[-1]
    cible = generer(paquet_reprise(export, titre))
    print("Repris : %s" % os.path.basename(chemin))
    print("Devis : %s" % cible)
    if pipeline.regles.NAVIGATEUR_INTEGRE:
        print("  → à ouvrir dans le navigateur intégré de Claude : %s" % pipeline.url_fichier(cible))
    else:
        print("  → ouvert dans le navigateur" if pipeline.ouvrir(cible) else "  → à ouvrir à la main")


if __name__ == "__main__":
    main()
