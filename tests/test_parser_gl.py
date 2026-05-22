"""Tests du parser GL Excel — fixés sur le fichier de référence UEMA 1T26."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parser import parser_gl_liste  # noqa: E402
from models import CodeJournal  # noqa: E402


GL_UEMA = Path(__file__).resolve().parents[1] / "samples" / "input" / "UEMA - GL FRS 2026.xlsx"


@pytest.fixture(scope="module")
def ecritures():
    return parser_gl_liste(GL_UEMA)


def test_nombre_ecritures(ecritures):
    """Le parser doit extraire exactement 1510 écritures du GL UEMA."""
    assert len(ecritures) == 1510


def test_nombre_fournisseurs(ecritures):
    """177 fournisseurs distincts dans le GL UEMA."""
    frs = {(e.code_fournisseur, e.nom_fournisseur) for e in ecritures}
    assert len(frs) == 177


def test_codes_journaux(ecritures):
    """Les 6 codes journaux observés doivent être présents."""
    cj = {e.code_journal for e in ecritures}
    assert cj == {CodeJournal.AN, CodeJournal.ACH, CodeJournal.BMCE,
                  CodeJournal.OD, CodeJournal.CAI, CodeJournal.BMCI}


def test_lettrages(ecritures):
    """Lettres A à H, un seul caractère."""
    lettres = {e.lettrage for e in ecritures if e.lettrage}
    assert lettres == {"A", "B", "C", "D", "E", "F", "G", "H"}


def test_a2cim_complet(ecritures):
    """A2CIM (FRS0000001) : 4 écritures, 2 lettrages A/B, montants exacts."""
    a2cim = [e for e in ecritures if e.code_fournisseur == "FRS0000001"]
    assert len(a2cim) == 4
    # Lettrage A : facture 2520 + paiement 2520 le 23/01
    fact_a = next(e for e in a2cim if e.lettrage == "A" and e.code_journal == CodeJournal.ACH)
    pay_a  = next(e for e in a2cim if e.lettrage == "A" and e.code_journal == CodeJournal.BMCE)
    assert fact_a.date_ecriture == date(2026, 1, 23)
    assert fact_a.credit == Decimal("2520")
    assert fact_a.libelle == "FN° 26FC0031 A2CIM"
    assert pay_a.date_ecriture == date(2026, 1, 23)
    assert pay_a.debit == Decimal("2520")


def test_abm_industrie_avec_an(ecritures):
    """ABM INDUSTRIE : 2 factures + 2 paiements (dont 1 AN), lettrage A soldé."""
    abm = [e for e in ecritures if e.code_fournisseur == "FRS0000003"]
    assert len(abm) == 4
    total_credit = sum(e.credit for e in abm)  # factures
    total_debit  = sum(e.debit  for e in abm)  # paiements
    assert total_credit == Decimal("63408")    # 336 + 63072
    assert total_debit  == Decimal("63408")    # 300 + 63108


def test_lignes_total_ignorees(ecritures):
    """Aucune écriture ne doit avoir un libellé contenant 'Total du tiers'."""
    for e in ecritures:
        assert "total du tiers" not in e.libelle.lower()


def test_codes_fournisseurs_normalises(ecritures):
    """Tous les codes fournisseurs commencent par FRS."""
    for e in ecritures:
        assert e.code_fournisseur.startswith("FRS")


def test_ecritures_non_nulles(ecritures):
    """Aucune écriture ne doit avoir débit ET crédit à zéro."""
    for e in ecritures:
        assert e.debit != 0 or e.credit != 0
