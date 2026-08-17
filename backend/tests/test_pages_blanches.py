"""Tests du saut des pages blanches a l'OCR.

POURQUOI CE TEST EXISTE. Le Code general des impots publie par la DGI
est une impression du site web : 2042 pages, dont environ 87 % blanches
— les sauts de page du navigateur. Les OCRiser coutait des heures de
calcul pour produire des pages vides.

Le risque du raccourci est evident : sauter une page qui portait du
texte, et perdre du droit en silence. Ces tests bornent le seuil des
deux cotes.
"""

from __future__ import annotations

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


def page(couleur: str = "white") -> Image.Image:
    return Image.new("RGB", (600, 850), couleur)


def test_une_page_vraiment_blanche_est_sautee(extracteur):
    assert extracteur.page_blanche(page()) is True


def test_une_page_entierement_noire_n_est_pas_blanche(extracteur):
    assert extracteur.page_blanche(page("black")) is False


def test_une_page_portant_une_seule_ligne_de_texte_est_conservee(extracteur):
    """LE GARDE-FOU QUI COMPTE.

    Une page ne portant qu'un titre — « LIVRE PREMIER » — a tres peu de
    pixels sombres. La sauter ferait disparaitre un niveau hierarchique
    entier, et tous les articles qui en dependent heriteraient d'un
    chemin faux.
    """
    image = page()
    dessin = ImageDraw.Draw(image)
    # Une bande de texte : quelques pour mille de la surface, comme un
    # titre isole sur une page autrement vide.
    dessin.rectangle([60, 400, 540, 428], fill="black")

    assert extracteur.page_blanche(image) is False


def test_une_poussiere_de_scan_ne_suffit_pas_a_retenir_une_page(extracteur):
    """L'inverse : quelques pixels parasites ne font pas un contenu."""
    image = page()
    dessin = ImageDraw.Draw(image)
    dessin.rectangle([10, 10, 14, 14], fill="black")

    assert extracteur.page_blanche(image) is True
