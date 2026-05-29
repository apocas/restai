/* global RESTaiAdmin, jQuery, wp */
(function ($) {
	"use strict";

	const apiFetch = wp.apiFetch;
	apiFetch.use(apiFetch.createNonceMiddleware(RESTaiAdmin.nonce));

	const url = (path) => RESTaiAdmin.restUrl + path;

	function setStatus($el, text, ok) {
		$el.text(text).removeClass("ok fail").addClass(ok ? "ok" : "fail");
	}

	// --- Test connection ---
	$("#restai-test-connection").on("click", function () {
		const $btn = $(this);
		const $status = $("#restai-connection-status");
		$btn.prop("disabled", true);
		$status.text("…").removeClass("ok fail");

		apiFetch({
			url: url("/test-connection"),
			method: "POST",
			data: {
				url: $("#restai_url").val(),
				api_key: $("#restai_api_key").val(),
			},
		})
			.then((res) => {
				if (res && res.ok) {
					setStatus($status, "✓ Connected as " + (res.username || "user"), true);
					populateTeamsDropdown();
				} else {
					setStatus($status, "✗ Authentication failed", false);
				}
			})
			.catch((err) => {
				setStatus($status, "✗ " + (err.message || "error"), false);
			})
			.finally(() => $btn.prop("disabled", false));
	});

	function populateTeamsDropdown() {
		const $sel = $("#restai_team_id");
		if (!$sel.length) return;
		const current = $sel.data("current") || $sel.val();
		apiFetch({ url: url("/teams"), method: "GET" })
			.then((res) => {
				const teams = (res && res.teams) || [];
				$sel.empty().append('<option value="">— select a team —</option>');
				teams.forEach((t) => {
					const opt = $("<option/>").val(t.id).text(t.name + " (#" + t.id + ")");
					if (String(t.id) === String(current)) opt.attr("selected", "selected");
					$sel.append(opt);
				});
				updateProvisionGate();
			})
			.catch(() => {});
	}

	function updateProvisionGate() {
		const teamSelected = !!$("#restai_team_id").val();
		$("#restai-provision").prop("disabled", !RESTaiAdmin.connected || !teamSelected);
	}

	function populateImageGeneratorDropdown() {
		const $sel = $("#restai_image_generator");
		if (!$sel.length) return;
		if (!RESTaiAdmin.connected || !$("#restai_team_id").val()) return;
		const current = $sel.data("current") || $sel.val();
		apiFetch({ url: url("/team-resources"), method: "GET" })
			.then((res) => {
				const gens = (res && res.image_generators) || [];
				$sel.empty().append('<option value="">— Auto (first available in team) —</option>');
				gens.forEach((g) => {
					const opt = $("<option/>").val(g).text(g);
					if (g === current) opt.attr("selected", "selected");
					$sel.append(opt);
				});
			})
			.catch(() => {});
	}

	$(document).on("change", "#restai_team_id", function () {
		updateProvisionGate();
		populateImageGeneratorDropdown();
	});

	// --- Auto-provision starter projects ---
	$("#restai-provision").on("click", function () {
		const $btn = $(this);
		const $status = $("#restai-provision-status");
		$btn.prop("disabled", true);
		$status.html('<span class="restai-spinner"></span> ' + (RESTaiAdmin.i18n.generating || "Working…"));

		apiFetch({ url: url("/provision"), method: "POST" })
			.then((res) => {
				const created = Object.keys(res.created || {}).length;
				const existing = Object.keys(res.existing || {}).length;
				const errors = Object.keys(res.errors || {}).length;
				const warnings = Object.keys(res.warnings || {}).length;
				let msg = created + " created · " + existing + " adopted";
				if (warnings) msg += " · " + warnings + " warnings";
				if (errors) msg += " · " + errors + " errors";
				$status.text((errors ? "⚠ " : "✓ ") + msg);
				if (errors && res.errors.no_team) {
					$status.text("✗ " + res.errors.no_team);
				}
				populateProjectDropdowns();
			})
			.catch((err) => {
				$status.text("✗ " + (err.message || "error"));
			})
			.finally(() => $btn.prop("disabled", false));
	});

	// --- Populate project dropdowns from RESTai ---
	function populateProjectDropdowns() {
		if (!RESTaiAdmin.connected) return;
		apiFetch({ url: url("/projects"), method: "GET" })
			.then((res) => {
				const projects = (res && res.projects) || [];
				$("select.restai-project-select").each(function () {
					const $sel = $(this);
					const current = String($sel.val());
					$sel.empty().append('<option value="">— not configured —</option>');
					projects.forEach((p) => {
						const opt = $("<option/>").val(p.id).text(p.name + " (#" + p.id + " · " + p.type + ")");
						if (String(p.id) === current) opt.attr("selected", "selected");
						$sel.append(opt);
					});
				});
			})
			.catch(() => {});
	}

	// On page load, populate dropdowns if connected.
	$(function () {
		populateProjectDropdowns();
		if (RESTaiAdmin.connected) {
			populateTeamsDropdown();
			populateImageGeneratorDropdown();
		}
		updateProvisionGate();
	});

	// --- Analytics: Push all to Support Bot ---
	$(document).on("click", "#restai-push-all-knowledge", function () {
		const $btn = $(this);
		const $status = $("#restai-push-status");
		if (!confirm("Push every published post and page to the Support Bot RAG project? This may take a while on big sites.")) return;

		$btn.prop("disabled", true);
		$status.html('<span class="restai-spinner"></span> Pushing…');

		apiFetch({
			url: url("/sync-knowledge"),
			method: "POST",
			data: { full: true },
		})
			.then((res) => {
				const pushed = res.pushed || 0;
				const errors = res.errors || 0;
				const skipped = res.skipped || 0;
				let msg = "✓ Pushed " + pushed;
				if (skipped) msg += " · skipped " + skipped + " empty";
				if (errors) {
					msg += " · " + errors + " errors";
					if (res.error_messages && res.error_messages.length) {
						msg += " — " + res.error_messages[0];
					}
				}
				$status.text(msg);
			})
			.catch((err) => {
				$status.text("✗ " + (err.message || "error"));
			})
			.finally(() => {
				$btn.prop("disabled", false);
			});
	});

	// --- Analytics page ---
	const $analytics = $("#restai-analytics-app");
	if ($analytics.length) {
		apiFetch({ url: url("/analytics"), method: "GET" })
			.then((res) => {
				const summary = res.summary || {};
				const tokens = (res.tokens && res.tokens.tokens) || [];
				const total = tokens.reduce((acc, t) => acc + (t.input || 0) + (t.output || 0), 0);
				const cost = tokens.reduce((acc, t) => acc + (t.cost || 0), 0);

				const html = [
					'<div class="stat-grid">',
					stat("Projects", summary.projects || 0),
					stat("Users", summary.users || 0),
					stat("Tokens (30d)", total.toLocaleString()),
					stat("Cost (30d)", cost.toFixed(3)),
					stat("Avg latency", (summary.avg_latency_ms || 0) + " ms"),
					"</div>",
				].join("");
				$analytics.html(html);
			})
			.catch(() => {
				$analytics.html("<p>Failed to load analytics.</p>");
			});
	}

	function stat(label, value) {
		return (
			'<div class="stat">' +
			'<div class="label">' + label + "</div>" +
			'<div class="value">' + value + "</div>" +
			"</div>"
		);
	}
})(jQuery);
