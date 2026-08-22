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
        versionCode = 1
        versionName = "1.0"

        // L'URL N'EST PAS ECRITE EN DUR, et ce n'est pas un detail : le
        // domaine de deploiement n'est pas encore fige. Elle vient de la
        // variable de depot URL_APPLICATION, injectee par le workflow.
        // Changer de domaine ne demandera donc pas de toucher au code —
        // seulement de relancer la construction.
        val urlApplication = (project.findProperty("urlApplication") as String?)
            ?: "https://chatdocs-ohada.vercel.app"
        buildConfigField("String", "URL_APPLICATION", "\"$urlApplication\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            // MINIFICATION ACTIVEE.
            //
            // Le raisonnement precedent — « une seule activite, rien a
            // reduire » — regardait le mauvais chiffre. Le code de
            // l'application tient en deux fichiers, mais celui des
            // BIBLIOTHEQUES pesait 2,7 Mo sur un APK de 3,2 Mo, soit
            // 83 %. R8 retire ce qui n'est jamais appele, ce qui est ici
            // la quasi-totalite.
            //
            // L'enjeu n'est pas l'elegance : un fichier plus lourd se
            // telecharge plus longtemps, et une coupure en cours de route
            // laisse l'utilisateur devant une barre bloquee a 100 %.
            // Mesure : une troncature sur quatre essais a 3,2 Mo.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }

        // LE BUILD DE DEBOGAGE RESTE INTACT. Tant qu'aucune cle de
        // signature n'est fournie, c'est LUI qui est publie (voir
        // .github/workflows/apk.yml) : le minifier priverait justement
        // l'APK distribue du benefice recherche. Il herite donc des
        // memes reglages que la release.
        debug {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
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
    // UNE SEULE DEPENDANCE, et elle sert a une seule chose :
    // `onBackPressedDispatcher`, qui fait que le bouton retour navigue
    // dans l'historique du WebView au lieu de fermer l'application.
    //
    // AppCompat a ete retiree : elle retro-porte des composants
    // d'interface — barres d'action, menus, boutons — dont une coquille
    // WebView n'utilise pas un seul, et elle pesait l'essentiel de l'APK.
    implementation("androidx.activity:activity-ktx:1.9.3")
}
