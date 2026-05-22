"""Module qualité — détection automatique d'anomalies."""

from .detection_doublons import (
    Anomalie,
    TypeAnomalie,
    annoter_lignes,
    detecter_doublons,
    stats,
)

__all__ = [
    "Anomalie",
    "TypeAnomalie",
    "detecter_doublons",
    "annoter_lignes",
    "stats",
]
