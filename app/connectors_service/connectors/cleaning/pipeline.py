"""Pipeline de nettoyage : applique une liste ordonnée de cleaners en chaîne.

Ne connaît QUE le contrat `Cleaner` (base.py), jamais les implémentations
concrètes (EncodingFixer, SignatureStripper...). L'ordre des cleaners est
injecté à la construction → réordonner/retirer une étape = changer la liste,
zéro réécriture (cf. SPEC §3 et §6).
"""
from connectors.cleaning.base import Cleaner


class CleaningPipeline:
    """Détient une liste ordonnée de cleaners et les applique en chaîne."""

    def __init__(self, cleaners: list[Cleaner]):
        self.cleaners = cleaners
        

    def run(self, text: str) -> str:
      for cleaner in self.cleaners:
         text = cleaner.clean(text)
      return text

