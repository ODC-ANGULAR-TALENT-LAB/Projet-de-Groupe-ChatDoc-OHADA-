# Regles de minification.
#
# R8 supprime tout ce qu'il ne voit appele nulle part. C'est ce qui fait
# passer l'APK de 3,2 Mo a une fraction de cette taille — mais c'est
# aussi ce qui casse, en silence, le code appele depuis l'EXTERIEUR du
# bytecode : R8 ne lit pas le JavaScript de la page web.

# ---------------------------------------------------------------------
# LE PONT DE TELECHARGEMENT — LA REGLE A NE PAS PERDRE
# ---------------------------------------------------------------------
# Les methodes annotees @JavascriptInterface ne sont appelees QUE depuis
# la page, par leur nom. Aucune reference n'existe dans le bytecode :
# sans cette regle, R8 les considere comme du code mort, les supprime, et
# les renomme. L'export PDF echouerait alors dans un silence total —
# l'utilisateur touche le bouton, rien ne se passe, aucune erreur.
#
# `class *` et non le nom du pont : une classe interne minifiee change de
# nom, et une regle nommee cesserait de s'appliquer au premier
# remaniement.
-keepclasseswithmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# ---------------------------------------------------------------------
# LE NOM DES METHODES DU PONT DOIT SURVIVRE
# ---------------------------------------------------------------------
# `recevoir` est ecrit en toutes lettres dans le script injecte
# (Telechargements.scriptDeLecture). Renommee en `a`, elle deviendrait
# introuvable depuis la page.
-keepclassmembernames class * {
    @android.webkit.JavascriptInterface <methods>;
}

# ---------------------------------------------------------------------
# BUILDCONFIG
# ---------------------------------------------------------------------
# URL_APPLICATION y est injectee au build. R8 sait la remplacer par sa
# valeur, mais on garde la classe : c'est ce qui permet de verifier dans
# un APK publie sur quelle URL il a ete construit.
-keep class cm.chatdocs.ohada.BuildConfig { *; }

# ---------------------------------------------------------------------
# TRACES LISIBLES
# ---------------------------------------------------------------------
# Sans ces attributs, un rapport de plantage ne designe plus ni fichier
# ni ligne. Ils ne coutent que quelques kilo-octets.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
