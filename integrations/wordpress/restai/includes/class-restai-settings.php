<?php
/**
 * Settings screen + Settings API integration.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Settings {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'admin_menu', array( $this, 'register_menu' ) );
		add_action( 'admin_init', array( $this, 'register_settings' ) );
	}

	public function register_menu() {
		add_options_page(
			__( 'RESTai', 'restai' ),
			__( 'RESTai', 'restai' ),
			'manage_options',
			'restai',
			array( $this, 'render_settings_page' )
		);
		add_menu_page(
			__( 'RESTai Analytics', 'restai' ),
			__( 'RESTai', 'restai' ),
			'manage_options',
			'restai-analytics',
			array( $this, 'render_analytics_page' ),
			Icon::data_url(),
			76
		);
	}

	public function register_settings() {
		register_setting(
			'restai_settings_group',
			'restai_settings',
			array(
				'sanitize_callback' => array( $this, 'sanitize_settings' ),
				'default'           => array(),
			)
		);
		register_setting(
			'restai_settings_group',
			'restai_project_map',
			array(
				'default'           => array(),
				'sanitize_callback' => array( $this, 'sanitize_project_map' ),
			)
		);
		register_setting(
			'restai_settings_group',
			'restai_widget_settings',
			array( 'default' => array() )
		);
	}

	/**
	 * Sanitise the entire settings array.
	 */
	public function sanitize_settings( $input ) {
		$out = array();

		$out['url']     = isset( $input['url'] ) ? esc_url_raw( trim( $input['url'] ) ) : '';
		$out['api_key'] = isset( $input['api_key'] ) ? sanitize_text_field( $input['api_key'] ) : '';
		$out['team_id'] = isset( $input['team_id'] ) ? absint( $input['team_id'] ) : 0;
		$out['image_generator'] = isset( $input['image_generator'] ) ? sanitize_text_field( $input['image_generator'] ) : '';

		foreach ( array(
			'enable_widget',
			'enable_search',
			'enable_knowledge',
			'enable_moderation',
			'enable_email_ai',
			'auto_alt_text',
		) as $bool_key ) {
			$out[ $bool_key ] = ! empty( $input[ $bool_key ] );
		}

		return $out;
	}

	/**
	 * Sanitise the task -> project_id map.
	 */
	public function sanitize_project_map( $input ) {
		if ( ! is_array( $input ) ) {
			return array();
		}
		$out = array();
		foreach ( $input as $task => $value ) {
			$task_key = sanitize_key( $task );
			$id       = absint( $value );
			if ( $task_key !== '' && $id > 0 ) {
				$out[ $task_key ] = $id;
			}
		}
		return $out;
	}

	public function render_settings_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'You do not have permission to access this page.', 'restai' ) );
		}
		require RESTAI_PLUGIN_DIR . 'admin/views/settings.php';
	}

	public function render_analytics_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'You do not have permission to access this page.', 'restai' ) );
		}
		require RESTAI_PLUGIN_DIR . 'admin/views/analytics.php';
	}
}
