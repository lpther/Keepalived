__version__ = '0.1.0a'

import sysadmintoolkit
import os


global plugin_instance

plugin_instance = None


def get_plugin(logger, config):
    global plugin_instance

    if plugin_instance is None:
        plugin_instance = Keepalived(logger, config)

    return plugin_instance


class Keepalived(sysadmintoolkit.plugin.Plugin):
    def __init__(self, logger, config):
        super(Keepalived, self).__init__('keepalived', logger, config)

        self.lvs_support = False
        self.vrrp_support = False
        if 'modes' in config:
            if 'vrrp' in config['modes'].split(','):
                self.vrrp_support = True

            if 'lvs' in config['modes'].split(','):
                self.lvs_support = True

        if self.lvs_support:
            self.logger.info('Keepalived plugin started with LVS support')

        if self.vrrp_support:
            self.logger.info('Keepalived plugin started with VRRP support')

        self.live_config_file = '/etc/keepalived/keepalived.conf'
        self.live_config_file_writable = True
        if 'live-config-file' in config:
            self.live_config_file = config['live-config-file']

        if not os.path.exists(self.live_config_file) and not os.access(os.path.dirname(self.live_config_file), os.W_OK):
            self.logger.warning('Current user cannot write the live config file %s' % self.live_config_file)
            self.live_config_file_writable = False

        self.config_dir = '/etc/keepalived/master'
        self.config_dir_writable = True
        if 'config-dir' in config:
            self.config_dir = config['config-dir']

        if not os.path.exists(self.config_dir) and not os.access(os.path.dirname(self.config_dir), os.W_OK):
            self.logger.warning('Current user cannot write in config dir %s' % self.config_dir)
            self.config_dir_writable = False

        self.logger.debug('Keepalived plugin initialization complete')

    # Dynamic keywords

    # Sysadmin-toolkit commands
