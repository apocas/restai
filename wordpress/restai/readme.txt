=== RESTai ===
Contributors:      apocas
Tags:              ai, content generation, seo, chatbot, translation
Requires at least: 6.0
Tested up to:      6.9
Requires PHP:      7.4
Stable tag:        0.1.0
License:           GPLv2 or later
License URI:       https://www.gnu.org/licenses/gpl-2.0.html

AI superpowers for WordPress — content generation, SEO, images, translations, AI search, embedded chat. Powered by your RESTai instance.

== Description ==

RESTai for WordPress connects your site to a [RESTai](https://restai.cloud) instance and uses one RESTai project per task — Content Writer, SEO Assistant, Translator, Support Bot, etc. — so each capability has its own model, prompt and budget.

= Features =

**Content & SEO**
* Generate post and page bodies from a brief, in Gutenberg or the classic editor
* Generate SEO title, meta description and focus keyphrase (works with Yoast / Rank Math fields)
* Auto-generate excerpts and image alt text
* Bulk regenerate descriptions across many posts at once

**Images**
* Generate featured images from the post title or summary
* Pulls from any image generator configured in your RESTai instance (Stable Diffusion, Flux, DALL·E…)

**Translations**
* Translate any post into N languages with one click — saved as drafts in your favourite multilingual plugin's structure (Polylang / WPML compatible)

**Comments**
* AI-assisted moderation: auto-flag spam, auto-reply or suggest replies for moderators
* Tone analysis on incoming comments

**WooCommerce**
* Generate product descriptions and FAQs from product attributes
* Add a product-aware support bot (RAG over your catalog)

**Knowledge sync**
* Automatically push every published post and page into a RESTai RAG project so the support bot is always current

**AI site search**
* Replace native WordPress search with semantic search powered by your RAG project

**Embedded chat**
* One-click toggle to add the RESTai chat widget to your site
* Per-page customisation via shortcodes or block

**Email**
* Personalise transactional emails (welcome, abandoned cart, etc.) with AI

**Analytics**
* Token usage and cost panel mirrored straight into your WP admin

**Auto-provisioning**
* On first connect, the plugin sets up a sensible default project for each task in your RESTai instance — you can re-map any task to a different project at any time.

= Privacy =

This plugin sends content you choose (post titles, bodies, comments) to the RESTai instance you configure. **You own the instance, the data and the model choice.** Nothing is sent to third-party services by the plugin itself. See the [Privacy](#privacy) section.

= Requirements =

* WordPress 6.0+
* PHP 7.4+
* A reachable RESTai instance with at least one LLM configured. [Quick start](https://restai.cloud).

== Installation ==

1. Upload the `restai` folder to `/wp-content/plugins/`, or install via the **Plugins** screen.
2. Activate the plugin.
3. Go to **Settings → RESTai**, paste your RESTai URL and API key, click **Connect**.
4. The plugin will offer to auto-provision starter projects on your RESTai instance. Accept or pick existing projects per task.

== Frequently Asked Questions ==

= Do I need to pay for an LLM API? =

You need access to one — OpenAI, Anthropic, Ollama (local, free), Gemini, etc. Configure it in your RESTai instance, then RESTai for WordPress uses what's already there.

= Does this work with WPML / Polylang? =

Yes. Translations are saved using each plugin's standard structure when detected.

= Can I customise the prompts? =

Yes. Each task maps to a RESTai project. Edit the project's system prompt in your RESTai admin and changes apply immediately — no plugin update required.

= Is the embedded chat widget GDPR-compliant? =

The widget is loaded only after the visitor accepts cookies if a consent plugin is detected. Conversations go to your RESTai instance only.

== Privacy ==

This plugin makes outbound HTTPS calls to the RESTai URL the site administrator configures. The following data may be sent:

* Post titles, bodies and metadata when generating content, SEO meta or translations.
* Comments when moderation is enabled.
* Search queries when AI search is enabled.

No data is sent to any third party from the plugin code. Logs and inference traces, if enabled, live on your RESTai instance.

== Screenshots ==

1. Settings page — connect and map tasks to projects.
2. Generate-with-AI panel inside the Gutenberg editor.
3. Token usage dashboard inside WP admin.

== Changelog ==

= 0.1.0 =
* Initial release.

== Upgrade Notice ==

= 0.1.0 =
First release.
