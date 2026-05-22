"""Tests du CLI `ddp`."""

from datetime import date
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cli.main import build_parser, parser_trimestre  # noqa: E402


# ─── Parsing du code trimestre ─────────────────────────────────────────────

@pytest.mark.parametrize("code, attendu", [
    ("1T26", (1, date(2026, 1, 1), date(2026, 3, 31))),
    ("2T26", (2, date(2026, 4, 1), date(2026, 6, 30))),
    ("3T26", (3, date(2026, 7, 1), date(2026, 9, 30))),
    ("4T26", (4, date(2026, 10, 1), date(2026, 12, 31))),
    ("1T2025", (1, date(2025, 1, 1), date(2025, 3, 31))),
])
def test_parser_trimestre(code, attendu):
    assert parser_trimestre(code) == attendu


@pytest.mark.parametrize("code", ["", "X26", "5T26", "1Z26", "1T"])
def test_parser_trimestre_invalide(code):
    with pytest.raises((ValueError, IndexError)):
        parser_trimestre(code)


# ─── Argparse — vérifier que les sous-commandes existent ───────────────────

def test_argparse_run_complete():
    p = build_parser()
    args = p.parse_args([
        "run",
        "--client", "UEMA",
        "--trimestre", "1T26",
        "--gl", "foo.xlsx",
        "--template", "tpl.xlsx",
    ])
    assert args.cmd == "run"
    assert args.client == "UEMA"
    assert args.trimestre == "1T26"
    assert args.delai_defaut == 60  # défaut


def test_argparse_parse():
    p = build_parser()
    args = p.parse_args(["parse", "--gl", "foo.xlsx"])
    assert args.cmd == "parse"
    assert args.gl == Path("foo.xlsx")


def test_argparse_diagnose():
    p = build_parser()
    args = p.parse_args(["diagnose", "--gl", "foo.xlsx", "--base", "b.xlsx"])
    assert args.cmd == "diagnose"


def test_argparse_run_arguments_manquants():
    """Sans --client, --trimestre, --gl, --template, ça doit échouer."""
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["run"])


# ─── Test end-to-end ───────────────────────────────────────────────────────

GL_UEMA = Path(__file__).resolve().parents[1] / "samples" / "input" / "UEMA - GL FRS 2026.xlsx"
TEMPLATE = Path(__file__).resolve().parents[1] / "samples" / "input" / "Modèle Suivi Global.xlsx"
REF_SUIVI = Path(__file__).resolve().parents[1] / "samples" / "output_reference" / "Modèle Suivi Global DDP2026.xlsx"
REF_SIMPL = Path(__file__).resolve().parents[1] / "samples" / "output_reference" / "Simpl délais de paiements UEMA -  TR 01-2026.xlsx"


def test_cli_run_end_to_end(tmp_path, capsys):
    """Pipeline complet via CLI : génère les deux fichiers Excel."""
    from cli.main import main
    rc = main([
        "run",
        "--client", "UEMA",
        "--trimestre", "1T26",
        "--gl", str(GL_UEMA),
        "--template", str(TEMPLATE),
        "--base", str(REF_SUIVI),
        "--simpl-template", str(REF_SIMPL),
        "--n-if", "14367938",
        "--raison-sociale", "STE UEMA INDUSTRY",
        "--ca-n1", "23369748.49",
        "--activite", "1",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mizan — UEMA — 1T26" in out
    assert "Terminé" in out

    # Les deux fichiers doivent être créés
    assert (tmp_path / "Suivi Global DDP UEMA 1T26.xlsx").exists()
    assert (tmp_path / "Simpl DDP UEMA 1T26.xlsx").exists()


def test_cli_parse(capsys):
    from cli.main import main
    rc = main(["parse", "--gl", str(GL_UEMA)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1510 écritures" in out
    assert "177 fournisseurs" in out
    assert "AN" in out
    assert "ACH" in out


def test_cli_diagnose(capsys):
    from cli.main import main
    rc = main(["diagnose", "--gl", str(GL_UEMA), "--base", str(REF_SUIVI)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Écritures non classifiées" in out
    assert "Fournisseurs hors base" in out


def test_cli_trimestre_invalide(capsys):
    from cli.main import main
    rc = main([
        "run", "--client", "UEMA", "--trimestre", "INVALID",
        "--gl", str(GL_UEMA), "--template", str(TEMPLATE),
    ])
    assert rc == 2  # erreur de validation
