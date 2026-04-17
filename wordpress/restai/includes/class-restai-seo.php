<?php
/**
 * SEO meta generation. Outputs structured data (title, description, focus
 * keyphrase, suggested tags) and writes it into Yoast / Rank Math fields when
 * those plugins are detected.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class SEO {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
	}

	/**
	 * Generate SEO meta for a given post id and write it to the appropriate
	 * SEO plugin's fields when present.
	 *
	 * @param int $post_id
	 * @return array|\WP_Error
	 */
	public function generate_for_post( $post_id ) {
		$post = get_post( $post_id );
		if ( ! $post ) {
			return new \WP_Error( 'restai_no_post', __( 'Post not found.', 'restai' ) );
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'seo_assistant' );
		if ( $project_id <= 0 ) {
			return new \WP_Error( 'restai_no_project', __( 'SEO project not configured.', 'restai' ) );
		}

		$body = wp_strip_all_tags( $post->post_content );
		$body = mb_substr( $body, 0, 4000 );

		// Carry the JSON contract in the user prompt so we don't depend on the
		// project's system prompt being in sync.
		$prompt = "Return ONLY a JSON object (no markdown, no preamble, no commentary) with this exact shape:\n" .
			"{\n" .
			'  "meta_title": "max 60 chars",' . "\n" .
			'  "meta_description": "max 155 chars",' . "\n" .
			'  "focus_keyphrase": "1-3 words",' . "\n" .
			'  "suggested_tags": ["tag1", "tag2", "..."]' . "\n" .
			"}\n\n" .
			"Source post:\nTITLE: " . $post->post_title . "\n\nCONTENT:\n" . $body;

		$answer = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $answer ) ) {
			return $answer;
		}

		$meta = $this->parse_json( $answer );
		if ( empty( $meta ) ) {
			$snippet = mb_substr( (string) $answer, 0, 200 );
			return new \WP_Error(
				'restai_seo_parse',
				sprintf(
					/* translators: %s response snippet */
					__( 'SEO response was not valid JSON. First 200 chars: %s', 'restai' ),
					$snippet
				)
			);
		}

		// Write into known SEO plugin fields where available.
		if ( ! empty( $meta['meta_title'] ) ) {
			update_post_meta( $post_id, '_yoast_wpseo_title', $meta['meta_title'] );
			update_post_meta( $post_id, 'rank_math_title', $meta['meta_title'] );
		}
		if ( ! empty( $meta['meta_description'] ) ) {
			update_post_meta( $post_id, '_yoast_wpseo_metadesc', $meta['meta_description'] );
			update_post_meta( $post_id, 'rank_math_description', $meta['meta_description'] );
		}
		if ( ! empty( $meta['focus_keyphrase'] ) ) {
			update_post_meta( $post_id, '_yoast_wpseo_focuskw', $meta['focus_keyphrase'] );
			update_post_meta( $post_id, 'rank_math_focus_keyword', $meta['focus_keyphrase'] );
		}
		if ( ! empty( $meta['suggested_tags'] ) && is_array( $meta['suggested_tags'] ) ) {
			wp_set_post_tags( $post_id, $meta['suggested_tags'], true );
		}

		return $meta;
	}

	/**
	 * Tolerantly parse a JSON response from the LLM (it sometimes wraps in
	 * markdown fences).
	 */
	private function parse_json( $text ) {
		$text = trim( (string) $text );
		if ( '' === $text ) {
			return null;
		}

		// 1. Try ```json ... ``` fenced blocks first (most LLM-friendly).
		if ( preg_match( '/```(?:json)?\s*(\{.*?\})\s*```/s', $text, $m ) ) {
			$data = json_decode( $m[1], true );
			if ( is_array( $data ) ) {
				return $data;
			}
		}

		// 2. Strip generic fences if present.
		$stripped = preg_replace( '/^```(?:[a-z]+)?\s*/i', '', $text );
		$stripped = preg_replace( '/\s*```$/', '', $stripped );

		// 3. Try the cleaned text as-is.
		$data = json_decode( $stripped, true );
		if ( is_array( $data ) ) {
			return $data;
		}

		// 4. Fallback: find the longest balanced {...} substring and try that.
		$start = strpos( $stripped, '{' );
		while ( false !== $start ) {
			$depth = 0;
			$len   = strlen( $stripped );
			for ( $i = $start; $i < $len; $i++ ) {
				if ( $stripped[ $i ] === '{' ) {
					$depth++;
				} elseif ( $stripped[ $i ] === '}' ) {
					$depth--;
					if ( 0 === $depth ) {
						$candidate = substr( $stripped, $start, $i - $start + 1 );
						$data      = json_decode( $candidate, true );
						if ( is_array( $data ) ) {
							return $data;
						}
						break;
					}
				}
			}
			$start = strpos( $stripped, '{', $start + 1 );
		}

		return null;
	}
}
