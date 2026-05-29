<?php
/**
 * AI-personalized transactional emails. Wraps wp_mail's $message before send,
 * passing it through the Email Personalizer project.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Email_Personalization {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_filter( 'wp_mail', array( $this, 'personalize' ), 99, 1 );
	}

	public function personalize( $args ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_email_ai'] ) ) {
			return $args;
		}
		if ( empty( $args['message'] ) ) {
			return $args;
		}

		// Only touch transactional emails — skip if header indicates marketing
		// or contains an unsubscribe link.
		$msg = (string) $args['message'];
		if ( false !== stripos( $msg, 'unsubscribe' ) ) {
			return $args;
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'email_personalizer' );
		if ( $project_id <= 0 ) {
			return $args;
		}

		$rewritten = $this->client->ask( $project_id, $msg );
		if ( is_wp_error( $rewritten ) || '' === trim( (string) $rewritten ) ) {
			return $args;
		}
		$args['message'] = $rewritten;
		return $args;
	}
}
