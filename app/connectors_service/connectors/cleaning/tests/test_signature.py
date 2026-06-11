"""Tests unitaires du SignatureStripper, en isolation (cf. SPEC §8)."""

from connectors.cleaning.signature import SignatureStripper


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

    assert "lampadaire" in resultat  # le corps du message est conservé
    assert "Jean Dupont" not in resultat  # la signature est retirée


def test_conserve_le_corps_sans_signature():
    # Un message sans bloc signature ne doit pas être amputé.
    stripper = SignatureStripper()
    message = "Le parc est sale et les poubelles débordent."

    assert stripper.clean(message) == message


def test_retire_signature_auto_mobile():
    # Les signatures auto de mobiles ("Sent from my iPhone") polluent BERTrend
    # et doivent être retirées même sans délimiteur "-- ".
    stripper = SignatureStripper()
    message = (
        "Le feu rouge du carrefour est bloqué.\n\nCordialement\nSent from my iPhone"
    )
    resultat = stripper.clean(message)

    assert "feu rouge" in resultat  # le corps reste
    assert "iphone" not in resultat.lower()  # la signature auto est retirée
