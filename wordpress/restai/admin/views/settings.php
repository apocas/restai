<?php
/**
 * Settings page view.
 *
 * @package RESTai
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$settings = get_option( 'restai_settings', array() );
$widget   = get_option( 'restai_widget_settings', array() );
$map      = get_option( 'restai_project_map', array() );
$tasks    = \RESTai\Provisioner::definitions();
$connected = \RESTai\Plugin::is_connected();
?>
<div class="wrap restai-settings">
	<h1><?php esc_html_e( 'RESTai for WordPress', 'restai' ); ?></h1>

	<?php settings_errors( 'restai_settings_group' ); ?>

	<form method="post" action="options.php" id="restai-settings-form">
		<?php settings_fields( 'restai_settings_group' ); ?>

		<h2 class="title"><?php esc_html_e( 'Connection', 'restai' ); ?></h2>
		<table class="form-table" role="presentation">
			<tr>
				<th scope="row"><label for="restai_url"><?php esc_html_e( 'RESTai URL', 'restai' ); ?></label></th>
				<td>
					<input type="url" id="restai_url" name="restai_settings[url]" class="regular-text" placeholder="https://your-restai.example.com" value="<?php echo esc_attr( isset( $settings['url'] ) ? $settings['url'] : '' ); ?>" />
					<p class="description"><?php esc_html_e( 'Base URL of your RESTai instance.', 'restai' ); ?></p>
				</td>
			</tr>
			<tr>
				<th scope="row"><label for="restai_api_key"><?php esc_html_e( 'API Key', 'restai' ); ?></label></th>
				<td>
					<input type="password" id="restai_api_key" name="restai_settings[api_key]" class="regular-text" autocomplete="off" value="<?php echo esc_attr( isset( $settings['api_key'] ) ? $settings['api_key'] : '' ); ?>" />
					<button type="button" class="button" id="restai-test-connection"><?php esc_html_e( 'Test connection', 'restai' ); ?></button>
					<span id="restai-connection-status" style="margin-left:8px;"></span>
					<p class="description"><?php esc_html_e( 'Create one in RESTai under Profile → API Keys.', 'restai' ); ?></p>
				</td>
			</tr>
			<tr>
				<th scope="row"><label for="restai_team_id"><?php esc_html_e( 'Team', 'restai' ); ?></label></th>
				<td>
					<select id="restai_team_id" name="restai_settings[team_id]" data-current="<?php echo esc_attr( isset( $settings['team_id'] ) ? $settings['team_id'] : '' ); ?>">
						<option value=""><?php esc_html_e( '— select a team —', 'restai' ); ?></option>
						<?php if ( ! empty( $settings['team_id'] ) ) : ?>
							<option value="<?php echo esc_attr( $settings['team_id'] ); ?>" selected><?php echo esc_html( sprintf( __( 'Team #%d', 'restai' ), $settings['team_id'] ) ); ?></option>
						<?php endif; ?>
					</select>
					<p class="description"><?php esc_html_e( 'Projects auto-provisioned by the plugin will be created in this team. Test the connection first to load the list.', 'restai' ); ?></p>
				</td>
			</tr>
		</table>

		<h2 class="title"><?php esc_html_e( 'Features', 'restai' ); ?></h2>
		<table class="form-table" role="presentation">
			<?php
			$feature_rows = array(
				'enable_widget'     => array( __( 'Embed chat widget', 'restai' ), __( 'Add the RESTai chat bubble to public pages.', 'restai' ) ),
				'enable_search'     => array( __( 'AI site search', 'restai' ), __( 'Replace native WordPress search with semantic search via the Support Bot project.', 'restai' ) ),
				'enable_knowledge'  => array( __( 'Knowledge sync', 'restai' ), __( 'Push every published post and page into the Support Bot RAG project, so the bot is always current.', 'restai' ) ),
				'enable_moderation' => array( __( 'AI comment moderation', 'restai' ), __( 'Auto-flag spam and toxic comments; suggest replies for moderators.', 'restai' ) ),
				'enable_email_ai'   => array( __( 'AI email personalization', 'restai' ), __( 'Personalize transactional emails (welcome, password reset…) using the Email Personalizer project.', 'restai' ) ),
				'auto_alt_text'     => array( __( 'Auto alt text on uploads', 'restai' ), __( 'Generate alt text for newly uploaded images using a vision model.', 'restai' ) ),
			);
			foreach ( $feature_rows as $key => $row ) :
				$checked = ! empty( $settings[ $key ] );
				?>
			<tr>
				<th scope="row"><?php echo esc_html( $row[0] ); ?></th>
				<td>
					<label>
						<input type="checkbox" name="restai_settings[<?php echo esc_attr( $key ); ?>]" value="1" <?php checked( $checked ); ?> />
						<?php echo esc_html( $row[1] ); ?>
					</label>
				</td>
			</tr>
			<?php endforeach; ?>
			<tr>
				<th scope="row"><label for="restai_image_generator"><?php esc_html_e( 'Image generator', 'restai' ); ?></label></th>
				<td>
					<?php $current_gen = isset( $settings['image_generator'] ) ? $settings['image_generator'] : ''; ?>
					<select id="restai_image_generator" name="restai_settings[image_generator]" data-current="<?php echo esc_attr( $current_gen ); ?>">
						<option value=""><?php esc_html_e( 'Auto (first available in team)', 'restai' ); ?></option>
						<?php if ( ! empty( $current_gen ) ) : ?>
							<option value="<?php echo esc_attr( $current_gen ); ?>" selected><?php echo esc_html( $current_gen ); ?></option>
						<?php endif; ?>
					</select>
					<p class="description"><?php esc_html_e( 'Used for featured-image generation. The list is loaded from the selected team after testing the connection.', 'restai' ); ?></p>
				</td>
			</tr>
		</table>

		<h2 class="title"><?php esc_html_e( 'Task → Project mapping', 'restai' ); ?></h2>
		<p>
			<?php esc_html_e( 'Each plugin task is handled by one RESTai project. Click below to auto-create starter projects, or pick existing ones from the dropdowns.', 'restai' ); ?>
		</p>
		<p>
			<button type="button" class="button button-secondary" id="restai-provision" <?php disabled( ! $connected ); ?>>
				<?php esc_html_e( 'Auto-provision starter projects', 'restai' ); ?>
			</button>
			<span id="restai-provision-status" style="margin-left:8px;"></span>
		</p>

		<table class="form-table" role="presentation">
			<?php foreach ( $tasks as $task_key => $task ) : ?>
			<tr>
				<th scope="row"><?php echo esc_html( $task['label'] ); ?></th>
				<td>
					<select name="restai_project_map[<?php echo esc_attr( $task_key ); ?>]" data-task="<?php echo esc_attr( $task_key ); ?>" class="restai-project-select">
						<option value=""><?php esc_html_e( '— not configured —', 'restai' ); ?></option>
						<?php if ( ! empty( $map[ $task_key ] ) ) : ?>
							<option value="<?php echo esc_attr( $map[ $task_key ] ); ?>" selected><?php echo esc_html( sprintf( __( 'Project #%s', 'restai' ), $map[ $task_key ] ) ); ?></option>
						<?php endif; ?>
					</select>
					<p class="description"><?php echo esc_html( $task['name'] ); ?> · <?php echo esc_html( strtoupper( $task['type'] ) ); ?></p>
				</td>
			</tr>
			<?php endforeach; ?>
		</table>

		<h2 class="title"><?php esc_html_e( 'Chat widget', 'restai' ); ?></h2>
		<table class="form-table" role="presentation">
			<tr>
				<th scope="row"><label for="restai_widget_title"><?php esc_html_e( 'Widget title', 'restai' ); ?></label></th>
				<td><input type="text" id="restai_widget_title" name="restai_widget_settings[title]" class="regular-text" value="<?php echo esc_attr( isset( $widget['title'] ) ? $widget['title'] : 'Chat with us' ); ?>" /></td>
			</tr>
			<tr>
				<th scope="row"><label for="restai_widget_color"><?php esc_html_e( 'Primary color', 'restai' ); ?></label></th>
				<td><input type="color" id="restai_widget_color" name="restai_widget_settings[color]" value="<?php echo esc_attr( isset( $widget['color'] ) ? $widget['color'] : '#6366f1' ); ?>" /></td>
			</tr>
			<tr>
				<th scope="row"><label for="restai_widget_welcome"><?php esc_html_e( 'Welcome message', 'restai' ); ?></label></th>
				<td><input type="text" id="restai_widget_welcome" name="restai_widget_settings[welcome]" class="regular-text" value="<?php echo esc_attr( isset( $widget['welcome'] ) ? $widget['welcome'] : __( 'Hi! How can I help?', 'restai' ) ); ?>" /></td>
			</tr>
		</table>

		<?php submit_button(); ?>
	</form>
</div>
