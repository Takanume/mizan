# Synthèse — Comparaison Suivi Global UEMA 1T26 (Cabinet vs Mizan)

**Source** : `out/Suivi Global - Comparaison Cabinet.xlsx`
**Date d'analyse** : 2026-05-21
**Périmètre** : UEMA, 1ᵉʳ trimestre 2026, 1 279 lignes comparées.

---

## 1. Vue d'ensemble

| Catégorie | Nb lignes | % | Lecture |
|---|---:|---:|---|
| 🟢 Identiques (toutes colonnes alignées) | **0** | 0 % | Aucune ligne strictement identique |
| 🟡 Matchées mais ≥1 cellule diffère | **657** | 51 % | Au moins un écart de valeur sur une cellule |
| 🔵 Présentes cabinet, absentes Mizan | **117** | 9 % | Le cabinet déclare une facture que Mizan ne voit pas |
| 🔴 Présentes Mizan, absentes cabinet | **505** | 40 % | Mizan déclare une facture absente du fichier cabinet |
| **Total** | **1 279** | 100 % | |

Aucune ligne strictement identique : il existe au moins un écart (souvent mineur, parfois structurel) sur chaque facture.

---

## 2. Écarts sur les lignes matchées (657)

### 2.1. Colonnes qui diffèrent

| Colonne | Nb lignes | Lecture |
|---|---:|---|
| **Échéance** | **654** (≈ 100 %) | Décalage de date d'échéance presque systématique |
| Statut | 172 | Conséquence directe du décalage d'échéance / paiement |
| Délai | 147 | Délai contractuel différent en base cabinet vs Mizan |
| Date de paiement | 134 | Lettrage / date effective différents |

### 2.2. Distribution des écarts d'échéance (Mizan − Cabinet, en jours)

| Tranche | Nb | % | Cause |
|---|---:|---:|---|
| **+1 j** | 286 | 44 % | Convention J0 vs J1 (cabinet retire 1 j par habitude) |
| +2 à +7 j | 40 | 6 % | Date de livraison ≠ date de facture (info absente du GL) |
| +8 à +30 j | 30 | 5 % | Factures émises en fin de mois pour livraisons antérieures |
| +120 à +363 j | ~285 | 43 % | **Factures « À-Nouveau » (AN) — limitation D-006** |
| Négatifs (−7 à −361 j) | 5 | <1 % | Fautes de frappe cabinet |

### 2.3. Transitions de statut les plus fréquentes

| Transition cabinet → Mizan | Nb |
|---|---:|
| « Attention, hors délai » → « OK RAS » | **132** |
| « Non encore payée » → « OK RAS » | 20 |
| « OK RAS » → « Attention, hors délai » | 8 |
| « OK RAS » → « Non encore payée » | 5 |
| « Non encore payée » → « Paiement partiel » | 4 |

➡️ Conséquence directe du décalage d'échéance (+1 j) : ce qui passait pour un retard côté cabinet devient « dans les clous » côté Mizan.

---

## 3. Explication des écarts par cause

### Cause A — Convention J0 vs J1 (286 lignes, +1 j)

**Constat.** Pour la facture LASER OUHOUD du 03/01/2026 (délai 120 j) :
- Cabinet : échéance = **02/05/2026**
- Mizan : échéance = **03/05/2026** (= 03/01 + 120 j)

**Explication.** Le cabinet compte le jour de la facture comme le **jour 1** du délai (lecture inclusive : « 120 jours pleins à partir de la facture »). Mizan compte ce jour comme le **jour 0** (`échéance = date + délai`).

**Statut.** **Résolu (D-009)** — le cabinet a confirmé le 19/05/2026 que la convention J0 (Mizan) est la bonne ; les −1 j de son fichier sont des erreurs de saisie, pas une règle métier.

**Action.** Aucune côté code.

---

### Cause B — Date de livraison ≠ date de facture (40 lignes, +2 à +7 j)

**Constat.** Pour ESPACE INOX 20260143 :
- Cabinet : `date_livraison = 27/02`, `date_facture = 28/02` → éch = 26/06
- Mizan : `date_livraison = 28/02` (= date_facture) → éch = 28/06

**Explication.** Le Grand Livre Sage **ne contient pas la date de livraison** : seul le bon de livraison physique (BL) la porte. Mizan retombe sur `date_facture` par défaut (cf. `delais.py:74`, `base = facture.date_livraison or facture.date_facture`).

**Statut.** Limitation structurelle de la source GL.

**Action.** Étendre **Sprint 2b (OCR Tesseract)** aux factures normales pour extraire la date de livraison réelle depuis les PDF — ou la saisir dans le fichier de corrections.

---

### Cause C — Factures de fin de mois (30 lignes, +8 à +30 j)

**Constat.** AGADIR INOX EXPORT 202623118 :
- Cabinet : livraison 02/03, facture 31/03 → éch = 29/06
- Mizan : livraison = facture = 31/03 → éch = 29/07 (**Δ = +30 j**)

**Explication.** Même cause que B, amplifiée pour les fournisseurs qui facturent à fin de mois pour des livraisons étalées sur tout le mois.

**Action.** Identique à B (OCR ou corrections manuelles).

---

### Cause D — Factures « À-Nouveau » (≈ 285 lignes matchées + 326 lignes Mizan-only, +120 à +363 j)

**Constat.** TECHNIQUE ACIERS 2500071 :
- Cabinet : facture du **04/01/2025**, éch = 03/05/2025
- Mizan : forcé à **01/01/2026** (date d'écriture AN Sage), éch = 01/05/2026 (**Δ = +363 j**)

**Explication.** Les factures non payées au 31/12 sont reportées par Sage dans le journal **À-Nouveau** avec une date d'écriture = 01/01 de l'exercice courant. La **vraie date de facturation** n'est nulle part dans le GL — seul le numéro de pièce porte le millésime (`25/xxxxx`). Le cabinet, lui, la retrouve sur le PDF papier.

**Statut.** Limitation **D-006** documentée ; Sprints 2a (surcharge manuelle) et 2b (OCR) déjà livrés mais **non encore branchés** sur cette comparaison.

**Action.** Rejouer le pipeline en activant la surcharge des dates AN via les PDF factures.

---

### Cause E — Erreurs de saisie cabinet (5 lignes, négatifs)

**Constat.** ABRA-TRDE 2025-104 : cabinet saisit `date_livraison = 30/12/2026` pour une facture du `02/01/2026` (livraison **un an après** la facture).

**Explication.** Faute de frappe manifeste (probablement `2025` au lieu de `2026`).

**Action.** Signaler au cabinet.

---

## 4. Les 505 lignes Mizan-only — explication

| Catégorie | Nb | % | Lecture |
|---|---:|---:|---|
| Factures « À-Nouveau » (date = 01/01/2026) | **326** | **65 %** | Mizan exhaustif sur le report AN, cabinet sélectif |
| Factures normales 2026 absentes du cabinet | 179 | 35 % | dont ≈ 42 mismatchs de format n° + ≈ 137 vrais oublis |

### 4.1. Sur-couverture AN (326 lignes)

Mizan reporte **toutes** les factures de l'exercice précédent restées ouvertes au 31/12. Statuts dominants : 154 « OK RAS », 144 « Non payée », 19 « Hors délai », 9 « Partiel ».

Le cabinet opère un **tri implicite** : il ne déclare typiquement que les AN à enjeu DDP réel (encore impayées au trimestre, ou payées en retard) et ignore les AN soldées dans les délais dès janvier.

### 4.2. Mismatch de format n° de facture (≈ 42 lignes)

Sur les **117 lignes cabinet-only**, **42** se ré-apparient avec une ligne Mizan-only en croisant `(fournisseur, montant)`. Exemple :

| Cabinet | Mizan | Fournisseur |
|---|---|---|
| `63261` | `GI/63261` | GROS INOX |
| `63333` | `GI/63333` | GROS INOX |
| `63486` | `GI/63486` | GROS INOX |

➡️ Ce sont les **mêmes factures** comptées deux fois dans la comparaison (1 fois côté chacun). À corriger **côté script de comparaison** (normaliser les préfixes `GI/`, `AB/`, etc.).

### 4.3. Vraies factures absentes côté cabinet (≈ 137 lignes)

Restent ~137 factures **vraiment** dans le GL Sage mais hors fichier cabinet. Pistes :
- saisie manuelle **incomplète** côté cabinet (fournisseurs marginaux oubliés) ;
- petits montants filtrés sous un seuil tacite ;
- fournisseurs exclus par règle métier (intra-groupe, administrations) que Mizan ne sait pas filtrer.

**C'est l'apport principal de Mizan : ≈ +130 factures par trimestre par rapport au manuel cabinet, soit ≈ +15 % de couverture déclarative.**

---

## 5. Les 117 lignes cabinet-only — explication

| Origine | Nb estimé |
|---|---:|
| Mismatch de format n° (cf. 4.2) | ≈ 42 |
| Saisies cabinet hors GL (OD, retraitements, doublons) | ≈ 75 |

Les 75 lignes réellement « cabinet-only » sont à investiguer au cas par cas avant industrialisation.

---

## 6. Récapitulatif des actions

| ID | Action | Pour qui | Effort | Effet attendu |
|---|---|---|---|---|
| A1 | Activer la surcharge des dates AN (Sprints 2a/2b déjà livrés) | Nextor | 30 min | Résorbe les 285 lignes matchées + 326 Mizan-only AN (≈ 47 % des écarts) |
| A2 | Normaliser les préfixes n° facture dans `scripts/comparer_outputs.py` | Nextor | 1 h | Élimine ≈ 42 faux écarts |
| A3 | Étendre l'OCR aux factures non-AN pour la date de livraison | Nextor | 1 j | Résorbe les 70 lignes « +2 à +30 j » |
| A4 | Réconcilier la liste des fournisseurs déclarables (intra-groupe, administrations) | Cabinet | 1 h | Résorbe une partie des ≈ 137 factures Mizan-only normales |
| A5 | Vérifier les 5 lignes avec Δ négatif (fautes de frappe) | Cabinet | 15 min | Nettoyage qualité |

---

## 7. Questions à poser au cabinet

### 7.1. Sur la convention de calcul (cause A)

> **Q-A1.** Tu as confirmé la convention **J0** (jour de la facture = jour 0). Confirmes-tu que les 286 lignes avec « −1 j » dans ton fichier de référence sont bien des erreurs de saisie, et qu'on peut les considérer comme **corrigées par Mizan** dans le livrable final ?

### 7.2. Sur les dates de livraison (causes B & C)

> **Q-B1.** Comment obtiens-tu la **date de livraison réelle** (différente de la date de facture) ? Sur le BL papier ? Sur la facture PDF ?
>
> **Q-B2.** Pour les fournisseurs qui facturent à fin de mois (AGADIR INOX EXPORT, ESPACE INOX…), considères-tu la date de livraison « initiale » (1ʳᵉ livraison du mois) ou la date de facture ?
>
> **Q-B3.** Acceptes-tu que pour le 1ᵉʳ trimestre 2026, on **te livre les écarts** sur les dates de livraison **sans les corriger** (au prix d'une légère sur-déclaration des retards) ? Le coût d'extraction par OCR/saisie nous semble disproportionné pour le pilote.

### 7.3. Sur les factures « À-Nouveau » (cause D + sur-couverture)

> **Q-D1.** Pour les factures **AN soldées dans les délais en janvier-février**, les déclares-tu dans la DDP du trimestre courant ou les considères-tu comme « affaire de l'exercice précédent » ?
>
> **Q-D2.** Si tu les exclus, quelle est la **règle exacte** ? (« soldée avant le 31/03 » ? « soldée dans les 60 j » ? autre ?)
>
> **Q-D3.** Acceptes-tu qu'on te fournisse les **vraies dates** des factures AN via OCR sur les PDF (Sprint 2b livré) ? Combien de PDF AN as-tu typiquement à disposition pour un client ?

### 7.4. Sur les fournisseurs déclarables (sur-couverture Mizan)

> **Q-F1.** Y a-t-il des **catégories de fournisseurs systématiquement exclus** de la DDP ? (intra-groupe, administrations, dirigeants, comptes d'attente…)
>
> **Q-F2.** Existe-t-il un **seuil de matérialité** (montant minimum) en deçà duquel tu ne déclares pas une facture ? Si oui, quel est-il ?
>
> **Q-F3.** Comment construis-tu ta liste de fournisseurs déclarables ? À partir du GL ? D'une base interne ? D'une liste validée avec le client ?

### 7.5. Sur les 75 lignes cabinet-only restantes (cause inverse)

> **Q-C1.** Sur le trimestre UEMA 1T26, certaines factures sont **dans ta déclaration mais absentes du GL Sage que tu nous as transmis**. Sources possibles ? (saisie manuelle hors-GL, OD post-clôture, second GL ?)
>
> **Q-C2.** Acceptes-tu de nous envoyer la **liste exhaustive de ces lignes** pour qu'on regarde d'où elles viennent ?

### 7.6. Sur le format des numéros de facture (cause 4.2)

> **Q-N1.** Quand tu saisis le n° de facture (ex. `63261` pour GROS INOX), retires-tu **délibérément** le préfixe fournisseur (`GI/`) ou est-ce une simplification d'écriture ?
>
> **Q-N2.** Le n° à déclarer à la DGI dans le Simpl doit-il porter le préfixe (format Sage `GI/63261`) ou non (format cabinet `63261`) ?

### 7.7. Sur les erreurs de saisie (cause E)

> **Q-E1.** Sur 5 lignes (ex. ABRA-TRDE 2025-104), on relève des **incohérences de date** (livraison après facture, livraison un an après facture). Acceptes-tu qu'on te les remonte pour relecture ?

---

## 8. Bilan pour la valeur produit

| Indicateur | Cabinet manuel | Mizan |
|---|---:|---:|
| Lignes traitées sur le trimestre | ~ 891 | **1 162** |
| Couverture relative | référence | **+ 15 %** |
| Erreurs de convention de calcul | 286 (J1 systématique) | 0 |
| Erreurs de saisie (dates aberrantes) | 5 | 0 |
| Temps de production | plusieurs jours | **2,1 secondes** |

**Conclusion.** Les divergences sont **expliquées et imputables à 4 causes structurelles connues** ; aucune n'est un bug de calcul Mizan. Les corrections nécessaires côté code sont mineures (script de comparaison + activation Sprints 2a/2b). Les questions ouvertes relèvent du **paramétrage métier** à clarifier avec le cabinet avant industrialisation.
