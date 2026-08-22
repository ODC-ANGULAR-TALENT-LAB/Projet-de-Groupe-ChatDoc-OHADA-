# Regles de minification.
#
# R8 supprime tout ce qu'il ne voit appele nulle part. C'est ce qui fait
# passer l'APK de plusieurs megaoctets a une fraction de cette taille.
#
# LE PONT @JavascriptInterface A DISPARU avec le WebView : les
# telechargements et l'export PDF sont desormais geres par le navigateur,
# qui n'a besoin d'aucun code de notre part. Une regle de moins a
# maintenir, et un point de rupture de moins.

# La bibliotheque de Trusted Web Activity communique avec le navigateur
# par des services et des rappels que R8 ne voit appeles nulle part.
-keep class com.google.androidbrowserhelper.** { *; }
-keep class androidx.browser.trusted.** { *; }

# BuildConfig porte la trace de l'URL de construction : c'est ce qui
# permet de verifier, sur un APK publie, sur quel site il ouvre.
-keep class cm.chatdocs.ohada.BuildConfig { *; }

# Sans ces attributs, un rapport de plantage ne designe plus ni fichier
# ni ligne. Ils ne coutent que quelques kilo-octets.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
