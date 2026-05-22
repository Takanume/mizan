"""Classification des écritures brutes en factures / paiements / avoirs.

Convertit une `EcritureBrute` issue du parser en un objet métier typé
(`Facture`, `Paiement`) selon les règles définies dans `docs/domain.md §2`.

Les décisions provisoires de `docs/decisions.md` sont appliquées ici :
  - D-001 : extraction du n° facture par regex `FN°\\s*(\\S+)`
  - D-002 : `date_livraison = date_facture` (pas d'autre info dans Sage),
            avec heuristique fin-de-mois (D-011) : si la facture est datée
            du dernier jour du mois, livraison = veille (norme cabinet).
  - D-005 : OD `Rentree …` à montant < 1 MAD → INCONNU
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import (  # noqa: E402
    CodeJournal,
    EcritureBrute,
    Facture,
    MoyenPaiement,
    Paiement,
    TypeEcriture,
)


# Regex d'extraction du n° de facture depuis le libellé (D-001).
# Capture les caractères non-blancs juste après "FN°", "F°" ou "FN N°".
RE_NUM_FACTURE = re.compile(r"FN?\s*°?\s*N?°\s*(\S+)", re.IGNORECASE)

# Préfixes/mots-clés indicateurs d'une facture.
# Variantes observées : "FN°" (standard), "F°" (SRM-SM), "FN N°" (S.BOUBAD).
PREFIXES_FACTURE = ("FN°", "F°", "FN N°", "FN N", "Fact")

# Mots-clés indicateurs d'un paiement (utilisé pour les écritures AN ou OD).
# "LC " (avec espace) est une variante de "LCN" observée pour les LCN.
KEYWORDS_PAIEMENT = ("VIR", "VIREMENT", "CHQ", "CHEQUE", "LCN", "LC ", "LC°",
                     "RGL", "VRT", "PAIEMENT", "ESPECE", "ESPACE")

SEUIL_OD_INSIGNIFIANT = Decimal("1")  # D-005


def _sans_accents(s: str) -> str:
    """Normalise pour comparaisons insensibles aux accents (é → e)."""
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


# ─── Détection du moyen de paiement ────────────────────────────────────────

def detecter_moyen_paiement(libelle: str, code_journal: CodeJournal) -> MoyenPaiement:
    """Déduit le moyen de paiement à partir du libellé + journal."""
    lib_upper = libelle.upper()

    if code_journal == CodeJournal.CAI:
        return MoyenPaiement.ESPECES
    # LCN avec ou sans espace ("LCN°", "LC N°", "LC ")
    if "LCN" in lib_upper or "LC N" in lib_upper or "LC°" in lib_upper:
        return MoyenPaiement.LCN
    if "CHQ" in lib_upper or "CHEQUE" in lib_upper:
        return MoyenPaiement.CHEQUE
    if "VRT" in lib_upper or "VIR" in lib_upper or "VIREMENT" in lib_upper:
        return MoyenPaiement.VIREMENT
    if "ESPECE" in lib_upper or "ESPACE" in lib_upper:
        return MoyenPaiement.ESPECES
    return MoyenPaiement.AUTRE


# ─── Extraction du n° de facture ───────────────────────────────────────────

def extraire_n_facture(libelle: str) -> Optional[str]:
    """Extrait le n° de facture du libellé (D-001).

    Exemples :
      "FN° 26FC0031 A2CIM"          → "26FC0031"
      "FN°03764/2026 VITECMA"       → "03764/2026"
      "FN° 0202522423 AGADIR INOX"  → "0202522423"
      "Fact ABM INDUSTRIE"          → None (pas de n° après "Fact")
    """
    m = RE_NUM_FACTURE.search(libelle)
    if m:
        return m.group(1)
    return None


# ─── Détection de la nature de l'écriture ──────────────────────────────────

def _est_libelle_facture(libelle: str) -> bool:
    return any(libelle.lstrip().startswith(p) for p in PREFIXES_FACTURE)


def _est_libelle_paiement(libelle: str) -> bool:
    lib_upper = libelle.upper()
    return any(kw in lib_upper for kw in KEYWORDS_PAIEMENT)


def _est_od_insignifiante(ecr: EcritureBrute) -> bool:
    """D-005 : OD `Rentree/Rentrée/Créance …` à montant < 1 MAD = bruit comptable."""
    if ecr.code_journal != CodeJournal.OD:
        return False
    lib_norm = _sans_accents(ecr.libelle).lower()
    if "rentree" not in lib_norm and "creance" not in lib_norm:
        return False
    return max(ecr.debit, ecr.credit) < SEUIL_OD_INSIGNIFIANT


def classifier_ecriture(ecr: EcritureBrute) -> TypeEcriture:
    """Détermine la nature comptable d'une écriture (cf. domain.md §2)."""
    if _est_od_insignifiante(ecr):
        return TypeEcriture.INCONNU

    # Facture : crédit > 0 sur ACH ou AN avec libellé facture
    if ecr.credit > 0:
        if ecr.code_journal in (CodeJournal.ACH, CodeJournal.AN):
            if _est_libelle_facture(ecr.libelle):
                return TypeEcriture.FACTURE
            # AN avec crédit mais libellé non-FN° = on considère facture par défaut
            # (cas "Fact ABM INDUSTRIE" — D-001 fallback)
            if ecr.code_journal == CodeJournal.AN:
                return TypeEcriture.FACTURE
        return TypeEcriture.INCONNU

    # Paiement : débit > 0
    if ecr.debit > 0:
        # Banques et caisse : toujours paiement
        if ecr.code_journal in (CodeJournal.BMCE, CodeJournal.BMCI, CodeJournal.CAI):
            return TypeEcriture.PAIEMENT
        # OD : tout débit significatif est un paiement (LCN, effet, régularisation,
        # solde résiduel). Les "Rentree" insignifiantes ont déjà été filtrées plus haut.
        if ecr.code_journal == CodeJournal.OD:
            return TypeEcriture.PAIEMENT
        # AN avec débit : paiement reporté de l'exercice précédent.
        # On accepte ce cas systématiquement (le sens du mouvement prime sur le libellé,
        # qui peut être mal saisi : "EPAIM", "Fact" avec débit, etc.).
        if ecr.code_journal == CodeJournal.AN:
            return TypeEcriture.PAIEMENT
        # ACH avec débit : avoir (rare)
        if ecr.code_journal == CodeJournal.ACH:
            return TypeEcriture.AVOIR
        return TypeEcriture.INCONNU

    return TypeEcriture.INCONNU


# ─── Conversion en objet métier ────────────────────────────────────────────

def _deduire_date_livraison(date_facture: date) -> Optional[date]:
    """Heuristique fin-de-mois (D-011, norme cabinet).

    Quand une facture est datée du **dernier jour du mois**, le cabinet
    positionne systématiquement la livraison la veille (J-1). On reproduit
    cette convention pour éviter le report du délai au mois suivant.

    Pour toutes les autres dates, on retourne None : `date_livraison`
    retombera sur `date_facture` via le fallback du calculateur.
    """
    dernier_jour = calendar.monthrange(date_facture.year, date_facture.month)[1]
    if date_facture.day == dernier_jour:
        return date_facture - timedelta(days=1)
    return None


def vers_facture(ecr: EcritureBrute) -> Facture:
    """Convertit une EcritureBrute classifiée FACTURE en `Facture`."""
    return Facture(
        code_fournisseur=ecr.code_fournisseur,
        nom_fournisseur=ecr.nom_fournisseur,
        n_piece=ecr.n_piece,
        n_facture=extraire_n_facture(ecr.libelle),
        date_facture=ecr.date_ecriture,
        date_livraison=_deduire_date_livraison(ecr.date_ecriture),
        montant_ttc=ecr.credit,
        lettrage=ecr.lettrage,
        is_report=(ecr.code_journal == CodeJournal.AN),
        source=ecr,
    )


def vers_paiement(ecr: EcritureBrute) -> Paiement:
    """Convertit une EcritureBrute classifiée PAIEMENT en `Paiement`."""
    return Paiement(
        code_fournisseur=ecr.code_fournisseur,
        nom_fournisseur=ecr.nom_fournisseur,
        n_piece=ecr.n_piece,
        date_paiement=ecr.date_ecriture,
        montant=ecr.debit,
        moyen=detecter_moyen_paiement(ecr.libelle, ecr.code_journal),
        lettrage=ecr.lettrage,
        is_report=(ecr.code_journal == CodeJournal.AN),
        source=ecr,
    )
