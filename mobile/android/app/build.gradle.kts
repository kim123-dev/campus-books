import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// 릴리스 서명 정보는 android/key.properties에서 읽는다. 키와 비밀번호를 저장소에 남기지 않으려고(.gitignore에 있음).
val keystoreProperties = Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}
val hasReleaseKey = keystoreProperties.getProperty("storeFile") != null

android {
    namespace = "com.kim123dev.campusbooks"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.kim123dev.campusbooks"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKey) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // 디버그 키로 서명된 릴리스가 남에게 나가지 않게, 업로드 키가 없으면 아래에서 빌드를 멈춘다.
            if (hasReleaseKey) signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// 릴리스 빌드인데 key.properties가 없으면 서명 안 된 APK 대신 이유를 알려 주고 멈춘다. (디버그 빌드는 상관없음)
gradle.taskGraph.whenReady {
    if (!hasReleaseKey && allTasks.any { it.project == project && it.name.contains("Release") }) {
        throw GradleException("android/key.properties가 없어 릴리스 APK에 서명할 수 없습니다. 서명 키를 만든 뒤 다시 빌드해 주세요.")
    }
}
