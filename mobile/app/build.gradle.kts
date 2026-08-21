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
            // PAS DE MINIFICATION. L'application ne contient qu'une
            // activite : il n'y a rien a reduire, et ProGuard
            // n'apporterait que des risques d'obfuscation mal reglee.
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
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
}
