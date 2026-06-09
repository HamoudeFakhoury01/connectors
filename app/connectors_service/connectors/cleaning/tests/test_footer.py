"""Tests unitaires du FooterStripper, en isolation (cf. SPEC §8)."""

from connectors.cleaning.footer import FooterStripper


def test_coupe_footer_avec_etoiles():
    stripper = FooterStripper()
    message = (
        "Le dossier avance bien.\n"
        "\n"
        "*****************************************\n"
        '"Le contenu de ce courriel et ses pièces jointes sont confidentiels."\n'
        "*****************************************"
    )
    res = stripper.clean(message)

    assert "dossier avance" in res  # le message reste
    assert "confidentiel" not in res  # le footer est coupé
    assert "*" not in res


def test_coupe_footer_par_phrase():
    stripper = FooterStripper()
    message = (
        "Merci pour votre retour rapide.\n"
        "Ce message et ses pièces jointes sont confidentiels et destinés au seul destinataire."
    )
    res = stripper.clean(message)

    assert "Merci pour votre retour" in res
    assert "confidentiel" not in res


def test_conserve_message_sans_footer():
    stripper = FooterStripper()
    message = "Le parc municipal est sale, merci d'intervenir."

    assert stripper.clean(message) == message
