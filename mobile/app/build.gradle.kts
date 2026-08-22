import java.io.FileInputStream
import java.net.URI
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "cm.chatdocs.ohada"
    compileSdk = 34

    defaultConfig {
        applicationId = "cm.chatdocs.ohada"
        minSdk = 24          // Android 7 : couvre le parc reel au Cameroun
        targetSdk = 34
        versionCode = 2
        versionName = "2.0"

        // L'URL N'EST PAS ECRITE EN DUR, et ce n'est pas un detail : le
        // domaine de deploiement peut changer. Elle vient de la variable
        // de depot URL_APPLICATION, injectee par le workflow.
        val urlApplication = (project.findProperty("urlApplication") as String?)
            ?: "https://chatdocs-web.onrender.com"

        // L'HOTE EST DERIVE, JAMAIS SAISI DEUX FOIS. Le manifeste a besoin
        // du domaine nu pour son filtre d'intention, la Trusted Web
        // Activity de l'URL complete. Les tenir a jour separement, c'est
        // se garantir qu'ils divergeront un jour — et le symptome serait
        // muet : l'application s'ouvrirait avec une barre d'adresse, sans
        // qu'aucune erreur ne l'explique.
        val hote = URI(urlApplication).host
            ?: error("urlApplication doit etre une URL absolue : $urlApplication")

        resValue("string", "url_application", urlApplication)
        resValue("string", "hote_application", hote)
    }

    // SIGNATURE DE PRODUCTION, LUE DANS L'ENVIRONNEMENT.
    //
    // Elle n'est plus optionnelle depuis le passage en Trusted Web
    // Activity : Android compare l'empreinte du certificat a celle
    // declaree dans assetlinks.json, et une cle de debogage — differente
    // sur chaque machine — ne peut correspondre a rien. L'application
    // s'ouvrirait alors avec la barre d'adresse de Chrome.
    //
    // Le magasin de cles ne figure JAMAIS dans le depot : le workflow
    // l'ecrit depuis un secret, le temps de la construction.
    val magasin = System.getenv("ANDROID_KEYSTORE_CHEMIN")
    signingConfigs {
        if (magasin != null && file(magasin).exists()) {
            create("production") {
                storeFile = file(magasin)
                storePassword = System.getenv("ANDROID_KEYSTORE_MOT_DE_PASSE")
                keyAlias = System.getenv("ANDROID_CLE_ALIAS")
                keyPassword = System.getenv("ANDROID_CLE_MOT_DE_PASSE")
                    ?: System.getenv("ANDROID_KEYSTORE_MOT_DE_PASSE")
            }
        }
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            // MINIFICATION ACTIVEE. Le code de l'application est
            // minuscule, mais celui des bibliotheques ne l'est pas : R8
            // retire ce qui n'est jamais appele, ce qui est ici la
            // quasi-totalite.
            //
            // L'enjeu n'est pas l'elegance : un fichier plus lourd se
            // telecharge plus longtemps, et une coupure en cours de route
            // laisse l'utilisateur devant une barre bloquee a 100 %.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (magasin != null && file(magasin).exists()) {
                signingConfig = signingConfigs.getByName("production")
            }
        }

        // Le build de debogage sert aux essais locaux. Il n'est PLUS
        // publie : une TWA signee en debogage ne peut pas etre verifiee
        // par le domaine, et s'ouvrirait avec une barre d'adresse.
        debug {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // La seule dependance. Elle apporte LauncherActivity, qui ouvre le
    // site dans le navigateur en mode Trusted Web Activity, gere l'ecran
    // d'attente et retombe proprement sur un onglet personnalise quand
    // aucun navigateur du telephone ne sait faire mieux.
    implementation("com.google.androidbrowserhelper:androidbrowserhelper:2.5.0")
}
