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
    r"dans l'attente",  # "Dans l'attente," OU "...de votre retour" (reste de ligne mangé par le motif global)
    r"en attente",  # "En attente de votre retour,"
    r"bonne (?:journée|réception)",
    r"à bientôt",
]


class PolitenessStripper(Cleaner):
    def __init__(self):
        openings = "|".join(_OPENINGS)
        closings = "|".join(_CLOSINGS)
        flags = re.IGNORECASE | re.MULTILINE
        # OUVERTURES : on retire le RUN de formules en début de ligne + leurs
        # séparateurs (espaces, virgules…), MAIS PAS le contenu qui suit sur la
        # même ligne. Ex. "Bonjour, le chauffage est en panne." -> on garde
        # "le chauffage est en panne." (avant : toute la phrase était supprimée).
        # [\s,.:;!?…–-]* = séparateurs uniquement, jamais du contenu.
        self._opening_re = re.compile(
            rf"^[ \t]*(?:(?:{openings})\b[\s,.:;!?…–-]*)+", flags
        )
        # CLÔTURES : en fin de message, après la formule il n'y a que de la
        # politesse ou un nom (PII) -> on supprime toute la fin de ligne.
        self._closing_re = re.compile(rf"^[ \t]*(?:{closings})\b[^\n]*\n?", flags)

    def clean(self, text: str) -> str:
        text = self._opening_re.sub("", text)
        text = self._closing_re.sub("", text)
        return text.strip()
