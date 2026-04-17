<?php
/**
 * Content generation glue + Gutenberg block registration.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Content {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'init', array( $this, 'register_block' ) );
		add_shortcode( 'restai_generate', array( $this, 'shortcode' ) );
	}

	/**
	 * Register the "RESTai Content" Gutenberg block.
	 */
	public function register_block() {
		if ( ! function_exists( 'register_block_type' ) ) {
			return;
		}
		register_block_type(
			'restai/content-generator',
			array(
				'api_version'     => 2,
				'title'           => __( 'RESTai: Generated Content', 'restai' ),
				'category'        => 'widgets',
				// Icon is set in JS via blocks/content-generator/index.js so we
				// can use a custom brain SVG (Dashicons has no brain glyph).
				'icon'            => 'admin-customizer',
				'editor_script'   => 'restai-block-content',
				'render_callback' => array( $this, 'render_block' ),
				'attributes'      => array(
					'task'   => array( 'type' => 'string', 'default' => 'content_writer' ),
					'prompt' => array( 'type' => 'string', 'default' => '' ),
					'cache'  => array( 'type' => 'boolean', 'default' => true ),
				),
			)
		);

		wp_register_script(
			'restai-block-content',
			RESTAI_PLUGIN_URL . 'blocks/content-generator/index.js',
			array( 'wp-blocks', 'wp-element', 'wp-i18n', 'wp-components', 'wp-block-editor' ),
			RESTAI_VERSION,
			true
		);
	}

	/**
	 * Server-side render — calls RESTai with the configured prompt.
	 *
	 * Caches per (post_id, task, prompt) in transients to avoid re-billing on
	 * every page load.
	 */
	public function render_block( $attrs ) {
		$task   = isset( $attrs['task'] ) ? sanitize_key( $attrs['task'] ) : 'content_writer';
		$prompt = isset( $attrs['prompt'] ) ? (string) $attrs['prompt'] : '';
		$cache  = ! isset( $attrs['cache'] ) || $attrs['cache'];

		if ( empty( $prompt ) ) {
			return '<!-- restai: missing prompt -->';
		}

		$key = 'restai_blk_' . md5( $task . '|' . $prompt );
		if ( $cache ) {
			$cached = get_transient( $key );
			if ( false !== $cached ) {
				return $cached;
			}
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( $task );
		if ( $project_id <= 0 ) {
			return '<!-- restai: no project mapped for ' . esc_html( $task ) . ' -->';
		}

		$answer = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $answer ) ) {
			return '<!-- restai error: ' . esc_html( $answer->get_error_message() ) . ' -->';
		}

		if ( $cache ) {
			set_transient( $key, $answer, DAY_IN_SECONDS );
		}
		return $answer;
	}

	/**
	 * [restai_generate task="content_writer" prompt="…"] shortcode.
	 */
	public function shortcode( $atts ) {
		$atts = shortcode_atts(
			array(
				'task'   => 'content_writer',
				'prompt' => '',
				'cache'  => '1',
			),
			$atts,
			'restai_generate'
		);
		return $this->render_block(
			array(
				'task'   => $atts['task'],
				'prompt' => $atts['prompt'],
				'cache'  => '1' === (string) $atts['cache'],
			)
		);
	}
}
