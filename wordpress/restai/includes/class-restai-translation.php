<?php
/**
 * Translation feature. Saves the translated copy as a draft post and links it
 * back to the source. Polylang / WPML connectors are stubbed for now.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Translation {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
	}

	/**
	 * @param int    $post_id
	 * @param string $language Target language name (e.g. "Spanish").
	 * @return array|\WP_Error
	 */
	public function translate_post( $post_id, $language ) {
		$post = get_post( $post_id );
		if ( ! $post ) {
			return new \WP_Error( 'restai_no_post', __( 'Post not found.', 'restai' ) );
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'translator' );
		if ( $project_id <= 0 ) {
			return new \WP_Error( 'restai_no_project', __( 'Translator project not configured.', 'restai' ) );
		}

		$prompt_title = "Translate the following text to {$language}. Return only the translated text.\n\n" . $post->post_title;
		$prompt_body  = "Translate the following HTML to {$language}. Preserve all tags. Return only the translated HTML.\n\n" . $post->post_content;

		$translated_title = $this->client->ask( $project_id, $prompt_title );
		if ( is_wp_error( $translated_title ) ) {
			return $translated_title;
		}
		$translated_body = $this->client->ask( $project_id, $prompt_body );
		if ( is_wp_error( $translated_body ) ) {
			return $translated_body;
		}

		$new_id = wp_insert_post(
			array(
				'post_title'   => wp_strip_all_tags( $translated_title ),
				'post_content' => wp_kses_post( $translated_body ),
				'post_status'  => 'draft',
				'post_type'    => $post->post_type,
				'post_author'  => get_current_user_id(),
			),
			true
		);

		if ( is_wp_error( $new_id ) ) {
			return $new_id;
		}

		update_post_meta( $new_id, '_restai_translated_from', $post_id );
		update_post_meta( $new_id, '_restai_translation_language', $language );

		// Polylang integration — register language if available.
		if ( function_exists( 'pll_set_post_language' ) ) {
			$lang_code = $this->language_to_code( $language );
			if ( $lang_code ) {
				pll_set_post_language( $new_id, $lang_code );
			}
		}

		return array(
			'new_post_id' => $new_id,
			'edit_url'    => get_edit_post_link( $new_id, '' ),
		);
	}

	private function language_to_code( $language ) {
		$map = array(
			'Spanish'              => 'es',
			'Portuguese'           => 'pt',
			'French'               => 'fr',
			'German'               => 'de',
			'Italian'              => 'it',
			'Dutch'                => 'nl',
			'Polish'               => 'pl',
			'Japanese'             => 'ja',
			'Chinese (Simplified)' => 'zh',
		);
		return isset( $map[ $language ] ) ? $map[ $language ] : null;
	}
}
