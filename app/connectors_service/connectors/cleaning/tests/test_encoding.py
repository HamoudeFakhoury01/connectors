from connectors.cleaning.encoding import EncodingFixer


def test_repare_mojibake():
    fixer = EncodingFixer()
    propre = "été"
    casse = propre.encode("utf-8").decode("latin-1")
    assert fixer.clean(casse) == propre
