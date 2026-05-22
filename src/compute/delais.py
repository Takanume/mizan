"""Calcul des échéances, retards, statuts pour chaque facture.

Entrée  : un `Lettrage` (factures + paiements groupés par lettre).
Sortie  : 1+ `LigneSuivi` (une par facture du lettrage).

Algorithme pour un lettrage donné :

  1. Pour chaque facture, calcul de l'échéance :
       date_echeance = (date_livraison ou date_facture)  +  délai_convenu

  2. Imputation des paiements aux factures par FIFO :
       Les paiements (triés par date) règlent en priorité les factures
       les plus anciennes (date_facture ASC).
       Cas couverts :
         - 1 facture + 1 paiement     → imputation simple
         - 1 facture + n paiements    → partiels (date paiement = date du
                                          paiement qui solde la facture)
         - n factures + 1 paiement    → groupé (le paiement règle plusieurs
                                          factures, on garde sa date)
         - n factures + n paiements   → mixte, FIFO

  3. Calcul du retard :
       date_paiement_effectif = date du dernier paiement nécessaire pour
                                  solder la facture (= imputation FIFO)
       jours_retard = date_paiement_effectif − date_echeance

  4. Détermination du statut (cf. modèle `StatutFacture`) :
       - Si pas de paiement imputé      → FNP
       - Si écart résiduel > tolérance  → PARTIEL
       - Si jours_retard ≤ 0            → OK_RAS (payée à temps ou en avance)
       - Si jours_retard > 0            → RETARD (libellé : "Attention, paiement hors délais")

Les écarts de lettrage absorbés par la tolérance D-004
(`max(1 MAD, 0,5%)`) ne génèrent pas de statut PARTIEL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import (  # noqa: E402
    Facture,
    Lettrage,
    LigneSuivi,
    Paiement,
    StatutFacture,
)


# Tolérance D-004 : max(1 MAD, 0,5%) du montant facture
TOLERANCE_ABSOLUE = Decimal("1")
TOLERANCE_RELATIVE = Decimal("0.005")



def tolerance(montant_facture: Decimal) -> Decimal:
    """Tolérance d'écart de lettrage pour une facture donnée (D-004)."""
    return max(TOLERANCE_ABSOLUE, montant_facture * TOLERANCE_RELATIVE)


def calculer_date_echeance(facture: Facture, delai_jours: int) -> date:
    """date_echeance = (date_livraison ou date_facture) + délai − 1.

    Convention J1 (D-009, révisée 2026-05-22) : le jour de la facture compte
    comme jour 1 du délai (lecture inclusive du cabinet). L'échéance tombe
    donc le (délai)ᵉ jour à partir de la facture incluse.

    Si la facture porte une surcharge de délai (Sprint 3 — D-003), elle
    prime sur le délai du fournisseur passé en argument.
    """
    base = facture.date_livraison or facture.date_facture
    delai_effectif = facture.delai_surcharge if facture.delai_surcharge else delai_jours
    return base + timedelta(days=delai_effectif - 1)


# ─── Imputation FIFO ───────────────────────────────────────────────────────

@dataclass
class Imputation:
    """Résultat d'une imputation pour une facture donnée."""
    montant_impute: Decimal                     # somme des paiements imputés
    date_paiement_effectif: Optional[date]      # date du dernier paiement nécessaire
    paiements_imputes: list[Paiement]           # paiements ayant contribué


def imputer_fifo(
    factures: list[Facture],
    paiements: list[Paiement],
) -> dict[str, Imputation]:
    """Impute les paiements aux factures par FIFO.

    Les factures sont triées par date croissante (les plus anciennes
    consomment les paiements en premier). Les paiements sont consommés
    dans l'ordre chronologique également.

    Retourne un dict {n_piece_facture → Imputation}.
    """
    # Trier factures et paiements par date
    factures_tri = sorted(factures, key=lambda f: (f.date_facture, f.n_piece))
    paiements_tri = sorted(paiements, key=lambda p: (p.date_paiement, p.n_piece))

    # Pool de paiements disponibles (montant restant à imputer par paiement)
    pool: list[tuple[Paiement, Decimal]] = [(p, p.montant) for p in paiements_tri]
    pool_idx = 0

    resultats: dict[str, Imputation] = {}

    for f in factures_tri:
        a_imputer = f.montant_ttc
        imputes: list[Paiement] = []
        date_dernier: Optional[date] = None

        while a_imputer > 0 and pool_idx < len(pool):
            paiement, restant = pool[pool_idx]
            if restant <= 0:
                pool_idx += 1
                continue
            consommé = min(a_imputer, restant)
            imputes.append(paiement)
            date_dernier = paiement.date_paiement
            a_imputer -= consommé
            pool[pool_idx] = (paiement, restant - consommé)
            if pool[pool_idx][1] == 0:
                pool_idx += 1

        montant_impute = f.montant_ttc - a_imputer
        resultats[f.n_piece] = Imputation(
            montant_impute=montant_impute,
            date_paiement_effectif=date_dernier,
            paiements_imputes=imputes,
        )

    return resultats


# ─── Détermination du statut ───────────────────────────────────────────────

def determiner_statut(
    facture: Facture,
    imputation: Imputation,
    date_echeance: date,
) -> tuple[StatutFacture, Optional[int]]:
    """Détermine le statut d'une facture et les jours de retard.

    Retourne (statut, jours_retard). `jours_retard` peut être None si la
    facture n'est pas payée.
    """
    reste = facture.montant_ttc - imputation.montant_impute
    tol = tolerance(facture.montant_ttc)

    # Facture totalement non payée
    if imputation.montant_impute == 0:
        return StatutFacture.NON_PAYE, None

    # Facture partiellement payée au-delà de la tolérance
    if reste > tol:
        # On calcule quand même le retard sur ce qui a été payé
        if imputation.date_paiement_effectif:
            jours = (imputation.date_paiement_effectif - date_echeance).days
            return StatutFacture.PARTIEL, jours
        return StatutFacture.PARTIEL, None

    # Soldée (à la tolérance près)
    assert imputation.date_paiement_effectif is not None
    jours = (imputation.date_paiement_effectif - date_echeance).days

    # Le cabinet n'utilise que deux statuts pour les factures payées : OK ou retard.
    # Toute facture payée à temps (≤ échéance) → OK RAS, peu importe l'avance.
    if jours > 0:
        return StatutFacture.RETARD, jours
    return StatutFacture.OK_RAS, jours


# ─── Pipeline principal ────────────────────────────────────────────────────

def calculer_lignes_suivi(lettrage: Lettrage) -> list[LigneSuivi]:
    """Convertit un Lettrage en 1+ `LigneSuivi` (une par facture).

    Applique l'imputation FIFO et le calcul du statut pour chaque facture.
    Le délai convenu provient du fournisseur attaché au lettrage.
    """
    if not lettrage.factures:
        return []

    delai = lettrage.fournisseur.delai_convenu_jours
    imputations = imputer_fifo(lettrage.factures, lettrage.paiements)

    lignes: list[LigneSuivi] = []
    for f in lettrage.factures:
        echeance = calculer_date_echeance(f, delai)
        delai_effectif = f.delai_surcharge if f.delai_surcharge else delai
        imp = imputations[f.n_piece]
        statut, jours = determiner_statut(f, imp, echeance)
        observations = _detecter_observations(f, None)

        lignes.append(LigneSuivi(
            n_facture=f.n_facture or f.n_piece,
            date_livraison=f.date_livraison or f.date_facture,
            date_facture=f.date_facture,
            fournisseur=f.nom_fournisseur,
            montant_ttc=f.montant_ttc,
            montant_du=f.montant_ttc - imp.montant_impute,
            delai_convenu_jours=delai_effectif,
            date_echeance=echeance,
            jours_retard=jours,
            statut=statut,
            date_paiement_effectif=imp.date_paiement_effectif,
            observations=observations,
            code_fournisseur=f.code_fournisseur,
            lettrage=lettrage.lettre,
        ))

    return lignes


import re

# Détection d'un millésime ancien dans le n° facture (ex: "25/02609", "24/0102").
# Capture les 2 chiffres en tête suivis d'un séparateur non chiffre.
_RE_MILLESIME = re.compile(r"^(\d{2})[^\d]")


def _detecter_observations(
    facture: Facture,
    debut_periode: Optional[date],
) -> Optional[str]:
    """Ajoute une observation visuelle lorsque la fiabilité de la date est suspecte.

    Cas couverts (D-006) :
      - Facture reportée (Cj = AN) → date d'écriture = 01/01/exercice ≠ date réelle
      - N° facture commence par un millésime antérieur (ex: "25/xxx" en 2026)

    Le statut et les calculs ne sont pas modifiés — c'est juste un flag visuel
    pour signaler au comptable les lignes à revoir depuis les PDF justificatifs.
    """
    if not facture.is_report:
        return None

    annee_courante = (debut_periode.year if debut_periode else facture.date_facture.year)
    annee_courte = annee_courante % 100  # 2026 → 26

    n_fact = (facture.n_facture or "").strip()
    m = _RE_MILLESIME.match(n_fact)
    if m:
        millesime = int(m.group(1))
        if millesime != annee_courte:
            annee_pleine = 2000 + millesime if millesime < 80 else 1900 + millesime
            return f"⚠️ Facture millésime {annee_pleine} — vérifier date facture sur PDF"

    # Facture reportée mais sans millésime identifiable : on flag quand même
    return "⚠️ Facture reportée (AN) — vérifier date facture sur PDF"


def _facture_soldee_pre_periode(
    facture: Facture,
    imputation: Imputation,
) -> bool:
    """True si la facture est entièrement payée par des paiements reportés (AN).

    Sage rapporte ces écritures en AN pour la cohérence du bilan, mais la
    transaction réelle a eu lieu avant la période. Pas à déclarer ce trimestre.
    """
    if not imputation.paiements_imputes:
        return False  # FNP — à déclarer
    # Toutes les imputations sont des paiements AN ?
    if not all(p.is_report for p in imputation.paiements_imputes):
        return False
    # Et la facture est bien soldée (à la tolérance près) ?
    reste = facture.montant_ttc - imputation.montant_impute
    return reste <= tolerance(facture.montant_ttc)


def calculer_lignes_suivi_avec_filtre(
    lettrage: Lettrage,
    debut_periode: Optional[date] = None,
) -> list[LigneSuivi]:
    """Comme `calculer_lignes_suivi` mais filtre les factures pré-période."""
    if not lettrage.factures:
        return []

    delai = lettrage.fournisseur.delai_convenu_jours
    imputations = imputer_fifo(lettrage.factures, lettrage.paiements)

    lignes: list[LigneSuivi] = []
    for f in lettrage.factures:
        imp = imputations[f.n_piece]

        if debut_periode is not None and _facture_soldee_pre_periode(f, imp):
            continue

        echeance = calculer_date_echeance(f, delai)
        delai_effectif = f.delai_surcharge if f.delai_surcharge else delai
        statut, jours = determiner_statut(f, imp, echeance)
        observations = _detecter_observations(f, debut_periode)

        lignes.append(LigneSuivi(
            n_facture=f.n_facture or f.n_piece,
            date_livraison=f.date_livraison or f.date_facture,
            date_facture=f.date_facture,
            fournisseur=f.nom_fournisseur,
            montant_ttc=f.montant_ttc,
            montant_du=f.montant_ttc - imp.montant_impute,
            delai_convenu_jours=delai_effectif,
            date_echeance=echeance,
            jours_retard=jours,
            statut=statut,
            date_paiement_effectif=imp.date_paiement_effectif,
            observations=observations,
            code_fournisseur=f.code_fournisseur,
            lettrage=lettrage.lettre,
        ))

    return lignes


def calculer_toutes_lignes(
    lettrages: list[Lettrage],
    debut_periode: Optional[date] = None,
) -> list[LigneSuivi]:
    """Produit toutes les lignes du Suivi Global à partir des lettrages.

    Si `debut_periode` est fourni, on exclut les factures entièrement soldées
    par des paiements reportés (AN) — elles ont été réglées en pratique avant
    la période courante.
    """
    lignes: list[LigneSuivi] = []
    for l in lettrages:
        lignes.extend(calculer_lignes_suivi_avec_filtre(l, debut_periode))
    return lignes
