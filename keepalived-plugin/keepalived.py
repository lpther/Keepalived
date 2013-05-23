__version__ = '0.1.0a'

import sysadmintoolkit
import os
import os.path
import tempfile



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

        self.clustering_plugin = None
        self.cluster_nodeset_name = 'default'

        ret, out = sysadmintoolkit.utils.get_status_output('which keepalived', self.logger)
        if ret is not 0:
            raise sysadmintoolkit.exception.PluginError('Critical error in keepalived plugin: keepalived command could not be found', errno=201)

        self.lvs_support = False
        self.vrrp_support = False
        if 'modes' in config:
            if 'vrrp' in [mode.strip() for mode in config['modes'].split(',')]:
                self.vrrp_support = True

            if 'lvs' in [mode.strip() for mode in config['modes'].split(',')]:
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
        self.master_config_file = os.path.normpath('%s/%s.master' % (self.config_dir, os.path.basename(self.live_config_file)))

        if not os.path.exists(self.config_dir) and not os.access(os.path.dirname(self.config_dir), os.W_OK):
            self.logger.warning('Current user cannot write in config dir %s' % self.config_dir)
            self.config_dir_writable = False
        else:
            self.prepare_config_dir()

        self.add_command(sysadmintoolkit.command.ExecCommand('debug keepalived', self, self.debug), modes=['root', 'config'])
        self.add_command(sysadmintoolkit.command.ExecCommand('show config keepalived', self, self.display_master_config_file), modes=['root', 'config'])

        self.logger.debug('Keepalived plugin initialization complete')

    def update_plugin_set(self, plugin_set):
        super(Keepalived, self).update_plugin_set(plugin_set)

        if 'clustering' in self.plugin_set.get_plugins():
            self.clustering_plugin = self.plugin_set.get_plugins()['clustering']

    def prepare_config_dir(self):
        try:
            self.logger.debug('Making sure RCS dir %s is present' % os.path.abspath('%s/RCS' % self.config_dir))
            os.makedirs(os.path.abspath('%s/RCS' % self.config_dir))
        except OSError as e:
            # Ignore if dir already exists
            if e.errno != 17:
                raise e

    def parse_config_file(self, filepath):
        '''
        Runs the filepath against the parser and returns (result, message)

        result     bool
        message    str
        '''
        parser_binpath = os.path.abspath('%s/keepalived-check.rb' % self.plugin_set.get_plugins()['commandprompt'].config['scripts-dir'])

        parse_is_ok = True

    def generate_config_from_master(self, master_config_file):
        config_file_map = {}

        if self.clustering_plugin:
            for node in self.plugin_set.get_plugins()['clustering'].get_nodeset(self.cluster_nodeset_name):
                config_file_map[node] = {}
                config_file_map[node]['node_configfile'] = tempfile.NamedTemporaryFile()
                config_file_map[node]['sedresults'] = []

                node_configfile = config_file_map[node]['node_configfile'].name

                config_file_map[node]['sedresults'].append(sysadmintoolkit.utils.get_status_output("""sed 's/\\$slb_hostname/%s/' %s > %s""" \
                                                                   % (node, master_config_file, node_configfile), self.logger))
                config_file_map[node]['sedresults'].append(sysadmintoolkit.utils.get_status_output("""sed -i 's/\\$master_backup\s*%s\s*\S*\s*$/priority 150/' %s""" \
                                                                   % (node, node_configfile), self.logger))
                config_file_map[node]['sedresults'].append(sysadmintoolkit.utils.get_status_output("""sed -i 's/\\$master_backup\s*\S*\s*%s\s*$/priority 100/' %s""" \
                                                                   % (node, node_configfile), self.logger))
                config_file_map[node]['sedresults'].append(sysadmintoolkit.utils.get_status_output("""sed -i 's/\\$master_backup.*$/priority 50/' %s""" \
                                                                   % (node_configfile), self.logger))
                config_file_map[node]['sedresults'].append(sysadmintoolkit.utils.get_status_output("""sed -i '/^\s*\\$/d' %s""" \
                                                                   % (node_configfile), self.logger))

    # Dynamic keywords

    # Sysadmin-toolkit commands

    def display_master_config_file(self, user_input_obj):
        '''
        Displays the content of the master configuration file
        '''
        if self.clustering_plugin:
            print 'Verifying that master config file is synchronized across the cluster...'
            print
            buffer_nodes_list = self.clustering_plugin.run_cluster_command('md5sum %s | sort' % self.master_config_file, \
                                               self.clustering_plugin.get_reachable_nodes(self.cluster_nodeset_name))

            self.clustering_plugin.display_symmetric_buffers(buffer_nodes_list)

            print '  ' + ('*' * 80)

        if not os.access(os.path.dirname(self.master_config_file), os.R_OK):
            self.logger.warning('Cannot open master config file %s for reading ' % self.master_config_file)
            raise sysadmintoolkit.exception.PluginError('Cannot open master config file %s for reading' % self.master_config_file, errmsg=400)

        fd = open(self.master_config_file, 'r')
        print
        print fd.read()
        fd.close()

        return 0

    def debug(self, user_input_obj):
        '''
        Displays keepalived configuration and state
        '''
        print 'Keepalived plugin configuration and state:'
        print
        print '  keepalived plugin version: %s' % __version__
        print '  keepalived version: %s' % sysadmintoolkit.utils.get_status_output('keepalived -v', self.logger)[1].strip()
        print
        print '  VRRP Support: %s' % self.vrrp_support
        print '  LVS Support: %s' % self.lvs_support
        print
        print '  Clustering support: %s' % ('clustering' in self.plugin_set.get_plugins())

        if 'clustering' in self.plugin_set.get_plugins():
            print '    Nodeset: %s' % self.cluster_nodeset_name
            print '      Nodes: %s' % self.plugin_set.get_plugins()['clustering'].get_nodeset(self.cluster_nodeset_name)

        print
        print '  Live keepalived configuration file: %s (writable = %s)' % (self.live_config_file, self.live_config_file_writable)
        print '  Keepalived configuration directory: %s (writable = %s)' % (self.config_dir, self.config_dir_writable)
        print '  Keepalived master configuration file: %s' % (self.master_config_file)
        print
        print '  Path to keepalived external file parser: %s' % os.path.normpath('%s/keepalived-check.rb' % self.plugin_set.get_plugins()['commandprompt'].config['scripts-dir'])

        print

        self.generate_config_from_master()
