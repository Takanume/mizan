"""Tests du module OCR (Sprint 2b)."""

from datetime import date
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ocr import (  # noqa: E402
    TypeDocument,
    detecter_type,
    extraire_date_facture,
    extraire_dates,
    extraire_n_facture,
)
from ocr.extracteur_facture import _est_n_facture_valide  # noqa: E402


# ─── Détection du type de document ─────────────────────────────────────────

def test_detecter_facture():
    texte = "Facture F26/084\nDate de la facture : 16/03/2026\nUEMA INDUSTRY"
    assert detecter_type(texte) == TypeDocument.FACTURE


def test_detecter_avis_virement():
    texte = "Avis d'opération de virement instantané\nCompte rendu de votre ordre n°\nBANK OF AFRICA"
    assert detecter_type(texte) == TypeDocument.AVIS_VIR


def test_detecter_lettre_change():
    texte = "Ordre de paiement\nLettre de change\nN° TLM 0038937"
    assert detecter_type(texte) == TypeDocument.LCN


def test_detecter_inconnu():
    texte = "Du texte aléatoire sans mots-clés."
    assert detecter_type(texte) == TypeDocument.INCONNU


# ─── Extraction de dates ───────────────────────────────────────────────────

def test_extraire_dates_ddmmyyyy():
    """Le pattern dd/mm/yyyy doit être correctement extrait."""
    texte = "Émis le 16/03/2026 à Casablanca"
    dates = extraire_dates(texte)
    # On vérifie juste que la date est trouvée, pas le détail du contexte/priorité
    assert any(d == date(2026, 3, 16) for d, _, _ in dates)


def test_extraire_dates_iso():
    texte = "Enregistré le 2026/01/23 à 11:17"
    dates = extraire_dates(texte)
    assert any(d == date(2026, 1, 23) for d, _, _ in dates)


def test_extraire_dates_avec_tirets():
    texte = "Date : 23-01-2026"
    dates = extraire_dates(texte)
    assert any(d == date(2026, 1, 23) for d, _, _ in dates)


def test_extraire_dates_invalides_ignorees():
    """Les dates impossibles (jour > 31, mois > 12) sont ignorées."""
    texte = "Numéro 42/85/2026 réf 99/99/9999"
    dates = extraire_dates(texte)
    # Aucune date valide ne doit être extraite
    assert not dates


def test_extraire_date_facture_avec_ancre():
    texte = """Facture F26/084
Date de la facture :
16/03/2026
Objet : ..."""
    d, conf = extraire_date_facture(texte)
    assert d == date(2026, 3, 16)
    assert conf >= 0.85  # haute confiance via l'ancre


def test_extraire_date_facture_sans_ancre():
    """Sans mot-clé d'ancre, la confiance doit être faible."""
    texte = "Réf 12345\nMontant : 1000 MAD\n16/03/2026"
    d, conf = extraire_date_facture(texte)
    assert d == date(2026, 3, 16)
    assert conf <= 0.5


def test_extraire_date_facture_aucune():
    assert extraire_date_facture("Texte sans aucune date") == (None, 0.0)


# ─── Extraction n° facture ─────────────────────────────────────────────────

def test_extraire_n_facture_pprime():
    texte = "Facture F26/084\nDate de la facture : 16/03/2026"
    assert extraire_n_facture(texte) == "26/084"


def test_extraire_n_facture_avec_slash():
    texte = "Facture N° 25/043 PPRIME"
    assert extraire_n_facture(texte) == "25/043"


def test_extraire_n_facture_long():
    texte = "Facture numéro 2602080 EQUITAS\nDate 28/02/2026"
    assert extraire_n_facture(texte) == "2602080"


def test_extraire_n_facture_aucun():
    assert extraire_n_facture("Texte sans rien de pertinent") is None


# ─── Validation interne ────────────────────────────────────────────────────

def test_est_n_facture_valide():
    assert _est_n_facture_valide("26FC0031")
    assert _est_n_facture_valide("25/043")
    assert _est_n_facture_valide("F2025-001")


def test_est_n_facture_invalide():
    assert not _est_n_facture_valide("ABC")  # pas de chiffre
    assert not _est_n_facture_valide("12")   # trop court
    assert not _est_n_facture_valide("invoice")  # mot dictionnaire
    assert not _est_n_facture_valide("INVOICE")
    assert not _est_n_facture_valide("ure")


# ─── Test d'intégration (lourd — opt-in) ───────────────────────────────────

@pytest.mark.slow
def test_extraction_pprime_pdf():
    """Test sur le PDF PPRIME — confirme que l'OCR + extraction fonctionne en bout-en-bout.

    Ce test est lourd (~3-5 sec). Le lancer avec : pytest -m slow
    """
    from ocr import extraire_pdf
    pdf = Path(__file__).resolve().parents[1] / "samples" / "input" / "Sondage" / "PPRIME.pdf"
    if not pdf.exists():
        pytest.skip("PDF PPRIME absent")
    resultats = extraire_pdf(pdf, dpi=150)
    assert len(resultats) >= 1
    # Au moins une page doit être identifiée comme facture
    factures = [r for r in resultats if r.type_document == TypeDocument.FACTURE]
    assert factures
    r = factures[0]
    assert r.n_facture == "26/084"
    assert r.date_facture == date(2026, 3, 16)
    assert r.confiance >= 0.9
