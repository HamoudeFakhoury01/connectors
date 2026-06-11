"""ReplyChainStripper : coupe les chaînes de réponse/transfert (emails cités, FR).

Dans un email, le message récent est EN HAUT et l'historique cité EN BAS. On
repère le PREMIER en-tête de chaîne (en début de ligne) et on coupe tout de là
jusqu'à la fin → il ne reste que le message du dessus.

email_reply_parser ne gère que l'anglais (« On … wrote: ») ; ce cleaner couvre
le français (« De : … », « Le … a écrit : », « Message d'origine »).

Place dans le pipeline : tôt (après EncodingFixer) — couper la chaîne retire
aussi les signatures/URLs des messages cités d'un seul coup.
"""

import re

from connectors.cleaning.base import Cleaner

# En-tête de chaîne en DÉBUT de ligne, puis tout jusqu'à la fin (DOTALL).
#   de\s*:\s*\S                 -> "De : ..."
#   le\b[^\n]*\ba\s+écrit\s*:   -> "Le <date>, X a écrit :" (sur une seule ligne)
#   -+\s*message d'origine\s*-+ -> "-----Message d'origine-----"
# [^\n]* borne la détection à une ligne ; .* (DOTALL) coupe le reste. Pas de
# quantificateur imbriqué -> linéaire, pas de ReDoS.
_REPLY_CHAIN_RE = re.compile(
    r"^[ \t]*(?:de\s*:\s*\S|le\b[^\n]*\ba\s+écrit\s*:|-+\s*message d'origine\s*-+).*",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


class ReplyChainStripper(Cleaner):
    def clean(self, text: str) -> str:
        return _REPLY_CHAIN_RE.sub("", text).strip()
