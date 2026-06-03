"""SignatureStripper : retire le bloc signature en fin de message.

⚠️ REPORTÉ (1er jet) : talon n'est PAS installé — sa dépendance `cchardet` exige
un compilateur C++ absent de l'image Wolfi. Ne PAS importer ce module tant que
l'intégration talon n'est pas tranchée (cf. message à Mohamed / SPEC §10).
Le code reste prêt à brancher : grâce au contrat Cleaner, l'ajouter = 1 ligne.

Outil : talon (Mailgun, open-source). On utilise la variante heuristique
`bruteforce.extract_signature(text)`, qui ne demande PAS d'expéditeur
(contrairement à `talon.signature.extract` qui exige un `sender` + `talon.init()`).
Ça colle à notre contrat `clean(text) -> str` (cf. SPEC §4).

Ordre : avant PolitenessStripper (la politesse est souvent DANS la signature, §6).
"""
from talon.signature.bruteforce import extract_signature

from connectors.cleaning.base import Cleaner


class SignatureStripper(Cleaner):
    # Pas d'__init__ : bruteforce.extract_signature n'a pas besoin de talon.init()
    # (aucun modèle ML à charger), contrairement à talon.signature.extract.

    def clean(self, text: str) -> str:
        stripped, _signature = extract_signature(text)
        return stripped
        
