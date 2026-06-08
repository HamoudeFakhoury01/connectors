"""Tests unitaires du ReplyChainStripper, en isolation (cf. SPEC §8)."""

from connectors.cleaning.reply_chain import ReplyChainStripper


def test_coupe_chaine_de_envoye():
    stripper = ReplyChainStripper()
    message = (
        "Oui, bloquons ces dates.\n"
        "\n"
        "De : Jean Martin <jean@x.fr>\n"
        "Envoyé : lundi 13 janvier 2025\n"
        "À : Marie\n"
        "Objet : RE: dialogue\n"
        "\n"
        "Bonjour, pouvez-vous confirmer les créneaux ?"
    )
    res = stripper.clean(message)

    assert "bloquons ces dates" in res  # le message récent (du haut) reste
    assert "Envoyé" not in res  # l'en-tête de chaîne est coupé
    assert "confirmer les créneaux" not in res  # le contenu cité est parti


def test_coupe_chaine_le_a_ecrit():
    stripper = ReplyChainStripper()
    message = (
        "Merci pour votre retour rapide.\n"
        "\n"
        "Le 13 janv. 2025, BRIA SEVERINE a écrit :\n"
        "Il faut accepter les invitations zoom."
    )
    res = stripper.clean(message)

    assert "Merci pour votre retour" in res
    assert "accepter les invitations" not in res


def test_conserve_message_sans_chaine():
    stripper = ReplyChainStripper()
    message = "Le parc municipal est sale, merci d'intervenir rapidement."

    assert stripper.clean(message) == message
