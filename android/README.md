# RESTai Mobile — Android client

This is the **Android** implementation of RESTai's Mobile pairing
protocol. A minimal Android app that pairs with a RESTai project via
QR code (generated from the project's **Mobile** tab) and exposes it as
a streaming chat — ChatGPT-style.

Future platforms (iOS, etc.) can implement the same QR payload and will
live in sibling folders.

## Architecture

- **Kotlin + Jetpack Compose + Material 3** for the UI.
- **ML Kit Barcode Scanning** + **CameraX** for the one-time QR scan.
- **OkHttp** `fetchEventSource`-style reader for SSE streaming against
  `POST /projects/{id}/chat` with `stream=true`.
- Credentials persisted in **EncryptedSharedPreferences**
  (AES-256-GCM, androidx.security.crypto).

## QR payload

The RESTai project **Mobile** tab generates a QR with this JSON:

```json
{
  "host": "https://restai.example.com",
  "project_id": 42,
  "project_name": "my-support-bot",
  "api_key": "xxxxxxxxxx"
}
```

- `host` is used as the base URL.
- `api_key` is a read-only project-scoped key. Rotation from the RESTai
  side immediately invalidates the app's session → the app falls back to
  the QR-scan screen.

## First run

1. App opens → camera permission → QR scan screen.
2. On scan, credentials are validated (`GET /auth/whoami` + Bearer),
   persisted encrypted, and the chat screen is shown.
3. Subsequent launches skip straight to the chat screen; if the stored
   key is rejected (401), the app returns to the QR screen.

## Build

Open `android/` in Android Studio (Giraffe or newer) and press ▶︎.
CLI build:

```bash
cd android
./gradlew assembleDebug
```

APK lands in `android/app/build/outputs/apk/debug/`.

## Files of interest

```
android/
  build.gradle.kts                   project-level config
  settings.gradle.kts                module list
  app/
    build.gradle.kts                 dependencies, Compose, min SDK 26
    src/main/AndroidManifest.xml     camera permission, theme, activity
    src/main/java/cloud/restai/mobile/
      MainActivity.kt                entry point
      Nav.kt                         QR ↔ Chat routing
      QrScreen.kt                    CameraX + ML Kit scan
      ChatScreen.kt                  Compose chat UI
      ChatClient.kt                  OkHttp SSE client
      Credentials.kt                 EncryptedSharedPreferences wrapper
      Models.kt                      QR payload, Message, UI state
      Theme.kt                       Material 3 theme
```
