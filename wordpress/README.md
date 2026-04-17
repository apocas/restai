# RESTai for WordPress

Source for the official RESTai WordPress plugin. The plugin connects WordPress
to a RESTai instance and uses one RESTai project per task (Content Writer, SEO
Assistant, Translator, Support Bot, Product Writer, Email Personalizer, Comment
Moderator, Image Alt Writer). The plugin auto-provisions these projects on
first connect and lets the admin re-map any task to a different existing
project.

## Layout

```
restai/
  restai.php            Plugin header + bootstrap
  readme.txt            wp.org readme
  uninstall.php         Cleanup on uninstall
  includes/             PHP classes (one feature per file)
  admin/views/          PHP templates for admin pages
  admin/css/            Admin styles
  admin/js/             Admin scripts (settings, editor sidebar)
  blocks/               Gutenberg blocks
  languages/            Translation files
```

## Building a release zip

```bash
cd wordpress
zip -r restai.zip restai \
    -x 'restai/.DS_Store' 'restai/**/.DS_Store'
```

Upload `restai.zip` via **WP admin → Plugins → Add New → Upload Plugin**.

## Submitting to wp.org

Coding standard: WordPress-Extra. Sanitisation/escaping rules followed
throughout. Strings are i18n-ready under text domain `restai` with `Domain
Path: /languages`. License: GPL-2.0-or-later. No outbound calls happen until
the admin enters a RESTai URL + API key in settings.

## Features delivered in v0.1

| Area | Feature |
|------|---------|
| Connection | Settings page, test-connection button, project map editor |
| Provisioning | One-click auto-create of all starter projects |
| Content | Gutenberg sidebar (body, excerpt), classic editor button, server-rendered block, `[restai_generate]` shortcode |
| SEO | Meta title/description/focus keyphrase + tag suggestions, writes to Yoast and Rank Math fields |
| Images | One-click featured image gen, optional auto alt text on uploads |
| Translation | Per-post translate-to-language, saves a draft (Polylang-aware) |
| Comments | Pre-publish AI moderation (spam / toxic / sentiment + suggested reply) |
| WooCommerce | Generate product description from attributes, FAQ shortcode |
| Knowledge | Auto-push posts/pages to the Support Bot RAG project, daily sweep |
| Search | AI answer panel injected on native search results |
| Widget | One-click chat-bubble embed, settings for title/color/welcome |
| Email | AI rewrite of transactional emails (`wp_mail` filter) |
| Analytics | Dashboard widget + dedicated page mirroring `/statistics` |
| Cron | Daily knowledge sync, weekly SEO audit |
```
