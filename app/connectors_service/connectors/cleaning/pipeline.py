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
        # Fail-loud centralisé : on valide le type au point d'entrée UNIQUE du
        # pipeline (plutôt que dans chaque cleaner → DRY). Jamais de retour
        # silencieux sur une entrée invalide.
        if not isinstance(text, str):
            msg = f"CleaningPipeline.run attend un str, reçu : {type(text).__name__}"
            raise TypeError(msg)
        for cleaner in self.cleaners:
            text = cleaner.clean(text)
        return text
