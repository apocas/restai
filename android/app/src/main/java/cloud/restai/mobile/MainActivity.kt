package cloud.restai.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8AB4F8),
    onPrimary = Color(0xFF002D6E),
    primaryContainer = Color(0xFF1A4A8A),
    onPrimaryContainer = Color(0xFFD3E3FD),
    surface = Color(0xFF1E1E1E),
    surfaceContainerLowest = Color(0xFF131313),
    onSurface = Color(0xFFE3E3E3),
    onSurfaceVariant = Color(0xFFC4C7C5),
    surfaceVariant = Color(0xFF2D2D2D),
    errorContainer = Color(0xFF8C1D18),
    onErrorContainer = Color(0xFFF9DEDC),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF1A73E8),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD3E3FD),
    onPrimaryContainer = Color(0xFF062E6F),
    surface = Color.White,
    surfaceContainerLowest = Color(0xFFF7F8FA),
    onSurface = Color(0xFF1F1F1F),
    onSurfaceVariant = Color(0xFF5F6368),
    surfaceVariant = Color(0xFFF1F3F4),
    errorContainer = Color(0xFFFCE8E6),
    onErrorContainer = Color(0xFF8C1D18),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            val dark = isSystemInDarkTheme()
            MaterialTheme(colorScheme = if (dark) DarkColors else LightColors) {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surfaceContainerLowest) {
                    App()
                }
            }
        }
    }

    @Composable
    private fun App() {
        val ctx = this
        var cred by remember { mutableStateOf<QrPayload?>(Credentials.load(ctx)) }

        if (cred == null) {
            QrScreen(onPaired = { payload ->
                Credentials.save(ctx, payload)
                cred = payload
            })
        } else {
            ChatScreen(cred = cred!!, onLogout = { cred = null })
        }
    }
}
