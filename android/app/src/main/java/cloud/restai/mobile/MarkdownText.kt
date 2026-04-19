package cloud.restai.mobile

import android.graphics.Color as AndroidColor
import android.util.TypedValue
import android.widget.TextView
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import android.net.Uri
import coil.ImageLoader
import io.noties.markwon.AbstractMarkwonPlugin
import okhttp3.OkHttpClient
import io.noties.markwon.Markwon
import io.noties.markwon.ext.strikethrough.StrikethroughPlugin
import io.noties.markwon.ext.tables.TablePlugin
import io.noties.markwon.ext.tables.TableTheme
import io.noties.markwon.ext.tasklist.TaskListPlugin
import io.noties.markwon.html.HtmlPlugin
import io.noties.markwon.image.ImagesPlugin
import io.noties.markwon.image.coil.CoilImagesPlugin
import io.noties.markwon.linkify.LinkifyPlugin

@Composable
fun MarkdownText(
    content: String,
    modifier: Modifier = Modifier,
) {
    val ctx = LocalContext.current
    val onSurface = MaterialTheme.colorScheme.onSurface.toArgb()
    val onSurfaceVariant = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    val divider = MaterialTheme.colorScheme.outlineVariant.toArgb()
    val linkColor = MaterialTheme.colorScheme.primary.toArgb()
    val codeBg = MaterialTheme.colorScheme.surfaceVariant.toArgb()

    // Resolve relative image URLs (e.g. `/image/cache/<id>.png`) against the
    // paired RESTai host so server-emitted markdown like the `draw_image`
    // builtin tool's output works regardless of whether the backend is set
    // up to emit absolute URLs.
    val cred = remember { Credentials.load(ctx) }
    val host = cred?.host?.trimEnd('/') ?: ""
    val apiKey = cred?.apiKey ?: ""
    val hostName = remember(host) { if (host.isNotEmpty()) Uri.parse(host).host else null }

    val markwon = remember(onSurface, linkColor, host) {
        val tableTheme = TableTheme.Builder()
            .tableBorderColor(divider)
            .tableBorderWidth(1)
            .tableCellPadding(dpToPx(ctx, 6f))
            .tableHeaderRowBackgroundColor(AndroidColor.TRANSPARENT)
            .tableEvenRowBackgroundColor(AndroidColor.TRANSPARENT)
            .tableOddRowBackgroundColor(AndroidColor.TRANSPARENT)
            .build()

        // Authenticated OkHttp client so protected endpoints like
        // /image/cache/<id>.png return the image bytes instead of 401/403.
        val authedHttp = OkHttpClient.Builder()
            .addInterceptor { chain ->
                val r = chain.request()
                if (apiKey.isNotEmpty() && hostName != null && r.url.host == hostName) {
                    chain.proceed(
                        r.newBuilder()
                            .header("Authorization", "Bearer $apiKey")
                            .build()
                    )
                } else {
                    chain.proceed(r)
                }
            }
            .build()

        val coilLoader = ImageLoader.Builder(ctx)
            .okHttpClient(authedHttp)
            .build()

        Markwon.builder(ctx)
            .usePlugin(TablePlugin.create(tableTheme))
            .usePlugin(StrikethroughPlugin.create())
            .usePlugin(TaskListPlugin.create(ctx))
            .usePlugin(LinkifyPlugin.create())
            .usePlugin(HtmlPlugin.create())
            .usePlugin(ImagesPlugin.create())
            .usePlugin(CoilImagesPlugin.create(ctx, coilLoader))
            .usePlugin(object : AbstractMarkwonPlugin() {
                override fun processMarkdown(markdown: String): String {
                    if (host.isEmpty()) return markdown
                    // 1. Prefix relative image URLs in markdown image syntax
                    //    (`![alt](/image/cache/xyz.png)` → `![alt](https://…/image/cache/xyz.png)`).
                    val mdImg = Regex("""!\[([^\]]*)]\((/[^)\s]+)\)""")
                    // 2. Promote bare relative image paths (`/image/cache/xyz.png`)
                    //    to markdown image syntax, since the LLM sometimes
                    //    returns just the path without the `![...]()` wrapper.
                    val bareImg = Regex("""(?<![\(\]\w/])(/image/cache/[^\s)]+\.(?:png|jpg|jpeg|gif|webp))""", RegexOption.IGNORE_CASE)
                    val step1 = mdImg.replace(markdown) { m ->
                        "![${m.groupValues[1]}](${host}${m.groupValues[2]})"
                    }
                    return bareImg.replace(step1) { m ->
                        "![](${host}${m.groupValues[1]})"
                    }
                }
            })
            .build()
    }

    AndroidView(
        factory = { c ->
            TextView(c).apply {
                setTextColor(onSurface)
                setLinkTextColor(linkColor)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                textSize
                setLineSpacing(0f, 1.25f)
                // selectable text so users can copy
                setTextIsSelectable(true)
            }
        },
        update = { tv -> markwon.setMarkdown(tv, content) },
        modifier = modifier,
    )
}

private fun dpToPx(ctx: android.content.Context, dp: Float): Int =
    (dp * ctx.resources.displayMetrics.density).toInt()
