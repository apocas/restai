<?php
/**
 * AI-assisted comment moderation. Hooked into pre_comment_approved so the
 * decision is made before the comment is committed.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Comments {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_filter( 'pre_comment_approved', array( $this, 'moderate' ), 9, 2 );
	}

	public function moderate( $approved, $commentdata ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_moderation'] ) ) {
			return $approved;
		}
		// Already in spam/trash — don't waste a call.
		if ( in_array( $approved, array( 'spam', 'trash' ), true ) ) {
			return $approved;
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'comment_moderator' );
		if ( $project_id <= 0 ) {
			return $approved;
		}

		$author = isset( $commentdata['comment_author'] ) ? $commentdata['comment_author'] : '';
		$body   = isset( $commentdata['comment_content'] ) ? $commentdata['comment_content'] : '';

		$prompt = "AUTHOR: {$author}\nCOMMENT:\n{$body}";
		$resp   = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $resp ) ) {
			return $approved;
		}

		$json = $this->parse_json( $resp );
		if ( ! is_array( $json ) ) {
			return $approved;
		}

		if ( ! empty( $json['spam'] ) ) {
			return 'spam';
		}
		if ( ! empty( $json['toxic'] ) ) {
			return 0; // hold for moderation.
		}

		// Stash the analysis on the post for the moderator to inspect later.
		add_action( 'comment_post', function ( $comment_id ) use ( $json ) {
			update_comment_meta( $comment_id, '_restai_analysis', $json );
		}, 10, 1 );

		return $approved;
	}

	private function parse_json( $text ) {
		$text = trim( (string) $text );
		if ( '' === $text ) {
			return null;
		}
		if ( preg_match( '/```(?:json)?\s*(\{.*?\})\s*```/s', $text, $m ) ) {
			$d = json_decode( $m[1], true );
			if ( is_array( $d ) ) {
				return $d;
			}
		}
		$stripped = preg_replace( '/^```(?:[a-z]+)?\s*/i', '', $text );
		$stripped = preg_replace( '/\s*```$/', '', $stripped );
		$d = json_decode( $stripped, true );
		if ( is_array( $d ) ) {
			return $d;
		}
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
						$d = json_decode( substr( $stripped, $start, $i - $start + 1 ), true );
						if ( is_array( $d ) ) {
							return $d;
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
