"""EncodingFixer : répare le mojibake (encodage cassé).

Ex. : "Ã©" -> "é", "â€™" -> "'". Utilise la lib dédiée `ftfy` plutôt qu'une
chaîne de .replace() fragile et incomplète (cf. SPEC §4).

Doit être le PREMIER cleaner du pipeline : tous les autres ont besoin de
caractères propres (§6).
"""

import ftfy

from connectors.cleaning.base import Cleaner


class EncodingFixer(Cleaner):
    # Pas d'__init__ : ftfy.fix_text est une fonction pure, aucun état à préparer.

    def clean(self, text: str) -> str:
        text = ftfy.fix_text(text)
        return text.replace("\u00a0", " ").replace("\u202f", " ")
