"""CLI principal — `mizan` (Déclaration Délais de Paiement).

Usage :
    mizan run    --client UEMA --trimestre 1T26 --gl PATH --template PATH --out DIR
    mizan parse  --gl PATH                                  # debug : juste parser
    mizan info   --gl PATH                                  # stats GL sans calcul
    mizan diagnose --gl PATH --base PATH                    # cas ambigus, hors-base

Le pipeline `run` enchaîne :
  1. Parser le GL Excel
  2. Charger la base fournisseurs
  3. Construire les lettrages
  4. Calculer les délais et statuts
  5. Générer Suivi Global + Simpl
  6. Afficher un résumé
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parser import parser_gl_liste  # noqa: E402
from lettrage import construire_lettrages  # noqa: E402
from compute import stats_delais_anormaux  # noqa: E402
from compute import (  # noqa: E402
    calculer_toutes_lignes,
    charger_base_fournisseurs,
    charger_corrections,
    construire_index,
)
from output import generer_simpl, generer_suivi_global  # noqa: E402
from quality import annoter_lignes, detecter_doublons, stats as stats_anomalies, TypeAnomalie  # noqa: E402
from models import LigneSuivi, StatutFacture  # noqa: E402


# ─── Mapping trimestre <-> dates ───────────────────────────────────────────

TRIMESTRES = {
    "1T": (1, 1, 3, 31),    # 01/01 → 31/03
    "2T": (4, 1, 6, 30),    # 01/04 → 30/06
    "3T": (7, 1, 9, 30),
    "4T": (10, 1, 12, 31),
}


def parser_trimestre(code: str) -> tuple[int, date, date]:
    """Convertit "1T26" en (trimestre, debut, fin)."""
    code = code.strip().upper()
    if len(code) < 4 or code[1] != "T":
        raise ValueError(f"Trimestre invalide : {code} — attendu '1T26', '2T26', etc.")
    tri = int(code[0])
    annee = int(code[2:])
    if annee < 100:
        annee += 2000
    if tri not in (1, 2, 3, 4):
        raise ValueError(f"Numéro de trimestre invalide : {tri}")
    m1, d1, m2, d2 = TRIMESTRES[f"{tri}T"]
    return tri, date(annee, m1, d1), date(annee, m2, d2)


# ─── Affichage console ─────────────────────────────────────────────────────

def banner(titre: str) -> None:
    bar = "─" * (len(titre) + 6)
    print(f"\n{bar}\n   {titre}\n{bar}")


def section(titre: str) -> None:
    print(f"\n▸ {titre}")


def tableau_stats(lignes: list[LigneSuivi]) -> None:
    """Affiche un tableau récapitulatif des statuts."""
    statuts = Counter(l.statut for l in lignes)
    total = len(lignes)
    print(f"\n  Total lignes : {total}\n")
    for s in StatutFacture:
        n = statuts.get(s, 0)
        if n == 0:
            continue
        pct = (n / total * 100) if total else 0
        print(f"    {s.value:40} {n:>5}   ({pct:>5.1f} %)")
    # Montant total par statut
    print()
    for s in StatutFacture:
        montants = [l.montant_ttc for l in lignes if l.statut == s]
        if not montants:
            continue
        total_mt = sum(montants, Decimal(0))
        print(f"    {s.value:40} {total_mt:>15,.2f} MAD")


# ─── Sous-commandes ────────────────────────────────────────────────────────

def cmd_run(args) -> int:
    t0 = time.time()
    banner(f"Mizan — {args.client} — {args.trimestre}")

    try:
        tri, debut, fin = parser_trimestre(args.trimestre)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    print(f"  Période : {debut.isoformat()} → {fin.isoformat()}")

    # 1) Charger la base fournisseurs
    section("Chargement de la base fournisseurs")
    base = charger_base_fournisseurs(args.base or args.template)
    print(f"  {len(base)} fournisseurs dans la base")
    stats_delais = stats_delais_anormaux()
    if stats_delais["atypiques"]:
        print(f"  ⚠ {len(stats_delais['atypiques'])} délai(s) non-standard(s) — à valider par le cabinet :")
        for code, (nom, d, proche) in stats_delais["atypiques"].items():
            print(f"     {code} {nom[:35]:35} : {d} j (proche du standard {proche} j)")

    # 2) Parser le GL
    section("Parsing du Grand Livre")
    ecritures = parser_gl_liste(args.gl)
    nb_frs_gl = len({e.code_fournisseur for e in ecritures})
    print(f"  {len(ecritures)} écritures · {nb_frs_gl} fournisseurs distincts")

    # 3) Corrections de date optionnelles (Phase 2 — D-006)
    corrections_idx = None
    if args.corrections:
        section("Chargement des corrections de date")
        corrections = charger_corrections(args.corrections)
        corrections_idx = construire_index(corrections)
        print(f"  {len(corrections)} corrections chargées")

    # 4) Lettrage
    section("Construction des lettrages")
    lettrages, inconnues, hors_base = construire_lettrages(
        ecritures,
        base_fournisseurs=base,
        delai_par_defaut_jours=args.delai_defaut,
        corrections_index=corrections_idx,
    )
    soldés = sum(1 for l in lettrages if l.lettre and l.est_solde)
    print(f"  {len(lettrages)} lettrages ({soldés} soldés) · "
          f"{len(inconnues)} écritures non classifiées · "
          f"{len(hors_base)} fournisseurs hors base")
    if hors_base and args.verbose:
        print(f"  Hors base : {', '.join(hors_base[:5])}{' …' if len(hors_base) > 5 else ''}")

    # 4) Calcul délais & statuts
    section("Calcul des délais")
    lignes = calculer_toutes_lignes(lettrages, debut_periode=debut, fin_periode=fin)
    print(f"  {len(lignes)} lignes de suivi générées")
    tableau_stats(lignes)

    # 4 bis) Détection des doublons et anomalies (Sprint 4 — qualité)
    section("Détection des anomalies")
    anomalies = detecter_doublons(lignes)
    cnt = stats_anomalies(anomalies)
    print(f"  {len(anomalies)} anomalies détectées :")
    print(f"    Doublons exacts        : {cnt[TypeAnomalie.DOUBLON_EXACT]}")
    print(f"    Doublons probables     : {cnt[TypeAnomalie.DOUBLON_PROBABLE]}")
    print(f"    Montants récurrents    : {cnt[TypeAnomalie.MONTANT_RECURRENT]}")
    lignes = annoter_lignes(lignes, anomalies)

    # 5) Génération des sorties
    section("Génération des fichiers")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    suivi_path = out_dir / f"Suivi Global DDP {args.client} {args.trimestre}.xlsx"
    generer_suivi_global(
        chemin_template=args.template,
        chemin_sortie=suivi_path,
        lignes=lignes,
        base_fournisseurs=base,
        client=args.client,
        exercice=debut.year,
    )
    print(f"  ✓ {suivi_path}")

    if args.simpl_template:
        simpl_path = out_dir / f"Simpl DDP {args.client} {args.trimestre}.xlsx"
        ca = Decimal(args.ca_n1) if args.ca_n1 else None
        generer_simpl(
            chemin_template=args.simpl_template,
            chemin_sortie=simpl_path,
            lignes=lignes,
            base_fournisseurs=base,
            n_if_client=args.n_if or "",
            raison_sociale=args.raison_sociale or args.client,
            periode_trimestre=tri,
            annee=debut.year,
            chiffre_affaires_n1=ca,
            activite_code=args.activite,
        )
        print(f"  ✓ {simpl_path}")
    else:
        print("  ⓘ Simpl non généré (--simpl-template absent)")

    print(f"\n✓ Terminé en {time.time() - t0:.1f} s")
    return 0


def cmd_parse(args) -> int:
    """Parse le GL et affiche les statistiques brutes."""
    banner(f"Parse GL — {Path(args.gl).name}")
    ecritures = parser_gl_liste(args.gl)
    nb_frs = len({e.code_fournisseur for e in ecritures})
    print(f"  {len(ecritures)} écritures · {nb_frs} fournisseurs")

    cj_count = Counter(e.code_journal.value for e in ecritures)
    print("\n  Codes journaux :")
    for cj, n in cj_count.most_common():
        print(f"    {cj:6} : {n:>5}")

    nb_lettrés = sum(1 for e in ecritures if e.lettrage)
    print(f"\n  Écritures lettrées : {nb_lettrés}")
    print(f"  Écritures non lettrées : {len(ecritures) - nb_lettrés}")

    total_debit  = sum(e.debit for e in ecritures)
    total_credit = sum(e.credit for e in ecritures)
    print(f"\n  Total débit  : {total_debit:>15,.2f} MAD")
    print(f"  Total crédit : {total_credit:>15,.2f} MAD")
    print(f"  Solde net    : {total_credit - total_debit:>15,.2f} MAD  (à payer)")
    return 0


def cmd_info(args) -> int:
    """Affiche les informations sur un GL sans rien calculer."""
    return cmd_parse(args)


def cmd_diagnose(args) -> int:
    """Affiche les cas ambigus et les fournisseurs hors base."""
    banner(f"Diagnostic — {Path(args.gl).name}")

    base = charger_base_fournisseurs(args.base) if args.base else {}
    ecritures = parser_gl_liste(args.gl)
    lettrages, inconnues, hors_base = construire_lettrages(ecritures, base_fournisseurs=base)

    section(f"Écritures non classifiées ({len(inconnues)})")
    if inconnues:
        for e in inconnues[:20]:
            print(f"  L{e.ligne_source:>4} | {e.code_journal.value:5} | "
                  f"D={e.debit:>8} | C={e.credit:>8} | {e.libelle[:60]}")
        if len(inconnues) > 20:
            print(f"  … et {len(inconnues) - 20} autres")

    section(f"Fournisseurs hors base ({len(hors_base)})")
    fournisseurs_par_code = {e.code_fournisseur: e.nom_fournisseur for e in ecritures}
    for code in hors_base[:30]:
        nom = fournisseurs_par_code.get(code, "?")
        print(f"  {code} · {nom}")
    if len(hors_base) > 30:
        print(f"  … et {len(hors_base) - 30} autres")

    section(f"Lettrages déséquilibrés ({sum(1 for l in lettrages if l.lettre and not l.est_solde)})")
    for l in lettrages:
        if l.lettre and not l.est_solde:
            print(f"  {l.fournisseur.nom:30} L={l.lettre}  écart={l.ecart:>10,.2f} MAD")

    return 0


# ─── Argparse ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mizan",
        description="Mizan — Automatisation de la Déclaration des Délais de Paiement (Nextor).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # run
    run = sub.add_parser("run", help="Pipeline complet : parse → lettrage → calcul → Excel")
    run.add_argument("--client",    required=True, help="Code client (ex: UEMA)")
    run.add_argument("--trimestre", required=True, help="Trimestre (ex: 1T26)")
    run.add_argument("--gl",        required=True, type=Path, help="Chemin du Grand Livre Sage (.xlsx)")
    run.add_argument("--template",  required=True, type=Path, help="Template Suivi Global vierge (.xlsx)")
    run.add_argument("--base",      type=Path, help="Référentiel fournisseurs (défaut : template)")
    run.add_argument("--corrections", type=Path,
                      help="Excel de corrections de date (Phase 2 — résout D-006)")
    run.add_argument("--simpl-template", type=Path, help="Template Simpl DGI (.xlsx)")
    run.add_argument("--out",       default="out", help="Dossier de sortie (défaut : ./out)")
    run.add_argument("--delai-defaut", type=int, default=60, help="Délai par défaut (60)")
    # Identification client (pour le Simpl)
    run.add_argument("--n-if",          help="N° IF du client (Simpl)")
    run.add_argument("--raison-sociale", help="Raison sociale du client (Simpl)")
    run.add_argument("--ca-n1",          help="Chiffre d'affaires N-1 du client (Simpl)")
    run.add_argument("--activite", type=int, help="Code activité (Simpl)")
    run.add_argument("--verbose", "-v", action="store_true", help="Sortie détaillée")
    run.set_defaults(func=cmd_run)

    # parse
    parse_p = sub.add_parser("parse", help="Parser un GL et afficher les statistiques")
    parse_p.add_argument("--gl", required=True, type=Path, help="Chemin du Grand Livre")
    parse_p.set_defaults(func=cmd_parse)

    # info (alias parse)
    info_p = sub.add_parser("info", help="Alias de parse")
    info_p.add_argument("--gl", required=True, type=Path)
    info_p.set_defaults(func=cmd_info)

    # diagnose
    diag = sub.add_parser("diagnose", help="Cas ambigus et fournisseurs hors base")
    diag.add_argument("--gl",   required=True, type=Path)
    diag.add_argument("--base", type=Path, help="Référentiel fournisseurs (.xlsx)")
    diag.set_defaults(func=cmd_diagnose)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
