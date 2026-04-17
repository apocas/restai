<?php
/**
 * Plugin bootstrap.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

require_once __DIR__ . '/class-restai-icon.php';
require_once __DIR__ . '/class-restai-client.php';
require_once __DIR__ . '/class-restai-settings.php';
require_once __DIR__ . '/class-restai-provisioner.php';
require_once __DIR__ . '/class-restai-rest.php';
require_once __DIR__ . '/class-restai-content.php';
require_once __DIR__ . '/class-restai-seo.php';
require_once __DIR__ . '/class-restai-images.php';
require_once __DIR__ . '/class-restai-translation.php';
require_once __DIR__ . '/class-restai-comments.php';
require_once __DIR__ . '/class-restai-woocommerce.php';
require_once __DIR__ . '/class-restai-knowledge-sync.php';
require_once __DIR__ . '/class-restai-search.php';
require_once __DIR__ . '/class-restai-email.php';
require_once __DIR__ . '/class-restai-analytics.php';
require_once __DIR__ . '/class-restai-cron.php';
require_once __DIR__ . '/class-restai-widget.php';

/**
 * Singleton entry point.
 */
final class Plugin {

	/** @var Plugin|null */
	private static $instance = null;

	/** @var Client */
	public $client;

	/** @var Settings */
	public $settings;

	/** @var Provisioner */
	public $provisioner;

	/**
	 * Get / create the singleton.
	 */
	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
			self::$instance->boot();
		}
		return self::$instance;
	}

	/**
	 * Wire everything up.
	 */
	private function boot() {
		load_plugin_textdomain( 'restai', false, dirname( RESTAI_PLUGIN_BASENAME ) . '/languages' );

		$this->client      = new Client();
		$this->settings    = new Settings( $this->client );
		$this->provisioner = new Provisioner( $this->client );

		new Rest_API( $this->client );
		new Content( $this->client );
		new SEO( $this->client );
		new Images( $this->client );
		new Translation( $this->client );
		new Comments( $this->client );
		new WooCommerce_Integration( $this->client );
		new Knowledge_Sync( $this->client );
		new Search( $this->client );
		new Email_Personalization( $this->client );
		new Analytics( $this->client );
		new Cron( $this->client );
		new Widget();

		add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_admin_assets' ) );
		add_filter( 'plugin_action_links_' . RESTAI_PLUGIN_BASENAME, array( $this, 'plugin_action_links' ) );
	}

	/**
	 * Enqueue admin CSS/JS only on plugin screens or post-edit screens.
	 *
	 * @param string $hook Current admin page.
	 */
	public function enqueue_admin_assets( $hook ) {
		$is_plugin_screen = ( false !== strpos( $hook, 'restai' ) );
		$is_editor_screen = in_array( $hook, array( 'post.php', 'post-new.php' ), true );

		if ( ! $is_plugin_screen && ! $is_editor_screen ) {
			return;
		}

		wp_enqueue_style(
			'restai-admin',
			RESTAI_PLUGIN_URL . 'admin/css/admin.css',
			array(),
			RESTAI_VERSION
		);

		wp_enqueue_script(
			'restai-admin',
			RESTAI_PLUGIN_URL . 'admin/js/admin.js',
			array( 'jquery', 'wp-api-fetch' ),
			RESTAI_VERSION,
			true
		);

		wp_localize_script(
			'restai-admin',
			'RESTaiAdmin',
			array(
				'restUrl'    => esc_url_raw( rest_url( 'restai/v1' ) ),
				'nonce'      => wp_create_nonce( 'wp_rest' ),
				'i18n'       => array(
					'generating'      => esc_html__( 'Generating…', 'restai' ),
					'generate'        => esc_html__( 'Generate with AI', 'restai' ),
					'error'           => esc_html__( 'Something went wrong. Please try again.', 'restai' ),
					'no_project'      => esc_html__( 'No project mapped for this task. Configure it in Settings → RESTai.', 'restai' ),
					'confirm_replace' => esc_html__( 'Replace the current content with the AI-generated version?', 'restai' ),
				),
				'connected' => self::is_connected(),
			)
		);

		if ( $is_editor_screen ) {
			wp_enqueue_script(
				'restai-editor',
				RESTAI_PLUGIN_URL . 'admin/js/editor.js',
				array( 'restai-admin', 'wp-blocks', 'wp-element', 'wp-editor', 'wp-components', 'wp-data', 'wp-i18n' ),
				RESTAI_VERSION,
				true
			);
		}
	}

	/**
	 * Add a "Settings" link in the plugins list.
	 */
	public function plugin_action_links( $links ) {
		$settings_link = sprintf(
			'<a href="%s">%s</a>',
			esc_url( admin_url( 'options-general.php?page=restai' ) ),
			esc_html__( 'Settings', 'restai' )
		);
		array_unshift( $links, $settings_link );
		return $links;
	}

	/**
	 * @return bool True if the plugin has a usable connection to RESTai.
	 */
	public static function is_connected() {
		$settings = get_option( 'restai_settings', array() );
		return ! empty( $settings['url'] ) && ! empty( $settings['api_key'] );
	}

	/**
	 * Activation hook.
	 */
	public static function activate() {
		if ( false === get_option( 'restai_settings' ) ) {
			add_option(
				'restai_settings',
				array(
					'url'                 => '',
					'api_key'             => '',
					'enable_widget'       => false,
					'enable_search'       => false,
					'enable_knowledge'    => false,
					'enable_moderation'   => false,
					'enable_email_ai'     => false,
					'auto_alt_text'       => true,
				)
			);
		}
		if ( false === get_option( 'restai_project_map' ) ) {
			add_option( 'restai_project_map', array() );
		}
	}

	/**
	 * Deactivation hook — clear scheduled jobs.
	 */
	public static function deactivate() {
		wp_clear_scheduled_hook( 'restai_knowledge_sync' );
		wp_clear_scheduled_hook( 'restai_seo_audit' );
	}
}
