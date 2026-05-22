"""Tests du chargement du Référentiel DGI Phase 2."""

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compute import charger_base_fournisseurs  # noqa: E402
from models import Fournisseur  # noqa: E402


REF_DGI    = Path(__file__).resolve().parents[1] / "samples" / "input" / "Référentiel DGI - Cabinet.xlsx"
REF_LEGACY = Path(__file__).resolve().parents[1] / "samples" / "output_reference" / "Modèle Suivi Global DDP2026.xlsx"


@pytest.fixture(scope="module")
def base_dgi():
    return charger_base_fournisseurs(REF_DGI)


@pytest.fixture(scope="module")
def base_legacy():
    return charger_base_fournisseurs(REF_LEGACY)


# ─── Format DGI (Phase 2) ──────────────────────────────────────────────────

def test_dgi_charge_109_fournisseurs(base_dgi):
    assert len(base_dgi) == 109


def test_dgi_fournisseurs_avec_if(base_dgi):
    """Au moins 30 fournisseurs doivent avoir un N° IF rempli."""
    nb = sum(1 for f in base_dgi.values() if f.n_if)
    assert nb >= 30


def test_dgi_aboucaid_partners_enrichi(base_dgi):
    """ABOUZAID PARTNERS (FRS0000587) doit avoir IF + ICE."""
    f = base_dgi.get("FRS0000587")
    assert f is not None
    assert f.nom == "ABOUZAID PARTNERS"
    assert f.delai_convenu_jours == 60
    assert f.n_if == "24840351"
    assert f.n_ice == "001971712000092"


def test_dgi_agadir_inox_enrichi(base_dgi):
    f = base_dgi.get("FRS0000013")
    assert f is not None
    assert f.n_if == "6902302"
    assert f.delai_convenu_jours == 120


def test_dgi_fournisseur_sans_if_garde_les_autres_champs(base_dgi):
    """Un fournisseur non-enrichi (sans IF) garde quand même nom + délai."""
    sans_if = [f for f in base_dgi.values() if not f.n_if]
    assert sans_if, "Au moins un fournisseur doit être non-enrichi"
    f = sans_if[0]
    assert f.code and f.nom
    assert f.delai_convenu_jours > 0
    assert f.n_ice is None


# ─── Backward compatibility (format legacy) ────────────────────────────────

def test_legacy_charge_correctement(base_legacy):
    """L'ancienne base Frs Permanente charge toujours sans erreur."""
    assert len(base_legacy) >= 100


def test_legacy_pas_de_champs_dgi(base_legacy):
    """Sur le format legacy, tous les champs DGI sont None."""
    for f in base_legacy.values():
        assert f.n_if is None
        assert f.n_ice is None
        assert f.adresse is None


# ─── Auto-détection d'onglet ───────────────────────────────────────────────

def test_auto_detection_format_dgi(base_dgi):
    """Avec l'onglet 'Référentiel DGI', le loader détecte le format enrichi."""
    f = next(f for f in base_dgi.values() if f.n_if)
    assert f.n_if is not None
    assert f.n_ice is not None


def test_auto_detection_format_legacy(base_legacy):
    """Avec l'onglet 'Base Frs Permanente', le loader fonctionne aussi."""
    assert all(isinstance(f, Fournisseur) for f in base_legacy.values())
