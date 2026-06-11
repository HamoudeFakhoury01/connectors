"""Tests unitaires du UrlStripper, en isolation (cf. SPEC §8)."""

from connectors.cleaning.url import UrlStripper


def test_retire_url_https():
    stripper = UrlStripper()
    res = stripper.clean("Réunion Zoom : https://zoom.us/j/12345?pwd=ab — merci")

    assert "http" not in res  # l'URL est partie
    assert "zoom.us" not in res
    assert "Réunion" in res and "merci" in res  # le texte utile reste


def test_retire_url_chevrons_et_www():
    stripper = UrlStripper()
    res = stripper.clean("Site <https://ameli.fr/page> et www.exemple.fr ici")

    assert "ameli.fr" not in res
    assert "exemple.fr" not in res
    assert "Site" in res and "ici" in res


def test_conserve_texte_sans_url():
    stripper = UrlStripper()
    message = "Le parc municipal est mal entretenu."

    assert stripper.clean(message) == message
