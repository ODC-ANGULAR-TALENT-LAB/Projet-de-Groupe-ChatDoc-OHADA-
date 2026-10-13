"""Capture une page dans les conditions d'un telephone.

DIFFERENCE AVEC LE BANC DE MESURE. Le banc chiffre : il compte les
debordements, les cibles trop petites, les polices trop fines. Il ne
voit pas un alignement. Un bandeau decale de 4 px ne casse aucune
regle et ne sort dans aucun releve — il se voit, et c'est tout.

D'ou cet outil : emulation d'appareil (viewport, densite, evenements
tactiles), puis capture. La densite a 3 donne une image ou l'on peut
mesurer un ecart de 1 px a l'oeil.

EMPLOI
  python outils/capturer.py <route> [largeur] [hauteur] [nom] [jeton] [selecteur-focus]
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import websockets

# Le serveur, le lancement de Chrome et le client DevTools sont deja
# ecrits a cote. Le module porte un tiret dans son nom, ce qu'un import
# ordinaire refuse : on le charge par son chemin.
_spec = importlib.util.spec_from_file_location(
    "mesurer_responsive", Path(__file__).resolve().parent / "mesurer-responsive.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Session = _mod.Session
lancer_chrome = _mod.lancer_chrome
arreter_chrome = _mod.arreter_chrome
servir = _mod.servir
OUTILS = _mod.OUTILS
PORT_DEBOGAGE = _mod.PORT_DEBOGAGE
PORT_SITE = _mod.PORT_SITE


def onglet_vide() -> str:
    requete = urllib.request.Request(
        f"http://127.0.0.1:{PORT_DEBOGAGE}/json/new?about:blank", method="PUT"
    )
    return json.loads(urllib.request.urlopen(requete).read())["webSocketDebuggerUrl"]


async def principal(
    route: str, largeur: int, hauteur: int, nom: str,
    jeton: str | None, focus: str | None = None,
):
    srv = servir()
    proc = lancer_chrome()
    try:
        async with websockets.connect(onglet_vide(), max_size=80 * 1024 * 1024) as ws:
            s = Session(ws)
            await s.appeler("Page.enable")
            await s.appeler("Runtime.enable")
            # `mobile: True` change plus que la taille : il active la
            # meta viewport et le rendu tactile. Sans lui on obtient une
            # fenetre etroite de poste de travail, pas un telephone.
            await s.appeler(
                "Emulation.setDeviceMetricsOverride",
                width=largeur,
                height=hauteur,
                deviceScaleFactor=3,
                mobile=True,
            )
            await s.appeler("Emulation.setTouchEmulationEnabled", enabled=True)

            await s.evaluer(
                f"location.href = 'http://127.0.0.1:{PORT_SITE}/'", attendre=False
            )
            await asyncio.sleep(2)
            await s.evaluer(
                "localStorage.setItem('chatdocs.jeton', %s); 1" % json.dumps(jeton)
                if jeton
                else "localStorage.clear(); 1"
            )
            await s.evaluer(
                f"location.href = 'http://127.0.0.1:{PORT_SITE}{route}'", attendre=False
            )
            await asyncio.sleep(3.5)

            if focus:
                # `focus-visible` ne s'active pas sur un appel direct a
                # `focus()` venu du script : le navigateur le reserve aux
                # interactions clavier. On simule donc une tabulation
                # depuis l'element precedent, ce qui est exactement le
                # geste qu'on veut photographier.
                await s.evaluer(
                    "document.querySelector(%s).focus(); 1" % json.dumps(focus)
                )
                await s.appeler(
                    "Input.dispatchKeyEvent", type="rawKeyDown", key="Tab",
                    windowsVirtualKeyCode=9, nativeVirtualKeyCode=9,
                )
                await s.appeler(
                    "Input.dispatchKeyEvent", type="keyUp", key="Tab",
                    windowsVirtualKeyCode=9, nativeVirtualKeyCode=9,
                )
                await asyncio.sleep(0.6)

            image = await s.appeler(
                "Page.captureScreenshot", format="png", captureBeyondViewport=False
            )
            sortie = OUTILS / f"{nom}.png"
            sortie.write_bytes(base64.b64decode(image["data"]))
            print(f"  {sortie}")
    finally:
        arreter_chrome(proc)
        srv.shutdown()


if __name__ == "__main__":
    route = sys.argv[1] if len(sys.argv) > 1 else "/"
    largeur = int(sys.argv[2]) if len(sys.argv) > 2 else 360
    hauteur = int(sys.argv[3]) if len(sys.argv) > 3 else 780
    nom = sys.argv[4] if len(sys.argv) > 4 else "capture"
    jeton = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "-" else None
    # Selecteur CSS optionnel : l'element recoit la mise au point avant
    # la capture, pour photographier l'anneau plutot que le repos.
    focus = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "-" else None
    asyncio.run(principal(route, largeur, hauteur, nom, jeton, focus))
