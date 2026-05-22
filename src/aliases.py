"""Normalisation et alias des noms de fournisseurs.

Le référentiel cabinet et le GL Sage utilisent parfois des variantes différentes
pour désigner le même fournisseur :
    - typos (INFOSC4YOU vs INFOSEC4YOU)
    - suffixes/préfixes (STE TUPORAVA vs TUPORAVA)
    - variantes numérotées (MAROC TELECOM 3 vs MAROC TELECOM)
    - abréviations (GHM vs GENERAL HYDROLIQUE MOTORS)

Ce module fournit une fonction `normaliser` qui ramène toute forme connue à un
nom canonique, pour aligner Mizan et la déclaration manuelle du cabinet.
"""

from __future__ import annotations

import re
import unicodedata


# ─── Table d'alias : forme rencontrée → nom canonique ─────────────────────
# Les clés sont en MAJUSCULES, sans accents, et sont matchées après strip.
ALIAS: dict[str, str] = {
    # Typos du fichier cabinet
    "INFOSC4YOU":              "INFOSEC4YOU",
    "DSM TECHNLOGIE":          "DSM TECHNOLOGIE",
    "MAGHREB INSTALATION":     "MAGHREB INSTALLATION",
    "ABRA TRDE":               "ABRA TRADE",   # normalisation supprime le tiret
    "ASSRANCES GRAND AGADIR":  "ASSURANCE GRAND AGADIR",
    "LES ATELIERS R E":        "LES ATELIERS RE",
    "SIRI":                    "SIRI MAROC",
    "FINITION PRO CRROSSERIEAUTO": "FINITION PRO CARROSSERIE AUTO",
    "CARREFOUR TECHNIQUE INDUSTRIEL DU SUD": "CARREFOUR TECHNIQUE INDUSTRI DU SUD",
    "MEGA TRANSMISSION HYDRAULIQUE": "MEGA TRANSMISSION HYDROLIQUE",
    "AIT MELLOUL CHIMIE":      "AIT MELOUL CHEMIE",
    "RECOING ET JACQUETY":     "RECOING AND JACQUETY",
    "TECHNIQUE DEOUP LASER":   "TECHNIQUE DECOUPE LASER",

    # Variantes / formes courtes ↔ longues
    "GHM":                     "GENERAL HYDROLIQUE MOTORS",
    "FIRST EQUIPEMENT":        "FIRST EQUIPEMENT INDUSTRIEL",
    "LOTNIK MAGHREB":          "LOTNIK",
    "TOP CAOUTCHOUC ET TRANSMISSION": "TOP CAOUTCHOUC ET TRANSMISSION GROUP",
    "NEW SUN DISTRIBUTION":    "NEW SUN DISTRIBUTION EXPRESS",
    "NEW SUN":                 "NEW SUN DISTRIBUTION EXPRESS",
    "MEGA TRANSMISSION":       "MEGA TRANSMISSION HYDROLIQUE",
    "FINITION PRO":            "FINITION PRO CARROSSERIE AUTO",
    "IBDAAE":                  "IBDAAE DESIGN",
    "NARPA":                   "NARPA MAROC",
    "BOUBAD SAID":             "S BOUBAD TRANSPORT",
    "TECHNIQUE LASER":         "TECHNIQUE DECOUPE LASER",
    "ESPACE METAUX":           "ESPACE METAUX DU MAROC",
    "FORVAL":                  "FORVAL SARL",
    "KITEA AGADIR":            "KITEA",  # à confirmer
}

# Préfixes de forme juridique à ignorer
PREFIXES_JURI = re.compile(r"^\s*(STE|SOCIETE|SOC|SARL|SA|EURL|SAS)\.?\s+")

# Suffixes numérotés (ex: "MAROC TELECOM 3" → "MAROC TELECOM")
SUFFIX_NUMERO = re.compile(r"\s+\d+\s*$")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def normaliser(nom: str | None) -> str:
    """Ramène un nom de fournisseur à sa forme canonique.

    Étapes :
        1. Strip + uppercase + suppression d'accents
        2. Suppression des préfixes de forme juridique (STE, SARL…)
        3. Suppression des suffixes numérotés (MAROC TELECOM 3 → MAROC TELECOM)
        4. Normalisation des séparateurs (- / . → espace)
        5. Application de la table d'alias (typos, variantes)
    """
    if not nom:
        return ""
    n = _strip_accents(nom.upper().strip())
    # Préfixe juridique
    n = PREFIXES_JURI.sub("", n).strip()
    # Suffixe numéroté (boucle pour "FOO 3 BIS 2" → "FOO 3 BIS")
    prev = None
    while n != prev:
        prev = n
        n = SUFFIX_NUMERO.sub("", n).strip()
    # Séparateurs
    n = re.sub(r"[-/.]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Alias direct
    if n in ALIAS:
        return ALIAS[n]
    return n
