package cm.chatdocs.ohada

import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.MimeTypeMap
import android.webkit.URLUtil
import android.webkit.WebView
import android.widget.Toast
import java.io.File
import java.io.FileOutputStream

/**
 * Téléchargements depuis le WebView.
 *
 * POURQUOI CE FICHIER EXISTE. Un WebView ne télécharge RIEN par défaut :
 * sans `DownloadListener`, un clic sur un lien de téléchargement ne
 * produit strictement aucun effet — pas d'erreur, pas de message, rien.
 * L'export PDF d'une réponse était donc inopérant dans l'application,
 * alors qu'il fonctionne dans un navigateur.
 *
 * DEUX CHEMINS, PARCE QU'IL Y A DEUX SORTES D'URL.
 *
 *   http(s):  le fichier vit sur un serveur. On délègue au
 *             DownloadManager d'Android, qui gère la notification, la
 *             reprise et l'ouverture du fichier.
 *
 *   blob:     le fichier a été CONSTRUIT dans la page. C'est le cas de
 *             l'export PDF : le frontend récupère le document par XHR —
 *             en portant le jeton d'authentification, qu'une URL ne peut
 *             pas transmettre — puis fabrique un blob local.
 *
 *             Le DownloadManager est incapable de lire un blob : cette
 *             URL n'existe que dans le moteur de rendu. Il faut donc
 *             redemander son contenu au JavaScript de la page, en
 *             base64, et l'écrire nous-mêmes.
 */
object Telechargements {

    /** Où le pont JavaScript est exposé à la page. */
    private const val PONT = "AndroidTelechargement"

    fun installer(vue: WebView, contexte: Context) {
        vue.addJavascriptInterface(PontBlob(contexte), PONT)

        vue.setDownloadListener { url, agent, disposition, typeMime, _ ->
            if (url.startsWith("blob:")) {
                vue.evaluateJavascript(scriptDeLecture(url, typeMime), null)
            } else {
                telechargerParLeSysteme(contexte, url, agent, disposition, typeMime)
            }
        }
    }

    private fun telechargerParLeSysteme(
        contexte: Context,
        url: String,
        agent: String?,
        disposition: String?,
        typeMime: String?,
    ) {
        val nom = URLUtil.guessFileName(url, disposition, typeMime)
        val requete = DownloadManager.Request(Uri.parse(url)).apply {
            setMimeType(typeMime)
            setTitle(nom)
            setDescription(contexte.getString(R.string.telechargement_en_cours))
            setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
            )
            setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nom)
            // LES COOKIES SUIVENT LA REQUETE. Le DownloadManager est un
            // service systeme : il ne partage pas la session du WebView.
            // Sans cet en-tete, une ressource protegee reviendrait en 401,
            // et l'utilisateur recevrait une page d'erreur nommee .pdf.
            CookieManager.getInstance().getCookie(url)?.let {
                addRequestHeader("Cookie", it)
            }
            agent?.let { addRequestHeader("User-Agent", it) }
        }

        val service =
            contexte.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        service.enqueue(requete)
        Toast.makeText(
            contexte,
            contexte.getString(R.string.telechargement_en_cours),
            Toast.LENGTH_SHORT,
        ).show()
    }

    /**
     * Le script qui relit le blob et le renvoie en base64.
     *
     * On passe par XMLHttpRequest et non fetch() : le WebView de
     * minSdk 24 (Android 7) ne connait pas toujours fetch(), et cette
     * application vise justement le parc ancien.
     */
    private fun scriptDeLecture(url: String, typeMime: String?): String = """
        (function() {
          var requete = new XMLHttpRequest();
          requete.open('GET', '$url', true);
          requete.responseType = 'blob';
          requete.onload = function() {
            if (requete.status !== 200 && requete.status !== 0) return;
            var lecteur = new FileReader();
            lecteur.onloadend = function() {
              $PONT.recevoir(lecteur.result, '${typeMime ?: "application/octet-stream"}');
            };
            lecteur.readAsDataURL(requete.response);
          };
          requete.send();
        })();
    """.trimIndent()

    /**
     * Le pont par lequel la page rend le contenu du blob.
     *
     * SURFACE VOLONTAIREMENT MINIMALE. Un objet expose a JavaScript est
     * atteignable par TOUTE page chargee dans le WebView. Une seule
     * methode, qui ne fait qu'ecrire un fichier dans le dossier des
     * telechargements : elle ne lit rien, n'ouvre rien, et ne peut pas
     * servir a atteindre le reste de l'appareil.
     */
    private class PontBlob(private val contexte: Context) {

        @JavascriptInterface
        fun recevoir(donneesUrl: String, typeMime: String) {
            val separateur = donneesUrl.indexOf(",")
            if (separateur < 0) return

            val octets = try {
                Base64.decode(donneesUrl.substring(separateur + 1), Base64.DEFAULT)
            } catch (_: IllegalArgumentException) {
                return
            }

            val extension =
                MimeTypeMap.getSingleton().getExtensionFromMimeType(typeMime) ?: "bin"
            val nom = "chatdocs-${System.currentTimeMillis()}.$extension"

            // DEUX ECRITURES, PARCE QU'ANDROID A CHANGE DE REGLE EN
            // COURS DE ROUTE. Depuis Android 10 (API 29), le stockage
            // cloisonne interdit d'ecrire directement dans le dossier
            // public Telechargements : un FileOutputStream y leve une
            // exception, meme avec la permission declaree. Il faut
            // passer par MediaStore, qui rend une URI.
            //
            // En dessous, MediaStore.Downloads n'existe pas, et le
            // chemin direct reste la seule voie — d'ou la permission
            // WRITE_EXTERNAL_STORAGE, limitee a l'API 28 dans le
            // manifeste.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val valeurs = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, nom)
                    put(MediaStore.Downloads.MIME_TYPE, typeMime)
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val resolveur = contexte.contentResolver
                val cible = resolveur.insert(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI, valeurs
                ) ?: return
                resolveur.openOutputStream(cible)?.use { it.write(octets) }
                valeurs.clear()
                valeurs.put(MediaStore.Downloads.IS_PENDING, 0)
                resolveur.update(cible, valeurs, null, null)
            } else {
                val dossier =
                    Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_DOWNLOADS
                    )
                dossier.mkdirs()
                FileOutputStream(File(dossier, nom)).use { it.write(octets) }
            }

            // Le Toast doit revenir sur le fil principal : cette methode
            // est appelee depuis le fil du moteur JavaScript.
            android.os.Handler(contexte.mainLooper).post {
                Toast.makeText(
                    contexte,
                    contexte.getString(R.string.telechargement_termine, nom),
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }
}
