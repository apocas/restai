<?php
/**
 * AI-powered site search. When enabled, intercepts the standard WP search
 * query and asks the Support Bot project for an answer + relevant sources.
 *
 * The native search results page is augmented with the AI answer at the top.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Search {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'pre_get_posts', array( $this, 'noop' ) );
		add_filter( 'the_content', array( $this, 'inject_ai_answer' ), 5 );
	}

	public function noop( $q ) {
		// reserved for future query rewrites
	}

	public function inject_ai_answer( $content ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_search'] ) ) {
			return $content;
		}
		if ( ! is_search() ) {
			return $content;
		}
		static $injected = false;
		if ( $injected ) {
			return $content;
		}
		$injected = true;

		$q = get_search_query();
		if ( '' === $q ) {
			return $content;
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'support_bot' );
		if ( $project_id <= 0 ) {
			return $content;
		}

		$key = 'restai_search_' . md5( $q );
		$cached = get_transient( $key );
		if ( false === $cached ) {
			$ans = $this->client->ask( $project_id, $q );
			$cached = is_wp_error( $ans ) ? '' : $ans;
			set_transient( $key, $cached, HOUR_IN_SECONDS );
		}
		if ( '' === $cached ) {
			return $content;
		}
		$panel = sprintf(
			'<div class="restai-ai-answer" style="background:#f6f7f9;border:1px solid #e0e0e6;border-radius:8px;padding:16px;margin-bottom:16px;"><strong>%s</strong><div style="margin-top:8px;">%s</div></div>',
			esc_html__( 'AI answer', 'restai' ),
			wp_kses_post( $cached )
		);
		return $panel . $content;
	}
}
