package cloud.restai.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Streaming chat UI against the paired RESTai project. Each send kicks off
 * an SSE read on a background dispatcher and mutates the assistant message
 * as chunks arrive.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(cred: QrPayload, onLogout: () -> Unit) {
    val ctx = LocalContext.current
    val client = remember(cred) { ChatClient(cred) }
    val messages = remember { mutableStateListOf<Message>() }
    var conversationId by remember { mutableStateOf<String?>(null) }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("RESTai", fontWeight = FontWeight.Bold)
                        Text(
                            cred.projectName,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = {
                        Credentials.clear(ctx)
                        onLogout()
                    }) {
                        Icon(Icons.Filled.Logout, contentDescription = "Log out")
                    }
                },
            )
        },
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad)) {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(messages) { msg -> Bubble(msg) }
            }

            HorizontalDivider()
            Row(
                Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text("Message") },
                    modifier = Modifier.weight(1f),
                    enabled = !sending,
                    maxLines = 4,
                )
                Spacer(Modifier.width(8.dp))
                FloatingActionButton(
                    onClick = fb@{
                        val text = input.trim()
                        if (text.isEmpty() || sending) return@fb
                        input = ""
                        sending = true
                        messages += Message(Message.Role.USER, text)
                        val assistant = Message(Message.Role.ASSISTANT, "")
                        messages += assistant
                        scope.launch(Dispatchers.IO) {
                            try {
                                val nextId = client.sendMessage(text, conversationId) { delta ->
                                    scope.launch {
                                        val idx = messages.indexOf(assistant)
                                        if (idx >= 0) {
                                            messages[idx] = assistant.copy(text = assistant.text + delta)
                                                .also { assistant.text += delta }
                                        }
                                    }
                                }
                                conversationId = nextId ?: conversationId
                            } catch (e: ApiException) {
                                scope.launch {
                                    val idx = messages.indexOf(assistant)
                                    val msg = if (e.isUnauthorized)
                                        "Authentication failed — the project key was likely regenerated. Re-scan the QR."
                                    else "Error: ${e.message}"
                                    if (idx >= 0) messages[idx] = assistant.copy(text = msg)
                                    if (e.isUnauthorized) {
                                        Credentials.clear(ctx)
                                        onLogout()
                                    }
                                }
                            } catch (t: Throwable) {
                                scope.launch {
                                    val idx = messages.indexOf(assistant)
                                    if (idx >= 0) messages[idx] = assistant.copy(text = "Network error: ${t.message}")
                                }
                            } finally {
                                scope.launch { sending = false }
                            }
                        }
                    },
                    modifier = Modifier.size(48.dp),
                ) { Icon(Icons.Filled.Send, contentDescription = "Send") }
            }
        }
    }
}

@Composable
private fun Bubble(msg: Message) {
    val isUser = msg.role == Message.Role.USER
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start) {
        Surface(
            shape = RoundedCornerShape(
                topStart = 16.dp, topEnd = 16.dp,
                bottomStart = if (isUser) 16.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 16.dp,
            ),
            color = if (isUser) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.clip(RoundedCornerShape(16.dp)).widthIn(max = 320.dp),
        ) {
            Text(
                msg.text.ifEmpty { "…" },
                modifier = Modifier.padding(12.dp),
                color = if (isUser) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
