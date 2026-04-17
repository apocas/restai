/* global RESTaiAdmin, wp */
/**
 * Adds the "RESTai" sidebar to Gutenberg with one-click actions:
 *   • Generate body content from the current title (or a brief)
 *   • Generate SEO meta (title / description / focus keyphrase)
 *   • Generate a featured image
 *   • Translate to a target language (saved as a new draft)
 *
 * Also adds a small floating button to the classic editor with the same
 * actions (when Gutenberg is disabled).
 */
(function (wp) {
	"use strict";

	if (!wp || !wp.plugins || !wp.editPost) {
		// classic editor fallback
		document.addEventListener("DOMContentLoaded", function () {
			const wrap = document.getElementById("postdivrich") || document.getElementById("postbody");
			if (!wrap) return;
			const btn = document.createElement("button");
			btn.type = "button";
			btn.className = "button button-primary";
			btn.textContent = RESTaiAdmin.i18n.generate;
			btn.style.margin = "8px 0";
			btn.addEventListener("click", function () {
				const titleEl = document.getElementById("title");
				const title = titleEl ? titleEl.value : "";
				if (!title) {
					alert("Add a post title first.");
					return;
				}
				generate("content_writer", "Write a blog post about: " + title)
					.then((out) => insertClassic(out))
					.catch((err) => alert(err.message || RESTaiAdmin.i18n.error));
			});
			wrap.parentNode.insertBefore(btn, wrap);
		});
		return;
	}

	const { registerPlugin } = wp.plugins;
	const { PluginSidebar, PluginSidebarMoreMenuItem } = wp.editPost;
	const { PanelBody, Button, TextareaControl, SelectControl, Spinner, Notice } = wp.components;
	const { useState, createElement: el } = wp.element;
	const { useSelect, useDispatch } = wp.data;
	const { __ } = wp.i18n;
	const apiFetch = wp.apiFetch;
	apiFetch.use(apiFetch.createNonceMiddleware(RESTaiAdmin.nonce));

	// Brain icon (Material Symbols "Psychology") used in the editor sidebar
	// and the more-menu entry, since Dashicons has no brain glyph.
	const BrainIcon = el(
		"svg",
		{ xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 24 24", width: 24, height: 24, "aria-hidden": "true", focusable: "false" },
		el("path", { d: "M13 8.57c-.79 0-1.43.64-1.43 1.43s.64 1.43 1.43 1.43 1.43-.64 1.43-1.43-.64-1.43-1.43-1.43z" }),
		el("path", { d: "M13 3C9.25 3 6.2 5.94 6.02 9.64L4.1 12.2c-.41.55 0 1.34.69 1.34H6V16c0 1.1.9 2 2 2h1v3h7v-4.68c2.36-1.12 4-3.53 4-6.32 0-3.87-3.13-7-7-7zm3 7c0 .13-.01.26-.02.39l.83.66c.08.06.1.16.05.25l-.8 1.39c-.05.09-.16.12-.24.09l-.99-.4c-.21.16-.43.28-.67.39l-.15 1.06c-.01.1-.1.17-.2.17h-1.6c-.1 0-.18-.07-.2-.17l-.15-1.06c-.25-.1-.47-.23-.68-.38l-.99.4c-.09.04-.2 0-.24-.09l-.8-1.39c-.05-.08-.03-.19.05-.25l.84-.66c-.01-.13-.02-.26-.02-.39 0-.13.01-.26.03-.39l-.84-.66c-.08-.06-.1-.16-.05-.25l.8-1.39c.05-.09.16-.12.24-.09l.99.4c.21-.16.43-.28.67-.39l.15-1.06c.02-.1.1-.17.2-.17h1.6c.1 0 .18.07.2.17l.15 1.06c.24.1.46.22.67.39l.99-.4c.09-.04.2 0 .24.09l.8 1.39c.05.09.03.19-.05.25l-.83.66c.01.13.02.26.02.39z" })
	);

	const url = (path) => RESTaiAdmin.restUrl + path;

	function generate(task, prompt) {
		return apiFetch({ url: url("/generate"), method: "POST", data: { task, prompt } }).then(
			(r) => r.output
		);
	}

	function insertClassic(html) {
		if (window.tinymce && window.tinymce.activeEditor) {
			window.tinymce.activeEditor.setContent(html);
		} else {
			const ta = document.getElementById("content");
			if (ta) ta.value = html;
		}
	}

	const RestAiSidebar = () => {
		const post = useSelect((sel) => sel("core/editor").getCurrentPost(), []);
		const { editPost } = useDispatch("core/editor");

		const [brief, setBrief] = useState("");
		const [busy, setBusy] = useState(null);
		const [error, setError] = useState("");
		const [language, setLanguage] = useState("Spanish");
		const [seoResult, setSeoResult] = useState(null);

		const run = (label, fn) => {
			setBusy(label);
			setError("");
			Promise.resolve()
				.then(fn)
				.catch((e) => setError(e.message || RESTaiAdmin.i18n.error))
				.finally(() => setBusy(null));
		};

		const writeContent = () =>
			run("content", () => {
				const prompt = brief.trim()
					? brief
					: "Write a well-structured blog post about: " + (post.title || "");
				return generate("content_writer", prompt).then((html) => {
					if (!confirm(RESTaiAdmin.i18n.confirm_replace)) return;
					editPost({ content: html });
				});
			});

		const writeExcerpt = () =>
			run("excerpt", () =>
				generate(
					"content_writer",
					'Summarize the following post in one sentence (max 25 words). HTML stripped to plain text.\n\nTITLE: ' +
						(post.title || "") +
						"\n\nCONTENT: " +
						(post.content || "")
				).then((excerpt) => editPost({ excerpt }))
			);

		const seoMeta = () =>
			run("seo", () =>
				apiFetch({ url: url("/seo-meta"), method: "POST", data: { post_id: post.id } }).then(
					(res) => {
						setSeoResult(res);
						if (res.meta_title) editPost({ meta: { _yoast_wpseo_title: res.meta_title } });
						if (res.meta_description)
							editPost({ meta: { _yoast_wpseo_metadesc: res.meta_description } });
					}
				)
			);

		const featuredImage = () =>
			run("image", () =>
				apiFetch({ url: url("/featured-image"), method: "POST", data: { post_id: post.id } }).then(
					(res) => {
						if (res && res.attachment_id) {
							editPost({ featured_media: res.attachment_id });
						}
					}
				)
			);

		const translate = () =>
			run("translate", () =>
				apiFetch({
					url: url("/translate"),
					method: "POST",
					data: { post_id: post.id, language: language },
				}).then((res) => {
					if (res && res.new_post_id) {
						alert(__("Translation saved as draft #", "restai") + res.new_post_id);
					}
				})
			);

		return wp.element.createElement(
			PluginSidebar,
			{ name: "restai-sidebar", title: __("RESTai", "restai"), icon: BrainIcon },
			wp.element.createElement(
				PanelBody,
				{ title: __("Content", "restai"), initialOpen: true },
				wp.element.createElement(TextareaControl, {
					label: __("Optional brief", "restai"),
					value: brief,
					onChange: setBrief,
					placeholder: __("Leave blank to use the post title as a brief.", "restai"),
				}),
				wp.element.createElement(
					Button,
					{ variant: "primary", onClick: writeContent, disabled: !!busy },
					busy === "content" ? wp.element.createElement(Spinner) : __("Generate body", "restai")
				),
				" ",
				wp.element.createElement(
					Button,
					{ variant: "secondary", onClick: writeExcerpt, disabled: !!busy },
					busy === "excerpt" ? wp.element.createElement(Spinner) : __("Generate excerpt", "restai")
				)
			),
			wp.element.createElement(
				PanelBody,
				{ title: __("SEO meta", "restai"), initialOpen: false },
				wp.element.createElement(
					Button,
					{ variant: "primary", onClick: seoMeta, disabled: !!busy },
					busy === "seo" ? wp.element.createElement(Spinner) : __("Generate SEO", "restai")
				),
				seoResult &&
					wp.element.createElement(
						"div",
						{ style: { marginTop: 8, fontSize: 12 } },
						wp.element.createElement("p", null, wp.element.createElement("strong", null, "Title: "), seoResult.meta_title || ""),
						wp.element.createElement("p", null, wp.element.createElement("strong", null, "Desc: "), seoResult.meta_description || ""),
						wp.element.createElement("p", null, wp.element.createElement("strong", null, "Focus: "), seoResult.focus_keyphrase || "")
					)
			),
			wp.element.createElement(
				PanelBody,
				{ title: __("Featured image", "restai"), initialOpen: false },
				wp.element.createElement(
					Button,
					{ variant: "primary", onClick: featuredImage, disabled: !!busy },
					busy === "image" ? wp.element.createElement(Spinner) : __("Generate image", "restai")
				)
			),
			wp.element.createElement(
				PanelBody,
				{ title: __("Translation", "restai"), initialOpen: false },
				wp.element.createElement(SelectControl, {
					label: __("Target language", "restai"),
					value: language,
					options: [
						{ label: "Spanish", value: "Spanish" },
						{ label: "Portuguese", value: "Portuguese" },
						{ label: "French", value: "French" },
						{ label: "German", value: "German" },
						{ label: "Italian", value: "Italian" },
						{ label: "Dutch", value: "Dutch" },
						{ label: "Polish", value: "Polish" },
						{ label: "Japanese", value: "Japanese" },
						{ label: "Chinese (Simplified)", value: "Chinese (Simplified)" },
					],
					onChange: setLanguage,
				}),
				wp.element.createElement(
					Button,
					{ variant: "primary", onClick: translate, disabled: !!busy },
					busy === "translate"
						? wp.element.createElement(Spinner)
						: __("Translate to " + language, "restai")
				)
			),
			error &&
				wp.element.createElement(Notice, { status: "error", isDismissible: true }, error)
		);
	};

	registerPlugin("restai-sidebar", { render: RestAiSidebar, icon: BrainIcon });
})(window.wp);
