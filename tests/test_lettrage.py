"""Tests du moteur de lettrage — fixés sur le GL UEMA 1T26."""

from decimal import Decimal
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parser import parser_gl_liste  # noqa: E402
from lettrage import (  # noqa: E402
    classifier_ecriture,
    construire_lettrages,
    detecter_moyen_paiement,
    extraire_n_facture,
)
from models import CodeJournal, MoyenPaiement, TypeEcriture  # noqa: E402


GL_UEMA = Path(__file__).resolve().parents[1] / "samples" / "input" / "UEMA - GL FRS 2026.xlsx"


# ─── Tests unitaires des fonctions ─────────────────────────────────────────

@pytest.mark.parametrize("libelle, attendu", [
    ("FN° 26FC0031 A2CIM",         "26FC0031"),
    ("FN°03764/2026 VITECMA",      "03764/2026"),
    ("FN° 0202522423 AGADIR INOX", "0202522423"),
    ("FN N°03/2026 S.BOUBAD",      "03/2026"),
    ("F°632686283 SRM-SM",         "632686283"),
    ("Fact ABM INDUSTRIE",          None),
    ("Vrt/A2CIM",                   None),
])
def test_extraire_n_facture(libelle, attendu):
    assert extraire_n_facture(libelle) == attendu


@pytest.mark.parametrize("libelle, cj, attendu", [
    ("Vrt/A2CIM",                CodeJournal.BMCE, MoyenPaiement.VIREMENT),
    ("VIREMENT ABM INDUSTRIE",   CodeJournal.AN,   MoyenPaiement.VIREMENT),
    ("CHQ N°6172531 / CASA",     CodeJournal.AN,   MoyenPaiement.CHEQUE),
    ("LCN° 0038932 CIQS",        CodeJournal.OD,   MoyenPaiement.LCN),
    ("LC N°0038929 TECHNIQUE",   CodeJournal.OD,   MoyenPaiement.LCN),
    ("ESPECE FN°2603004 AMAL",   CodeJournal.CAI,  MoyenPaiement.ESPECES),
    ("RGL AUTOROUTES DU MAROC",  CodeJournal.AN,   MoyenPaiement.AUTRE),
])
def test_detecter_moyen_paiement(libelle, cj, attendu):
    assert detecter_moyen_paiement(libelle, cj) == attendu


# ─── Tests sur GL UEMA ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def lettrages_uema():
    ecritures = parser_gl_liste(GL_UEMA)
    lettrages, inconnues, _ = construire_lettrages(ecritures)
    return lettrages, inconnues


def test_nombre_lettrages(lettrages_uema):
    """316 lettrages construits sur le GL UEMA."""
    lettrages, _ = lettrages_uema
    assert len(lettrages) == 316


def test_inconnues_uniquement_rentree(lettrages_uema):
    """Les écritures inconnues restantes sont uniquement les 'Rentree Créance' D-005."""
    _, inconnues = lettrages_uema
    assert len(inconnues) == 7
    for e in inconnues:
        assert e.code_journal == CodeJournal.OD
        assert "rentree" in e.libelle.lower() or "rentréé" in e.libelle.lower()
        assert max(e.debit, e.credit) < Decimal("1")


def test_lettrages_soldés_majoritaires(lettrages_uema):
    """Au moins 95% des lettrages avec lettre doivent être soldés."""
    lettrages, _ = lettrages_uema
    lettrés = [l for l in lettrages if l.lettre]
    soldés = [l for l in lettrés if l.est_solde]
    ratio = len(soldés) / len(lettrés)
    assert ratio >= 0.95, f"Seulement {ratio:.1%} des lettrages soldés"


def test_a2cim_lettrages_soldés(lettrages_uema):
    """A2CIM doit avoir 2 lettrages (A et B) parfaitement soldés."""
    lettrages, _ = lettrages_uema
    a2cim = [l for l in lettrages if l.fournisseur.code == "FRS0000001"]
    assert len(a2cim) == 2
    for l in a2cim:
        assert l.est_solde
        assert len(l.factures) == 1
        assert len(l.paiements) == 1


def test_abm_industrie_lettrage_complet(lettrages_uema):
    """ABM INDUSTRIE : lettrage A avec 2 factures + 2 paiements (1 AN, 1 BMCE)."""
    lettrages, _ = lettrages_uema
    abm = [l for l in lettrages if l.fournisseur.code == "FRS0000003"]
    assert len(abm) == 1
    l = abm[0]
    assert l.lettre == "A"
    assert len(l.factures) == 2
    assert len(l.paiements) == 2
    assert l.total_factures == Decimal("63408")
    assert l.total_paiements == Decimal("63408")
    assert l.est_solde


def test_frontex_lettrage_4_ecritures(lettrages_uema):
    """FRONTEX : lettrage A avec 1 facture + 3 paiements (AN + AN + OD)."""
    lettrages, _ = lettrages_uema
    frontex = [l for l in lettrages if "FRONTEX" in l.fournisseur.nom.upper()]
    assert frontex, "FRONTEX manquant"
    l = frontex[0]
    assert len(l.factures) == 1
    assert len(l.paiements) == 3
    # somme des paiements = 18245 + 18245 + 7298 = 43788 = facture
    assert l.total_paiements == Decimal("43788")
    assert l.est_solde


def test_fnp_non_vide(lettrages_uema):
    """Il doit y avoir des FNP (lettrages sans paiement) — c'est l'objet de la déclaration."""
    lettrages, _ = lettrages_uema
    fnp = [l for l in lettrages if l.est_non_paye]
    assert len(fnp) >= 70
    assert sum(l.total_factures for l in fnp) > Decimal("1000000")


def test_classifier_facture_ach():
    """Classification d'une écriture ACH avec crédit + libellé FN° → FACTURE."""
    from models import EcritureBrute
    from datetime import date
    ecr = EcritureBrute(
        ligne_source=1, code_fournisseur="FRS0000001", nom_fournisseur="A2CIM",
        date_ecriture=date(2026, 1, 23), code_journal=CodeJournal.ACH,
        n_piece="37", libelle="FN° 26FC0031 A2CIM", lettrage="A",
        debit=Decimal(0), credit=Decimal("2520"), solde_progressif=None,
    )
    assert classifier_ecriture(ecr) == TypeEcriture.FACTURE


def test_classifier_paiement_bmce():
    """Classification d'une écriture BMCE avec débit → PAIEMENT."""
    from models import EcritureBrute
    from datetime import date
    ecr = EcritureBrute(
        ligne_source=2, code_fournisseur="FRS0000001", nom_fournisseur="A2CIM",
        date_ecriture=date(2026, 1, 23), code_journal=CodeJournal.BMCE,
        n_piece="196", libelle="Vrt/A2CIM", lettrage="A",
        debit=Decimal("2520"), credit=Decimal(0), solde_progressif=None,
    )
    assert classifier_ecriture(ecr) == TypeEcriture.PAIEMENT


def test_classifier_od_insignifiante():
    """OD 'Rentree' < 1 MAD → INCONNU (D-005)."""
    from models import EcritureBrute
    from datetime import date
    ecr = EcritureBrute(
        ligne_source=581, code_fournisseur="FRS0000123", nom_fournisseur="GOFM",
        date_ecriture=date(2026, 2, 25), code_journal=CodeJournal.OD,
        n_piece="540", libelle="Rentree Créance / GOFM", lettrage=None,
        debit=Decimal("0.01"), credit=Decimal(0), solde_progressif=None,
    )
    assert classifier_ecriture(ecr) == TypeEcriture.INCONNU
