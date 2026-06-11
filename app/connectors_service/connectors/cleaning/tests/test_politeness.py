"""Tests unitaires du PolitenessStripper, en isolation (cf. SPEC §8)."""

from connectors.cleaning.politeness import PolitenessStripper


def test_retire_ouverture_et_cloture():
    # Arrange : on prépare l'entrée et l'objet à tester
    stripper = PolitenessStripper()
    mail = "Bonjour Madame,\nLe parc municipal est mal entretenu.\nCordialement"

    # Act : on exécute la méthode
    resultat = stripper.clean(mail)

    # Assert : on vérifie le résultat attendu
    assert resultat == "Le parc municipal est mal entretenu."


def test_conserve_bonjour_au_milieu_de_phrase():
    # Le piège de la SPEC §4 : un "bonjour" qui n'est PAS en début de ligne
    # ne doit PAS être supprimé.
    stripper = PolitenessStripper()
    texte = "Je passe vous dire bonjour demain au sujet du bruit."

    resultat = stripper.clean(texte)
    assert "bonjour" in resultat


def test_ouverture_inline_garde_le_contenu():
    # BUG corrigé : une ouverture sur la MÊME ligne que le message ne doit PAS
    # emporter la phrase (avant, toute la ligne était supprimée).
    stripper = PolitenessStripper()

    assert (
        stripper.clean("Bonjour, le chauffage est en panne depuis 3 semaines.")
        == "le chauffage est en panne depuis 3 semaines."
    )
    assert stripper.clean("Bonjour Madame, le parc est sale.") == "le parc est sale."


def test_cloture_forte_inline_en_fin_de_ligne():
    # Clôture forte en FIN de ligne de contenu -> retirée, contenu gardé.
    stripper = PolitenessStripper()
    assert stripper.clean("Le parc est sale. Merci d'avance.") == "Le parc est sale."
    assert (
        stripper.clean("La vitre est brisée. Bien à vous, Jean")
        == "La vitre est brisée."
    )
    # MAIS "en attente" est ambigu (= du contenu) -> NON retiré en milieu de phrase.
    assert "en attente" in stripper.clean("Ma demande est en attente de traitement.")


def test_retire_clotures_attente():
    # "Dans l'attente," (sans "de") et "En attente de votre retour," doivent partir.
    stripper = PolitenessStripper()

    assert stripper.clean("Pas de réponse.\nDans l'attente,") == "Pas de réponse."
    assert (
        stripper.clean("Plus d'eau chaude.\nEn attente de votre retour,")
        == "Plus d'eau chaude."
    )
