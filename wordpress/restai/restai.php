<?php
/**
 * Plugin Name:       RESTai
 * Plugin URI:        https://restai.cloud
 * Description:       AI superpowers for WordPress — generate content, SEO meta, images, translations, AI search, embedded chat and more, powered by your own RESTai instance.
 * Version:           0.1.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            Pedro Dias
 * Author URI:        https://restai.cloud
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       restai
 * Domain Path:       /languages
 *
 * @package RESTai
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'RESTAI_VERSION', '0.1.0' );
define( 'RESTAI_PLUGIN_FILE', __FILE__ );
define( 'RESTAI_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'RESTAI_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'RESTAI_PLUGIN_BASENAME', plugin_basename( __FILE__ ) );

require_once RESTAI_PLUGIN_DIR . 'includes/class-restai.php';

register_activation_hook( __FILE__, array( 'RESTai\\Plugin', 'activate' ) );
register_deactivation_hook( __FILE__, array( 'RESTai\\Plugin', 'deactivate' ) );

add_action( 'plugins_loaded', array( 'RESTai\\Plugin', 'instance' ) );
