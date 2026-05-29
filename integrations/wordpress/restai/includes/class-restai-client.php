<?php
/**
 * Thin HTTP client for the RESTai REST API.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Client {

	/**
	 * Resolve the base URL from settings.
	 */
	public function base_url() {
		$settings = get_option( 'restai_settings', array() );
		return isset( $settings['url'] ) ? untrailingslashit( $settings['url'] ) : '';
	}

	/**
	 * Resolve the API key from settings.
	 */
	public function api_key() {
		$settings = get_option( 'restai_settings', array() );
		return isset( $settings['api_key'] ) ? $settings['api_key'] : '';
	}

	/**
	 * Build standard auth headers.
	 */
	private function auth_headers() {
		$key = $this->api_key();
		if ( empty( $key ) ) {
			return array();
		}
		return array( 'Authorization' => 'Bearer ' . $key );
	}

	/**
	 * Run a GET request.
	 *
	 * @param string $path
	 * @param array  $args extra wp_remote args.
	 * @return array|\WP_Error
	 */
	public function get( $path, $args = array() ) {
		return $this->request( 'GET', $path, null, $args );
	}

	/**
	 * Run a POST request with a JSON body.
	 *
	 * @param string $path
	 * @param mixed  $body
	 * @param array  $args
	 * @return array|\WP_Error
	 */
	public function post( $path, $body = null, $args = array() ) {
		return $this->request( 'POST', $path, $body, $args );
	}

	/**
	 * Run a PATCH request with a JSON body.
	 */
	public function patch( $path, $body = null, $args = array() ) {
		return $this->request( 'PATCH', $path, $body, $args );
	}

	/**
	 * Run a DELETE request.
	 */
	public function delete( $path, $args = array() ) {
		return $this->request( 'DELETE', $path, null, $args );
	}

	/**
	 * Single dispatch point — handles auth, JSON encoding, error normalisation.
	 *
	 * @param string $method
	 * @param string $path
	 * @param mixed  $body
	 * @param array  $extra
	 * @return array|\WP_Error
	 */
	private function request( $method, $path, $body = null, $extra = array() ) {
		$base = $this->base_url();
		if ( empty( $base ) ) {
			return new \WP_Error( 'restai_no_url', __( 'RESTai URL is not configured.', 'restai' ) );
		}

		$url = $base . '/' . ltrim( $path, '/' );

		$args = wp_parse_args(
			$extra,
			array(
				'method'  => $method,
				'timeout' => 120,
				'headers' => array_merge(
					array( 'Content-Type' => 'application/json' ),
					$this->auth_headers()
				),
			)
		);

		if ( null !== $body ) {
			$args['body'] = wp_json_encode( $body );
		}

		$response = wp_remote_request( $url, $args );

		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$status = wp_remote_retrieve_response_code( $response );
		$raw    = wp_remote_retrieve_body( $response );
		$data   = json_decode( $raw, true );

		if ( $status >= 400 ) {
			$detail = is_array( $data ) && isset( $data['detail'] ) ? $data['detail'] : $raw;
			return new \WP_Error(
				'restai_http_' . $status,
				is_string( $detail ) ? $detail : wp_json_encode( $detail ),
				array( 'status' => $status )
			);
		}

		return $data;
	}

	/**
	 * Convenience: ask a project a one-shot question.
	 *
	 * RESTai project routes (`/projects/{projectID}/...`) are typed as `int`
	 * server-side, so callers MUST pass an integer project id — names will be
	 * rejected with HTTP 422.
	 *
	 * @param int    $project_id
	 * @param string $question
	 * @return string|\WP_Error  the answer text, or WP_Error.
	 */
	public function ask( $project_id, $question ) {
		$id = (int) $project_id;
		if ( $id <= 0 ) {
			return new \WP_Error( 'restai_bad_project_id', __( 'A valid integer project id is required.', 'restai' ) );
		}
		$resp = $this->post(
			'projects/' . $id . '/question',
			array( 'question' => $question )
		);
		if ( is_wp_error( $resp ) ) {
			return $resp;
		}
		return isset( $resp['answer'] ) ? $resp['answer'] : '';
	}

	/**
	 * Quick health-check used by the settings page.
	 */
	public function ping() {
		return $this->get( 'auth/whoami' );
	}
}
