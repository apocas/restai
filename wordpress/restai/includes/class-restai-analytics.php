<?php
/**
 * Lightweight analytics card surfaced in the dashboard widget area.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Analytics {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'wp_dashboard_setup', array( $this, 'register_widget' ) );
	}

	public function register_widget() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		wp_add_dashboard_widget(
			'restai_dashboard',
			__( 'RESTai usage (last 30 days)', 'restai' ),
			array( $this, 'render' )
		);
	}

	public function render() {
		if ( ! Plugin::is_connected() ) {
			echo '<p>';
			printf(
				/* translators: %s settings link */
				esc_html__( 'Not connected. Configure RESTai in %s.', 'restai' ),
				'<a href="' . esc_url( admin_url( 'options-general.php?page=restai' ) ) . '">Settings → RESTai</a>'
			);
			echo '</p>';
			return;
		}
		$tokens = $this->client->get( 'statistics/daily-tokens?days=30' );
		if ( is_wp_error( $tokens ) ) {
			echo '<p>' . esc_html( $tokens->get_error_message() ) . '</p>';
			return;
		}
		$rows = isset( $tokens['tokens'] ) ? $tokens['tokens'] : array();
		$total_in  = 0;
		$total_out = 0;
		$cost      = 0.0;
		foreach ( $rows as $r ) {
			$total_in  += isset( $r['input'] ) ? (int) $r['input'] : 0;
			$total_out += isset( $r['output'] ) ? (int) $r['output'] : 0;
			$cost      += isset( $r['cost'] ) ? (float) $r['cost'] : 0.0;
		}
		echo '<ul>';
		echo '<li><strong>' . esc_html__( 'Input tokens:', 'restai' ) . '</strong> ' . esc_html( number_format_i18n( $total_in ) ) . '</li>';
		echo '<li><strong>' . esc_html__( 'Output tokens:', 'restai' ) . '</strong> ' . esc_html( number_format_i18n( $total_out ) ) . '</li>';
		echo '<li><strong>' . esc_html__( 'Cost:', 'restai' ) . '</strong> ' . esc_html( number_format_i18n( $cost, 3 ) ) . '</li>';
		echo '</ul>';
		echo '<p><a href="' . esc_url( admin_url( 'admin.php?page=restai-analytics' ) ) . '">' . esc_html__( 'Full analytics →', 'restai' ) . '</a></p>';
	}
}
