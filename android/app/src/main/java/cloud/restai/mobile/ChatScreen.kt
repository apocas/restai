package cloud.restai.mobile

import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(cred: QrPayload, onLogout: () -> Unit) {
    val ctx = LocalContext.current
    val client = remember(cred) { ChatClient(cred) }
    var messages by remember { mutableStateOf(listOf<Message>()) }
    var conversationId by remember { mutableStateOf<String?>(null) }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var attachments by remember { mutableStateOf(listOf<Attachment>()) }
    var showAttachMenu by remember { mutableStateOf(false) }
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()

    val bgColor = MaterialTheme.colorScheme.surfaceContainerLowest
    val surfaceColor = MaterialTheme.colorScheme.surface

    // --- Pickers ---

    // Camera photo URI
    var cameraUri by remember { mutableStateOf<Uri?>(null) }

    fun uriToAttachment(uri: Uri, fallbackName: String): Attachment? {
        val mime = ctx.contentResolver.getType(uri) ?: "application/octet-stream"
        val bytes = ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
        val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
        // Try to get display name
        val name = ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
            if (c.moveToFirst() && idx >= 0) c.getString(idx) else null
        } ?: fallbackName
        return Attachment(name, b64, mime)
    }

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            uriToAttachment(uri, "file")?.let { attachments = attachments + it }
        }
    }

    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            uriToAttachment(uri, "image.jpg")?.let { attachments = attachments + it }
        }
    }

    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) {
            cameraUri?.let { uri ->
                uriToAttachment(uri, "photo_${System.currentTimeMillis()}.jpg")?.let {
                    attachments = attachments + it
                }
            }
        }
    }

    fun launchCamera() {
        val dir = File(ctx.cacheDir, "photos").also { it.mkdirs() }
        val file = File(dir, "photo_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        cameraUri = uri
        cameraLauncher.launch(uri)
    }

    // --- Send logic ---
    fun doSend() {
        val text = input.trim()
        if (text.isEmpty() && attachments.isEmpty()) return
        if (sending) return
        val question = text.ifEmpty { "Attached ${attachments.size} file(s)" }
        input = ""
        sending = true
        val sent = attachments.toList()
        attachments = emptyList()
        messages = messages +
            Message(Message.Role.USER, question, sent) +
            Message(Message.Role.ASSISTANT, "")
        val assistantIdx = messages.lastIndex
        scope.launch(Dispatchers.IO) {
            try {
                var streamed = ""
                val result = client.sendMessage(question, conversationId, sent) { delta ->
                    streamed += delta
                    val snap = streamed
                    scope.launch {
                        messages = messages.toMutableList().also {
                            it[assistantIdx] = Message(Message.Role.ASSISTANT, snap)
                        }
                    }
                }
                withContext(Dispatchers.Main) {
                    val answer = result.answer.ifEmpty { streamed }
                    messages = messages.toMutableList().also {
                        it[assistantIdx] = Message(Message.Role.ASSISTANT, answer)
                    }
                    conversationId = result.conversationId ?: conversationId
                }
            } catch (e: ApiException) {
                withContext(Dispatchers.Main) {
                    val errMsg = if (e.isUnauthorized)
                        "Session expired. Please re-scan the QR code."
                    else "Error: ${e.message}"
                    messages = messages.toMutableList().also {
                        it[assistantIdx] = Message(Message.Role.ASSISTANT, errMsg)
                    }
                    if (e.isUnauthorized) {
                        Credentials.clear(ctx)
                        onLogout()
                    }
                }
            } catch (t: Throwable) {
                withContext(Dispatchers.Main) {
                    messages = messages.toMutableList().also {
                        it[assistantIdx] = Message(Message.Role.ASSISTANT, "Network error: ${t.message}")
                    }
                }
            } finally {
                withContext(Dispatchers.Main) { sending = false }
            }
        }
    }

    // --- Scroll ---
    LaunchedEffect(messages.size, messages.lastOrNull()?.text) {
        scrollState.animateScrollTo(scrollState.maxValue)
    }

    // --- UI ---
    Scaffold(
        containerColor = bgColor,
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text(
                        cred.projectName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                },
                navigationIcon = {
                    Surface(
                        shape = CircleShape,
                        color = MaterialTheme.colorScheme.primaryContainer,
                        modifier = Modifier.padding(start = 12.dp).size(34.dp),
                    ) {
                        Icon(
                            Icons.Filled.SmartToy,
                            contentDescription = null,
                            modifier = Modifier.padding(6.dp),
                            tint = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = {
                        Credentials.clear(ctx)
                        onLogout()
                    }) {
                        Icon(
                            Icons.AutoMirrored.Filled.Logout,
                            contentDescription = "Log out",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(containerColor = bgColor),
            )
        },
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad)) {
            // Messages
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(scrollState),
            ) {
                if (messages.isEmpty()) {
                    Box(Modifier.fillMaxWidth().padding(top = 120.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Surface(
                                shape = CircleShape,
                                color = MaterialTheme.colorScheme.primaryContainer,
                                modifier = Modifier.size(56.dp),
                            ) {
                                Icon(
                                    Icons.Filled.SmartToy,
                                    contentDescription = null,
                                    modifier = Modifier.padding(14.dp),
                                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                            Spacer(Modifier.height(16.dp))
                            Text(
                                "How can I help you?",
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurface,
                            )
                        }
                    }
                } else {
                    Spacer(Modifier.height(8.dp))
                    for (msg in messages) {
                        MessageRow(msg)
                    }
                    Spacer(Modifier.height(16.dp))
                }
            }

            // Input area
            Surface(color = bgColor, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                    // Attachment previews
                    AnimatedVisibility(visible = attachments.isNotEmpty()) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            for ((i, att) in attachments.withIndex()) {
                                AttachmentChip(att) { attachments = attachments.filterIndexed { idx, _ -> idx != i } }
                            }
                        }
                    }

                    // Input pill
                    Surface(
                        shape = RoundedCornerShape(24.dp),
                        color = surfaceColor,
                        tonalElevation = 1.dp,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Row(
                            Modifier.padding(start = 4.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
                            verticalAlignment = Alignment.Bottom,
                        ) {
                            // + button
                            Box {
                                IconButton(
                                    onClick = { showAttachMenu = true },
                                    enabled = !sending,
                                    modifier = Modifier.size(40.dp),
                                ) {
                                    Icon(
                                        Icons.Filled.Add,
                                        contentDescription = "Attach",
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                DropdownMenu(
                                    expanded = showAttachMenu,
                                    onDismissRequest = { showAttachMenu = false },
                                ) {
                                    DropdownMenuItem(
                                        text = { Text("Take Photo") },
                                        onClick = {
                                            showAttachMenu = false
                                            launchCamera()
                                        },
                                        leadingIcon = { Icon(Icons.Filled.CameraAlt, null) },
                                    )
                                    DropdownMenuItem(
                                        text = { Text("Choose Image") },
                                        onClick = {
                                            showAttachMenu = false
                                            imagePicker.launch("image/*")
                                        },
                                        leadingIcon = { Icon(Icons.Filled.Image, null) },
                                    )
                                    DropdownMenuItem(
                                        text = { Text("Upload File") },
                                        onClick = {
                                            showAttachMenu = false
                                            filePicker.launch("*/*")
                                        },
                                        leadingIcon = { Icon(Icons.Filled.AttachFile, null) },
                                    )
                                }
                            }

                            OutlinedTextField(
                                value = input,
                                onValueChange = { input = it },
                                placeholder = {
                                    Text(
                                        "Message",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                                    )
                                },
                                modifier = Modifier.weight(1f),
                                enabled = !sending,
                                maxLines = 5,
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = Color.Transparent,
                                    unfocusedBorderColor = Color.Transparent,
                                    disabledBorderColor = Color.Transparent,
                                    focusedContainerColor = Color.Transparent,
                                    unfocusedContainerColor = Color.Transparent,
                                    disabledContainerColor = Color.Transparent,
                                ),
                            )
                            Spacer(Modifier.width(4.dp))
                            val canSend = (input.trim().isNotEmpty() || attachments.isNotEmpty()) && !sending
                            FilledIconButton(
                                onClick = { doSend() },
                                modifier = Modifier.size(40.dp),
                                shape = CircleShape,
                                enabled = canSend,
                                colors = IconButtonDefaults.filledIconButtonColors(
                                    containerColor = MaterialTheme.colorScheme.primary,
                                    contentColor = MaterialTheme.colorScheme.onPrimary,
                                    disabledContainerColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.12f),
                                    disabledContentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f),
                                ),
                            ) {
                                Icon(Icons.Filled.ArrowUpward, "Send", Modifier.size(20.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

// ---- Composables ----

@Composable
private fun AttachmentChip(att: Attachment, onRemove: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Row(
            Modifier.padding(start = 8.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (att.isImage) {
                val bytes = Base64.decode(att.base64, Base64.DEFAULT)
                val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                if (bmp != null) {
                    Image(
                        bmp.asImageBitmap(),
                        contentDescription = att.name,
                        modifier = Modifier
                            .size(36.dp)
                            .clip(RoundedCornerShape(6.dp)),
                        contentScale = ContentScale.Crop,
                    )
                    Spacer(Modifier.width(6.dp))
                }
            } else {
                Icon(
                    Icons.Filled.Description,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.width(4.dp))
            }
            Text(
                att.name,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.widthIn(max = 100.dp),
            )
            IconButton(onClick = onRemove, modifier = Modifier.size(24.dp)) {
                Icon(
                    Icons.Filled.Close,
                    contentDescription = "Remove",
                    modifier = Modifier.size(14.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun MessageRow(msg: Message) {
    val isUser = msg.role == Message.Role.USER

    AnimatedVisibility(visible = true, enter = fadeIn()) {
        if (isUser) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalAlignment = Alignment.End,
            ) {
                // Show image thumbnails
                for (att in msg.attachments.filter { it.isImage }) {
                    val bytes = Base64.decode(att.base64, Base64.DEFAULT)
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    if (bmp != null) {
                        Image(
                            bmp.asImageBitmap(),
                            contentDescription = att.name,
                            modifier = Modifier
                                .widthIn(max = 200.dp)
                                .heightIn(max = 200.dp)
                                .clip(RoundedCornerShape(16.dp)),
                            contentScale = ContentScale.Fit,
                        )
                        Spacer(Modifier.height(4.dp))
                    }
                }
                // Show file chips
                for (att in msg.attachments.filter { !it.isImage }) {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f),
                    ) {
                        Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Description, null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onPrimary)
                            Spacer(Modifier.width(4.dp))
                            Text(att.name, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimary)
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
                // Text bubble
                if (msg.text.isNotEmpty() && msg.attachments.none { msg.text == "Attached ${msg.attachments.size} file(s)" }) {
                    Surface(
                        shape = RoundedCornerShape(20.dp, 20.dp, 4.dp, 20.dp),
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.widthIn(max = 300.dp),
                    ) {
                        Text(
                            msg.text,
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                            style = MaterialTheme.typography.bodyLarge,
                            lineHeight = 22.sp,
                        )
                    }
                }
            }
        } else {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.Start,
            ) {
                Surface(
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.size(28.dp),
                ) {
                    Icon(
                        Icons.Filled.SmartToy,
                        contentDescription = null,
                        modifier = Modifier.padding(5.dp),
                        tint = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
                Spacer(Modifier.width(10.dp))
                if (msg.text.isEmpty()) {
                    TypingIndicator()
                } else {
                    Text(
                        msg.text,
                        modifier = Modifier
                            .widthIn(max = 300.dp)
                            .padding(top = 4.dp),
                        color = MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.bodyLarge,
                        lineHeight = 22.sp,
                    )
                }
            }
        }
    }
}

@Composable
private fun TypingIndicator() {
    Row(
        modifier = Modifier.padding(top = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        repeat(3) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f)),
            )
        }
    }
}
