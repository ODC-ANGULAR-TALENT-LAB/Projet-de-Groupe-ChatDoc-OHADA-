"""Tests de l'empreinte de provenance (B.1).

CE QUE L'EMPREINTE PROMET. « Voici exactement le document qui est entré
en base. » Six mois plus tard, face à une réponse contestée, c'est elle
qui permet de dire quelle version a servi. Une empreinte qui varierait
d'une machine à l'autre, ou qui ne changerait pas quand le document
change, ne promet plus rien.
"""

from __future__ import annotations

import hashlib


def test_l_empreinte_d_un_fichier_est_celle_de_son_contenu(provenancier, tmp_path):
    fichier = tmp_path / "texte.pdf"
    fichier.write_bytes(b"contenu officiel")

    assert (
        provenancier.empreinte_sha256(fichier)
        == hashlib.sha256(b"contenu officiel").hexdigest()
    )


# ---------------------------------------------------------------------
# La source peut être un DOSSIER DE PAGES
#
# La Direction générale des impôts ne publie pas le Code général des
# impôts en PDF : elle le publie en 1008 images, une par page. La
# provenance doit pouvoir empreindre cette forme-là aussi, sinon le seul
# texte fiscal camerounais du corpus entrerait en base sans traçabilité.
# ---------------------------------------------------------------------


def dossier_de_pages(racine, pages: dict[str, bytes]):
    dossier = racine / "pages"
    dossier.mkdir(parents=True)
    for nom, contenu in pages.items():
        (dossier / nom).write_bytes(contenu)
    return dossier


def test_un_dossier_de_pages_a_une_empreinte(provenancier, tmp_path):
    dossier = dossier_de_pages(
        tmp_path, {"cgi-0000.jpg": b"page une", "cgi-0001.jpg": b"page deux"}
    )

    empreinte = provenancier.empreinte_sha256(dossier)

    assert empreinte == hashlib.sha256(b"page unepage deux").hexdigest()


def test_l_empreinte_d_un_dossier_suit_l_ordre_des_pages(provenancier, tmp_path):
    """L'ordre est CELUI DES NOMS, pas celui du système de fichiers.

    Sans tri explicite, l'empreinte dépendrait de l'ordre dans lequel le
    système rend les entrées du dossier — variable d'une machine et
    d'un système à l'autre. Elle ne prouverait alors plus rien : deux
    ingestions du même document produiraient deux empreintes.
    """
    a = dossier_de_pages(tmp_path / "a", {"p-0001.jpg": b"deux", "p-0000.jpg": b"un"})
    b = dossier_de_pages(tmp_path / "b", {"p-0000.jpg": b"un", "p-0001.jpg": b"deux"})

    assert provenancier.empreinte_sha256(a) == provenancier.empreinte_sha256(b)
    assert provenancier.empreinte_sha256(a) == hashlib.sha256(b"undeux").hexdigest()


def test_une_page_modifiee_change_l_empreinte(provenancier, tmp_path):
    """C'est tout l'intérêt : une source altérée doit se voir."""
    avant = dossier_de_pages(tmp_path / "avant", {"p-0000.jpg": b"texte officiel"})
    apres = dossier_de_pages(tmp_path / "apres", {"p-0000.jpg": b"texte modifie"})

    assert provenancier.empreinte_sha256(avant) != provenancier.empreinte_sha256(apres)


def test_la_taille_d_un_dossier_additionne_ses_pages(provenancier, tmp_path):
    dossier = dossier_de_pages(
        tmp_path, {"p-0000.jpg": b"12345", "p-0001.jpg": b"678"}
    )

    assert provenancier.taille_octets(dossier) == 8
