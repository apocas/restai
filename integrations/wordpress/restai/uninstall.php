<?php
/**
 * Uninstall handler — removes plugin options when the user explicitly deletes
 * the plugin from the WP admin. Does NOT delete any data on the connected
 * RESTai instance.
 *
 * @package RESTai
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

$option_keys = array(
	'restai_settings',
	'restai_project_map',
	'restai_widget_settings',
	'restai_widget_credentials',
	'restai_knowledge_project_id',
	'restai_knowledge_last_sync',
	'restai_install_signature',
);

foreach ( $option_keys as $key ) {
	delete_option( $key );
	delete_site_option( $key );
}

// Clear scheduled cron jobs.
wp_clear_scheduled_hook( 'restai_knowledge_sync' );
wp_clear_scheduled_hook( 'restai_seo_audit' );
