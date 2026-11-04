# 7. Premier devis

Fais-le sur une vraie demande, sans te presser : ce sera le test de bout en bout. Aucun envoi au client n'a lieu sans toi.

## Avant de commencer

```bash
python verifier_installation.py
```

Il ne doit plus rester de ligne « À FAIRE » pour HubSpot, WhatsApp et le veilleur.

## Les étapes

1. **La fiche.** Dans Claude Code : « Crée la fiche de NOM Prénom », et colle les informations du client. Claude pose une note « Fiche client » sur la transaction.
2. **Le devis.** « Fais le devis de NOM Prénom. » Claude contrôle d'abord les valeurs et te pose ses questions, s'il en a. Le calculateur s'ouvre ensuite dans le navigateur intégré à Claude, dans le panneau de droite, déjà rempli, une seule fois. S'il n'apparaît pas, appuie sur Ctrl+Maj+B. Vérifie la marge, les temps et les options.
3. **L'export.** Clique sur **« Exporter JSON »**. Le veilleur fait le reste : note, propriétés, étape « Devis en révision », PDF. Laisse Claude Code ouvert : il attend l'export et te présente le PDF.
4. **La relecture.** Relis le PDF. Choisis : valider, corriger le texte, ou changer le chiffrage.
5. **La validation.** Le devis et l'inventaire rejoignent la transaction, et le message part à l'équipe.
6. **L'envoi.** Sandrine envoie le devis au client depuis son adresse, avec toi en copie.

## À contrôler la première fois

Dans HubSpot, sur la transaction :

- [ ] une note « Fiche client », avec le chiffrage à jour ;
- [ ] l'étape « Devis en révision » après l'export ;
- [ ] le montant et les propriétés de chiffrage ;
- [ ] après validation : une note « Devis n° » avec le PDF, et une note « Inventaire » si le dossier en a un.

Sur WhatsApp, dans « Devis/inventaire » : le message avec le lien HubSpot, puis l'inventaire.

Sur le PDF : le numéro suit bien le dernier devis, le nom, les adresses, les dates et les montants sont justes.

Si un point ne va pas, dis à Claude Code ce que tu vois : il connaît la chaîne et ses journaux. Voir aussi le [guide 8](08-depannage.md).
