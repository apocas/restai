package cloud.restai.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.fillMaxSize

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
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
