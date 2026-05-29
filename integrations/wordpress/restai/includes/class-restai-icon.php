<?php
/**
 * Brand icon helper. Returns the RESTai brain glyph as raw SVG or as a
 * base64-encoded data URL suitable for `add_menu_page()`.
 *
 * @package RESTai
 */

namespace RESTai;

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Icon {

	/**
	 * Inline SVG of the brain glyph (Material Symbols "Psychology", 24x24).
	 *
	 * @param string $color CSS colour for `fill`.
	 */
	public static function svg( $color = 'currentColor' ) {
		return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="' . esc_attr( $color ) . '">'
			. '<path d="M13 8.57c-.79 0-1.43.64-1.43 1.43s.64 1.43 1.43 1.43 1.43-.64 1.43-1.43-.64-1.43-1.43-1.43z"/>'
			. '<path d="M13 3C9.25 3 6.2 5.94 6.02 9.64L4.1 12.2c-.41.55 0 1.34.69 1.34H6V16c0 1.1.9 2 2 2h1v3h7v-4.68c2.36-1.12 4-3.53 4-6.32 0-3.87-3.13-7-7-7zm3 7c0 .13-.01.26-.02.39l.83.66c.08.06.1.16.05.25l-.8 1.39c-.05.09-.16.12-.24.09l-.99-.4c-.21.16-.43.28-.67.39l-.15 1.06c-.01.1-.1.17-.2.17h-1.6c-.1 0-.18-.07-.2-.17l-.15-1.06c-.25-.1-.47-.23-.68-.38l-.99.4c-.09.04-.2 0-.24-.09l-.8-1.39c-.05-.08-.03-.19.05-.25l.84-.66c-.01-.13-.02-.26-.02-.39 0-.13.01-.26.03-.39l-.84-.66c-.08-.06-.1-.16-.05-.25l.8-1.39c.05-.09.16-.12.24-.09l.99.4c.21-.16.43-.28.67-.39l.15-1.06c.02-.1.1-.17.2-.17h1.6c.1 0 .18.07.2.17l.15 1.06c.24.1.46.22.67.39l.99-.4c.09-.04.2 0 .24.09l.8 1.39c.05.09.03.19-.05.25l-.83.66c.01.13.02.26.02.39z"/>'
			. '</svg>';
	}

	/**
	 * Base64-encoded data URL — the format `add_menu_page()` expects when
	 * passing a custom icon (instead of `dashicons-…`).
	 *
	 * Uses a colour that matches the WP admin sidebar (`#a7aaad`) so the icon
	 * inherits correctly without hover artifacts.
	 */
	public static function data_url() {
		return 'data:image/svg+xml;base64,' . base64_encode( self::svg( '#a7aaad' ) );
	}
}
