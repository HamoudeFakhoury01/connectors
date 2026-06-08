"""UrlStripper : retire les URLs du texte (http/https/www).

Les liens (Zoom, logos, sites institutionnels…) sont du bruit pour l'analyse de
sujets (BERTrend) : aucun signal métier. On les retire par regex, sans lib externe.

Place dans le pipeline : après EncodingFixer (caractères propres), avant le reste.
"""

import re

from connectors.cleaning.base import Cleaner

# http(s):// ou www. , avec chevrons <...> optionnels (fréquents dans les emails).
# [^\s>]+ = classe de caractères simple -> linéaire, pas de risque ReDoS.
_URL_RE = re.compile(r"<?(?:https?://|www\.)[^\s>]+>?", re.IGNORECASE)


class UrlStripper(Cleaner):
    def clean(self, text: str) -> str:
        return _URL_RE.sub("", text).strip()
