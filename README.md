# Mizan

> **Mizan** (ميزان) = balance, équilibre.
> Automatisation de la **Déclaration des Délais de Paiement** (DDP) fournisseurs — Nextor.

Pipeline qui transforme un Grand Livre Sage en deux livrables synchronisés :

- Un **Suivi Global** détaillé (piste d'audit cabinet).
- Un **Simpl DGI** pré-rempli (formulaire officiel à signer par le client).

> **Pour Claude Code et tout contributeur** : lire `CLAUDE.md` avant toute action.

## Quickstart

### Pipeline complet (recommandé avec Référentiel DGI enrichi)

```bash
python3 mizan.py run \
  --client UEMA \
  --trimestre 1T26 \
  --gl "samples/input/UEMA - GL FRS 2026.xlsx" \
  --template "samples/input/Modèle Suivi Global.xlsx" \
  --base "samples/input/Référentiel DGI - Cabinet.xlsx" \
  --simpl-template "samples/output_reference/Simpl délais de paiements UEMA -  TR 01-2026.xlsx" \
  --n-if 14367938 \
  --raison-sociale "STE UEMA INDUSTRY" \
  --ca-n1 23369748.49 \
  --activite 1 \
  --out out
```

> Le Référentiel DGI Cabinet contient pour chaque fournisseur : code, nom, délai,
> N° IF, ICE, RC, adresse, ville. Avec ce référentiel, le Simpl est auto-rempli
> à ~60 % (pour les fournisseurs déjà connus du cabinet).

### Interface web (recommandé pour usage cabinet)

```bash
streamlit run app/streamlit_app.py
```

Ouvre http://localhost:8501 dans le navigateur. L'interface permet :
- Drag-and-drop des fichiers d'entrée (GL Sage, référentiel DGI, corrections)
- Configuration du client (nom, IF, raison sociale, CA, trimestre)
- Exécution en un clic
- Dashboard interactif (KPI, tableau filtrable, anomalies)
- Téléchargement direct des fichiers Suivi Global et Simpl DGI

### Autres commandes

```bash
# Statistiques brutes d'un GL
python3 mizan.py parse --gl path/to/gl.xlsx

# Diagnostic (cas ambigus, fournisseurs hors base, lettrages déséquilibrés)
python3 mizan.py diagnose --gl path/to/gl.xlsx --base path/to/base.xlsx

# Aide complète
python3 mizan.py --help
python3 mizan.py run --help
```

### Sortie

Le pipeline génère 2 fichiers dans `out/` :
- `Suivi Global DDP <client> <trimestre>.xlsx` — piste d'audit cabinet
- `Simpl DDP <client> <trimestre>.xlsx` — formulaire DGI à signer

## Structure

```
mizan/
├── CLAUDE.md           Mémoire projet — contexte, glossaire, roadmap
├── README.md           Ce fichier
├── mizan.py            Point d'entrée CLI
├── src/
│   ├── parser/         Lecture GL (Sage Excel)
│   ├── lettrage/       Reconstitution facture ↔ paiement
│   ├── compute/        Calculs échéances, retards, cas particuliers
│   ├── output/         Génération Suivi Global + Simpl
│   └── cli/            Orchestrateur CLI
├── tests/              Tests unitaires (pytest) — 84 verts
├── samples/            Fichiers de référence pilote UEMA
├── scripts/            Utilitaires (comparaison, validation)
├── docs/               Documentation métier + ADR + validation
└── .claude/            Skills, agents, slash commands projet
```

## Roadmap

Voir `CLAUDE.md` § 8.

- ✅ **Phase 1** terminée — pilote UEMA 1T26
- 🔜 **Phase 2** — enrichissement OCR (D-006), référentiel DGI (D-007), délai par facture
- **Phase 3** — multi-clients, multi-logiciels (Ciel, ERP), reporting consolidé
- **Phase 4** — onboarding cabinets, formation, commercialisation Maroc
