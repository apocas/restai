<?php
/**
 * Embed the RESTai chat widget on the front-end via a single <script> tag.
 *
 * Lazily provisions a widget on the support bot project the first time the
 * tag is rendered, so the embedded script gets a real `wk_…` widget key and
 * authenticates instead of falling into preview mode.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Widget {

	const STORE_KEY = 'restai_widget_credentials';

	public function __construct() {
		add_action( 'wp_footer', array( $this, 'maybe_embed' ) );
		add_shortcode( 'restai_chat', array( $this, 'shortcode' ) );
	}

	public function maybe_embed() {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_widget'] ) ) {
			return;
		}
		echo $this->script_tag(); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	}

	public function shortcode( $atts = array() ) {
		return $this->script_tag( $atts );
	}

	private function script_tag( $overrides = array() ) {
		$settings   = get_option( 'restai_settings', array() );
		$widget_cfg = get_option( 'restai_widget_settings', array() );
		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'support_bot' );
		if ( empty( $settings['url'] ) || $project_id <= 0 ) {
			return '';
		}

		$widget_key = $this->ensure_widget_key( $project_id, $widget_cfg );
		if ( empty( $widget_key ) ) {
			// Fall back to preview mode rather than a broken script tag.
			return '';
		}

		$url     = untrailingslashit( $settings['url'] );
		$title   = isset( $widget_cfg['title'] )   ? $widget_cfg['title']   : __( 'Chat with us', 'restai' );
		$color   = isset( $widget_cfg['color'] )   ? $widget_cfg['color']   : '#6366f1';
		$welcome = isset( $widget_cfg['welcome'] ) ? $widget_cfg['welcome'] : __( 'Hi! How can I help?', 'restai' );

		$title   = isset( $overrides['title'] )   ? $overrides['title']   : $title;
		$color   = isset( $overrides['color'] )   ? $overrides['color']   : $color;
		$welcome = isset( $overrides['welcome'] ) ? $overrides['welcome'] : $welcome;

		return sprintf(
			'<script src="%1$s/widget/chat.js" data-widget-key="%2$s" data-stream="true" data-title="%3$s" data-primary-color="%4$s" data-welcome-message="%5$s"></script>',
			esc_url( $url ),
			esc_attr( $widget_key ),
			esc_attr( $title ),
			esc_attr( $color ),
			esc_attr( $welcome )
		);
	}

	/**
	 * Returns a `wk_…` widget key for the given support-bot project. If we've
	 * already provisioned one (and it's still bound to the same project) we
	 * reuse it; otherwise we create a new one on RESTai and stash the key.
	 *
	 * @param int   $project_id
	 * @param array $widget_cfg user-tunable widget settings (title/color/...)
	 * @return string|null
	 */
	private function ensure_widget_key( $project_id, $widget_cfg ) {
		$stored = get_option( self::STORE_KEY, array() );
		if ( ! empty( $stored['widget_key'] ) && (int) ( $stored['project_id'] ?? 0 ) === $project_id ) {
			return $stored['widget_key'];
		}

		$client = Plugin::instance()->client;
		$home_host = wp_parse_url( home_url(), PHP_URL_HOST );

		$payload = array(
			'name'            => 'WordPress chat widget',
			'allowed_domains' => $home_host ? array( $home_host ) : array(),
			'config'          => array(
				'title'          => isset( $widget_cfg['title'] )   ? (string) $widget_cfg['title']   : 'Chat with us',
				'subtitle'       => '',
				'primaryColor'   => isset( $widget_cfg['color'] )   ? (string) $widget_cfg['color']   : '#6366f1',
				'welcomeMessage' => isset( $widget_cfg['welcome'] ) ? (string) $widget_cfg['welcome'] : 'Hi! How can I help?',
				'stream'         => true,
			),
		);

		$resp = $client->post( 'projects/' . $project_id . '/widgets', $payload );
		if ( is_wp_error( $resp ) || empty( $resp['widget_key'] ) ) {
			if ( is_wp_error( $resp ) ) {
				error_log( '[RESTai] widget create failed: ' . $resp->get_error_message() );
			}
			return null;
		}

		$record = array(
			'widget_key' => $resp['widget_key'],
			'widget_id'  => isset( $resp['id'] ) ? (int) $resp['id'] : 0,
			'project_id' => $project_id,
			'created_at' => time(),
		);
		update_option( self::STORE_KEY, $record );
		return $record['widget_key'];
	}
}
