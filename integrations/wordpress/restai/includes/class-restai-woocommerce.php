<?php
/**
 * WooCommerce hooks: AI-generated product descriptions, FAQ generation, and a
 * product-aware support shortcode.
 *
 * Loads only when WooCommerce is active.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class WooCommerce_Integration {

	/** @var Client */
	private $client;

	public function __construct( Client $client ) {
		$this->client = $client;
		add_action( 'init', array( $this, 'maybe_register' ) );
		add_shortcode( 'restai_product_faq', array( $this, 'product_faq_shortcode' ) );
	}

	public function maybe_register() {
		if ( ! class_exists( 'WooCommerce' ) ) {
			return;
		}
		add_action( 'add_meta_boxes', array( $this, 'metabox' ) );
		add_action( 'wp_ajax_restai_generate_product_desc', array( $this, 'ajax_generate_description' ) );
	}

	public function metabox() {
		add_meta_box(
			'restai_woocommerce',
			__( 'RESTai (AI)', 'restai' ),
			array( $this, 'metabox_view' ),
			'product',
			'side',
			'low'
		);
	}

	public function metabox_view( $post ) {
		wp_nonce_field( 'restai_product', '_restai_product_nonce' );
		echo '<p><button type="button" class="button" id="restai-gen-desc" data-post-id="' . esc_attr( $post->ID ) . '">' . esc_html__( 'Generate description', 'restai' ) . '</button></p>';
		echo '<p class="description">' . esc_html__( 'Calls the WP Product Writer project with this product\'s attributes.', 'restai' ) . '</p>';
		// Inline JS — keep it tiny.
		?>
		<script>
		jQuery(document).on('click', '#restai-gen-desc', function () {
			var $btn = jQuery(this);
			$btn.prop('disabled', true).text(<?php echo wp_json_encode( __( 'Generating…', 'restai' ) ); ?>);
			jQuery.post(ajaxurl, {
				action: 'restai_generate_product_desc',
				_wpnonce: jQuery('#_restai_product_nonce').val(),
				post_id: $btn.data('post-id'),
			}).done(function (res) {
				if (res && res.success && res.data && res.data.description) {
					var ed = document.getElementById('content');
					if (ed) ed.value = res.data.description;
					if (window.tinymce && window.tinymce.activeEditor) {
						window.tinymce.activeEditor.setContent(res.data.description);
					}
				} else {
					alert(<?php echo wp_json_encode( __( 'Could not generate description.', 'restai' ) ); ?>);
				}
			}).always(function () {
				$btn.prop('disabled', false).text(<?php echo wp_json_encode( __( 'Generate description', 'restai' ) ); ?>);
			});
		});
		</script>
		<?php
	}

	public function ajax_generate_description() {
		check_ajax_referer( 'restai_product', '_wpnonce' );
		$post_id = isset( $_POST['post_id'] ) ? absint( $_POST['post_id'] ) : 0;
		if ( ! $post_id || ! current_user_can( 'edit_post', $post_id ) ) {
			wp_send_json_error( 'forbidden', 403 );
		}

		$product = function_exists( 'wc_get_product' ) ? wc_get_product( $post_id ) : null;
		if ( ! $product ) {
			wp_send_json_error( 'not_a_product', 400 );
		}

		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'product_writer' );
		if ( $project_id <= 0 ) {
			wp_send_json_error( 'no_project', 400 );
		}

		$attrs = array(
			'name'  => $product->get_name(),
			'price' => $product->get_price(),
			'sku'   => $product->get_sku(),
			'short' => $product->get_short_description(),
		);
		$prompt = "Product attributes: " . wp_json_encode( $attrs );
		$desc   = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $desc ) ) {
			wp_send_json_error( $desc->get_error_message(), 502 );
		}
		wp_send_json_success( array( 'description' => $desc ) );
	}

	/**
	 * [restai_product_faq] — renders an AI-generated FAQ for the current
	 * product, cached in a transient.
	 */
	public function product_faq_shortcode() {
		if ( ! is_product() ) {
			return '';
		}
		$pid = get_the_ID();
		$key = 'restai_faq_' . $pid;
		$cached = get_transient( $key );
		if ( false !== $cached ) {
			return $cached;
		}
		$plugin     = Plugin::instance();
		$project_id = $plugin->provisioner->project_for( 'product_writer' );
		if ( $project_id <= 0 ) {
			return '';
		}
		$product = wc_get_product( $pid );
		if ( ! $product ) {
			return '';
		}
		$prompt = "Generate an HTML <h3>FAQ</h3> with 5 likely customer questions and answers for this product:\n" .
			'Name: ' . $product->get_name() . "\n" .
			'Description: ' . wp_strip_all_tags( $product->get_description() );
		$out = $this->client->ask( $project_id, $prompt );
		if ( is_wp_error( $out ) ) {
			return '';
		}
		set_transient( $key, $out, WEEK_IN_SECONDS );
		return $out;
	}
}
