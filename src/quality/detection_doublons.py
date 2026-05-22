"""Détection automatique de doublons et anomalies (Phase 2 Sprint 4).

Trois types d'anomalies signalées au cabinet :

1. **Doublon exact** — deux lignes du Suivi avec :
     même fournisseur ET même n° facture ET même montant
   → saisie en double dans le système comptable, à corriger côté Sage

2. **Doublon probable** — deux lignes du Suivi avec :
     même fournisseur ET même montant TTC ET dates proches (±7 jours)
   → possible saisie en double avec orthographe différente du n°

3. **Montants récurrents non lettrés** — N+ lignes avec :
     même fournisseur ET même montant ET aucune lettrage Sage
   → cas Maroc Telecom (factures mensuelles identiques) → ambiguïté
     facture-paiement, à vérifier manuellement

Le détecteur retourne une liste d'`Anomalie`. Chaque anomalie pointe vers
1 à N lignes du Suivi et porte une description en français.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Iterable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import LigneSuivi  # noqa: E402


# ─── Modèle d'anomalie ─────────────────────────────────────────────────────

class TypeAnomalie(str, Enum):
    DOUBLON_EXACT      = "doublon_exact"
    DOUBLON_PROBABLE   = "doublon_probable"
    MONTANT_RECURRENT  = "montant_recurrent"


@dataclass(frozen=True)
class Anomalie:
    type: TypeAnomalie
    description: str                     # phrase humaine
    fournisseur: str                     # nom du fournisseur concerné
    # Indices (0-based) des lignes concernées dans la liste passée en entrée
    indices_lignes: tuple[int, ...]


# ─── Détecteur principal ──────────────────────────────────────────────────

PROXIMITE_DATE_JOURS = 7   # tolérance pour "doublon probable"


def detecter_doublons(
    lignes: list[LigneSuivi],
    proximite_jours: int = PROXIMITE_DATE_JOURS,
) -> list[Anomalie]:
    """Détecte 3 types d'anomalies dans une liste de LigneSuivi.

    Retourne les anomalies triées par type puis par fournisseur.
    """
    anomalies: list[Anomalie] = []

    # Indexer les lignes par fournisseur pour limiter les comparaisons
    par_fournisseur: dict[str, list[tuple[int, LigneSuivi]]] = defaultdict(list)
    for i, l in enumerate(lignes):
        par_fournisseur[l.fournisseur].append((i, l))

    for fournisseur, items in par_fournisseur.items():
        if len(items) < 2:
            continue
        anomalies.extend(_detecter_par_fournisseur(fournisseur, items, proximite_jours))

    # Tri stable : type puis fournisseur
    anomalies.sort(key=lambda a: (a.type.value, a.fournisseur))
    return anomalies


def _detecter_par_fournisseur(
    fournisseur: str,
    items: list[tuple[int, LigneSuivi]],
    proximite_jours: int,
) -> list[Anomalie]:
    """Détecte les anomalies pour un seul fournisseur."""
    out: list[Anomalie] = []

    # 1) Doublons exacts par (n_facture, montant)
    par_cle_exacte: dict[tuple[str, Decimal], list[int]] = defaultdict(list)
    for idx, l in items:
        cle = ((l.n_facture or "").strip().upper(), l.montant_ttc)
        if cle[0]:
            par_cle_exacte[cle].append(idx)
    for (n_fact, montant), indices in par_cle_exacte.items():
        if len(indices) >= 2:
            out.append(Anomalie(
                type=TypeAnomalie.DOUBLON_EXACT,
                description=(
                    f"{len(indices)} lignes identiques : facture {n_fact} "
                    f"montant {montant:,.2f} MAD chez {fournisseur}"
                ),
                fournisseur=fournisseur,
                indices_lignes=tuple(indices),
            ))

    # 2) Doublons probables par montant + proximité de date
    #    (on exclut les doublons exacts déjà détectés)
    indices_exacts = {i for ano in out for i in ano.indices_lignes}
    par_montant: dict[Decimal, list[tuple[int, LigneSuivi]]] = defaultdict(list)
    for idx, l in items:
        if idx in indices_exacts:
            continue
        par_montant[l.montant_ttc].append((idx, l))

    for montant, lignes_montant in par_montant.items():
        if len(lignes_montant) < 2:
            continue
        # On cherche des groupes de dates proches
        lignes_triees = sorted(lignes_montant, key=lambda x: x[1].date_facture)
        groupes: list[list[tuple[int, LigneSuivi]]] = []
        courant: list[tuple[int, LigneSuivi]] = []
        for idx, l in lignes_triees:
            if not courant:
                courant = [(idx, l)]
                continue
            ecart = abs((l.date_facture - courant[-1][1].date_facture).days)
            if ecart <= proximite_jours:
                courant.append((idx, l))
            else:
                if len(courant) >= 2:
                    groupes.append(courant)
                courant = [(idx, l)]
        if len(courant) >= 2:
            groupes.append(courant)

        for g in groupes:
            indices = tuple(i for i, _ in g)
            dates = [l.date_facture for _, l in g]
            out.append(Anomalie(
                type=TypeAnomalie.DOUBLON_PROBABLE,
                description=(
                    f"{len(g)} lignes proches ({min(dates).isoformat()} → "
                    f"{max(dates).isoformat()}) à {montant:,.2f} MAD chez {fournisseur}"
                ),
                fournisseur=fournisseur,
                indices_lignes=indices,
            ))

    # 3) Montants récurrents (même montant, non lettré, ≥ 2 lignes)
    indices_traitees = {i for ano in out for i in ano.indices_lignes}
    par_montant_recurrent: dict[Decimal, list[int]] = defaultdict(list)
    for idx, l in items:
        if idx in indices_traitees:
            continue
        if l.lettrage:   # déjà lettré par le comptable, pas d'ambiguïté
            continue
        par_montant_recurrent[l.montant_ttc].append(idx)
    for montant, indices in par_montant_recurrent.items():
        if len(indices) >= 2:
            out.append(Anomalie(
                type=TypeAnomalie.MONTANT_RECURRENT,
                description=(
                    f"{len(indices)} factures non lettrées au même montant "
                    f"{montant:,.2f} MAD chez {fournisseur} — "
                    "ambiguïté facture/paiement, à vérifier manuellement"
                ),
                fournisseur=fournisseur,
                indices_lignes=tuple(indices),
            ))

    return out


# ─── Helpers d'application aux lignes ──────────────────────────────────────

def annoter_lignes(
    lignes: list[LigneSuivi],
    anomalies: list[Anomalie],
) -> list[LigneSuivi]:
    """Ajoute aux observations des LigneSuivi une mention des anomalies détectées.

    Retourne une nouvelle liste de LigneSuivi (immuables). Les lignes non
    concernées sont inchangées.
    """
    from dataclasses import replace

    # Index : ligne idx → liste de messages à ajouter
    msgs: dict[int, list[str]] = defaultdict(list)
    icones = {
        TypeAnomalie.DOUBLON_EXACT:      "🔁",
        TypeAnomalie.DOUBLON_PROBABLE:   "❓",
        TypeAnomalie.MONTANT_RECURRENT:  "🔄",
    }
    for ano in anomalies:
        icone = icones[ano.type]
        autres = ", ".join(str(i + 10) for i in ano.indices_lignes)  # 10 = offset Excel
        for idx in ano.indices_lignes:
            msgs[idx].append(
                f"{icone} {ano.type.value.replace('_', ' ')} (lignes {autres})"
            )

    nouvelles: list[LigneSuivi] = []
    for i, l in enumerate(lignes):
        if i in msgs:
            nouvelles_obs_parts = []
            if l.observations:
                nouvelles_obs_parts.append(l.observations)
            nouvelles_obs_parts.extend(msgs[i])
            nouvelles.append(replace(l, observations=" · ".join(nouvelles_obs_parts)))
        else:
            nouvelles.append(l)
    return nouvelles


# ─── Statistiques pour la CLI ──────────────────────────────────────────────

def stats(anomalies: Iterable[Anomalie]) -> dict[TypeAnomalie, int]:
    """Compte d'anomalies par type."""
    counts: dict[TypeAnomalie, int] = {t: 0 for t in TypeAnomalie}
    for a in anomalies:
        counts[a.type] += 1
    return counts
