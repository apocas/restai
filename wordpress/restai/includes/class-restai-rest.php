<?php
/**
 * Plugin REST API endpoints — used by the admin UI to drive RESTai actions
 * without exposing the connected RESTai key to the browser.
 *
 * Routes are registered under namespace restai/v1. All routes require the
 * caller to have the WordPress capability appropriate to the action.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Rest_API {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'rest_api_init', array( $this, 'register_routes' ) );
	}

	public function register_routes() {
		$ns = 'restai/v1';

		register_rest_route( $ns, '/test-connection', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'test_connection' ),
			'permission_callback' => array( $this, 'admin_only' ),
			'args'                => array(
				'url'     => array( 'required' => true ),
				'api_key' => array( 'required' => true ),
			),
		) );

		register_rest_route( $ns, '/provision', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'provision' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/projects', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'list_projects' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/llms', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'list_llms' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/teams', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'list_teams' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/team-resources', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'team_resources' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/generate', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'generate' ),
			'permission_callback' => array( $this, 'editor_only' ),
			'args'                => array(
				'task'   => array( 'required' => true ),
				'prompt' => array( 'required' => true ),
			),
		) );

		register_rest_route( $ns, '/seo-meta', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'seo_meta' ),
			'permission_callback' => array( $this, 'editor_only' ),
			'args'                => array(
				'post_id' => array( 'required' => true ),
			),
		) );

		register_rest_route( $ns, '/featured-image', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'featured_image' ),
			'permission_callback' => array( $this, 'editor_only' ),
			'args'                => array(
				'post_id' => array( 'required' => true ),
			),
		) );

		register_rest_route( $ns, '/translate', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'translate' ),
			'permission_callback' => array( $this, 'editor_only' ),
			'args'                => array(
				'post_id'  => array( 'required' => true ),
				'language' => array( 'required' => true ),
			),
		) );

		register_rest_route( $ns, '/analytics', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'analytics' ),
			'permission_callback' => array( $this, 'admin_only' ),
		) );

		register_rest_route( $ns, '/sync-knowledge', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'sync_knowledge_now' ),
			'permission_callback' => array( $this, 'admin_only' ),
			'args'                => array(
				'full' => array( 'required' => false, 'type' => 'boolean', 'default' => false ),
			),
		) );
	}

	public function admin_only() {
		return current_user_can( 'manage_options' );
	}

	public function editor_only() {
		return current_user_can( 'edit_posts' );
	}

	/**
	 * Test the supplied URL + API key by hitting /auth/whoami on RESTai.
	 */
	public function test_connection( $request ) {
		$url     = esc_url_raw( $request->get_param( 'url' ) );
		$api_key = sanitize_text_field( $request->get_param( 'api_key' ) );

		if ( empty( $url ) || empty( $api_key ) ) {
			return new \WP_REST_Response( array( 'ok' => false, 'error' => 'missing_credentials' ), 400 );
		}

		$response = wp_remote_get( untrailingslashit( $url ) . '/auth/whoami', array(
			'timeout' => 15,
			'headers' => array( 'Authorization' => 'Bearer ' . $api_key ),
		) );

		if ( is_wp_error( $response ) ) {
			return new \WP_REST_Response( array( 'ok' => false, 'error' => $response->get_error_message() ), 502 );
		}

		$status = wp_remote_retrieve_response_code( $response );
		if ( $status >= 400 ) {
			return new \WP_REST_Response( array( 'ok' => false, 'status' => $status ), 200 );
		}

		$body = json_decode( wp_remote_retrieve_body( $response ), true );
		return new \WP_REST_Response( array(
			'ok'       => true,
			'username' => isset( $body['username'] ) ? $body['username'] : null,
			'is_admin' => isset( $body['is_admin'] ) ? (bool) $body['is_admin'] : false,
		), 200 );
	}

	public function provision() {
		$plugin = Plugin::instance();
		$result = $plugin->provisioner->provision_all();
		return new \WP_REST_Response( $result, 200 );
	}

	public function list_projects() {
		$resp = $this->client->get( 'projects' );
		if ( is_wp_error( $resp ) ) {
			return new \WP_Error( 'restai_upstream', $resp->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( $resp, 200 );
	}

	public function list_llms() {
		$resp = $this->client->get( 'llms' );
		if ( is_wp_error( $resp ) ) {
			return new \WP_Error( 'restai_upstream', $resp->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( array( 'llms' => $resp ), 200 );
	}

	public function team_resources() {
		$settings = get_option( 'restai_settings', array() );
		$team_id  = isset( $settings['team_id'] ) ? (int) $settings['team_id'] : 0;
		if ( $team_id <= 0 ) {
			return new \WP_REST_Response( array( 'image_generators' => array(), 'audio_generators' => array() ), 200 );
		}
		$team = $this->client->get( 'teams/' . $team_id );
		if ( is_wp_error( $team ) ) {
			return new \WP_Error( 'restai_upstream', $team->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response(
			array(
				'image_generators' => isset( $team['image_generators'] ) ? array_values( (array) $team['image_generators'] ) : array(),
				'audio_generators' => isset( $team['audio_generators'] ) ? array_values( (array) $team['audio_generators'] ) : array(),
			),
			200
		);
	}

	public function list_teams() {
		$resp = $this->client->get( 'teams' );
		if ( is_wp_error( $resp ) ) {
			return new \WP_Error( 'restai_upstream', $resp->get_error_message(), array( 'status' => 502 ) );
		}
		$out = array();
		$teams = isset( $resp['teams'] ) ? $resp['teams'] : array();
		foreach ( $teams as $t ) {
			if ( isset( $t['id'], $t['name'] ) ) {
				$out[] = array( 'id' => (int) $t['id'], 'name' => $t['name'] );
			}
		}
		return new \WP_REST_Response( array( 'teams' => $out ), 200 );
	}

	public function generate( $request ) {
		$task   = sanitize_key( $request->get_param( 'task' ) );
		$prompt = (string) $request->get_param( 'prompt' );

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( $task );
		if ( $project_id <= 0 ) {
			return new \WP_Error( 'restai_no_project', sprintf( __( 'No RESTai project mapped for task "%s". Configure it in Settings → RESTai.', 'restai' ), $task ), array( 'status' => 400 ) );
		}

		$answer = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $answer ) ) {
			return new \WP_Error( 'restai_upstream', $answer->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( array( 'output' => $answer ), 200 );
	}

	public function seo_meta( $request ) {
		$post_id = absint( $request->get_param( 'post_id' ) );
		if ( ! $post_id || ! current_user_can( 'edit_post', $post_id ) ) {
			return new \WP_Error( 'restai_forbidden', __( 'You do not have permission to edit this post.', 'restai' ), array( 'status' => 403 ) );
		}
		$seo = new SEO( $this->client );
		$res = $seo->generate_for_post( $post_id );
		if ( is_wp_error( $res ) ) {
			return new \WP_Error( 'restai_upstream', $res->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( $res, 200 );
	}

	public function featured_image( $request ) {
		$post_id = absint( $request->get_param( 'post_id' ) );
		if ( ! $post_id || ! current_user_can( 'edit_post', $post_id ) ) {
			return new \WP_Error( 'restai_forbidden', __( 'You do not have permission to edit this post.', 'restai' ), array( 'status' => 403 ) );
		}
		$images = new Images( $this->client );
		$res    = $images->generate_featured_image( $post_id );
		if ( is_wp_error( $res ) ) {
			return new \WP_Error( 'restai_upstream', $res->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( $res, 200 );
	}

	public function translate( $request ) {
		$post_id  = absint( $request->get_param( 'post_id' ) );
		$language = sanitize_text_field( $request->get_param( 'language' ) );
		if ( ! $post_id || ! current_user_can( 'edit_post', $post_id ) ) {
			return new \WP_Error( 'restai_forbidden', __( 'You do not have permission to edit this post.', 'restai' ), array( 'status' => 403 ) );
		}
		$tr  = new Translation( $this->client );
		$res = $tr->translate_post( $post_id, $language );
		if ( is_wp_error( $res ) ) {
			return new \WP_Error( 'restai_upstream', $res->get_error_message(), array( 'status' => 502 ) );
		}
		return new \WP_REST_Response( $res, 200 );
	}

	public function analytics() {
		$summary = $this->client->get( 'statistics/summary' );
		$tokens  = $this->client->get( 'statistics/daily-tokens?days=30' );
		return new \WP_REST_Response(
			array(
				'summary' => is_wp_error( $summary ) ? null : $summary,
				'tokens'  => is_wp_error( $tokens ) ? null : $tokens,
			),
			200
		);
	}

	public function sync_knowledge_now( $request ) {
		$settings = get_option( 'restai_settings', array() );
		if ( empty( $settings['enable_knowledge'] ) ) {
			return new \WP_Error(
				'restai_knowledge_disabled',
				__( 'Knowledge sync is disabled. Enable it in Settings → RESTai.', 'restai' ),
				array( 'status' => 400 )
			);
		}
		$full = (bool) $request->get_param( 'full' );
		if ( $full ) {
			$sync   = new Knowledge_Sync( $this->client );
			$result = $sync->run_force_full_sync();
			return new \WP_REST_Response( $result, 200 );
		}
		do_action( 'restai_knowledge_sync' );
		return new \WP_REST_Response( array( 'ok' => true ), 200 );
	}
}
