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
