"""SpacyNormalizer : normalisation finale du texte.

Minuscules + suppression des chiffres, de la ponctuation et des stopwords FR.
Étape DESTRUCTIVE → doit être le DERNIER cleaner, et rester désactivable /
déplaçable (cf. SPEC §6 : un anonymiseur à base de NER a besoin de la casse et
de la ponctuation que ce cleaner détruit).

Corrections par rapport au snippet initial (SPEC §5) :
  1. `import re` présent (sinon crash).
  2. Modèle chargé UNE fois, dans __init__ (spacy.load est coûteux).
  3. Composants inutiles désactivés (on n'utilise que token.is_stop) → 5-10x plus rapide.
  4. Batch `nlp.pipe` : optimisation future (notre contrat est clean(text)->str,
     un texte à la fois ; on batchera quand le flux le justifiera).
  5. Fail-loud : entrée non-str → erreur typée, jamais de `return ""` silencieux.
"""

import re

import spacy

from connectors.cleaning.base import Cleaner


class SpacyNormalizer(Cleaner):
    def __init__(self, model: str = "fr_core_news_sm"):
        # Corrections 2 + 3 : charger le modèle UNE fois et désactiver les
        # composants qu'on n'utilise pas (on ne se sert que de token.is_stop).
        self.nlp = spacy.load(model, disable=["parser", "ner", "tagger", "lemmatizer"])

    def clean(self, text: str) -> str:
        # Fail-loud (correction 5) : entrée non-str → erreur typée, jamais "".
        if not isinstance(text, str):
            msg = f"SpacyNormalizer attend un str, reçu : {type(text).__name__}"
            raise TypeError(msg)
        text = text.lower()
        text = re.sub(r"\d+", "", text)
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        doc = self.nlp(text)
        tokens = [token.text for token in doc if not token.is_stop]
        return " ".join(tokens)
