package cm.chatdocs.ohada

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback

/**
 * ChatDocs OHADA — coquille Android.
 *
 * CE QUE CETTE APPLICATION EST, ET CE QU'ELLE N'EST PAS. Elle ouvre le
 * site déployé dans un WebView plein écran. Elle ne réimplémente rien :
 * le corpus, la recherche et l'assistant restent côté web, et une
 * correction du site profite immédiatement à l'application, sans
 * republier d'APK.
 *
 * POURQUOI PAS UNE TRUSTED WEB ACTIVITY. Une TWA supprimerait la barre
 * d'adresse, mais elle exige un fichier `assetlinks.json` servi par le
 * domaine ET une empreinte de clé de signature stable. Tant que le
 * domaine n'est pas figé, la TWA afficherait justement cette barre.
 * Comme le WebView gère les service workers, la bibliothèque reste
 * consultable hors ligne — l'avantage principal de la TWA disparaît.
 */
/*
 * COMPONENTACTIVITY ET NON APPCOMPATACTIVITY. AppCompat retro-porte des
 * composants d'interface — barres d'action, boutons, menus — dont une
 * coquille WebView n'utilise pas un seul. Elle pesait pourtant l'essentiel
 * de l'APK, et un fichier plus lourd se telecharge plus longtemps, donc
 * casse plus souvent sur un reseau mobile.
 *
 * `onBackPressedDispatcher`, la seule chose dont on avait besoin, vient
 * d'androidx.activity — pas d'AppCompat.
 */
class ActivitePrincipale : ComponentActivity() {

    private lateinit var vue: WebView
    private lateinit var messageHorsLigne: TextView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(etatSauvegarde: Bundle?) {
        super.onCreate(etatSauvegarde)
        setContentView(R.layout.activite_principale)

        vue = findViewById(R.id.vue_web)
        messageHorsLigne = findViewById(R.id.message_hors_ligne)

        vue.setBackgroundColor(Color.parseColor("#F4F2EC"))
        configurer(vue.settings)
        vue.webViewClient = ClientWeb()

        // SANS CECI, AUCUN TELECHARGEMENT NE FONCTIONNE. Un WebView
        // ignore purement et simplement les liens de telechargement tant
        // qu'on ne lui pose pas de DownloadListener : l'export PDF d'une
        // reponse ne produisait donc aucun effet dans l'application, et
        // rien ne le signalait — ni erreur, ni message.
        Telechargements.installer(vue, this)

        // Restaurer l'état évite de recharger la page à chaque rotation :
        // sans cela, une rotation renverrait l'utilisateur à l'accueil et
        // lui ferait perdre sa question en cours.
        if (etatSauvegarde != null) {
            vue.restoreState(etatSauvegarde)
        } else {
            vue.loadUrl(BuildConfig.URL_APPLICATION)
        }

        // LE BOUTON RETOUR DOIT NAVIGUER, PAS QUITTER. Sans cela, revenir
        // en arrière depuis un article fermerait l'application — le
        // réflexe le plus courant sur Android deviendrait le plus
        // destructeur.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (vue.canGoBack()) vue.goBack() else finish()
            }
        })
    }

    private fun configurer(reglages: WebSettings) {
        // L'application est une SPA Angular : sans JavaScript, elle
        // n'affiche rien du tout.
        reglages.javaScriptEnabled = true
        // Le jeton de session vit dans localStorage.
        reglages.domStorageEnabled = true
        // C'est ce qui préserve le cache hors ligne de la PWA, et donc la
        // consultation de la bibliothèque sans réseau.
        reglages.cacheMode = WebSettings.LOAD_DEFAULT
        reglages.databaseEnabled = true
        // Le site est responsive : on le laisse gérer sa mise en page
        // plutôt que d'imposer un zoom de bureau.
        reglages.useWideViewPort = true
        reglages.loadWithOverviewMode = true
        reglages.setSupportZoom(true)
        reglages.builtInZoomControls = true
        reglages.displayZoomControls = false
    }

    override fun onSaveInstanceState(etat: Bundle) {
        super.onSaveInstanceState(etat)
        vue.saveState(etat)
    }

    private inner class ClientWeb : WebViewClient() {

        /**
         * Ce qui reste dans l'application, et ce qui en sort.
         *
         * LA CONNEXION GOOGLE IMPOSE CE PARTAGE. Google refuse
         * catégoriquement de s'authentifier dans un WebView — la page
         * répond « navigateur non sécurisé ». Garder ces liens ici
         * rendrait la connexion Google impossible sans le moindre
         * message utile.
         */
        override fun shouldOverrideUrlLoading(
            vueAppelante: WebView,
            requete: WebResourceRequest,
        ): Boolean {
            val destination = requete.url
            val hote = destination.host ?: return false

            if (hote == hoteDeLApplication()) return false

            return try {
                startActivity(Intent(Intent.ACTION_VIEW, destination))
                true
            } catch (_: ActivityNotFoundException) {
                // Aucune application pour ce lien (tel:, mailto: sans
                // client). Mieux vaut ne rien faire que planter.
                true
            }
        }

        override fun onPageFinished(vueAppelante: WebView, url: String) {
            messageHorsLigne.visibility = View.GONE
            vue.visibility = View.VISIBLE
        }

        /**
         * Hors ligne : un message lisible, pas la page d'erreur de Chrome.
         *
         * On ne masque l'application que si RIEN n'a pu être chargé. Une
         * ressource secondaire en échec — une image, une police — ne doit
         * pas effacer une page par ailleurs utilisable.
         */
        override fun onReceivedError(
            vueAppelante: WebView,
            requete: WebResourceRequest,
            erreur: android.webkit.WebResourceError,
        ) {
            if (!requete.isForMainFrame) return
            vue.visibility = View.GONE
            messageHorsLigne.visibility = View.VISIBLE
        }
    }

    private fun hoteDeLApplication(): String =
        Uri.parse(BuildConfig.URL_APPLICATION).host ?: ""
}
