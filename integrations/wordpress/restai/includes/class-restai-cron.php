<?php
/**
 * Schedules background jobs — daily knowledge sync, weekly SEO audit.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Cron {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'init', array( $this, 'maybe_schedule' ) );
		add_action( 'restai_seo_audit', array( $this, 'run_seo_audit' ) );
	}

	public function maybe_schedule() {
		if ( ! wp_next_scheduled( 'restai_knowledge_sync' ) ) {
			wp_schedule_event( time() + 600, 'daily', 'restai_knowledge_sync' );
		}
		if ( ! wp_next_scheduled( 'restai_seo_audit' ) ) {
			wp_schedule_event( time() + 3600, 'weekly', 'restai_seo_audit' );
		}
	}

	/**
	 * Sweep recent posts and (re)generate SEO meta if missing.
	 */
	public function run_seo_audit() {
		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'seo_assistant' );
		if ( $project_id <= 0 ) {
			return;
		}

		$posts = get_posts( array(
			'post_type'      => array( 'post', 'page' ),
			'post_status'    => 'publish',
			'posts_per_page' => 50,
			'meta_query'     => array(
				'relation' => 'OR',
				array( 'key' => '_yoast_wpseo_metadesc', 'compare' => 'NOT EXISTS' ),
				array( 'key' => '_yoast_wpseo_metadesc', 'value' => '', 'compare' => '=' ),
			),
		) );

		$seo = new SEO( $this->client );
		foreach ( $posts as $post ) {
			$seo->generate_for_post( $post->ID );
		}
	}
}
