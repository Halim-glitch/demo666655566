// android_project/app/build.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "org.fatih.markliv"
    compileSdk = 34

    defaultConfig {
        applicationId = "org.fatih.markliv"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }

        python {
            version = "3.11"
            pip {
                install("requests>=2.31")
                install("urllib3")
                install("certifi")
                install("charset-normalizer")
                install("idna")
                install("numpy>=1.24")
                install("websockets>=12.0")
                install("aiohttp>=3.9")
                install("pydantic>=2.0")
                install("fastapi>=0.110")
                install("uvicorn>=0.27")
                install("cryptography")
            }
        }
    }

    sourceSets {
        getByName("main") {
            python.srcDir("src/main/python")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
}
