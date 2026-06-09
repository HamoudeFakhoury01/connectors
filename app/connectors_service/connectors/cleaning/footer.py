"""FooterStripper : coupe les footers légaux de confidentialité en bas de mail.

Ex. : « Le contenu de ce courriel … sont confidentiels … », souvent entouré de
lignes de '*****'. C'est du bruit pour BERTrend.

Stratégie (comme ReplyChainStripper) : repérer le DÉBUT du footer — ligne de
'****' OU phrase de confidentialité connue — et couper jusqu'à la fin.

Place dans le pipeline : tôt (après ReplyChain), avant le reste.
"""

import re

from connectors.cleaning.base import Cleaner

# Début de footer en DÉBUT de ligne, puis tout jusqu'à la fin (DOTALL) :
#   \*{4,}                                  -> ligne de "*****"
#   "?le contenu de ce courriel            -> "Le contenu de ce courriel..."
#   "?ce (courriel|message|e-mail) ... confidentiel  -> "Ce message ... confidentiel"
# Pas de quantificateur imbriqué -> linéaire, pas de ReDoS.
_FOOTER_RE = re.compile(
    r'^[ \t]*(?:\*{4,}|"?le contenu de ce courriel'
    r'|"?ce (?:courriel|message|e-?mail)\b[^\n]*confidentiel).*',
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


class FooterStripper(Cleaner):
    def clean(self, text: str) -> str:
        return _FOOTER_RE.sub("", text).strip()
