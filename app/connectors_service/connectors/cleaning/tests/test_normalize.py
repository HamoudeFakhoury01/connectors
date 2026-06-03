"""Tests unitaires du SpacyNormalizer.

⚠️ Nécessite spaCy + le modèle fr_core_news_sm → tourne en DOCKER, pas en local
(spaCy ne s'installe pas sur l'environnement Windows/py3.14).
"""

import pytest

# Skip ce fichier si spaCy n'est pas installé (cas de l'env local Windows/py3.14).
# En Docker, spaCy est présent -> les tests s'exécutent normalement.
pytest.importorskip("spacy")

from connectors.cleaning.normalize import SpacyNormalizer  # noqa: E402


def test_normalise_minuscules_chiffres_ponctuation_stopwords():
    norm = SpacyNormalizer()
    resultat = norm.clean("Le PARC est SALE 123 !!!")
    # minuscules + chiffres/ponctuation retirés + stopwords ("le", "est") retirés
    assert resultat == "parc sale"


def test_fail_loud_si_pas_un_str():
    norm = SpacyNormalizer()
    with pytest.raises(TypeError):
        norm.clean(None)
