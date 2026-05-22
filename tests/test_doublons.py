"""Tests Sprint 4 — détection automatique des doublons."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quality import Anomalie, TypeAnomalie, annoter_lignes, detecter_doublons, stats  # noqa: E402
from models import LigneSuivi, StatutFacture  # noqa: E402


def _ligne(n_fact, fournisseur, montant, d, lettrage=None):
    return LigneSuivi(
        n_facture=n_fact,
        date_livraison=d,
        date_facture=d,
        fournisseur=fournisseur,
        montant_ttc=Decimal(str(montant)),
        delai_convenu_jours=60,
        date_echeance=date(d.year, d.month, d.day),
        jours_retard=None,
        statut=StatutFacture.NON_PAYE,
        date_paiement_effectif=None,
        observations=None,
        code_fournisseur="FRS_X",
        lettrage=lettrage,
    )


# ─── Doublons exacts ──────────────────────────────────────────────────────

def test_doublon_exact_detecte():
    """Deux lignes avec même n° facture + montant → doublon exact."""
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 5)),  # même n° + montant
    ]
    anomalies = detecter_doublons(lignes)
    assert len(anomalies) == 1
    assert anomalies[0].type == TypeAnomalie.DOUBLON_EXACT
    assert anomalies[0].indices_lignes == (0, 1)


def test_doublons_exacts_differents_fournisseurs():
    """Même n° chez deux fournisseurs différents → pas un doublon."""
    lignes = [
        _ligne("F001", "PPRIME",   1000, date(2026, 1, 1)),
        _ligne("F001", "AUTRE",    1000, date(2026, 1, 1)),
    ]
    anomalies = detecter_doublons(lignes)
    assert len(anomalies) == 0


# ─── Doublons probables ────────────────────────────────────────────────────

def test_doublon_probable_dates_proches():
    """Mêmes fournisseur + montant + dates < 7j d'écart → doublon probable."""
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F002", "PPRIME", 1000, date(2026, 1, 5)),  # n° différent, montant identique
    ]
    anomalies = detecter_doublons(lignes)
    assert len(anomalies) == 1
    assert anomalies[0].type == TypeAnomalie.DOUBLON_PROBABLE


def test_pas_de_doublon_si_dates_eloignees():
    """Même montant mais dates éloignées (> 7j) → pas doublon probable."""
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F002", "PPRIME", 1000, date(2026, 2, 15)),  # +45j
    ]
    anomalies = detecter_doublons(lignes)
    # Doit être détecté en "montant récurrent" (non lettré), pas "doublon probable"
    assert all(a.type != TypeAnomalie.DOUBLON_PROBABLE for a in anomalies)


def test_doublon_exact_exclu_de_probable():
    """Un doublon exact ne doit pas être doublonné en 'probable'."""
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 2)),
    ]
    anomalies = detecter_doublons(lignes)
    assert len(anomalies) == 1
    assert anomalies[0].type == TypeAnomalie.DOUBLON_EXACT


# ─── Montants récurrents ───────────────────────────────────────────────────

def test_montant_recurrent_non_lettre():
    """Plusieurs factures même montant, non lettrées, dates éloignées."""
    lignes = [
        _ligne("F001", "MAROC TEL", 500, date(2026, 1, 15), lettrage=None),
        _ligne("F002", "MAROC TEL", 500, date(2026, 2, 15), lettrage=None),
        _ligne("F003", "MAROC TEL", 500, date(2026, 3, 15), lettrage=None),
    ]
    anomalies = detecter_doublons(lignes)
    recurrents = [a for a in anomalies if a.type == TypeAnomalie.MONTANT_RECURRENT]
    assert len(recurrents) == 1
    assert len(recurrents[0].indices_lignes) == 3


def test_lettrees_pas_signalees_comme_recurrentes():
    """Les factures lettrées ne sont pas signalées comme récurrentes."""
    lignes = [
        _ligne("F001", "MAROC TEL", 500, date(2026, 1, 15), lettrage="A"),
        _ligne("F002", "MAROC TEL", 500, date(2026, 2, 15), lettrage="B"),
    ]
    anomalies = detecter_doublons(lignes)
    assert all(a.type != TypeAnomalie.MONTANT_RECURRENT for a in anomalies)


# ─── Annotation des lignes ─────────────────────────────────────────────────

def test_annotation_ajoute_observation():
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F002", "PPRIME", 1000, date(2026, 1, 3)),
    ]
    anomalies = detecter_doublons(lignes)
    annotees = annoter_lignes(lignes, anomalies)
    assert all(l.observations is not None for l in annotees)
    assert "doublon" in annotees[0].observations.lower()


def test_annotation_preserve_obs_existantes():
    """Si une ligne a déjà une observation (ex: ⚠️ AN), on la préserve."""
    l1 = _ligne("F001", "PPRIME", 1000, date(2026, 1, 1))
    l1_existant = LigneSuivi(**{**l1.__dict__, "observations": "⚠️ AN"})
    l2 = _ligne("F002", "PPRIME", 1000, date(2026, 1, 3))
    lignes = [l1_existant, l2]
    anomalies = detecter_doublons(lignes)
    annotees = annoter_lignes(lignes, anomalies)
    assert "⚠️ AN" in annotees[0].observations
    assert "doublon" in annotees[0].observations.lower()


# ─── Stats ─────────────────────────────────────────────────────────────────

def test_stats():
    lignes = [
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 1)),
        _ligne("F001", "PPRIME", 1000, date(2026, 1, 2)),  # exact
        _ligne("F002", "AUTRE",  500,  date(2026, 1, 1)),
        _ligne("F003", "AUTRE",  500,  date(2026, 1, 3)),  # probable
    ]
    anomalies = detecter_doublons(lignes)
    s = stats(anomalies)
    assert s[TypeAnomalie.DOUBLON_EXACT] == 1
    assert s[TypeAnomalie.DOUBLON_PROBABLE] == 1


# ─── Intégration UEMA ──────────────────────────────────────────────────────

def test_uema_anomalies_detectees():
    """Sur UEMA 1T26, on doit trouver au moins quelques anomalies."""
    from parser import parser_gl_liste
    from lettrage import construire_lettrages
    from compute import calculer_toutes_lignes, charger_base_fournisseurs

    ROOT = Path(__file__).resolve().parents[1]
    base = charger_base_fournisseurs(
        ROOT / "samples" / "input" / "Référentiel DGI - Cabinet.xlsx"
    )
    ecritures = parser_gl_liste(ROOT / "samples" / "input" / "UEMA - GL FRS 2026.xlsx")
    lettrages, _, _ = construire_lettrages(ecritures, base_fournisseurs=base)
    lignes = calculer_toutes_lignes(lettrages, debut_periode=date(2026, 1, 1))

    anomalies = detecter_doublons(lignes)
    assert len(anomalies) > 0
    # Au moins quelques doublons probables (vu chez ABOUZAID, CHAHIR INOX, etc.)
    probables = [a for a in anomalies if a.type == TypeAnomalie.DOUBLON_PROBABLE]
    assert len(probables) >= 5
