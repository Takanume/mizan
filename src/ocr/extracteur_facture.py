"""Extraction OCR de la date et du n° d'une facture PDF (Sprint 2b — D-006).

Stratégie :
  1. Convertit chaque page du PDF en image (pdf2image).
  2. Lance Tesseract OCR en français (+ arabe) sur chaque page.
  3. Détecte le type de document : facture / avis de virement / lettre de change.
  4. Pour les pages de type "facture", extrait la date de facturation et le n°.
  5. Retourne une liste de `ResultatOCR` (1 par facture trouvée).

Dépendances système :
  - tesseract (`brew install tesseract tesseract-lang`)
  - poppler  (`brew install poppler` — requis par pdf2image)

Performance : ~1-2 sec par page à 150 DPI en français + arabe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError as e:
    raise ImportError(
        "Dépendances OCR manquantes : `pip install pytesseract pdf2image pillow` "
        "et `brew install tesseract tesseract-lang poppler`"
    ) from e


# ─── Modèle de résultat ────────────────────────────────────────────────────

class TypeDocument(str):
    """Type détecté pour une page de PDF."""
    FACTURE     = "facture"
    AVIS_VIR    = "avis_virement"
    LCN         = "lettre_change"
    INCONNU     = "inconnu"


@dataclass(frozen=True)
class ResultatOCR:
    """Résultat de l'extraction OCR d'une page."""
    chemin_pdf: str
    page: int
    type_document: str
    n_facture: Optional[str]
    date_facture: Optional[date]
    confiance: float            # 0.0 à 1.0
    texte_brut: str             # pour debug


# ─── Détection du type de document ─────────────────────────────────────────

MOTS_FACTURE = (
    "facture", "fact n", "fn°", "f°", "invoice", "facturation",
    "date de la facture", "n° facture", "numéro",
)
MOTS_AVIS_VIR = (
    "avis de virement", "compte rendu", "ordre n°",
    "ordre de virement", "virement instantané", "virement émis",
)
MOTS_LCN = (
    "lettre de change", "ordre de paiement", "tirage",
    "veuillez régler à l'échéance", "n° tlm",
)


def detecter_type(texte: str) -> str:
    """Devine le type d'un document à partir du texte OCR.

    On compte les mots-clés de chaque catégorie ; celle qui en a le plus gagne.
    """
    lower = texte.lower()
    counts = {
        TypeDocument.FACTURE:  sum(1 for kw in MOTS_FACTURE if kw in lower),
        TypeDocument.AVIS_VIR: sum(1 for kw in MOTS_AVIS_VIR if kw in lower),
        TypeDocument.LCN:      sum(1 for kw in MOTS_LCN if kw in lower),
    }
    if max(counts.values()) == 0:
        return TypeDocument.INCONNU
    return max(counts, key=counts.get)


# ─── Extraction de date ────────────────────────────────────────────────────

# Patterns de date courants en français : JJ/MM/AAAA, JJ-MM-AAAA, JJ.MM.AAAA
RE_DATE = re.compile(
    r"(\d{1,2})[\s./\\-](\d{1,2})[\s./\\-](\d{2,4})"
)
# Date au format AAAA-MM-JJ (rare sur facture mais possible)
RE_DATE_ISO = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")

# Mots-clés qui annoncent la date facture (ordre = priorité)
ANCRES_DATE_FACTURE = (
    "date de la facture",
    "date facture",
    "date d'émission",
    "date d'emission",
    "date d'edition",
    "fait le",
    "le ",
)


def _ligne_contient_ancre(ligne: str) -> tuple[bool, int]:
    """Retourne (True, priorité) si la ligne contient une ancre de date facture."""
    lower = ligne.lower()
    for i, ancre in enumerate(ANCRES_DATE_FACTURE):
        if ancre in lower:
            return True, i
    return False, 99


def _parser_date(jour: str, mois: str, annee: str) -> Optional[date]:
    try:
        j = int(jour); m = int(mois); a = int(annee)
        if a < 100:
            a += 2000 if a < 80 else 1900
        if 1 <= j <= 31 and 1 <= m <= 12 and 2000 <= a <= 2099:
            return date(a, m, j)
    except (ValueError, TypeError):
        pass
    return None


def extraire_dates(texte: str) -> list[tuple[date, str, int]]:
    """Trouve toutes les dates dans un texte. Retourne (date, contexte, ancre_priorite)."""
    lignes = texte.split("\n")
    resultats: list[tuple[date, str, int]] = []
    for idx, ligne in enumerate(lignes):
        # Cherche d'abord ISO YYYY-MM-DD
        for m in RE_DATE_ISO.finditer(ligne):
            d = _parser_date(m.group(3), m.group(2), m.group(1))
            if d:
                # contexte = la ligne courante + précédente
                ctx = (lignes[idx-1] + " | " + ligne) if idx > 0 else ligne
                _, prio = _ligne_contient_ancre(ctx)
                resultats.append((d, ctx.strip(), prio))
        # Puis DD/MM/YYYY
        for m in RE_DATE.finditer(ligne):
            d = _parser_date(m.group(1), m.group(2), m.group(3))
            if d:
                ctx = (lignes[idx-1] + " | " + ligne) if idx > 0 else ligne
                _, prio = _ligne_contient_ancre(ctx)
                resultats.append((d, ctx.strip(), prio))
    return resultats


def extraire_date_facture(texte: str) -> tuple[Optional[date], float]:
    """Extrait la date la plus probable d'être la date facture.

    Retourne (date, confiance ∈ [0, 1]).
    """
    dates = extraire_dates(texte)
    if not dates:
        return None, 0.0

    # Trier par priorité d'ancre, puis par ordre d'apparition
    # priorité 0 = ancre "date de la facture" trouvée à proximité, c'est la meilleure
    dates_triees = sorted(dates, key=lambda x: x[2])

    meilleure_date, _, meilleure_prio = dates_triees[0]
    if meilleure_prio < len(ANCRES_DATE_FACTURE):
        # Ancre trouvée → confiance élevée
        confiance = 0.95 - meilleure_prio * 0.1
    else:
        # Aucune ancre → on prend la première date trouvée mais confiance basse
        confiance = 0.4
    return meilleure_date, max(0.1, min(0.99, confiance))


# ─── Extraction du n° de facture ───────────────────────────────────────────

RE_N_FACTURE = re.compile(
    r"(?:facture|fact)\s*[n°#:]*\s*([A-Z0-9][A-Z0-9/.\-]{2,})", re.IGNORECASE
)
RE_F_TYPE = re.compile(r"\bF([0-9]{2}/[0-9]+)\b")           # ex : F26/084
RE_NUM_AVEC_SLASH = re.compile(r"\b(\d{2,4}[/\-]\d{3,8})\b")  # ex : 25/043, 26/00225 (suffixe ≥ 3 chiffres pour éviter les dates)
RE_NUM_LONG = re.compile(r"\b(\d{6,12})\b")                  # n° longs : 2602080, 056043346


def _est_n_facture_valide(n: str) -> bool:
    """Heuristique : un vrai n° de facture contient au moins un chiffre et au moins 3 caractères."""
    if len(n) < 3 or len(n) > 30:
        return False
    if not any(c.isdigit() for c in n):
        return False
    # Rejette les mots anglais courants qu'OCR peut prendre pour des n°
    if n.lower() in {"invoice", "facture", "ure", "ures", "numero", "number"}:
        return False
    # Rejette les patterns date "JJ/AAAA" ou "MM/AAAA" (ex : 02/2026)
    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", n)
    if m:
        deuxieme = int(m.group(2))
        if 1900 <= deuxieme <= 2099:
            return False
    return True


def extraire_n_facture(texte: str) -> Optional[str]:
    """Extrait le n° de facture du texte OCR.

    Priorités :
      1. Patterns dédiés : F26/084, 25/043, etc. (très spécifiques)
      2. Numéro long (6+ chiffres) : 2602080, 056043346
      3. Fallback regex générique après "facture"
    """
    # Patterns spécifiques d'abord (les plus distinctifs)
    m = RE_F_TYPE.search(texte)
    if m:
        cand = m.group(1)
        if _est_n_facture_valide(cand):
            return cand

    m = RE_NUM_AVEC_SLASH.search(texte)
    if m:
        cand = m.group(1)
        if _est_n_facture_valide(cand) and len(cand) >= 5:
            return cand

    # Generic après "facture"
    m = RE_N_FACTURE.search(texte)
    if m:
        n = m.group(1).strip().rstrip(".,;:")
        if _est_n_facture_valide(n):
            return n

    # Dernier recours : un long n° quelque part
    m = RE_NUM_LONG.search(texte)
    if m:
        cand = m.group(1)
        # Exclure les patterns trop évidents (téléphone, IF, etc.)
        if _est_n_facture_valide(cand) and not cand.startswith(("0021", "00135")):
            return cand

    return None


# ─── Pipeline principal ────────────────────────────────────────────────────

def extraire_pdf(
    chemin: Path | str,
    dpi: int = 150,
    langues: str = "fra+ara",
    pages_max: Optional[int] = None,
) -> list[ResultatOCR]:
    """OCR + extraction d'un PDF. Une entrée par page.

    Arguments :
      - dpi : résolution de conversion image (150 = compromis vitesse/qualité)
      - langues : langues Tesseract (fra+ara couvre français + arabe)
      - pages_max : limiter le nombre de pages (None = toutes)
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(chemin)

    kwargs = {"dpi": dpi}
    if pages_max:
        kwargs["last_page"] = pages_max
    images = convert_from_path(str(chemin), **kwargs)

    resultats: list[ResultatOCR] = []
    for i, img in enumerate(images, start=1):
        texte = pytesseract.image_to_string(img, lang=langues)
        type_doc = detecter_type(texte)
        n_fact = extraire_n_facture(texte) if type_doc == TypeDocument.FACTURE else None
        date_fact, confiance = (
            extraire_date_facture(texte)
            if type_doc == TypeDocument.FACTURE
            else (None, 0.0)
        )
        resultats.append(ResultatOCR(
            chemin_pdf=str(chemin),
            page=i,
            type_document=type_doc,
            n_facture=n_fact,
            date_facture=date_fact,
            confiance=confiance,
            texte_brut=texte,
        ))
    return resultats


def extraire_dossier(
    dossier: Path | str,
    langues: str = "fra+ara",
    dpi: int = 150,
) -> list[ResultatOCR]:
    """OCR sur tous les PDF d'un dossier. Retourne uniquement les pages de type FACTURE."""
    dossier = Path(dossier)
    resultats: list[ResultatOCR] = []
    pdfs = sorted(dossier.glob("*.pdf"))
    for pdf in pdfs:
        for r in extraire_pdf(pdf, dpi=dpi, langues=langues):
            if r.type_document == TypeDocument.FACTURE:
                resultats.append(r)
    return resultats
