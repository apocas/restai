<?php
/**
 * Auto-provision starter RESTai projects on first connect.
 *
 * Each task the plugin performs maps to one RESTai project so the user can
 * tune model/prompt/budget per task. The provisioner creates a sensible
 * default project for each task; the settings page lets the admin re-map any
 * task to a different existing project later.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Provisioner {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
	}

	/**
	 * Definitions of the starter projects, keyed by task slug.
	 *
	 * @return array
	 */
	public static function definitions() {
		return array(
			'content_writer' => array(
				'name'   => 'wp-content-writer',
				'type'   => 'agent',
				'system' => 'You are a senior WordPress content writer. Given a brief, write engaging, well-structured blog content in HTML using <h2>, <h3>, <p>, <ul>, <strong>. Never include <html>, <head> or <body> tags. Match the requested tone and length.',
				'label'  => __( 'Content Writer', 'restai' ),
			),
			'seo_assistant' => array(
				'name'   => 'wp-seo-assistant',
				'type'   => 'agent',
				'system' => 'You are an SEO expert. Given a post title and body, return a JSON object with keys: meta_title (max 60 chars), meta_description (max 155 chars), focus_keyphrase (1-3 words), suggested_tags (array of 3-7 tags), readability_notes (brief). Output ONLY the JSON, no preamble.',
				'label'  => __( 'SEO Assistant', 'restai' ),
			),
			'translator' => array(
				'name'   => 'wp-translator',
				'type'   => 'agent',
				'system' => 'You are a professional translator. Translate the input HTML into the requested language. Preserve all HTML tags, attributes and structure. Return only the translated HTML, no preamble or explanation.',
				'label'  => __( 'Translator', 'restai' ),
			),
			'comment_moderator' => array(
				'name'   => 'wp-comment-moderator',
				'type'   => 'agent',
				'system' => 'You are a comment moderator. Given a comment, return a JSON object: { "spam": true|false, "toxic": true|false, "sentiment": "positive|neutral|negative", "suggested_reply": "..." }. Output ONLY the JSON.',
				'label'  => __( 'Comment Moderator', 'restai' ),
			),
			'support_bot' => array(
				'name'   => 'wp-support-bot',
				'type'   => 'rag',
				'system' => 'You are a helpful support assistant for this website. Answer using only the provided context. If the answer is not in the context, say you do not have that information and suggest contacting the team.',
				'label'  => __( 'Support Bot (RAG)', 'restai' ),
			),
			'product_writer' => array(
				'name'   => 'wp-product-writer',
				'type'   => 'agent',
				'system' => 'You are an e-commerce copywriter. Given product attributes, generate a compelling product description (2-3 short paragraphs) and a 5-bullet feature list. Persuasive, specific, no fluff.',
				'label'  => __( 'Product Writer (WooCommerce)', 'restai' ),
			),
			'email_personalizer' => array(
				'name'   => 'wp-email-personalizer',
				'type'   => 'agent',
				'system' => 'You rewrite transactional emails to feel personal and on-brand. Keep all dynamic placeholders intact (anything inside curly braces). Match the original intent and length.',
				'label'  => __( 'Email Personalizer', 'restai' ),
			),
			'image_alt' => array(
				'name'   => 'wp-image-alt',
				'type'   => 'agent',
				'system' => 'You write concise, descriptive alt text for images. Return only the alt text, no quotes or preamble. Max 125 characters.',
				'label'  => __( 'Image Alt Writer', 'restai' ),
			),
		);
	}

	/**
	 * Map of task slug => RESTai project ID (int).
	 */
	public function get_project_map() {
		$map = get_option( 'restai_project_map', array() );
		return is_array( $map ) ? $map : array();
	}

	/**
	 * Save the project map.
	 *
	 * @param array $map
	 */
	public function save_project_map( $map ) {
		update_option( 'restai_project_map', $map );
	}

	/**
	 * Return the project name (or id) currently mapped to a given task slug.
	 *
	 * @param string $task
	 * @return string|null
	 */
	/**
	 * @param string $task one of the keys in self::definitions().
	 * @return int  the RESTai project id mapped to that task, or 0 when none.
	 */
	public function project_for( $task ) {
		$map = $this->get_project_map();
		return isset( $map[ $task ] ) ? (int) $map[ $task ] : 0;
	}

	/**
	 * Provision any missing starter projects on the connected RESTai instance.
	 *
	 * Idempotent: if a project with the conventional name already exists, we
	 * just record it in the map. Tasks the user has already mapped manually
	 * are left alone.
	 *
	 * @return array { created: string[], existing: string[], errors: array }
	 */
	public function provision_all() {
		$results = array(
			'created'  => array(),
			'existing' => array(),
			'errors'   => array(),
			'warnings' => array(),
		);

		$settings = get_option( 'restai_settings', array() );
		$team_id  = isset( $settings['team_id'] ) ? (int) $settings['team_id'] : 0;
		if ( $team_id <= 0 ) {
			$results['errors']['no_team'] = __( 'Select a team in Settings → RESTai before provisioning.', 'restai' );
			return $results;
		}

		$existing = $this->client->get( 'projects' );
		$by_name  = array();
		if ( ! is_wp_error( $existing ) && isset( $existing['projects'] ) && is_array( $existing['projects'] ) ) {
			foreach ( $existing['projects'] as $p ) {
				if ( isset( $p['name'] ) ) {
					$by_name[ $p['name'] ] = $p;
				}
			}
		}

		$map = $this->get_project_map();

		foreach ( self::definitions() as $task => $def ) {
			// User already chose a project for this task — leave it alone.
			if ( ! empty( $map[ $task ] ) ) {
				$results['existing'][ $task ] = $map[ $task ];
				continue;
			}

			$name = $def['name'];

			// Project with the conventional name exists — adopt it and re-sync prompt.
			if ( isset( $by_name[ $name ] ) && isset( $by_name[ $name ]['id'] ) ) {
				$existing_id                  = (int) $by_name[ $name ]['id'];
				$map[ $task ]                 = $existing_id;
				$results['existing'][ $task ] = $existing_id;
				$this->sync_system_prompt( $existing_id, $def['system'], $results, $task );
				continue;
			}

			// Need to create — pick the first LLM the user has access to.
			$llm = $this->pick_default_llm();
			if ( null === $llm ) {
				$results['errors'][ $task ] = __( 'No LLM available — add one in RESTai first.', 'restai' );
				continue;
			}

			$payload = array(
				'name'       => $name,
				'human_name' => $def['label'],
				'type'       => $def['type'],
				'llm'        => $llm,
				'team_id'    => $team_id,
			);

			// RAG projects need an embeddings model + vectorstore.
			if ( 'rag' === $def['type'] ) {
				$emb = $this->pick_default_embeddings();
				if ( null === $emb ) {
					$results['errors'][ $task ] = __( 'No embeddings model available — skipping RAG project.', 'restai' );
					continue;
				}
				$payload['embeddings']  = $emb;
				$payload['vectorstore'] = 'chroma';
			}

			$resp = $this->client->post( 'projects', $payload );
			if ( is_wp_error( $resp ) ) {
				$results['errors'][ $task ] = $resp->get_error_message();
				continue;
			}

			// POST /projects returns { "project": <id> }.
			$new_id = isset( $resp['project'] ) ? (int) $resp['project'] : 0;
			if ( $new_id <= 0 ) {
				$results['errors'][ $task ] = __( 'Project created but no id returned.', 'restai' );
				continue;
			}

			$map[ $task ]                = $new_id;
			$results['created'][ $task ] = $new_id;

			// Set the system prompt via PATCH (not accepted at creation time).
			$this->sync_system_prompt( $new_id, $def['system'], $results, $task );
		}

		$this->save_project_map( $map );
		update_option( 'restai_install_signature', md5( wp_json_encode( $map ) . RESTAI_VERSION ) );

		return $results;
	}

	/**
	 * Update a project's system prompt. Used for both freshly created and
	 * adopted projects so the canonical prompt in definitions() stays the
	 * source of truth.
	 */
	private function sync_system_prompt( $project_id, $system, &$results, $task ) {
		$resp = $this->client->patch(
			'projects/' . (int) $project_id,
			array( 'system' => $system )
		);
		if ( is_wp_error( $resp ) ) {
			$results['warnings'][ $task ] = sprintf(
				/* translators: %s error message */
				__( 'Project ready but prompt not synced: %s', 'restai' ),
				$resp->get_error_message()
			);
		}
	}

	/**
	 * Pick a default LLM name. Prefers a fast/cheap model when available.
	 */
	private function pick_default_llm() {
		$llms = $this->client->get( 'llms' );
		if ( is_wp_error( $llms ) || ! is_array( $llms ) ) {
			return null;
		}
		$names = array();
		foreach ( $llms as $llm ) {
			if ( isset( $llm['name'] ) ) {
				$names[] = $llm['name'];
			}
		}
		if ( empty( $names ) ) {
			return null;
		}
		// Prefer common cheap models if present.
		$preferred = array( 'gpt-4o-mini', 'gpt-4o', 'claude-3-5-haiku', 'gemini-2.0-flash' );
		foreach ( $preferred as $p ) {
			foreach ( $names as $n ) {
				if ( stripos( $n, $p ) !== false ) {
					return $n;
				}
			}
		}
		return $names[0];
	}

	/**
	 * Pick a default embeddings model name.
	 */
	private function pick_default_embeddings() {
		$embs = $this->client->get( 'embeddings' );
		if ( is_wp_error( $embs ) || ! is_array( $embs ) ) {
			return null;
		}
		$names = array();
		foreach ( $embs as $e ) {
			if ( isset( $e['name'] ) ) {
				$names[] = $e['name'];
			}
		}
		return empty( $names ) ? null : $names[0];
	}
}
