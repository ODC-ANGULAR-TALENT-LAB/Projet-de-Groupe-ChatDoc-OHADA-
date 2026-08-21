# Lance l'API et la maintient en marche.
#
#     powershell -ExecutionPolicy Bypass -File scripts\demarrer_api.ps1
#
# POURQUOI CE SCRIPT EXISTE. L'API tombait regulierement, et pour deux
# raisons distinctes qu'il fallait traiter separement.
#
#   1. LANCEE DEPUIS UN TERMINAL, elle meurt avec lui. Fermer la
#      fenetre, terminer une session, redemarrer un shell : le
#      processus part avec son parent.
#
#   2. "--reload" EST UN PIEGE SUR WINDOWS. Le rechargeur lance un
#      processus ENFANT qui herite de la socket d'ecoute. Quand le
#      parent meurt sans emporter l'enfant, celui-ci garde le port 8000
#      tout en servant l'ANCIEN code : l'API repond, mais les routes
#      ajoutees depuis renvoient 404. Le symptome est trompeur au
#      possible : on croit a une erreur de code alors que c'est un
#      fantome qui repond.
#
# Ce script traite les deux. Il tourne sans "--reload", et se relance
# automatiquement si le processus s'arrete. Le prix a payer est qu'il
# faut le redemarrer apres une modification du code : echange
# volontaire, mieux vaut un redemarrage explicite qu'un serveur qui
# ment sur ce qu'il execute.
#
# NOTE D'ECRITURE : ni ponctuation typographique, ni operateur de
# redirection ("*>>", "2>&1"). Les premiers arrivent en mojibake quand
# PowerShell 5.1 lit un fichier UTF-8 sans BOM ; les seconds se parsent
# mal derriere une commande native. Start-Process rend les deux
# inutiles.

$ErrorActionPreference = "Stop"

$racine  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python  = Join-Path $racine ".venv\Scripts\python.exe"
$journal = Join-Path $racine "journal-api.log"
$erreurs = Join-Path $racine "journal-api-erreurs.log"

if (-not (Test-Path $python)) {
    Write-Host "  Interpreteur introuvable : $python"
    Write-Host "  Creez l'environnement : python -m venv .venv"
    exit 1
}

Set-Location $racine

# Liberer le port avant de demarrer. Un fantome qui l'occupe ferait
# echouer le demarrage sur un "address already in use" peu parlant, ou
# pire, laisserait l'ancien code repondre.
#
# ATTENTION : $pid est une variable AUTOMATIQUE de PowerShell, en
# lecture seule. L'employer comme variable de boucle fait echouer le
# script avant qu'il ait ouvert son journal, donc sans laisser de trace.
$occupants = netstat -ano | Select-String "LISTENING" | Select-String ":8000" |
    ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
foreach ($occupant in $occupants) {
    Write-Host "  Port 8000 occupe par $occupant : arret."
    taskkill /PID $occupant /T /F 2>&1 | Out-Null
}

Add-Content $journal "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] Demarrage du surveillant."

# BOUCLE DE SURVEILLANCE. Une exception non rattrapee, une coupure de la
# base, un plantage : le processus repart, au lieu de laisser
# l'application injoignable jusqu'a ce que quelqu'un s'en apercoive.
while ($true) {
    $debut = Get-Date

    # UVICORN TOURNE DANS CE PROCESSUS, sans intermediaire. Deux
    # tentatives ont echoue avant d'en arriver la, et les deux causes
    # meritent d'etre notees :
    #
    #   - Start-Process -RedirectStandardOutput ouvre le fichier en
    #     ECRASEMENT et echoue si le processus precedent tient encore le
    #     descripteur. Au premier redemarrage, le lancement echouait en
    #     silence : le journal annoncait « Redemarrage » et l'API
    #     restait injoignable.
    #
    #   - Passer par cmd /c pour rediriger echoue aussi : le chemin du
    #     projet contient des PARENTHESES — « (Groupe 6) » — et cmd les
    #     traite comme des operateurs de groupement. La commande se
    #     termine instantanement sans rien ecrire.
    #
    # L'appel direct evite les deux. La sortie d'uvicorn part dans la
    # console masquee de cette fenetre et n'est pas conservee ; seuls
    # les evenements de cycle de vie sont journalises. C'est un echange
    # assume : un serveur qui redemarre vaut mieux qu'un journal
    # complet sur un serveur eteint.
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

    $secondes = [int]((Get-Date) - $debut).TotalSeconds
    $quand = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')

    # Un arret quasi immediat signale une erreur de demarrage : import
    # casse, port pris, configuration absente. Redemarrer en boucle
    # serree noierait le journal sans rien resoudre. On attend.
    if ($secondes -lt 5) {
        Add-Content $journal "[$quand] Arret en $secondes s : erreur de demarrage probable. Voir journal-api-erreurs.log. Nouvelle tentative dans 15 s."
        Start-Sleep -Seconds 15
    } else {
        Add-Content $journal "[$quand] Processus arrete apres $secondes s. Redemarrage."
        Start-Sleep -Seconds 2
    }
}
