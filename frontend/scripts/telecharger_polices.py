"""Telecharge Source Serif 4 + Inter depuis Google Fonts et les embarque.

POURQUOI EMBARQUER PLUTOT QUE LIER. Le cahier des charges vise des
utilisateurs a Douala, ou la connexion n'est ni constante ni rapide. Une
police servie par un CDN, c'est une requete tierce qui peut echouer, une
typographie qui saute au chargement, et un appel exterieur a chaque
visite. On telecharge une fois, on livre avec l'application.

ON NE GARDE QUE LE SOUS-ENSEMBLE LATIN. Google decoupe chaque police en
sous-ensembles (cyrillique, grec, vietnamien...). Le corpus est en
francais : le latin de base et le latin etendu suffisent. Prendre le
reste ferait tripler le poids pour des caracteres jamais affiches.
"""

from __future__ import annotations

import pathlib
import re
import urllib.request

AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Le serif sert aussi aux extraits d'articles, pas seulement aux titres :
# il lui faut donc le poids normal (400) en plus des poids de titrage.
DEMANDE = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600"
    "&family=Source+Serif+4:wght@400;600;700"
    "&display=swap"
)

SOUS_ENSEMBLES_GARDES = ("latin", "latin-ext")

# Les .woff2 vont dans public/ (copies tels quels par Angular), la
# feuille dans src/ (compilee avec le reste : une requete de moins, et
# les @font-face arrivent avec la premiere feuille au lieu d'attendre
# une cascade de telechargements).
RACINE = pathlib.Path(__file__).resolve().parent.parent
DESTINATION = RACINE / "public" / "polices"
FEUILLE = RACINE / "src" / "_polices.scss"


def lire(url: str) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        return reponse.read()


def nom_fichier(famille: str, graisse: str, sous_ensemble: str) -> str:
    return f"{famille.replace(' ', '-').lower()}-{graisse}-{sous_ensemble}.woff2"


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    css = lire(DEMANDE).decode("utf-8")

    # Chaque bloc @font-face est precede d'un commentaire nommant le
    # sous-ensemble : c'est ce commentaire qui permet de trier.
    blocs = re.findall(r"/\* (\S+) \*/\s*(@font-face \{.*?\})", css, re.S)
    print(f"{len(blocs)} blocs @font-face recus")

    regles = []
    poids_total = 0
    for sous_ensemble, bloc in blocs:
        if sous_ensemble not in SOUS_ENSEMBLES_GARDES:
            continue

        famille = re.search(r"font-family: '([^']+)'", bloc).group(1)
        graisse = re.search(r"font-weight: (\d+)", bloc).group(1)
        source = re.search(r"url\((https://[^)]+\.woff2)\)", bloc).group(1)
        plage = re.search(r"unicode-range: ([^;]+);", bloc)

        nom = nom_fichier(famille, graisse, sous_ensemble)
        octets = lire(source)
        (DESTINATION / nom).write_bytes(octets)
        poids_total += len(octets)
        print(f"  {nom:44s} {len(octets) // 1024:4d} Ko")

        regles.append(
            "@font-face {\n"
            f"  font-family: '{famille}';\n"
            "  font-style: normal;\n"
            f"  font-weight: {graisse};\n"
            "  font-display: swap;\n"
            f"  src: url('/polices/{nom}') format('woff2');\n"
            + (f"  unicode-range: {plage.group(1)};\n" if plage else "")
            + "}\n"
        )

    entete = (
        "/* Polices embarquees — NE PAS MODIFIER A LA MAIN.\n"
        " *\n"
        " * Genere par scripts/telecharger_polices.py. Les fichiers sont\n"
        " * servis depuis public/polices/ : aucune requete vers un CDN, donc\n"
        " * aucune dependance reseau pour afficher la bonne typographie.\n"
        " *\n"
        " * font-display: swap — le texte s'affiche immediatement dans la\n"
        " * police de repli puis bascule. Sur une connexion lente, mieux\n"
        " * vaut un texte lisible tout de suite qu'une page blanche.\n"
        " */\n\n"
    )
    FEUILLE.write_text(entete + "\n".join(regles), encoding="utf-8")
    print(f"\ntotal {poids_total // 1024} Ko dans {DESTINATION}")
    print(f"feuille : {FEUILLE}")


if __name__ == "__main__":
    main()
