# CLAUDE.md — Projet `Mizan`

> **Mizan** (ميزان) = *balance, équilibre, justice* en arabe.
> Référence à *Mizan al-Mouhassaba* (ميزان المحاسبة) — la balance comptable,
> terme du quotidien des cabinets marocains.
>
> Mémoire de travail pour Claude Code. Lis ce fichier à chaque ouverture de session.
> **Langue de travail : français.** Toute communication, commentaires et docs en français.

---

## 1. Mission

Automatiser, de bout en bout, la **Déclaration des Délais de Paiement** (DDP) fournisseurs imposée par la DGI marocaine via le portail **Simpl-TVA**.

À partir du **Grand Livre fournisseurs** (export Sage / Ciel / Excel) :

1. Reconstituer les couples **facture ↔ paiement(s)** via le lettrage.
2. Calculer les **échéances** et **retards** au regard des délais convenus.
3. Produire deux livrables synchronisés :
   - `Suivi Global DDP.xlsx` — piste d'audit interne du cabinet
   - `Simpl délais de paiements.xlsx` — formulaire officiel pré-rempli, prêt à signer par le client

**Promesse produit** : zéro saisie côté client. Le cabinet maîtrise toute la chaîne, du GL au dépôt DGI.

## 2. Acteurs

| Acteur | Rôle |
|---|---|
| **Nextor** | Éditeur de l'outil |
| **Cabinet comptable** | Utilisateur principal — opère l'outil pour ses clients |
| **Client final** (UEMA…) | Assujetti — signe la déclaration |
| **DGI** | Administration fiscale — réceptionne la déclaration |

## 3. Périmètre actuel (Phase 1 — Pilote UEMA, 1ᵉʳ trimestre 2026)

- **Logiciel source** : Sage 100cloud Comptabilité Premium 5.03
- **Client pilote** : STE UEMA
- **Trimestre cible** : 1T26 (01/01/2026 → 31/03/2026)
- **Fichiers sources** : voir `samples/` (liens symboliques vers `../3.Modèle DDP/Input/`)
- **Livrables cibles** : voir `samples/output_reference/` (liens vers `../3.Modèle DDP/Output/`)

## 4. Glossaire métier

| Terme | Définition |
|---|---|
| **DDP** | Déclaration des Délais de Paiement (déclaration trimestrielle DGI) |
| **GL** | Grand Livre — extrait comptable par tiers (fournisseur) |
| **FNP** | Facture Non Payée — facture sans lettrage à la date de clôture |
| **Lettrage** | Lien entre une facture et son/ses paiement(s), matérialisé par une lettre (A, B, C…) dans la colonne `Lettr.` |
| **C.j** (Code journal) | Type d'écriture : `ACH` = achats (facture) · `BMCE`/banque = paiement · `AN` = à-nouveau (report exercice précédent) |
| **Délai convenu** | Délai contractuel entre facture et paiement (60 j par défaut, jusqu'à 120 j sous convention) |
| **Échéance** | `date facture + délai convenu` |
| **Jours de retard** | `date paiement effectif − date échéance` (positif = retard, négatif = anticipation) |
| **Simpl-TVA** | Portail DGI de télédéclaration |
| **Sondage** | Échantillon trimestriel de fournisseurs à justifier (PDF par fournisseur) |

## 5. Règles métier (à valider en Phase 1)

- Délai par défaut si non précisé en base fournisseurs : **60 jours**.
- Plafond légal sous convention : **120 jours**.
- **Date de référence** pour l'échéance : date de livraison si dispo, sinon date facture.
- **Avoirs / notes de débit** : à déduire du montant dû avant calcul.
- **Paiements partiels** : ventiler entre part dans les délais et part hors délais.
- **Paiements groupés** : un virement règle plusieurs factures → répartir.
- **Montants récurrents identiques** (loyer, télécom) : marquer pour revue manuelle.
- **FNP** : reportées au trimestre suivant avec retard cumulé.

## 6. Architecture cible

```
INPUTS                    MOTEUR                       OUTPUTS
──────                    ──────                       ───────
GL fournisseurs (PDF/Xls) ──► parser  ──► lettrage ──► Suivi Global DDP.xlsx
Base Frs (délais)         ──► compute (échéances)  ──► Simpl pré-rempli.xlsx
Relevés bancaires (opt.)        ▲                      Rapport sondage.xlsx
Liste de sondage          ──────┘
```

Modules Python :

| Module | Responsabilité |
|---|---|
| `src/parser/` | Lecture GL Sage PDF & Excel → modèle d'écritures normalisé |
| `src/lettrage/` | Regroupement des écritures par lettre → couples facture/paiement |
| `src/compute/` | Échéances, retards, statuts, gestion des cas particuliers |
| `src/output/` | Génération `Suivi Global` et `Simpl` à partir de templates |
| `src/cli/` | Point d'entrée CLI (`mizan run --client UEMA --trimestre 1T26`) |

## 7. Conventions de code

- **Python 3.11+**, type hints obligatoires, `dataclasses` pour les modèles.
- **openpyxl** pour Excel (lecture + écriture), **pdfplumber** pour le GL PDF.
- **Tests** : pytest. Chaque règle métier = au moins un test.
- **Pas de logique métier dans `output/`** — pure mise en forme à partir d'objets calculés.
- **Devise** : MAD, format `1 234,56` (espace fine, virgule décimale).
- **Dates** : ISO en interne (`date`), formatées FR à la sortie (`JJ/MM/AAAA`).
- **Commentaires en français**, uniquement quand le « pourquoi » n'est pas évident.

## 8. Roadmap phase 1 — pas à pas

Cocher au fur et à mesure. Ne pas démarrer une étape avant d'avoir validé la précédente.

- [x] **Étape 1 — Spec du modèle de données** ✅ *2026-05-18*
  - `src/models.py` : `EcritureBrute`, `Facture`, `Paiement`, `Fournisseur`, `Lettrage`, `LigneSuivi`, `JeuDonnees`
  - `docs/domain.md` : structure du GL Sage, codes journaux, règles de classification, exemples UEMA
- [x] **Étape 2 — Parser GL Excel** ✅ *2026-05-18*
  - `src/parser/gl_excel.py` — extrait 1510 écritures du GL UEMA (177 fournisseurs, 6 codes journaux, lettrages A-H)
  - `tests/test_parser_gl.py` — 9 tests verts (sanity checks A2CIM, ABM INDUSTRIE)
- [~] **Étape 3 — Parser GL PDF** — *reportée en phase 2* (option B retenue)
- [x] **Étape 4 — Moteur de lettrage** ✅ *2026-05-18*
  - `src/lettrage/classifier.py` — classification facture/paiement/avoir + extraction n° + moyen
  - `src/lettrage/engine.py` — regroupement par (fournisseur, lettre)
  - `tests/test_lettrage.py` — 24 tests (paramétrés inclus), 33 tests verts au total
  - Résultat UEMA 1T26 : 316 lettrages, 192 soldés au centime, 7 déséquilibrés < 1 MAD (D-004), 74 groupes FNP (396 factures, 6,53 M MAD)
- [x] **Étape 5 — Calcul délais & retards** ✅ *2026-05-18*
  - `src/compute/base_fournisseurs.py` — chargeur de la base (délais convenus)
  - `src/compute/delais.py` — imputation FIFO, échéance, statut, tolérance D-004
  - 16 tests unitaires + 4 intégration UEMA, **49 tests verts** au total
  - Limitation MVP : factures AN gardent date 01/01 (D-006). 700-1100 lignes générées (cible 774). Cas A2CIM (OK RAS) et ABM INDUSTRIE (Retard 49j) parfaitement reproduits.
- [x] **Étape 6 — Génération `Suivi Global DDP.xlsx`** ✅ *2026-05-18*
  - `src/output/suivi_global.py` — chargement du template + remplissage onglet Suivi + Base Frs
  - Onglets préservés du template ; styles, formats date/montant respectés
  - `tests/test_output.py` — 9 tests, **58 tests verts** au total
  - Output `out/Modèle Suivi Global DDP2026 - AUTO.xlsx` : 1037 lignes, statuts au vocabulaire cabinet
- [x] **Étape 7 — Génération `Simpl délais de paiements.xlsx`** ✅ *2026-05-18*
  - `src/output/simpl.py` — formulaire DGI (CERFA ADC500B-23I, 31 colonnes)
  - Modèle `Fournisseur` étendu (N° IF, ICE, RC, adresse, ville, secteur, nature)
  - Filtre auto : seules FNP + Retard + Partiel sont déclarées (OK RAS exclues)
  - D-007 ajoutée — référentiel DGI = dépendance externe phase 2
  - `tests/test_simpl.py` — 8 tests, **66 tests verts** au total
  - Output : 575 lignes (cible 352, écart D-006). En-tête (IF, raison, période, année, CA, BAM) correctement rempli
- [x] **Étape 8 — CLI + orchestration** ✅ *2026-05-18*
  - `src/cli/main.py` — argparse + sous-commandes `run`, `parse`, `info`, `diagnose`
  - `mizan.py` — point d'entrée à la racine
  - Pipeline complet UEMA 1T26 en **2.1 secondes**
  - `tests/test_cli.py` — 11 tests, **84 tests verts** au total
  - README mis à jour avec quickstart
- [x] **Étape 9 — Validation sur UEMA 1T26** ✅ *2026-05-18*
  - `scripts/comparer_outputs.py` — diff automatique référence vs auto
  - `docs/validation_uema_1t26.md` — rapport complet (10 sections)
  - Convention de signe retard alignée avec le cabinet (`échéance − paiement`)
  - **Résultats** : 438 lignes communes, 82 % statuts cohérents, 97 % retards cohérents
  - Écarts résiduels documentés et imputés à D-006 (≈ 65 %), D-001 (15 %), D-007 (Simpl)
  - **Phase 1 livrable** : pipeline opérationnel, divergences explicables et corrigibles en ≈ 30 min par le cabinet

## 9. Phases ultérieures

- **Phase 2** : interface utilisateur (bureau à distance), base Frs paramétrable côté cabinet, module TVA.
- **Phase 3** : connecteurs Ciel / ERP, gestion portefeuille (multi-clients), reporting consolidé.
- **Phase 4** : onboarding cabinets, formation, support, commercialisation Maroc.

## 10. Artefacts de référence

| Quoi | Où |
|---|---|
| GL UEMA 1T26 (PDF + Excel) | `../3.Modèle DDP/Input/UEMA - GL FRS 2026.*` |
| Modèle Suivi Global vide | `../3.Modèle DDP/Input/Modèle Suivi Global.xlsx` |
| Sondage 1T26 + 17 PDF justificatifs | `../3.Modèle DDP/Input/Sondage/` |
| Suivi Global rempli (référence) | `../3.Modèle DDP/Output/Modèle Suivi Global DDP2026.xlsx` |
| Simpl rempli (référence) | `../3.Modèle DDP/Output/Simpl délais de paiements UEMA - TR 01-2026.xlsx` |
| Présentation projet | `../Presentation_DDP_Automatisation.pptx` |
| Résumé réunion initiale | `../summary-reunion.txt` |

## 11. Extension de l'environnement Claude Code

Au fil du projet, créer dans `.claude/` :

| Besoin détecté | À créer | Emplacement |
|---|---|---|
| Tâche récurrente complexe (ex: "valide un trimestre") | **Slash command** | `.claude/commands/<nom>.md` |
| Compétence réutilisable (ex: parsing Sage) | **Skill** | `.claude/skills/<nom>/SKILL.md` |
| Sous-traitance d'investigation lourde | **Agent** | `.claude/agents/<nom>.md` |
| Service externe (Sage API, DGI Simpl) | **MCP server** | configurer dans `~/.claude.json` |

Avant de créer un nouveau composant, vérifier qu'il n'existe pas déjà au niveau utilisateur (`~/.claude/`) ou plugin.

## 12. Charte produit (rappels Nextor)

- Couleurs : navy `#2B4C6F`, teal accent `#4ECDC4`, navy foncé `#1E3A5F`.
- Logo : `nextor-guidelines/img/Logo présentation*.png`.
- URL : nextor-it.com.
- Toute interface utilisateur du produit DOIT respecter cette charte.

## 13. Décisions métier

Toutes les décisions de règles métier sont consignées dans **`docs/decisions.md`** au format ADR
(Architecture Decision Record). Chaque décision liste les **questions à poser au cabinet
comptable** pour validation.

**Statut des décisions** :

| ID | Sujet | Statut |
|---|---|---|
| D-001 | Extraction n° facture | 🟡 Provisoire |
| D-002 | Date livraison vs facture | 🟡 Provisoire |
| D-003 | Détection paiements récurrents | 🟠 Partiellement résolue (Sprint 3 — surcharge délai/facture) |
| D-004 | Tolérance écart de lettrage | 🟡 Provisoire |
| D-005 | Écritures OD insignifiantes | 🟡 Provisoire |
| D-006 | Dates des factures AN | 🟢 **Résolue** (Sprint 2a + 2b) — surcharge manuelle + OCR auto |
| D-007 | Référentiel DGI | 🟢 **Résolue** (Phase 2 Sprint 1) |
| D-008 | Mode de dépôt Simpl-TVA | 🔴 **Bloquante** — question à poser au cabinet |
| D-009 | Convention de comptage du délai (J0 vs J1) | 🟢 **Résolue** (2026-05-19) — Q9.1 = jour 0 |

⚠️ **Toutes provisoires** : à valider avec un cabinet d'expertise comptable avant industrialisation.
Voir `docs/decisions.md` pour les questions précises à poser.

## 14. Autres décisions ouvertes (techniques)

- [ ] Format final du Simpl : Excel uniquement, ou Excel + XML DGI ?
- [ ] Gestion multi-devises (export, import) — hors scope phase 1 ?
- [ ] Stratégie de stockage de la Base Frs : par client / partagée cabinet ?
- [ ] Mécanisme d'apprentissage des cas ambigus récurrents ?

---

**Statut** : 🟡 **Phase 2 en cours** (démarrée 2026-05-18). Phase 1 terminée, 93 tests verts.

**Phase 2 — sprints :**
1. ✅ **Sprint 1 — Référentiel DGI partagé** (D-007) — *2026-05-18* — Simpl auto-rempli à 61 %
2. ✅ **Sprint 2a — Mécanisme de surcharge manuelle des dates** (D-006) — *2026-05-18*
3. ✅ **Sprint 2b — OCR sur PDF justificatifs** (D-006) — *2026-05-18* — Tesseract fra+ara
4. ✅ **Sprint 3 — Délai par facture** (D-003) — *2026-05-18* — Col G du fichier corrections, surcharge ponctuelle du délai fournisseur
5. ✅ **Sprint 4 — Détection auto des doublons** — *2026-05-18* — Module `quality/` : doublons exacts, doublons probables (montants identiques, dates ±7j), montants récurrents non lettrés. Annotation auto des LigneSuivi avec icônes 🔁❓🔄
6. ✅ **Sprint 5 — Interface utilisateur web (Streamlit MVP)** — *2026-05-18* — `app/streamlit_app.py` : upload drag-and-drop, configuration client en sidebar, exécution en 1 clic, dashboard interactif (KPI + tableau filtrable + anomalies), téléchargement des Excel finaux. Charte Nextor (navy / teal), logo, transitions. Lancement : `streamlit run app/streamlit_app.py`.
7. ⏳ Sprint 6 — Connecteurs Ciel / autres ERP
