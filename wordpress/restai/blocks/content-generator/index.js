/* global wp */
/**
 * "RESTai: Generated Content" Gutenberg block.
 *
 * Server-rendered: the editor shows a configuration form (task + prompt), the
 * front-end renders the AI-generated HTML returned by the Content class.
 */
(function (wp) {
	const { registerBlockType } = wp.blocks;
	const { TextControl, TextareaControl, SelectControl, PanelBody, ToggleControl } = wp.components;
	const { InspectorControls } = wp.blockEditor || wp.editor;
	const { __ } = wp.i18n;
	const el = wp.element.createElement;

	const BrainIcon = el(
		"svg",
		{ xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 24 24", width: 24, height: 24 },
		el("path", { d: "M13 8.57c-.79 0-1.43.64-1.43 1.43s.64 1.43 1.43 1.43 1.43-.64 1.43-1.43-.64-1.43-1.43-1.43z" }),
		el("path", { d: "M13 3C9.25 3 6.2 5.94 6.02 9.64L4.1 12.2c-.41.55 0 1.34.69 1.34H6V16c0 1.1.9 2 2 2h1v3h7v-4.68c2.36-1.12 4-3.53 4-6.32 0-3.87-3.13-7-7-7zm3 7c0 .13-.01.26-.02.39l.83.66c.08.06.1.16.05.25l-.8 1.39c-.05.09-.16.12-.24.09l-.99-.4c-.21.16-.43.28-.67.39l-.15 1.06c-.01.1-.1.17-.2.17h-1.6c-.1 0-.18-.07-.2-.17l-.15-1.06c-.25-.1-.47-.23-.68-.38l-.99.4c-.09.04-.2 0-.24-.09l-.8-1.39c-.05-.08-.03-.19.05-.25l.84-.66c-.01-.13-.02-.26-.02-.39 0-.13.01-.26.03-.39l-.84-.66c-.08-.06-.1-.16-.05-.25l.8-1.39c.05-.09.16-.12.24-.09l.99.4c.21-.16.43-.28.67-.39l.15-1.06c.02-.1.1-.17.2-.17h1.6c.1 0 .18.07.2.17l.15 1.06c.24.1.46.22.67.39l.99-.4c.09-.04.2 0 .24.09l.8 1.39c.05.09.03.19-.05.25l-.83.66c.01.13.02.26.02.39z" })
	);

	registerBlockType("restai/content-generator", {
		icon: BrainIcon,
		edit: ({ attributes, setAttributes }) => {
			const { task, prompt, cache } = attributes;
			return el(
				"div",
				{ className: "restai-block-edit", style: { padding: 12, background: "#f6f7f9", borderRadius: 6 } },
				el(InspectorControls, null,
					el(PanelBody, { title: __("RESTai", "restai") },
						el(SelectControl, {
							label: __("Task", "restai"),
							value: task,
							options: [
								{ label: "Content writer", value: "content_writer" },
								{ label: "SEO assistant", value: "seo_assistant" },
								{ label: "Translator", value: "translator" },
								{ label: "Product writer", value: "product_writer" },
							],
							onChange: (v) => setAttributes({ task: v }),
						}),
						el(ToggleControl, {
							label: __("Cache result", "restai"),
							checked: cache,
							onChange: (v) => setAttributes({ cache: v }),
						})
					)
				),
				el("strong", null, "RESTai → " + task),
				el(TextareaControl, {
					label: __("Prompt", "restai"),
					value: prompt,
					onChange: (v) => setAttributes({ prompt: v }),
					rows: 4,
					placeholder: __("Describe what you want generated…", "restai"),
				}),
				el("p", { style: { fontSize: 12, color: "#666" } },
					__("Output is generated on the front-end and (when caching is on) reused for subsequent visits.", "restai")
				)
			);
		},
		save: () => null, // server-rendered
	});
})(window.wp);
