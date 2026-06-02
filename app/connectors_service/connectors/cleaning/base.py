"""Contrat commun à tous les cleaners de texte (cf. SPEC §3).

Tout cleaner respecte la même signature `clean(text: str) -> str` :
fonction pure, déterministe, sans effet de bord. C'est ce qui les rend
interchangeables et réordonnables dans le CleaningPipeline.
"""
from abc import ABC, abstractmethod


class Cleaner(ABC):
    @abstractmethod
    def clean(self, text: str) -> str:
        """Nettoie le texte passé en entrée et retourne le résultat nettoyé."""
