<?php
/**
 * Featured-image generation + auto alt text on uploads. Uses RESTai's
 * OpenAI-compatible /v1/images/generations endpoint for image gen and a vision
 * LLM project for alt text.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Images {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_filter( 'wp_handle_upload', array( $this, 'maybe_alt_text_on_upload' ), 10, 2 );
	}

	/**
	 * Generate a featured image for the given post and attach it.
	 *
	 * @param int $post_id
	 * @return array|\WP_Error
	 */
	public function generate_featured_image( $post_id ) {
		$post = get_post( $post_id );
		if ( ! $post ) {
			return new \WP_Error( 'restai_no_post', __( 'Post not found.', 'restai' ) );
		}

		$prompt = $this->build_image_prompt( $post );

		$model = $this->pick_image_generator();
		if ( null === $model ) {
			return new \WP_Error(
				'restai_no_image_gen',
				__( 'No image generator available — assign one to your team in RESTai (Team → Image generators), or grant access to dalle3 / imagen3.', 'restai' )
			);
		}

		$resp = $this->client->post(
			'v1/images/generations',
			array(
				'model'           => $model,
				'prompt'          => $prompt,
				'n'               => 1,
				'size'            => '1024x1024',
				'response_format' => 'b64_json',
			),
			array( 'timeout' => 300 )
		);

		if ( is_wp_error( $resp ) ) {
			return $resp;
		}
		if ( empty( $resp['data'][0] ) ) {
			return new \WP_Error( 'restai_image_empty', __( 'Image generator returned no data.', 'restai' ) );
		}

		$item = $resp['data'][0];
		$bytes = null;
		if ( ! empty( $item['b64_json'] ) ) {
			$bytes = base64_decode( $item['b64_json'] );
		} elseif ( ! empty( $item['url'] ) ) {
			$dl = wp_remote_get( $item['url'], array( 'timeout' => 30 ) );
			if ( is_wp_error( $dl ) ) {
				return $dl;
			}
			$bytes = wp_remote_retrieve_body( $dl );
		}
		if ( empty( $bytes ) ) {
			return new \WP_Error( 'restai_image_empty', __( 'No image bytes received.', 'restai' ) );
		}

		$filename = sanitize_file_name( 'restai-' . $post_id . '-' . time() . '.png' );
		$upload   = wp_upload_bits( $filename, null, $bytes );
		if ( ! empty( $upload['error'] ) ) {
			return new \WP_Error( 'restai_upload_failed', $upload['error'] );
		}

		require_once ABSPATH . 'wp-admin/includes/file.php';
		require_once ABSPATH . 'wp-admin/includes/image.php';

		$attachment = array(
			'post_mime_type' => 'image/png',
			'post_title'     => $post->post_title,
			'post_content'   => '',
			'post_status'    => 'inherit',
		);
		$attach_id  = wp_insert_attachment( $attachment, $upload['file'], $post_id );
		if ( is_wp_error( $attach_id ) ) {
			return $attach_id;
		}
		$metadata = wp_generate_attachment_metadata( $attach_id, $upload['file'] );
		wp_update_attachment_metadata( $attach_id, $metadata );
		set_post_thumbnail( $post_id, $attach_id );

		return array(
			'attachment_id' => $attach_id,
			'url'           => $upload['url'],
		);
	}

	/**
	 * After upload, request alt text from RESTai if auto-alt is enabled.
	 */
	public function maybe_alt_text_on_upload( $upload, $context ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['auto_alt_text'] ) ) {
			return $upload;
		}
		if ( empty( $upload['type'] ) || strpos( $upload['type'], 'image/' ) !== 0 ) {
			return $upload;
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'image_alt' );
		if ( $project_id <= 0 ) {
			return $upload;
		}

		// We can't easily ship the binary in a one-shot question; use the
		// public URL once the attachment is committed. Hook into add_attachment.
		add_action( 'add_attachment', function ( $att_id ) use ( $project_id ) {
			$src = wp_get_attachment_url( $att_id );
			if ( empty( $src ) ) {
				return;
			}
			$prompt = 'Write alt text for the image at this URL: ' . $src;
			$alt    = ( Plugin::instance()->client )->ask( $project_id, $prompt );
			if ( ! is_wp_error( $alt ) && '' !== trim( (string) $alt ) ) {
				update_post_meta( $att_id, '_wp_attachment_image_alt', wp_strip_all_tags( $alt ) );
			}
		}, 20, 1 );

		return $upload;
	}

	/**
	 * Look up the first image generator the configured team has access to.
	 * Cached for a minute to avoid extra round-trips when generating multiple
	 * images in a session.
	 */
	private function pick_image_generator() {
		$settings = get_option( 'restai_settings', array() );

		// Admin explicitly chose a generator — use it.
		if ( ! empty( $settings['image_generator'] ) ) {
			return (string) $settings['image_generator'];
		}

		$cached = wp_cache_get( 'restai_team_image_gen' );
		if ( false !== $cached ) {
			return $cached ?: null;
		}
		$team_id = isset( $settings['team_id'] ) ? (int) $settings['team_id'] : 0;
		if ( $team_id <= 0 ) {
			return null;
		}
		$team = $this->client->get( 'teams/' . $team_id );
		if ( is_wp_error( $team ) ) {
			return null;
		}
		$generators = isset( $team['image_generators'] ) ? (array) $team['image_generators'] : array();
		$pick       = ! empty( $generators ) ? (string) $generators[0] : '';
		wp_cache_set( 'restai_team_image_gen', $pick, '', MINUTE_IN_SECONDS );
		return $pick !== '' ? $pick : null;
	}

	private function build_image_prompt( $post ) {
		$snippet = wp_strip_all_tags( $post->post_content );
		$snippet = mb_substr( $snippet, 0, 400 );
		return sprintf(
			'A clean, modern editorial illustration for a blog post titled "%s". %s. Photorealistic, well-composed, no text, no watermark.',
			$post->post_title,
			$snippet
		);
	}
}
