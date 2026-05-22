"""Parser du Grand Livre fournisseurs Sage (export Excel).

Convertit un fichier Excel `UEMA - GL FRS 2026.xlsx` en flux d'objets
`EcritureBrute` interprétables par le moteur de lettrage.

Hypothèses (validées sur UEMA 1T26) :
  - Le fichier est un export Sage 100cloud, en-têtes de la page 1 sur les lignes 1-8.
  - Les blocs fournisseurs commencent par une ligne `FRSxxxxxxx <NOM>` (code col 1, nom col 4 ou 3).
  - Les écritures occupent les colonnes 1, 2, 3, 6, 9, 13, 15, 18 (cf. docs/domain.md §1).
  - Les lignes `Total du tiers` clôturent chaque bloc et sont ignorées.
  - Les en-têtes répétés (multi-page) sont détectés et sautés.

Voir `docs/domain.md` pour les détails sémantiques et `docs/decisions.md` pour
les choix de classification.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

import openpyxl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import CodeJournal, EcritureBrute  # noqa: E402


# Indices de colonnes (1-based) — cf. docs/domain.md §1
COL_DATE     = 1
COL_CJ       = 2
COL_N_PIECE  = 3
COL_LIBELLE  = 6
COL_LETTRAGE = 9
COL_DEBIT    = 13
COL_CREDIT   = 15
COL_SOLDE    = 18

# Détection des blocs fournisseurs
RE_CODE_FOURNISSEUR = re.compile(r"^FRS\d+$")

# Lignes à ignorer (peu importe la position dans le fichier)
LIBELLES_IGNORES = {
    "total du tiers",  # clôture de bloc
}

# En-têtes répétés sur les pages suivantes du PDF/export (à filtrer)
LIBELLES_ENTETE = {"libellé écriture", "date", "n° pièce"}


# ─── Conversion utilitaires ────────────────────────────────────────────────

def _to_date(value) -> Optional[date]:
    """Convertit un datetime openpyxl en date, ou None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _to_decimal(value) -> Decimal:
    """Convertit un montant Excel en Decimal (0 si vide)."""
    if value is None or value == "":
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_code_journal(value) -> Optional[CodeJournal]:
    """Convertit le contenu de la cellule Cj en enum, ou None si inconnu."""
    if not value:
        return None
    s = str(value).strip().upper()
    try:
        return CodeJournal(s)
    except ValueError:
        return None


def _normaliser_lettrage(value) -> Optional[str]:
    """Garde uniquement une lettre majuscule A-Z, sinon None."""
    if not value:
        return None
    s = str(value).strip().upper()
    if len(s) == 1 and s.isalpha():
        return s
    return None


# ─── Parser principal ──────────────────────────────────────────────────────

def parser_gl(chemin: Path | str) -> Iterator[EcritureBrute]:
    """Parcourt un export Excel du GL Sage et émet des `EcritureBrute`.

    Utilisation :
        for ecr in parser_gl("UEMA - GL FRS 2026.xlsx"):
            print(ecr.code_fournisseur, ecr.libelle, ecr.debit, ecr.credit)
    """
    chemin = Path(chemin)
    wb = openpyxl.load_workbook(chemin, data_only=True, read_only=True)
    ws = wb.active

    code_frs_courant: Optional[str] = None
    nom_frs_courant: Optional[str] = None

    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        # row peut être plus court que 18 si l'export est tronqué
        c1  = row[COL_DATE - 1]    if len(row) >= COL_DATE     else None
        c2  = row[COL_CJ - 1]      if len(row) >= COL_CJ       else None
        c3  = row[COL_N_PIECE - 1] if len(row) >= COL_N_PIECE  else None
        c6  = row[COL_LIBELLE - 1] if len(row) >= COL_LIBELLE  else None
        c9  = row[COL_LETTRAGE - 1]if len(row) >= COL_LETTRAGE else None
        c13 = row[COL_DEBIT - 1]   if len(row) >= COL_DEBIT    else None
        c15 = row[COL_CREDIT - 1]  if len(row) >= COL_CREDIT   else None
        c18 = row[COL_SOLDE - 1]   if len(row) >= COL_SOLDE    else None

        # 1) Ligne d'en-tête de bloc fournisseur
        if isinstance(c1, str) and RE_CODE_FOURNISSEUR.match(c1.strip()):
            code_frs_courant = c1.strip()
            # Le nom est tantôt en col 4, tantôt en col 3 selon les exports.
            nom_brut = row[3] if len(row) >= 4 else None
            if not nom_brut:
                nom_brut = c3
            nom_frs_courant = str(nom_brut).strip() if nom_brut else ""
            continue

        # 2) Lignes administratives / d'en-tête / vides
        libelle_norm = str(c6).strip().lower() if c6 else ""
        if libelle_norm in LIBELLES_IGNORES or libelle_norm in LIBELLES_ENTETE:
            continue

        # 3) On exige une date valide et un code journal valide
        d = _to_date(c1)
        cj = _to_code_journal(c2)
        if d is None or cj is None:
            continue

        # 4) Sécurité : on doit être dans un bloc fournisseur
        if code_frs_courant is None or nom_frs_courant is None:
            continue

        debit  = _to_decimal(c13)
        credit = _to_decimal(c15)
        if debit == 0 and credit == 0:
            # Ligne sans mouvement → on saute
            continue

        yield EcritureBrute(
            ligne_source=i,
            code_fournisseur=code_frs_courant,
            nom_fournisseur=nom_frs_courant,
            date_ecriture=d,
            code_journal=cj,
            n_piece=str(c3).strip() if c3 is not None else "",
            libelle=str(c6).strip() if c6 else "",
            lettrage=_normaliser_lettrage(c9),
            debit=debit,
            credit=credit,
            solde_progressif=_to_decimal(c18) if c18 is not None else None,
        )

    wb.close()


def parser_gl_liste(chemin: Path | str) -> list[EcritureBrute]:
    """Version eager qui retourne directement une liste (pour les tests)."""
    return list(parser_gl(chemin))
