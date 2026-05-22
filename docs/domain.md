# Domaine métier — DDP automation

> Référence concrète pour comprendre les modèles de `src/models.py`.
> Tous les exemples sont tirés du **GL UEMA 1ᵉʳ trimestre 2026**.

---

## 1. Structure du Grand Livre Sage

Export type : `UEMA - GL FRS 2026.xlsx` (Sage 100cloud Comptabilité Premium 5.03).

### En-têtes (lignes 1-8 du fichier)

```
L2  : STE UEMA          Grand-livre des tiers     Période du 2026-01-01
L3  :                                              au         2026-12-31
L4  :                   Fournisseur               Tenue de compte : MAD
L6  : © Sage …                                    Date de tirage 2026-05-13
L8  : Date  C.j  N° pièce  Libellé écriture  Lettr.  Mouvement débit  Mouvement crédit  Solde progressif
```

### Colonnes des données (lignes 12+)

| Col Excel | Champ | Exemple |
|---|---|---|
| 1  | Date de l'écriture | 2026-01-23 |
| 2  | Code journal (`Cj`) | `ACH`, `BMCE`, `AN`, `OD`, `CAI`, `BMCI` |
| 3  | N° pièce Sage | `37`, `196` |
| 6  | Libellé écriture | `FN° 26FC0031 A2CIM` |
| 9  | Lettrage | `A` (une lettre A-Z, ou vide) |
| 13 | Mouvement débit (paiements) | `2520` |
| 15 | Mouvement crédit (factures) | `2520` |
| 18 | Solde progressif | `-2520` |

⚠️ Les en-têtes (L8) ne sont **pas alignés** avec les données : Sage place les libellés
d'en-tête dans la première cellule d'un groupe fusionné, alors que les valeurs sont
dans la dernière. Toujours se fier aux colonnes de données ci-dessus.

### Bloc fournisseur

Chaque fournisseur est délimité par :

- **Ouverture** : ligne `FRSxxxxxxx <NOM>` (code en col 1, nom en col 4).
- **Écritures** : 1 à N lignes (factures + paiements).
- **Clôture** : ligne `Total du tiers` (à ignorer).

### Codes journaux observés (1T26 UEMA)

| Code | Volume | Sens |
|---|---|---|
| `AN`   | 732 | À-Nouveau — report des écritures non lettrées de l'exercice précédent |
| `ACH`  | 539 | Achats — nouvelles factures de l'exercice |
| `BMCE` | 195 | Paiements via banque BMCE (virement, chèque) |
| `OD`   | 36  | Opérations Diverses — typiquement LCN (effets) |
| `CAI`  | 7   | Caisse — paiements en espèces (`ESPECE`, `ESPACE`) |
| `BMCI` | 1   | Paiements via banque BMCI |

### Lettrages observés

- Caractères : **A à H** uniquement (un fournisseur peut avoir jusqu'à 8 lettrages distincts).
- Longueur : **1 seul caractère** (pas de `AA`, `BC`, etc.).
- Vide → écriture non lettrée → facture FNP ou paiement orphelin.

---

## 2. Reconnaître la nature d'une écriture

### Règle générale (Phase 1 — UEMA)

| Si … | Alors c'est … |
|---|---|
| `Cj ∈ {ACH, AN}` et `credit > 0` et libellé commence par `FN°` ou `Fact` | **Facture** |
| `Cj ∈ {BMCE, BMCI, CAI}` et `debit > 0` | **Paiement** |
| `Cj = OD` et `debit > 0` et libellé contient `LCN` | **Paiement** (effet de commerce) |
| `Cj = AN` et `debit > 0` et libellé contient `VIR`, `CHQ`, `LCN`, `RGL`, `Vrt`, `Paiement` | **Paiement** (reporté depuis l'exercice précédent) |
| `Cj = ACH` et `debit > 0` (rare) | **Avoir** (à confirmer) |
| `Cj = OD` et libellé `Rentree …` | **Autre** (régularisation, montant ≈ 0) |

### Préfixes de libellé observés

- **Factures** : `FN°` (980 occ.), `Fact` (170 occ.)
- **Paiements** : `Vrt` / `VIR` / `VIREMENT` (virements), `Chq` / `CHQ` (chèques),
  `LCN` / `LCN°` (effets), `Paiement` (générique), `RGL` (règlement),
  `ESPECE` / `ESPACE` (caisse, code journal `CAI`)
- **À ignorer** : `Total du tiers` (clôture de bloc)

---

## 3. Exemples réels du GL UEMA

### 3.1. Cas simple — A2CIM (L12-17)

```
FRS0000001  A2CIM
─────────────────────────────────────────────────────────────────────
L13  23/01  ACH   #37   FN° 26FC0031 A2CIM     [A]   D=·       C=2520
L14  23/01  BMCE  #196  Vrt/A2CIM              [A]   D=2520    C=·
L15  05/03  BMCE  #814  Vrt/A2CIM              [B]   D=4838.40 C=·
L16  06/03  ACH   #335  FN° 26FC0129 A2CIM     [B]   D=·       C=4838.40
L17  Total du tiers
```

- **Lettre A** : facture du 23/01 (2 520) ↔ virement du 23/01 (2 520) — payé à J+0.
- **Lettre B** : facture du 06/03 (4 838,40) ↔ virement du 05/03 (4 838,40) — payé à J−1 (anticipé).

### 3.2. Cas reporté — ABM INDUSTRIE (L18-23)

```
FRS0000003  ABM INDUSTRIE
─────────────────────────────────────────────────────────────────────
L19  01/01  AN    #442   Fact ABM INDUSTRIE          [A]   D=·     C=336
L20  01/01  AN    #2390  FN° 2500521 ABM INDUSTRIE   [A]   D=·     C=63072
L21  01/01  AN    #2523  VIREMENT ABM INDUSTRIE      [A]   D=300   C=·
L22  20/04  BMCE  #1142  Vrt/ABM INDUSTRIE           [A]   D=63108 C=·
L23  Total du tiers                                        63408   63408
```

- 2 factures reportées du 2025 (336 + 63 072 = 63 408) lettrées `A`.
- 1 paiement partiel reporté (300) lettré `A`.
- 1 paiement banque du 20/04/2026 (63 108) qui solde le tout.
- Total débit = total crédit = 63 408 → lettrage soldé ✓.

### 3.3. Cas effet — CIQS (extrait)

```
L316  08/05  OD  #1049  LCN° 0038932 CIQS   [A]   D=34447.20  C=·
L317  09/06  OD  #1058  LCN N°38946 CIQS    [B]   D=70221.60  C=·
```

Ces écritures `OD` représentent des **Lettres de Change Normalisées** — instrument
de paiement à terme. Comptablement, elles soldent une dette (débit) au moment
de l'échéance de l'effet. Pour la DDP, elles comptent comme des **paiements**.

---

## 4. Calcul de l'échéance et du retard

```
date_echeance = date_livraison (ou date_facture si absente)  +  délai_convenu
jours_retard  = date_paiement_effectif  −  date_echeance
```

| Cas | Statut |
|---|---|
| `jours_retard ≤ 0` | OK RAS (ou Anticipé si très en avance) |
| `jours_retard > 0` | Retard |
| `lettrage soldé` mais `dates ≠` | Calcul à partir du dernier paiement |
| `lettrage non soldé` partiel | Paiement partiel — à ventiler |
| `pas de paiement` (lettrage vide) | FNP — non payée |

Pour une facture réglée par **plusieurs paiements partiels**, on calcule le retard
par paiement (en imputant le montant payé sur la facture la plus ancienne en premier — méthode FIFO).

Pour un **paiement groupé** (un virement règle plusieurs factures), même logique :
imputation FIFO du montant aux factures les plus anciennes du lettrage.

---

## 5. Référentiel fournisseurs

Sourcé depuis l'onglet **`Base Frs Permanente`** du fichier `Modèle Suivi Global.xlsx` :

| N° Fournisseur | Nom | Délai (jours) | Observations |
|---|---|---|---|
| FRS0000359 | LASER OUHOUD | 120 | — |
| FRS0000078 | CIQS | 120 | — |
| FRS0000587 | ABOUZAID PARTNERS | 60 | — |
| … | … | … | … |

Si un fournisseur du GL est absent de la base → délai par défaut **60 jours**
(à signaler dans `JeuDonnees.fournisseurs_hors_base`).

---

## 6. Sortie attendue — `Suivi Global DP`

Onglet `Suivi Global DP` du fichier `Modèle Suivi Global DDP2026.xlsx`.
Une ligne par **facture**, jamais par paiement.

| Col | En-tête | Source |
|---|---|---|
| B | N° Facture | extrait du libellé (`FN° XXX …`) — ou n° pièce Sage si non extractible |
| C | Date Livraison | à défaut = Date Facture |
| D | Date Facture/pièce (y compris FNP) | `EcritureBrute.date_ecriture` de la facture |
| E | Fournisseur | nom |
| F | Montant TTC | `EcritureBrute.credit` |
| G | Délai Convenu / Par défaut | base fournisseurs (60 / 120) |
| H | Date Échéance | `LigneSuivi.date_echeance` |
| I | Jours de Retard | calcul (peut être vide si FNP) |
| J | Statut | `OK RAS`, `Retard`, `FNP`, … |
| K | Date Paiement Effectif | date du dernier paiement du lettrage |
| L | Observations | libre (cas ambigus, etc.) |

### Exemple (LASER OUHOUD, lignes 10-15 du fichier de référence)

| N° Facture | Date Livr. | Date Fact. | Fournisseur | Montant | Délai | Échéance | Retard | Statut | Paiement |
|---|---|---|---|---|---|---|---|---|---|
| 26/00007 | 03/01/2026 | 03/01/2026 | LASER OUHOUD | 1 440 | 120 | 02/05/2026 | — | OK RAS | 01/05/2026 |
| 26/00008 | 03/01/2026 | 03/01/2026 | LASER OUHOUD | 384   | 120 | 02/05/2026 | — | OK RAS | 01/05/2026 |

---

## 7. Points en suspens (à trancher en Phase 1)

- [ ] **Extraction du n° de facture** depuis le libellé : regex `FN°\s*(\S+)`. Robustesse à valider sur tout le GL.
- [ ] **Date de livraison** : aucune colonne dédiée dans le GL Sage. Politique actuelle = date facture. Vérifier que c'est aligné avec la pratique du cabinet.
- [ ] **Détection des récurrents** : 2+ factures de même montant chez le même fournisseur dans la période → statut `À vérifier`.
- [ ] **Gestion des écarts** de lettrage (avoirs, escomptes) : seuil de tolérance ?
- [ ] **OD non typés** (libellé `Rentree …` à montant ≈ 0) : ignorer ou tracer ?
