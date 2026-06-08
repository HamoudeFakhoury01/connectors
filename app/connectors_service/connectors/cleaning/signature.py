"""SignatureStripper : retire le bloc signature en fin de message.

Outil : `email_reply_parser` (portage pur Python du parser de GitHub/Zapier),
choisi plutôt que talon (qui dépend de `cchardet`, non compilable dans Wolfi).

On combine deux passes :
  1. `email_reply_parser.parse_reply` : cas standards (délimiteur '-- ', etc.).
  2. une regex maison pour les signatures AUTO de clients mobiles/mail que la lib
     rate parfois (« Sent from my iPhone », « Envoyé de mon iPhone »…). Ces bouts
     polluent l'analyse de sujets (BERTrend), donc on les retire explicitement.

Ordre : avant PolitenessStripper (la politesse est souvent DANS la signature, §6).
"""

import re

from email_reply_parser import EmailReplyParser

from connectors.cleaning.base import Cleaner

# Signatures auto ancrées en DÉBUT de ligne ; tout ce qui suit la formule jusqu'à
# la fin du message est retiré (la signature est toujours en fin). Ancrage en
# début de ligne pour éviter de couper une phrase qui contiendrait ces mots.
_AUTO_SIGNOFF_RE = re.compile(
    r"^[ \t]*(?:sent from my|envoyé de mon|envoyé depuis|envoyé à partir|"
    r"get outlook for|obtenir outlook)\b.*",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


class SignatureStripper(Cleaner):
    def clean(self, text: str) -> str:
        text = EmailReplyParser.parse_reply(text)
        text = _AUTO_SIGNOFF_RE.sub("", text)
        return text.strip()
