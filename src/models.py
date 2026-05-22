"""Modèles de données du projet DDP — Étape 1.

Trois niveaux d'abstraction, du plus brut au plus métier :

  1. EcritureBrute        : ligne du Grand Livre Sage telle qu'extraite.
  2. Facture / Paiement   : interprétation comptable d'une EcritureBrute.
  3. Lettrage / LigneSuivi: regroupement métier et résultats de calcul.

Tous les montants sont en MAD (dirham marocain).
Toutes les dates sont des `date` (pas `datetime`) — la date d'écriture
ne comporte pas d'heure en comptabilité française.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


# ════════════════════════════════════════════════════════════
# Niveau 1 — Primitives Sage (parser)
# ════════════════════════════════════════════════════════════

class CodeJournal(str, Enum):
    """Codes journaux observés dans les exports Sage UEMA.

    - ACH  : Journal des Achats (factures fournisseurs courantes).
    - AN   : À-Nouveau (report d'écritures non lettrées de l'exercice précédent).
    - BMCE : Journal banque BMCE (paiements virement / chèque).
    - BMCI : Journal banque BMCI.
    - CAI  : Journal caisse (paiements en espèces — « ESPECE/ESPACE »).
    - OD   : Opérations Diverses — typiquement les Lettres de Change Normalisées
             (LCN, instrument de paiement à terme) ou régularisations.

    NB : la liste n'est pas figée. D'autres clients utilisent des codes
    différents (autres banques, journaux dédiés). À paramétrer en phase 2.
    """
    ACH  = "ACH"
    AN   = "AN"
    BMCE = "BMCE"
    BMCI = "BMCI"
    CAI  = "CAI"
    OD   = "OD"


@dataclass(frozen=True)
class EcritureBrute:
    """Une ligne d'écriture du Grand Livre Sage, brute.

    Reflète exactement une ligne de l'export — sans interprétation.
    Le parser remplit ces objets ; le moteur de lettrage les regroupe.

    Champs renseignés selon les colonnes Sage observées :
      col 1  → date
      col 2  → code_journal
      col 3  → n_piece
      col 6  → libelle
      col 9  → lettrage
      col 13 → debit
      col 15 → credit
      col 18 → solde_progressif

    Le code et le nom du fournisseur sont propagés depuis le bloc parent
    (en-tête `FRSxxxx <NOM>` au-dessus du groupe d'écritures).
    """
    ligne_source: int                       # ligne dans le fichier source (debug)
    code_fournisseur: str                   # ex. "FRS0000001"
    nom_fournisseur: str                    # ex. "A2CIM"
    date_ecriture: date
    code_journal: CodeJournal
    n_piece: str                            # ex. "37"
    libelle: str                            # ex. "FN° 26FC0031 A2CIM"
    lettrage: Optional[str]                 # ex. "A" (une seule lettre A-Z ou None)
    debit: Decimal                          # MAD, 0 si crédit
    credit: Decimal                         # MAD, 0 si débit
    solde_progressif: Optional[Decimal]     # cumul depuis le début du bloc fournisseur


# ════════════════════════════════════════════════════════════
# Niveau 2 — Interprétation comptable (compute)
# ════════════════════════════════════════════════════════════

class TypeEcriture(str, Enum):
    """Nature comptable d'une écriture, déduite du code journal + libellé.

    Règles de classification (Phase 1 — à raffiner) :
      FACTURE  : crédit > 0 ET (Cj ∈ {ACH, AN}) ET libellé débute par "FN°"/"Fact".
      PAIEMENT : débit  > 0 ET Cj ∈ {BMCE, BMCI, CAI, OD}, ou Cj=AN avec
                 libellé contenant {VIREMENT, CHQ, VIR, RGL, LCN, Vrt, Paiement}.
      AVOIR    : débit  > 0 ET Cj=ACH (rare ; à confirmer sur d'autres clients).
      INCONNU  : tout le reste — à signaler pour revue manuelle.
    """
    FACTURE  = "facture"
    PAIEMENT = "paiement"
    AVOIR    = "avoir"
    INCONNU  = "inconnu"


class MoyenPaiement(str, Enum):
    """Instrument de paiement, déduit du libellé."""
    VIREMENT = "virement"        # Vrt, VIR, VIREMENT
    CHEQUE   = "chèque"          # CHQ, Chq
    LCN      = "lcn"             # Lettre de Change Normalisée (effet)
    ESPECES  = "espèces"         # ESPECE, ESPACE (caisse)
    AUTRE    = "autre"           # RGL non typé, Paiement générique


@dataclass(frozen=True)
class Fournisseur:
    """Référentiel fournisseur — délai convenu et identification DGI.

    Sourcé depuis l'onglet `Base Frs Permanente` du modèle de suivi.
    Si un fournisseur du GL n'est pas dans la base, on applique
    `delai_par_defaut_jours` (60 jours en l'absence de convention).

    Les champs DGI (N° IF, ICE, RC, adresse, ville, secteur) sont requis
    par le formulaire Simpl mais ne figurent pas dans le GL Sage. Ils
    proviennent d'un référentiel enrichi maintenu par le cabinet.
    """
    code: str                               # FRS0000001
    nom: str                                # A2CIM
    delai_convenu_jours: int                # 60 ou 120 (ou autre selon convention)
    observations: Optional[str] = None
    # Champs DGI (formulaire Simpl)
    n_if: Optional[str] = None              # Identifiant Fiscal
    n_ice: Optional[str] = None             # Identifiant Commun de l'Entreprise (15 chiffres)
    n_rc: Optional[str] = None              # Registre du Commerce
    adresse: Optional[str] = None
    ville_rc: Optional[str] = None
    secteur_activite: Optional[str] = None  # pour le délai sectoriel
    nature_marchandises: Optional[str] = None


@dataclass(frozen=True)
class Facture:
    """Une facture fournisseur — interprétation d'une EcritureBrute de type FACTURE."""
    code_fournisseur: str
    nom_fournisseur: str
    n_piece: str                            # n° pièce Sage (clé interne)
    n_facture: Optional[str]                # extrait du libellé après "FN°"
    date_facture: date                      # date comptable de la pièce
    date_livraison: Optional[date]          # quand disponible, sinon = date_facture
    montant_ttc: Decimal
    lettrage: Optional[str]
    is_report: bool                         # True si issue d'un À-Nouveau (Cj=AN)
    source: EcritureBrute
    # Phase 2 — Sprint 3 (D-003) : surcharge ponctuelle du délai pour cette facture
    delai_surcharge: Optional[int] = None


@dataclass(frozen=True)
class Paiement:
    """Un paiement fournisseur — interprétation d'une EcritureBrute de type PAIEMENT."""
    code_fournisseur: str
    nom_fournisseur: str
    n_piece: str
    date_paiement: date
    montant: Decimal
    moyen: MoyenPaiement
    lettrage: Optional[str]
    is_report: bool                         # True si paiement passé en AN
    source: EcritureBrute


# ════════════════════════════════════════════════════════════
# Niveau 3 — Lettrage et résultats (lettrage + output)
# ════════════════════════════════════════════════════════════

@dataclass
class Lettrage:
    """Regroupement par lettre — relie une (ou plusieurs) facture(s)
    à un (ou plusieurs) paiement(s) du même fournisseur.

    Cas attendus :
      - 1 facture + 1 paiement, montants égaux                   → simple, OK
      - 1 facture + n paiements (partiels), somme = montant      → partiel
      - n factures + 1 paiement (groupé), somme = montant        → groupé
      - n factures + n paiements                                 → mixte
      - factures sans paiement (lettrage vide)                   → FNP
      - lettrage déséquilibré (avoir ou écart)                   → à signaler
    """
    fournisseur: Fournisseur
    lettre: Optional[str]                   # None pour les non lettrés (FNP)
    factures: list[Facture] = field(default_factory=list)
    paiements: list[Paiement] = field(default_factory=list)

    @property
    def total_factures(self) -> Decimal:
        return sum((f.montant_ttc for f in self.factures), Decimal(0))

    @property
    def total_paiements(self) -> Decimal:
        return sum((p.montant for p in self.paiements), Decimal(0))

    @property
    def ecart(self) -> Decimal:
        """Différence factures − paiements. 0 = soldé, >0 = reste à payer, <0 = trop payé."""
        return self.total_factures - self.total_paiements

    @property
    def est_solde(self) -> bool:
        return self.ecart == 0

    @property
    def est_non_paye(self) -> bool:
        return not self.paiements


class StatutFacture(str, Enum):
    """Statut final d'une facture pour la déclaration.

    Libellés alignés sur le vocabulaire du cabinet observé dans
    l'output de référence UEMA 1T26.
    """
    OK_RAS              = "OK RAS"                              # payée dans les délais
    RETARD              = "Attention, paiement hors délais"     # payée hors délais
    NON_PAYE            = "Non encore payée"                    # FNP
    PARTIEL             = "Paiement partiel"                    # à ventiler
    A_VERIFIER          = "À vérifier"                          # cas ambigu


@dataclass
class LigneSuivi:
    """Une ligne du tableau « Suivi Global DP » — résultat final.

    Une ligne = une facture, enrichie de l'échéance, du paiement effectif
    (consolidé depuis tous les paiements du lettrage) et du statut.

    Correspond aux colonnes 2..12 du modèle de référence
    `Modèle Suivi Global DDP2026.xlsx` onglet `Suivi Global DP`.
    """
    n_facture: Optional[str]                # col B
    date_livraison: Optional[date]          # col C
    date_facture: date                      # col D
    fournisseur: str                        # col E
    montant_ttc: Decimal                    # col F
    delai_convenu_jours: int                # col G
    date_echeance: date                     # col H — date_facture (ou livraison) + délai
    jours_retard: Optional[int]             # col I — positif=retard, négatif=anticipé, None=FNP
    statut: StatutFacture                   # col J
    date_paiement_effectif: Optional[date]  # col K — date du dernier paiement du lettrage
    observations: Optional[str] = None      # col L
    # Reste à payer (= montant_ttc − payé). Pour un paiement partiel, c'est
    # le montant qui figurera dans la DDP (le retard porte sur le reste).
    # Pour OK_RAS / RETARD soldés, = 0. Pour NON_PAYE, = montant_ttc.
    montant_du: Optional[Decimal] = None
    # traçabilité (pour audit, n'apparaît pas dans le rendu Excel)
    code_fournisseur: Optional[str] = None
    lettrage: Optional[str] = None


# ════════════════════════════════════════════════════════════
# Conteneurs de résultat
# ════════════════════════════════════════════════════════════

@dataclass
class JeuDonnees:
    """Tout ce qu'on a appris d'un GL pour un trimestre donné.

    C'est ce que produit le moteur (parser + lettrage + compute)
    et que consomme la couche output pour générer les Excel.
    """
    client: str                             # ex. "UEMA"
    exercice: int                           # ex. 2026
    periode_debut: date
    periode_fin: date
    fournisseurs: dict[str, Fournisseur] = field(default_factory=dict)
    ecritures: list[EcritureBrute]         = field(default_factory=list)
    lettrages: list[Lettrage]              = field(default_factory=list)
    lignes_suivi: list[LigneSuivi]         = field(default_factory=list)
    # diagnostic
    ecritures_inconnues: list[EcritureBrute] = field(default_factory=list)
    fournisseurs_hors_base: list[str]        = field(default_factory=list)
