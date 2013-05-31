__website__ = 'https://github.com/lpther/Keepalived'
__version__ = '0.1.0b'

import sysadmintoolkit
import os
import os.path
import tempfile
import shutil
import filecmp
import collections
import time
import socket

global plugin_instance

plugin_instance = None


def get_plugin(logger, config):
    global plugin_instance

    if plugin_instance is None:
        plugin_instance = Keepalived(logger, config)

    return plugin_instance


class Keepalived(sysadmintoolkit.plugin.Plugin):
    '''
    Description
    -----------

    Provides a keepalived configuration manager, to manage an any-node
    cluster of keepalived/LVS servers.

    Some keywords are replaced in the master configuration file to
    generate per node configuration.

    Requirements
    ------------

    The plugin uses the Clustering plugin to communicated with nodes
    across the cluster.

    The keepalived package must be installed.

    Configuration
    -------------

    *modes*
      Supported modes:

      ::

        lvs:  Linux virtual server commands, such as healthchecks status (not implemented yet)
        vrrp: VRRP commands, such as vrrp status display (not implemented yet)

      Example: modes = lvs, vrrp

      Default: no mode loaded by default

    *live-config-file*
      Configuration file used by the keepalived daemon,
      must be the same on all nodes of the cluster.

      Default: live-config-file = /etc/keepalived/keepalived.conf

    *config-dir*
      Main directory where revisions, master configuration
      and node configuration files are kept.

      Default: config-dir = /etc/keepalived/master

    *reload-cmd*
      Command to trigger a reload of the keepalied daemon.

      Default: reload-cmd = service keepalived reload

    Master Configuration Special Keywords
    -------------------------------------

    *$slb_hostname*
      This is replaced by the local hostname on each node. It must be left
      verbatim in the *global_defs* section.

      Example:

      ::

        global_defs  {
          router_id $slb_hostname
        }

    *$master_backup*
      This keyword takes 2 arguments: the node you want normally you service to run on, and
      the second preferred node you want your service to run on.

      This is a bloc of configuration that is present in a *vrrp_instance* bloc. This
      replaces the "priority" keyword.

      On the master node, the priority is switched to 150, on the backup 100 and on any other
      node to 50.

      Example:

      ::

        vrrp_instance vip-group-a {
          state BACKUP
          interface eth0
          $master_backup node1 node2
          [...]
        }

      This will replace generate 3 configuration files with
      the line $master_backup changed to:

      ::

        Node        Declaration
        -------------------------
        node1       priority 150
        node2       priority 100
        node3       priority 50

    Keepalived Configuration Parser
    -------------------------------

    The parser's original website is https://github.com/frsyuki/keepalived-check, but
    the plugin uses a modified version available at https://github.com/lpther/keepalived-check


    '''
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

        self.reload_cmd = 'service keepalived reload'
        if 'reload-cmd' in config:
            self.reload_cmd = config['reload-cmd']

        self.logger.debug('Using reload command "%s"' % self.reload_cmd)

        self.add_command(sysadmintoolkit.command.ExecCommand('debug keepalived', self, self.debug), modes=['root', 'config'])
        self.add_command(sysadmintoolkit.command.ExecCommand('show config keepalived', self, self.display_master_config_file), modes=['root', 'config'])

        self.pending_config = None

        self.logger.debug('Keepalived plugin initialization complete')

    def update_plugin_set(self, plugin_set):
        super(Keepalived, self).update_plugin_set(plugin_set)

        if 'clustering' in self.plugin_set.get_plugins():
            self.clustering_plugin = self.plugin_set.get_plugins()['clustering']
            self.add_command(sysadmintoolkit.command.ExecCommand('edit keepalived', self, self.edit_master_config_file), modes=['config'])
            self.add_command(sysadmintoolkit.command.ExecCommand('show config keepalived pending', self, self.display_pending_config), modes=['config'])
            self.add_command(sysadmintoolkit.command.ExecCommand('commit keepalived', self, self.commit_pending_config), modes=['config'])


    def enter_mode(self, cmdprompt):
        super(Keepalived, self).enter_mode(cmdprompt)

        if cmdprompt.get_mode() == 'config':
            self.logger.debug('Copying master config file to a temporary file')

            master_config_copy = tempfile.NamedTemporaryFile()

            self.pending_config = { 'master_config': master_config_copy, 'node_config_files': {} }
            shutil.copyfile(self.master_config_file, master_config_copy.name)

    def leave_mode(self, cmdprompt):
        super(Keepalived, self).leave_mode(cmdprompt)

        if cmdprompt.get_mode() == 'config':
            if not filecmp.cmp(self.master_config_file, self.pending_config['master_config'].name, shallow=False):
                self.logger.warning('Uncommitted configuration files')

                print
                print '  Pending keepalived configuration changes:'
                self.display_pending_config(None)

                while True:
                    input = raw_input('>> Do you want to commit ? (y/n) - ')

                    if input.lower() in ['y', 'yes', 'n', 'no']:
                        break

                    print

                if input.lower() in ['n', 'no']:
                    print
                    print '  Aborting changes, no harm done!'
                    print

                elif input.lower() in ['y', 'yes']:
                    self.commit_pending_config(None)

            self.pending_config = None

    def prepare_config_dir(self):
        try:
            self.logger.debug('Making sure archive dir %s is present' % os.path.abspath('%s/archive' % self.config_dir))
            os.makedirs(os.path.abspath('%s/archive' % self.config_dir))
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

        (ret, out) = sysadmintoolkit.utils.get_status_output('cd %s; %s %s' % (os.path.dirname(parser_binpath), parser_binpath, filepath), self.logger)

        return (ret == 0, out)

    def generate_config_from_master(self, master_config_file):
        config_file_map = collections.OrderedDict()

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

        return config_file_map

    # Dynamic keywords

    # Sysadmin-toolkit commands

    def display_master_config_file(self, user_input_obj):
        '''
        Display the content of the master configuration file
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

    def edit_master_config_file(self, user_input_obj):
        '''
        Edit a copy of the master configuration file
        '''
        temp_master_file = tempfile.NamedTemporaryFile()
        shutil.copyfile(self.pending_config['master_config'].name, temp_master_file.name)

        self.logger.debug('Editing file %s' % temp_master_file.name)

        sysadmintoolkit.utils.execute_interactive_cmd('vi %s' % temp_master_file.name, self.logger)

        if filecmp.cmp(self.pending_config['master_config'].name, temp_master_file.name, shallow=False):
            print
            print 'No changes done, ignoring previous command'
            print

            return 0
        else:
            print
            print 'The following changes were made:'
            print

            sysadmintoolkit.utils.execute_interactive_cmd('diff --label "Master Configuration File (Working Copy)" --label "Last Edit" -U 7 %s %s' \
                                                          % (self.pending_config['master_config'].name, \
                                                             temp_master_file.name), self.logger)

            self.pending_config['master_config'].close()
            self.pending_config['master_config'] = temp_master_file

            return 0

    def display_pending_config(self, user_input_obj):
        '''
        Display uncommitted configuration
        '''
        if filecmp.cmp(self.master_config_file, self.pending_config['master_config'].name, shallow=False):
            print
            print '  No pending configuration'
            print
        else:
            print

            sysadmintoolkit.utils.execute_interactive_cmd('diff --label "Master Configuration File" --label "Pending Configuration File" -U 7 %s %s' \
                                                      % (self.master_config_file, \
                                                         self.pending_config['master_config'].name), self.logger)

            print

    def commit_pending_config(self, user_input_obj):
        '''
        Generate configuration from new master configuration file, validate, push to
        nodes of the cluster and reload the keepalived daemon
        '''
        self.logger.info('Commit requested')

        if filecmp.cmp(self.master_config_file, self.pending_config['master_config'].name, shallow=False):
            self.logger.warning('Master configuration file unchanged, no commit to do!')
            return 0

        self.logger.debug('Generating node configuration file')

        self.pending_config['node_config'] = self.generate_config_from_master(self.pending_config['master_config'].name)

        self.logger.debug('Pending config: %s' % self.pending_config)

        sed_problem = False

        for node in self.pending_config['node_config']:
            for sed_result in self.pending_config['node_config'][node]['sedresults']:
                if sed_result[0] is not 0:
                    sed_problem = sed_result
                    break

        if sed_problem:
            raise sysadmintoolkit.exception.PluginError(errmsg='Error generating node configuration file, sed result: \n%s' % sed_result[1], \
                                                        errno=300, plugin=self)
        else:
            self.logger.info('Node configuration files generated successfully')

        all_parse_ok = True
        for node in self.pending_config['node_config']:
            (parse_ok, msg) = self.parse_config_file(self.pending_config['node_config'][node]['node_configfile'].name)

            if parse_ok:
                self.logger.info('%s configuration file is OK' % node)
            else:
                self.logger.error('%s configuration file parsing FAILED:\n  %s' % (node, msg))
                print 'Error parsing configuration for node %s:\n%s' % (node, msg)
                print
                print '>> Aborting commit!'
                print

                all_parse_ok = False

                break

        if all_parse_ok:
            self.logger.info('All files have been parsed successfully')

            self.logger.debug('Backing up previous master configuration file')
            self.logger.debug('Populating config dir with new files')

            time_suffix = time.strftime("%Y-%m-%d_%H:%M:%S", time.gmtime())
            shutil.copy(self.master_config_file, '%s/archive/%s_%s' % (self.config_dir, os.path.basename(self.master_config_file), time_suffix))
            shutil.copy(self.pending_config['master_config'].name, self.master_config_file)

            for node in self.pending_config['node_config']:
                shutil.copy(self.pending_config['node_config'][node]['node_configfile'].name, \
                            '%s/%s_%s' % (self.config_dir, os.path.basename(self.master_config_file), node))

            self.logger.info('Pushing files to other nodes')

            buffer_nodes_list = self.clustering_plugin.run_cluster_command('rsync -avrp --delete %s:%s %s; echo "Return Code=$?"' % \
                                                          (socket.gethostname(), self.config_dir, self.config_dir), \
                                                          self.clustering_plugin.get_reachable_nodes(self.cluster_nodeset_name))

            all_rsync_ok = True
            for (buffer, nodes) in buffer_nodes_list:
                buffer_str = [c for c in buffer]
                if 'Return Code=0' not in buffer_str[-1]:
                    all_rsync_ok = False
                    self.logger.error('Problem with rsync with node %s:\n%s' % (nodes, '\n'.join(buffer_str)))

            if all_rsync_ok:
                self.logger.info('All files successfully pushed to all reachable nodes (%s)' % \
                                 self.clustering_plugin.get_reachable_nodes(self.cluster_nodeset_name))

                buffer_nodes_list = self.clustering_plugin.run_cluster_command('cp %s_`uname -n` %s' % \
                                                                               (self.master_config_file, self.live_config_file), \
                                                                               self.clustering_plugin.get_reachable_nodes(self.cluster_nodeset_name))

                self.logger.info('Reloading keepalived on all nodes')

                buffer_nodes_list = self.clustering_plugin.run_cluster_command('%s ; echo "Return Code=$?"' % self.reload_cmd, \
                                                          self.clustering_plugin.get_reachable_nodes(self.cluster_nodeset_name))

                all_reload_ok = True
                for (buffer, nodes) in buffer_nodes_list:
                    buffer_str = [c for c in buffer]
                    if 'Return Code=0' not in buffer_str[-1]:
                        all_reload_ok = False
                        self.logger.error('Problem with keepalived reload with node %s:\n%s' % (nodes, '\n'.join(buffer_str)))


        self.pending_config['node_config'] = {}

        if not all_parse_ok:
            return 1
        elif not all_rsync_ok:
            return 2
        elif not all_reload_ok:
            return 3
        else:
            self.logger.debug('Commit completed successfully')
            print
            print 'Commit completed successfully'
            print
            return 0

    def debug(self, user_input_obj):
        '''
        Display keepalived configuration and state
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
        print '  Keepalived reload command: "%s"' % self.reload_cmd
        print
        print '  Path to keepalived external file parser: %s' % \
                                os.path.normpath('%s/keepalived-check.rb' % \
                                self.plugin_set.get_plugins()['commandprompt'].config['scripts-dir'])
        print

        if self.pending_config:
            print '  Configuration pending commit:'
            print
            print '    Master configuration file copy: %s' % self.pending_config['master_config'].name

        print
