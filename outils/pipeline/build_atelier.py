#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrique la variante « atelier » du calculateur depuis le fichier maitre.

Deux artefacts, un seul code source :

  outils/pipeline/calculateurs/calculateur-devis.html          maitre — partage par lien, collage manuel
  outils/pipeline/calculateurs/calculateur-devis-atelier.html  genere — base de donnees, zero collage

L'atelier declare la capacite `db` de l'artefact : Claude y depose les dossiers prepares,
la page les liste a l'ouverture, un clic remplit le formulaire. Un artefact qui declare une
base devient interne a l'organisation et ne peut plus etre partage publiquement — c'est
exactement pourquoi il est separe du maitre (arbitrage Karim, 08/09/2026).

Ce fichier ne DUPLIQUE rien : il injecte un bloc dans une copie du maitre. Toute evolution du
calculateur se fait dans le maitre, puis :

    python outils/pipeline/build_atelier.py       # regenere l'atelier
    # puis republier les deux artefacts
"""

import io
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.normpath(os.path.join(ICI, "..", ".."))
MAITRE = os.path.join(ICI, "calculateurs", "calculateur-devis.html")
ATELIER = os.path.join(ICI, "calculateurs", "calculateur-devis-atelier.html")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# --- 1. le bandeau des dossiers en attente -----------------------------------

ANCRE_BANDEAU = '    <div class="example-banner" id="exBanner">'
BANDEAU = '''    <div class="example-banner" id="dossiersBox" hidden></div>
''' + ANCRE_BANDEAU

ANCRE_CSS = "  #loadBox { margin-top: 10px; }"
CSS = """  #loadBox { margin-top: 10px; }
  #dossiersBox { flex-wrap: wrap; }
  #dossiersBox button { margin-left: 0; }
  #dossiersBox .att { font-weight: 600; color: var(--ink); }"""

ANCRE_ENTETE = "cible 35 % · sans commission · Notion reste la source de vérité"
ENTETE = "ATELIER · cible 35 % · sans commission · dossiers chargés depuis la file"

# Nom propre : les deux artefacts vivent cote a cote dans la galerie, un titre identique
# rendrait le bon impossible a retrouver.
ANCRE_TITRE = "<title>Calculateur de devis Sam'Déménage</title>"
TITRE = "<title>Atelier devis Sam'Déménage</title>"


# --- 2. le code qui lit la file ----------------------------------------------
# `claude.use` n'existe pas hors du visualiseur (copie locale, autre hote) et resout `null`
# quand la capacite n'est pas accordee : dans les deux cas la page reste celle du maitre,
# avec son collage manuel. On n'enleve donc jamais « Charger un dossier ».

BLOC_JS = r"""
/* ---------- file des dossiers préparés (capacité `db` de l'artefact atelier) ----------
   Claude dépose ici les dossiers d'un lot ; la page les liste et un clic remplit le
   formulaire. Le collage manuel reste disponible : si la capacité n'est pas là (copie
   locale, artefact sans `db`), la page se comporte exactement comme le calculateur maître. */
let dossierEnCours = null;
let baseAtelier = null;

(async function fileDossiers() {
  if (!window.claude || typeof window.claude.use !== "function") return;
  try { baseAtelier = await window.claude.use("db"); } catch (e) { return; }
  if (!baseAtelier) return;

  const box = document.getElementById("dossiersBox");
  if (!box) return;

  const nomDe = (v) => (v.fiche && v.fiche.titre) || (v.ex && v.ex.clientNom) || "dossier";

  function rendre(docs) {
    const attente = docs.filter(d => { const v = d.data() || {}; return !v.traite; });
    box.textContent = "";
    if (!attente.length) { box.hidden = true; return; }
    const titre = document.createElement("span");
    titre.className = "att";
    titre.textContent = attente.length > 1
      ? attente.length + " dossiers en attente"
      : "1 dossier en attente";
    box.appendChild(titre);
    attente.forEach(d => {
      const v = d.data() || {};
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.doc = d.id;
      b.textContent = nomDe(v) + ((v.ex && v.ex.volume) ? " · " + v.ex.volume + " m³" : "");
      if (d.id === dossierEnCours) b.textContent = "✓ " + b.textContent;
      box.appendChild(b);
    });
    box.hidden = false;
  }

  // Pas de where() ni d'orderBy() : la file est courte, on filtre et on trie ici — une
  // requête simple ne peut pas échouer sur une contrainte d'index côté store.
  baseAtelier.collection("dossiers").limit(50).onSnapshot(
    s => rendre(s.docs.slice().reverse()),      // ids horodatés : le plus récent d'abord
    () => { box.hidden = true; });

  box.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-doc]");
    if (!b) return;
    try {
      const snap = await baseAtelier.doc("dossiers/" + b.dataset.doc).get();
      if (!snap.exists) { toast("Dossier introuvable"); return; }
      chargerDossier(JSON.stringify(snap.data()));
      dossierEnCours = b.dataset.doc;
    } catch (err) {
      toast("Lecture impossible — " + (err && err.code ? err.code : "erreur"));
    }
  });
})();

/* Un dossier exporté sort de la file : la page ne propose jamais deux fois le même travail.
   L'échec est sans conséquence — le JSON est déjà dans le presse-papier, la fiche se remplit. */
async function marquerTraite() {
  if (!baseAtelier || !dossierEnCours) return;
  try {
    await baseAtelier.doc("dossiers/" + dossierEnCours).update(
      { traite: true, traite_le: new Date().toISOString() });
  } catch (e) {}
  dossierEnCours = null;
}
"""

ANCRE_EXPORT = """  return e;
}
$("#jsonBtn").addEventListener("click", () => exporter(true));"""
EXPORT = """  if (prevenir) marquerTraite();
  return e;
}
$("#jsonBtn").addEventListener("click", () => exporter(true));"""


def construire(maitre=MAITRE, cible=ATELIER):
    s = io.open(maitre, encoding="utf-8").read()
    for vieux, neuf in ((ANCRE_CSS, CSS), (ANCRE_BANDEAU, BANDEAU),
                        (ANCRE_ENTETE, ENTETE), (ANCRE_TITRE, TITRE), (ANCRE_EXPORT, EXPORT)):
        if vieux not in s:
            raise SystemExit("Ancre absente du maître — le calculateur a changé :\n  %s"
                             % vieux.strip()[:110])
        s = s.replace(vieux, neuf, 1)
    # le bloc s'insere a la fin du script principal, apres l'init
    fin = "\n</script>"
    if fin not in s:
        raise SystemExit("Fin de script introuvable dans le maître.")
    s = s.replace(fin, BLOC_JS + fin, 1)
    io.open(cible, "w", encoding="utf-8", newline="\n").write(s)
    return cible


if __name__ == "__main__":
    chemin = construire()
    print("Atelier généré : %s (%d octets)" % (chemin, os.path.getsize(chemin)))
    print("Publier cet artefact avec capabilities {\"db\": {}} — il devient interne à")
    print("l'organisation et ne peut plus être partagé par lien public.")
