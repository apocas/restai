<?php
/**
 * Knowledge sync — pushes WordPress posts/pages into the Support Bot RAG
 * project so the bot is always current.
 *
 * Triggered on save_post (debounced) and via a daily cron sweep.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Knowledge_Sync {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'save_post', array( $this, 'queue_sync_for_post' ), 20, 3 );
		add_action( 'restai_knowledge_sync', array( $this, 'run_full_sync' ) );
	}

	/**
	 * On save, push (or re-push) the single post into the Support Bot project.
	 */
	public function queue_sync_for_post( $post_id, $post, $update ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_knowledge'] ) ) {
			return;
		}
		if ( wp_is_post_revision( $post_id ) || wp_is_post_autosave( $post_id ) ) {
			return;
		}
		if ( ! in_array( $post->post_status, array( 'publish' ), true ) ) {
			return;
		}
		if ( ! in_array( $post->post_type, array( 'post', 'page' ), true ) ) {
			return;
		}
		$this->push_post( $post );
	}

	/**
	 * Push a single post as a knowledge base entry. Uses RESTai's
	 * /projects/{id}/embeddings/text endpoint (text ingestion).
	 *
	 * @return true|\WP_Error
	 */
	public function push_post( $post ) {
		$plugin     = Plugin::instance();
		$project_id = (int) $plugin->provisioner->project_for( 'support_bot' );
		if ( $project_id <= 0 ) {
			return new \WP_Error( 'restai_no_support_bot', __( 'Support Bot project is not mapped.', 'restai' ) );
		}

		$text = wp_strip_all_tags( $post->post_content );
		if ( '' === trim( $text ) ) {
			return true; // nothing to push, treat as a no-op success
		}

		// Source is the only metadata RESTai's text-ingest accepts; embed the
		// permalink in it so the support bot can cite the URL back.
		$source = (string) get_permalink( $post );
		if ( '' === $source ) {
			$source = 'wp:' . $post->ID;
		}

		$resp = $this->client->post(
			'projects/' . $project_id . '/embeddings/ingest/text',
			array(
				'text'   => "Title: " . $post->post_title . "\n\n" . $text,
				'source' => $source,
			)
		);
		if ( is_wp_error( $resp ) ) {
			error_log( '[RESTai] knowledge push failed for post ' . $post->ID . ': ' . $resp->get_error_message() );
			return $resp;
		}
		return true;
	}

	/**
	 * Cron sweep — re-push everything modified since the last sync.
	 */
	public function run_full_sync() {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_knowledge'] ) ) {
			return;
		}

		$last  = get_option( 'restai_knowledge_last_sync', 0 );
		$since = $last ? date( 'Y-m-d H:i:s', $last ) : '1970-01-01 00:00:00';

		$posts = get_posts( array(
			'post_type'      => array( 'post', 'page' ),
			'post_status'    => 'publish',
			'posts_per_page' => 100,
			'date_query'     => array( array( 'after' => $since, 'column' => 'post_modified' ) ),
		) );

		foreach ( $posts as $post ) {
			$this->push_post( $post );
		}
		update_option( 'restai_knowledge_last_sync', time() );
	}

	/**
	 * Force-push every published post and page, ignoring the last-sync
	 * timestamp. Used by the "Push all to Support Bot" admin button.
	 *
	 * @return array { pushed: int, skipped: int, errors: int, error_messages: string[] }
	 */
	public function run_force_full_sync() {
		$result = array(
			'pushed'         => 0,
			'skipped'        => 0,
			'errors'         => 0,
			'error_messages' => array(),
		);

		$plugin     = Plugin::instance();
		$project_id = (int) $plugin->provisioner->project_for( 'support_bot' );
		if ( $project_id <= 0 ) {
			$result['error_messages'][] = __( 'Support Bot project is not mapped — provision it first.', 'restai' );
			$result['errors']           = 1;
			return $result;
		}

		$paged    = 1;
		$per_page = 50;
		while ( true ) {
			$posts = get_posts( array(
				'post_type'      => array( 'post', 'page' ),
				'post_status'    => 'publish',
				'posts_per_page' => $per_page,
				'paged'          => $paged,
				'orderby'        => 'ID',
				'order'          => 'ASC',
				'no_found_rows'  => false,
			) );
			if ( empty( $posts ) ) {
				break;
			}
			foreach ( $posts as $post ) {
				$pushed = $this->push_post( $post );
				if ( true === $pushed ) {
					$result['pushed']++;
				} elseif ( is_wp_error( $pushed ) ) {
					$result['errors']++;
					$msg = $pushed->get_error_message();
					if ( count( $result['error_messages'] ) < 5 ) {
						$result['error_messages'][] = '#' . $post->ID . ': ' . $msg;
					}
				} else {
					$result['skipped']++;
				}
			}
			if ( count( $posts ) < $per_page ) {
				break;
			}
			$paged++;
		}

		update_option( 'restai_knowledge_last_sync', time() );
		return $result;
	}
}
