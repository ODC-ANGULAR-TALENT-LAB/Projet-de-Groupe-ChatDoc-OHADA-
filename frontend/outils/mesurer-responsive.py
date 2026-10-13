"""Mesure le rendu de l'application a plusieurs largeurs d'ecran.

CE QUE CET OUTIL REMPLACE. Ouvrir les outils de developpement, activer
le mode appareil, choisir une taille, regarder, changer de taille,
recommencer pour chaque page. Ce geste ne laisse aucune trace : on ne
peut ni relire ce qu'on a vu la fois d'avant, ni prouver qu'une
correction a bien pris. A dix-sept pages et quatre largeurs, il faudrait
soixante-huit inspections a la main pour un seul passage.

Ici Chrome est pilote par le protocole DevTools, chaque route est
chargee dans un cadre de largeur fixe, et chaque constat sort avec la
page, la largeur et l'element en cause. Deux executions se comparent
ligne a ligne.

POURQUOI UN CADRE ET NON UNE FENETRE REDIMENSIONNEE. Les media queries
repondent a la largeur du CADRE autant qu'a celle de la fenetre. Un
`iframe` de 320 px declenche exactement les memes regles qu'un telephone
de 320 px, sans avoir a redimensionner quoi que ce soit entre deux
mesures.

LES QUATRE LARGEURS. 320 px est le plancher reel du parc Android
(Galaxy Fold ferme, appareils d'entree de gamme anciens) ; 360 px est la
largeur la plus repandue en Afrique de l'Ouest et centrale, donc celle
des utilisateurs vises ; 375 px couvre les iPhone jusqu'au SE ; 412 px
les Android recents. Au-dela, la mise en page bascule sur les regles de
tablette et ce n'est plus du telephone.

CE QUI EST VERIFIE
  1. Debordement horizontal — l'element fautif, pas la page.
  2. Cibles tactiles sous 44 px (Apple HIG ; Material demande 48 dp).
  3. Champs sous 16 px de police, seuil en deca duquel iOS agrandit
     la page a la mise au point.
  4. Texte rogne sans `text-overflow: ellipsis`.

EMPLOI
  1. Compiler :  npx ng build --configuration development
  2. Lancer l'API locale sur le port 8000, si l'on veut les pages qui
     exigent une session.
  3. python outils/mesurer-responsive.py [jeton]

Sans jeton, seules les pages publiques sont mesurees. Avec, les deux
series le sont — le jeton est pose puis retire entre chaque page, car
une session ouverte redirige « / » et « /inscription » vers le tableau
de bord et l'on mesurerait trois fois la meme page.

Le fichier `banc-responsive.html` est copie dans le paquet compile le
temps de la mesure, puis retire. Il n'est pas dans `public/`, dont le
contenu part integralement en production.
"""

from __future__ import annotations

import asyncio
import http.server
import io
import json
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import websockets

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OUTILS = Path(__file__).resolve().parent
FRONTEND = OUTILS.parent
DIST = FRONTEND / "dist" / "frontend" / "browser"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT_DEBOGAGE = 9222
PORT_SITE = 4321
# UN PROFIL NEUF A CHAQUE LANCEMENT, jete a la fin. Un profil partage
# garde un verrou que Chrome ne relache pas toujours quand il est tue :
# l'execution suivante echouait alors sur « Chrome ne repond pas », et
# le diagnostic accusait le lancement au lieu du nettoyage. Un
# repertoire temporaire coute une seconde et supprime la classe entiere
# de pannes.
PROFIL = None
BANC = f"http://127.0.0.1:{PORT_SITE}/banc-responsive.html"

LARGEURS = [320, 360, 375, 412]

ROUTES_PUBLIQUES = [
    ("/", "Accueil public"),
    ("/connexion", "Connexion"),
    ("/inscription", "Inscription"),
    ("/bibliotheque", "Bibliotheque"),
    ("/methodologie", "Methodologie"),
    ("/forfaits", "Forfaits"),
    ("/journal", "Journal"),
    ("/cgu", "CGU"),
]
ROUTES_PRIVEES = [
    ("/chat", "Conversation"),
    ("/accueil", "Tableau de bord"),
    ("/favoris", "Favoris"),
    ("/conformite", "Conformite"),
    ("/calculateurs", "Calculateurs"),
    ("/parametres", "Parametres"),
    ("/historique", "Historique"),
    ("/compte", "Compte"),
    ("/avis", "Avis"),
]


# --- Le site -------------------------------------------------------
# Les routes sont gerees par le navigateur : tout chemin inconnu doit
# rendre index.html, sinon /chat repond 404 et l'on mesure une page
# d'erreur en croyant mesurer la conversation.


class Repli(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DIST), **kw)

    def do_GET(self):  # noqa: N802
        chemin = DIST / self.path.lstrip("/").split("?")[0]
        if self.path != "/" and not chemin.is_file():
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, *a):
        pass


def servir() -> socketserver.TCPServer:
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT_SITE), Repli)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# --- Le navigateur -------------------------------------------------


def arreter_chrome(proc: subprocess.Popen) -> None:
    """Tue l'arbre de processus, pas seulement la racine.

    Chrome se disperse en une dizaine de processus (rendu, GPU, reseau,
    utilitaires). `terminate()` n'atteint que celui qu'on a lance : les
    autres survivent, gardent le verrou du profil et le port de
    debogage, et l'execution suivante echoue sur « Chrome ne repond pas »
    — un message qui accuse le lancement alors que la faute est au
    nettoyage precedent.
    """
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Le processus rend la main avant que Windows ne libere le port :
    # deux executions qui se suivent tombaient sur « port deja pris »
    # alors que le Chrome precedent etait bel et bien mort.
    for _ in range(40):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{PORT_DEBOGAGE}/json/version", timeout=1
            )
            time.sleep(0.25)
        except (urllib.error.URLError, TimeoutError, OSError):
            break

    profil = getattr(proc, "profil", None)
    if profil:
        shutil.rmtree(profil, ignore_errors=True)


def lancer_chrome() -> subprocess.Popen:
    # Un Chrome oublie par une execution precedente tient le port et
    # rendrait les mesures muettes. On le dit tout de suite.
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT_DEBOGAGE}/json/version", timeout=1
        )
        raise SystemExit(
            f"Le port {PORT_DEBOGAGE} est deja pris par un Chrome en cours.\n"
            f"  taskkill /F /IM chrome.exe /T"
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    profil = Path(tempfile.mkdtemp(prefix="chatdocs-chrome-"))
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            f"--remote-debugging-port={PORT_DEBOGAGE}",
            f"--user-data-dir={profil}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--window-size=1280,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.profil = profil  # relu par arreter_chrome pour le menage
    for _ in range(60):
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{PORT_DEBOGAGE}/json/version", timeout=1
            )
            return proc
        except Exception:
            time.sleep(0.5)
    arreter_chrome(proc)
    raise RuntimeError("Chrome ne repond pas sur le port de debogage")


def onglet() -> str:
    # /json/new exige PUT depuis Chrome 111 ; urlopen ne prend pas de
    # methode en argument, il faut passer par une Request.
    requete = urllib.request.Request(
        f"http://127.0.0.1:{PORT_DEBOGAGE}/json/new?{BANC}", method="PUT"
    )
    return json.loads(urllib.request.urlopen(requete).read())["webSocketDebuggerUrl"]


class Session:
    def __init__(self, ws):
        self.ws = ws
        self.n = 0

    async def appeler(self, methode: str, **params):
        self.n += 1
        await self.ws.send(
            json.dumps({"id": self.n, "method": methode, "params": params})
        )
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]

    async def evaluer(self, expression: str, attendre: bool = True):
        resultat = await self.appeler(
            "Runtime.evaluate",
            expression=expression,
            awaitPromise=attendre,
            returnByValue=True,
        )
        if resultat.get("exceptionDetails"):
            details = resultat["exceptionDetails"]
            objet = details.get("exception") or {}
            raise RuntimeError(
                objet.get("description") or objet.get("value") or details.get("text")
            )
        return resultat["result"].get("value")


# --- La campagne ---------------------------------------------------


async def principal(jeton: str | None, routes):
    if not (DIST / "index.html").is_file():
        raise SystemExit(
            "Paquet introuvable. Compiler d'abord :\n"
            "  npx ng build --configuration development"
        )

    copie = DIST / "banc-responsive.html"
    shutil.copy(OUTILS / "banc-responsive.html", copie)
    srv = servir()
    proc = lancer_chrome()
    try:
        async with websockets.connect(onglet(), max_size=40 * 1024 * 1024) as ws:
            s = Session(ws)
            await s.appeler("Page.enable")
            await s.appeler("Runtime.enable")
            await s.evaluer(f"location.href = {json.dumps(BANC)}", attendre=False)
            await asyncio.sleep(3)

            tout = []
            for route, nom in routes:
                # La session est posee ou retiree AVANT chaque page. Une
                # session ouverte ne fait pas que deverrouiller les pages
                # privees : elle redirige « / » et « /inscription » vers
                # le tableau de bord.
                prive = (route, nom) in ROUTES_PRIVEES
                await s.evaluer(
                    "localStorage.setItem('chatdocs.jeton', %s); 1" % json.dumps(jeton)
                    if (prive and jeton)
                    else "localStorage.removeItem('chatdocs.jeton'); 1"
                )
                for largeur in LARGEURS:
                    try:
                        r = await s.evaluer(f"mesurer({json.dumps(route)}, {largeur})")
                    except Exception as e:
                        print(f"  !! {nom} {largeur}px : {e}")
                        continue
                    r["nom"] = nom
                    tout.append(r)
                    n = len(r["constats"])
                    etat = "ok" if n == 0 and not r["defilementPage"] else f"{n} constat(s)"
                    defile = " + DEFILEMENT HORIZONTAL" if r["defilementPage"] else ""
                    print(f"  {nom:18} {largeur}px  {etat}{defile}")

            sortie = OUTILS / "constats-responsive.json"
            sortie.write_text(
                json.dumps(tout, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            total = sum(len(r["constats"]) for r in tout)
            print(f"\n  {len(tout)} mesures, {total} constat(s)")
            print(f"  detail : {sortie}")
    finally:
        arreter_chrome(proc)
        srv.shutdown()
        copie.unlink(missing_ok=True)


if __name__ == "__main__":
    jeton = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else None
    asyncio.run(principal(jeton, ROUTES_PUBLIQUES + (ROUTES_PRIVEES if jeton else [])))
