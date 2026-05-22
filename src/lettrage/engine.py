"""Moteur de lettrage — regroupe les écritures en `Lettrage`.

Un `Lettrage` est l'unité métier centrale :
  - même fournisseur
  - même lettre (A, B, …) ou lettrage vide
  - regroupe 1+ factures et 0+ paiements

Le moteur :
  1. Classifie chaque `EcritureBrute` en facture / paiement / avoir / inconnu.
  2. Regroupe par `(code_fournisseur, lettre)`.
  3. Marque comme `non-lettré` les écritures sans lettrage (futurs FNP).
  4. Renvoie aussi les écritures inconnues pour diagnostic.

Hypothèses :
  - Les avoirs sont rattachés au lettrage de leur fournisseur s'ils sont lettrés,
    sinon ignorés (à raffiner phase 2 selon les retours du cabinet).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import (  # noqa: E402
    EcritureBrute,
    Facture,
    Fournisseur,
    Lettrage,
    Paiement,
    TypeEcriture,
)

from .classifier import classifier_ecriture, vers_facture, vers_paiement  # noqa: E402


def _resoudre_fournisseur(
    code: str,
    nom: str,
    base: dict[str, Fournisseur],
    delai_par_defaut_jours: int = 60,
) -> Fournisseur:
    """Retourne le fournisseur de la base, ou en crée un avec le délai par défaut."""
    if code in base:
        return base[code]
    return Fournisseur(code=code, nom=nom, delai_convenu_jours=delai_par_defaut_jours)


def construire_lettrages(
    ecritures: Iterable[EcritureBrute],
    base_fournisseurs: dict[str, Fournisseur] | None = None,
    delai_par_defaut_jours: int = 60,
    corrections_index: dict | None = None,
) -> tuple[list[Lettrage], list[EcritureBrute], list[str]]:
    """Construit les lettrages à partir d'un flux d'écritures.

    Arguments :
      - `ecritures` : flux d'écritures parsées du GL
      - `base_fournisseurs` : référentiel (code → Fournisseur)
      - `corrections_index` : dict produit par `compute.construire_index()` ; les
        factures dont le couple (fournisseur, n°) y figure se voient appliquer
        la vraie date.

    Retourne :
      - `lettrages` : liste des Lettrage construits
      - `ecritures_inconnues` : écritures qu'on n'a pas su classifier
      - `fournisseurs_hors_base` : codes fournisseurs absents de la base
    """
    base = base_fournisseurs or {}

    # Regroupement : (code_fournisseur, lettre) → {factures, paiements, avoirs}
    buckets: dict[tuple[str, str | None], dict[str, list]] = defaultdict(
        lambda: {"factures": [], "paiements": [], "avoirs": []}
    )

    # Suivi des fournisseurs croisés (pour résolution + diagnostic)
    fournisseurs_vus: dict[str, str] = {}      # code → nom (premier rencontré)
    ecritures_inconnues: list[EcritureBrute] = []

    for ecr in ecritures:
        fournisseurs_vus.setdefault(ecr.code_fournisseur, ecr.nom_fournisseur)

        type_ecr = classifier_ecriture(ecr)
        key = (ecr.code_fournisseur, ecr.lettrage)

        if type_ecr == TypeEcriture.FACTURE:
            facture = vers_facture(ecr)
            # Application optionnelle d'une correction de date (D-006)
            if corrections_index:
                from compute.corrections import trouver_correction, appliquer_correction
                correction = trouver_correction(facture, corrections_index)
                if correction:
                    facture = appliquer_correction(facture, correction)
            buckets[key]["factures"].append(facture)
        elif type_ecr == TypeEcriture.PAIEMENT:
            buckets[key]["paiements"].append(vers_paiement(ecr))
        elif type_ecr == TypeEcriture.AVOIR:
            # Pour l'instant on garde l'écriture brute (à transformer plus tard)
            buckets[key]["avoirs"].append(ecr)
        else:
            ecritures_inconnues.append(ecr)

    # Construction des Lettrage
    lettrages: list[Lettrage] = []
    for (code_frs, lettre), contenu in buckets.items():
        fournisseur = _resoudre_fournisseur(
            code_frs,
            fournisseurs_vus[code_frs],
            base,
            delai_par_defaut_jours,
        )
        # Ne crée un Lettrage que s'il contient au moins une facture ou un paiement
        if not contenu["factures"] and not contenu["paiements"]:
            continue
        lettrages.append(
            Lettrage(
                fournisseur=fournisseur,
                lettre=lettre,
                factures=contenu["factures"],
                paiements=contenu["paiements"],
            )
        )

    # Diagnostic : fournisseurs absents de la base
    fournisseurs_hors_base = [c for c in fournisseurs_vus if c not in base]

    return lettrages, ecritures_inconnues, fournisseurs_hors_base
