"""Tests unitaires du SignatureStripper (cf. SPEC §8).

⚠️ talon n'est pas encore installé (cchardet non compilable dans l'image Wolfi,
décision en attente côté Mohamed). Ce module s'AUTO-SKIP tant que talon est
absent, et tournera automatiquement le jour où talon sera disponible.
"""

import pytest

# Si "talon" n'est pas importable -> pytest SKIP tout ce fichier (au lieu de
# planter à la collection). DOIT être placé AVANT l'import de signature.py.
pytest.importorskip("talon")

from connectors.cleaning.signature import SignatureStripper  # noqa: E402


def test_retire_la_signature():
    stripper = SignatureStripper()
    message = (
        "Le lampadaire de ma rue est cassé depuis une semaine.\n"
        "\n"
        "-- \n"
        "Jean Dupont\n"
        "06 12 34 56 78"
    )
    resultat = stripper.clean(message)

    # NB : asserts "best guess" sur le comportement de talon — à confirmer/ajuster
    # le jour où talon tournera réellement.
    assert "lampadaire" in resultat  # le corps du message est conservé
    assert "Jean Dupont" not in resultat  # la signature est retirée
