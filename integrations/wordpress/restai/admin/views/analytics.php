<?php
/**
 * Analytics page — mirrors RESTai's /statistics endpoints into WP admin.
 *
 * @package RESTai
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>
<div class="wrap restai-analytics">
	<h1><?php esc_html_e( 'RESTai Analytics', 'restai' ); ?></h1>
	<?php if ( ! \RESTai\Plugin::is_connected() ) : ?>
		<div class="notice notice-warning"><p>
			<?php
			printf(
				/* translators: %s settings link */
				esc_html__( 'Not connected. Configure your RESTai instance first in %s.', 'restai' ),
				'<a href="' . esc_url( admin_url( 'options-general.php?page=restai' ) ) . '">' . esc_html__( 'Settings → RESTai', 'restai' ) . '</a>'
			);
			?>
		</p></div>
		<?php return; ?>
	<?php endif; ?>

	<?php $settings = get_option( 'restai_settings', array() ); ?>
	<?php if ( ! empty( $settings['enable_knowledge'] ) ) : ?>
		<div class="restai-knowledge-actions" style="margin: 12px 0; padding: 12px 14px; background:#fff; border:1px solid #e0e0e6; border-radius:6px;">
			<strong><?php esc_html_e( 'Knowledge sync', 'restai' ); ?></strong>
			<p style="margin: 4px 0 8px;">
				<?php esc_html_e( 'Push every published post and page into the Support Bot RAG project. Useful as a one-off seed when first enabling the support bot, or to recover after a vector store wipe.', 'restai' ); ?>
			</p>
			<button type="button" class="button button-primary" id="restai-push-all-knowledge">
				<?php esc_html_e( 'Push all to Support Bot', 'restai' ); ?>
			</button>
			<span id="restai-push-status" style="margin-left: 10px;"></span>
		</div>
	<?php else : ?>
		<div class="notice notice-info" style="margin: 12px 0;"><p>
			<?php
			printf(
				/* translators: %s settings link */
				esc_html__( 'Knowledge sync is disabled. Enable it in %s to surface the "Push all to Support Bot" action here.', 'restai' ),
				'<a href="' . esc_url( admin_url( 'options-general.php?page=restai' ) ) . '">' . esc_html__( 'Settings → RESTai', 'restai' ) . '</a>'
			);
			?>
		</p></div>
	<?php endif; ?>

	<div id="restai-analytics-app" class="restai-analytics-app">
		<p class="description"><?php esc_html_e( 'Loading…', 'restai' ); ?></p>
	</div>
</div>
