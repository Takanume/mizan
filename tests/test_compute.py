"""Tests du moteur de calcul des délais."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parser import parser_gl_liste  # noqa: E402
from lettrage import construire_lettrages  # noqa: E402
from compute import (  # noqa: E402
    calculer_date_echeance,
    calculer_toutes_lignes,
    charger_base_fournisseurs,
    determiner_statut,
    imputer_fifo,
    tolerance,
)
from compute.delais import Imputation  # noqa: E402
from models import (  # noqa: E402
    CodeJournal,
    EcritureBrute,
    Facture,
    Fournisseur,
    MoyenPaiement,
    Paiement,
    StatutFacture,
)


GL_UEMA = Path(__file__).resolve().parents[1] / "samples" / "input" / "UEMA - GL FRS 2026.xlsx"
REF_OUTPUT = Path(__file__).resolve().parents[1] / "samples" / "output_reference" / "Modèle Suivi Global DDP2026.xlsx"


# ─── Tests unitaires ───────────────────────────────────────────────────────

def test_tolerance_petit_montant():
    """Pour une petite facture, le seuil absolu (1 MAD) prime."""
    assert tolerance(Decimal("100")) == Decimal("1")


def test_tolerance_grand_montant():
    """Pour une grosse facture, le seuil relatif (0,5 %) prime."""
    assert tolerance(Decimal("100000")) == Decimal("500.000")


def test_echeance_60j():
    """Échéance = date facture + délai − 1 (J1, D-009 révisée 2026-05-22)."""
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    assert calculer_date_echeance(f, 60) == date(2026, 3, 1)


def test_echeance_120j():
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    assert calculer_date_echeance(f, 120) == date(2026, 4, 30)


def test_imputation_simple():
    """1 facture + 1 paiement de même montant."""
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    p = _pay(date(2026, 1, 15), Decimal("1000"))
    imp = imputer_fifo([f], [p])[f.n_piece]
    assert imp.montant_impute == Decimal("1000")
    assert imp.date_paiement_effectif == date(2026, 1, 15)
    assert len(imp.paiements_imputes) == 1


def test_imputation_partielle():
    """1 facture + paiements partiels — date = dernier paiement nécessaire."""
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    p1 = _pay(date(2026, 1, 15), Decimal("400"))
    p2 = _pay(date(2026, 2, 1),  Decimal("600"))
    imp = imputer_fifo([f], [p1, p2])[f.n_piece]
    assert imp.montant_impute == Decimal("1000")
    assert imp.date_paiement_effectif == date(2026, 2, 1)


def test_imputation_groupee():
    """1 paiement règle 2 factures par FIFO."""
    f1 = _fact(date(2026, 1, 5), Decimal("400"), n_piece="1")
    f2 = _fact(date(2026, 1, 8), Decimal("600"), n_piece="2")
    p  = _pay(date(2026, 1, 20), Decimal("1000"))
    imps = imputer_fifo([f1, f2], [p])
    assert imps["1"].montant_impute == Decimal("400")
    assert imps["2"].montant_impute == Decimal("600")
    # Les deux ont été payées par le même paiement → même date
    assert imps["1"].date_paiement_effectif == date(2026, 1, 20)
    assert imps["2"].date_paiement_effectif == date(2026, 1, 20)


def test_statut_ok_ras():
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    imp = Imputation(
        montant_impute=Decimal("1000"),
        date_paiement_effectif=date(2026, 2, 15),
        paiements_imputes=[_pay(date(2026, 2, 15), Decimal("1000"))],
    )
    statut, jours = determiner_statut(f, imp, date(2026, 3, 2))  # échéance future
    assert statut == StatutFacture.OK_RAS
    assert jours == -15


def test_statut_retard():
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    imp = Imputation(
        montant_impute=Decimal("1000"),
        date_paiement_effectif=date(2026, 4, 1),
        paiements_imputes=[_pay(date(2026, 4, 1), Decimal("1000"))],
    )
    statut, jours = determiner_statut(f, imp, date(2026, 3, 2))
    assert statut == StatutFacture.RETARD
    assert jours == 30


def test_statut_fnp():
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    imp = Imputation(montant_impute=Decimal("0"), date_paiement_effectif=None, paiements_imputes=[])
    statut, jours = determiner_statut(f, imp, date(2026, 3, 2))
    assert statut == StatutFacture.NON_PAYE
    assert jours is None


def test_statut_tolerance_absorbee():
    """Écart 0,50 MAD sur facture 1000 → tolérance 5 MAD → OK_RAS."""
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    imp = Imputation(
        montant_impute=Decimal("999.50"),
        date_paiement_effectif=date(2026, 2, 15),
        paiements_imputes=[_pay(date(2026, 2, 15), Decimal("999.50"))],
    )
    statut, jours = determiner_statut(f, imp, date(2026, 3, 2))
    assert statut == StatutFacture.OK_RAS  # écart absorbé par tolérance


def test_statut_partiel():
    """Écart 100 MAD sur facture 1000 → > tolérance → PARTIEL."""
    f = _fact(date(2026, 1, 1), Decimal("1000"))
    imp = Imputation(
        montant_impute=Decimal("900"),
        date_paiement_effectif=date(2026, 2, 15),
        paiements_imputes=[_pay(date(2026, 2, 15), Decimal("900"))],
    )
    statut, _ = determiner_statut(f, imp, date(2026, 3, 2))
    assert statut == StatutFacture.PARTIEL


# ─── Tests intégration sur UEMA ────────────────────────────────────────────

@pytest.fixture(scope="module")
def lignes_uema():
    base = charger_base_fournisseurs(REF_OUTPUT)
    ecritures = parser_gl_liste(GL_UEMA)
    lettrages, _, _ = construire_lettrages(ecritures, base_fournisseurs=base)
    return calculer_toutes_lignes(lettrages, debut_periode=date(2026, 1, 1))


def test_uema_a2cim_ok_ras(lignes_uema):
    """A2CIM : 2 factures payées en avance → OK RAS."""
    a2cim = [l for l in lignes_uema if l.code_fournisseur == "FRS0000001"]
    assert len(a2cim) == 2
    for l in a2cim:
        assert l.statut == StatutFacture.OK_RAS


def test_uema_abm_industrie_retard(lignes_uema):
    """ABM INDUSTRIE : factures de début janvier, payées 20/04 → retard."""
    abm = [l for l in lignes_uema if l.code_fournisseur == "FRS0000003"]
    assert len(abm) == 2
    for l in abm:
        # Convention J1 : échéance = 01/01 + 60 − 1 = 01/03 ; paiement 20/04 → +50j
        assert l.statut == StatutFacture.RETARD
        assert l.jours_retard == 50


def test_uema_fnp_non_vides(lignes_uema):
    """Il doit y avoir des FNP dans le résultat."""
    fnp = [l for l in lignes_uema if l.statut == StatutFacture.NON_PAYE]
    assert len(fnp) > 100


def test_uema_volume_dans_lordre(lignes_uema):
    """Volume du résultat dans une fourchette acceptable (cible 774)."""
    assert 700 <= len(lignes_uema) <= 1100  # marge d'erreur due aux dates AN (D-006)


# ─── Helpers ───────────────────────────────────────────────────────────────

def _fact(d: date, montant: Decimal, n_piece: str = "1") -> Facture:
    ecr = EcritureBrute(
        ligne_source=0, code_fournisseur="FRS0000099", nom_fournisseur="TEST",
        date_ecriture=d, code_journal=CodeJournal.ACH, n_piece=n_piece,
        libelle="FN° " + n_piece, lettrage="A",
        debit=Decimal(0), credit=montant, solde_progressif=None,
    )
    return Facture(
        code_fournisseur="FRS0000099", nom_fournisseur="TEST",
        n_piece=n_piece, n_facture=n_piece,
        date_facture=d, date_livraison=None, montant_ttc=montant,
        lettrage="A", is_report=False, source=ecr,
    )


def _pay(d: date, montant: Decimal, n_piece: str = "P1") -> Paiement:
    ecr = EcritureBrute(
        ligne_source=0, code_fournisseur="FRS0000099", nom_fournisseur="TEST",
        date_ecriture=d, code_journal=CodeJournal.BMCE, n_piece=n_piece,
        libelle="Vrt", lettrage="A",
        debit=montant, credit=Decimal(0), solde_progressif=None,
    )
    return Paiement(
        code_fournisseur="FRS0000099", nom_fournisseur="TEST",
        n_piece=n_piece, date_paiement=d, montant=montant,
        moyen=MoyenPaiement.VIREMENT, lettrage="A", is_report=False, source=ecr,
    )
