"""PolitenessStripper : retire ouvertures et clôtures de politesse (FR).

Outil : liste FR curée + regex (pas de lib). Les motifs sont ANCRÉS en début
de ligne (^ + re.MULTILINE) pour ne pas manger un mot de politesse situé au
milieu d'une phrase (cf. SPEC §4).
"""

import re

from connectors.cleaning.base import Cleaner

# Ouvertures (début de message). Ajoutez d'autres si on en croise.
_OPENINGS = [
    r"bonjour",
    r"bonsoir",
    r"madame,?\s+monsieur",
    r"madame",
    r"monsieur",
    r"cher(?:e|s|es)?",  # cher, chère, chers, chères
    r"salut",
    r"coucou",
    r"hello",
]

# Clôtures (fin de message).
_CLOSINGS = [
    r"cordialement",
    r"bien (?:à vous|cordialement)",
    r"sincères salutations",
    r"salutations distinguées",
    r"merci (?:d'avance|par avance)",
    r"dans l'attente de[^\n]*",  # "dans l'attente de votre retour..."
    r"bonne (?:journée|réception)",
    r"à bientôt",
]


class PolitenessStripper(Cleaner):
    def __init__(self):
        # On assemble chaque liste en une alternance (a|b|c), puis on compile
        # un motif qui matche une LIGNE entière commençant par une formule.
        #   ^\s*        : début de ligne + espaces éventuels
        #   (?:...)     : une des formules
        #   \b[^\n]*    : fin du mot + reste de la ligne
        #   \n?         : le saut de ligne final (pour effacer la ligne entière)
        openings = "|".join(_OPENINGS)
        closings = "|".join(_CLOSINGS)
        flags = re.IGNORECASE | re.MULTILINE
        self._opening_re = re.compile(rf"^\s*(?:{openings})\b[^\n]*\n?", flags)
        self._closing_re = re.compile(rf"^\s*(?:{closings})\b[^\n]*\n?", flags)

    def clean(self, text: str) -> str:
        text = self._opening_re.sub("", text)
        text = self._closing_re.sub("", text)
        return text.strip()
