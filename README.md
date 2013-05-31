# Keepalived Plugin #

A Sysadmin-Toolkit Plugin that manages keepalived's configuration across a cluster of LVS/Keepalived nodes.

## Plugin Description ##

The plugin synchronizes configuration across the cluster, after archiving and parsing for syntax validation.

## Installation ##

Clustering Plugin is coded for python 2.7 on Ubuntu 12.04, and requires the following packages:

- Sysadmin-Toolkit ([https://github.com/lpther/SysadminToolkit](https://github.com/lpther/SysadminToolkit))
- LVS plugin ([https://github.com/lpther/LVS](https://github.com/lpther/LVS))
- Clustering plugin ([https://github.com/lpther/Clustering](https://github.com/lpther/Clustering "https://github.com/lpther/Clustering"))

## Basic Usage ##

The plugin introduces keywords in the master keepalived.conf configuration file:

	   $slb_hostname
	          This is replaced by the local hostname on each node. It must be left verbatim in the global_defs section.
	
	          Example:
	
	          global_defs  {
	            router_id $slb_hostname
	          }
	
	   $master_backup
	          This keyword takes 2 arguments: the node you want normally you service to run on, and the second preferred node 
			  you want your service to run on.
	
	          This is a bloc of configuration that is present in a vrrp_instance bloc. This replaces the "priority" keyword.
	
	          On the master node, the priority is switched to 150, on the backup 100 and on any other node to 50.
	
	          Example:
	
	          vrrp_instance vip-group-a {
	            state BACKUP
	            interface eth0
	            $master_backup node1 node2
	            [...]
	          }
	
	          This will replace generate 3 configuration files with the line $master_backup changed to:
	
	          Node        Declaration
	          -------------------------
	          node1       priority 150
	          node2       priority 100
	          node3       priority 50
	
Display the actual configuration, after verifying that it is synchronized across the cluster.

	sysadmin-toolkit(root)# show config keepalived
	Verifying that master config file is synchronized across the cluster...
	
	Symmteric
	      lvs-1, lvs-2:
	        9ca6b36ccc7edc66f41c0af898e9b7d9  /root/keepalived/master/keepalived.conf.master
	
	  ********************************************************************************
	
	global_defs  {
	        router_id $slb_hostname
	}
	
	vrrp_instance vrrp_vips {
	        state BACKUP
	        interface eth0
	        virtual_router_id 10
	        $master_backup lvs-1 lvs-2
	        advert_int 1
	        preempt_delay 10
	        authentication {
	                auth_type PASS
	                auth_pass lvspassw0rd
	        }
	        virtual_ipaddress {
	                10.10.10.100/24 dev eth0
	        }
	}

To modify the keepalived configuration, the CLI must be in configuration mode:

	sysadmin-toolkit(root)# switchmode config
	sysadmin-toolkit(config)# edit keepalived
	
	The following changes were made:
	
	--- Master Configuration File (Working Copy)
	+++ Last Edit
	@@ -5,15 +5,15 @@
	 vrrp_instance vrrp_vips {
	        state BACKUP
	        interface vlan221
	        virtual_router_id 10
	-       $master_backup lvs-1 lvs-2
	+       $master_backup lvs-2 lvs-1
	        advert_int 1
	        preempt_delay 10
	        authentication {
	                auth_type PASS
	                auth_pass lvspassw0rd
	        }
	        virtual_ipaddress {

	sysadmin-toolkit(config)# commit keepalived
	
	Commit completed successfully

The actual configuration running on the LVS/Keepalived nodes will be changed and applied, after a parsing validation.

Ex (on lvs-1):

	cat keepalived.conf

	global_defs  {
	        router_id lvs-1
	}
	
	vrrp_instance vrrp_vips {
	        state BACKUP
	        interface vlan221
	        virtual_router_id 10
	        priority 150
	        advert_int 1
	        preempt_delay 10
	        authentication {
	                auth_type PASS
	                auth_pass lvspassw0rd
	        }
	        virtual_ipaddress {
	                10.10.10.100/24 dev vlan221
	        }
	}

All configuration revision are available on all nodes of the cluster:

	lvs-1:/etc/keepalived/master# find .
	.
	./keepalived.conf.master_lvs-2
	./keepalived.conf.master_lvs-1
	./keepalived.conf.master
	./archive
	./archive/keepalived.conf.master_2013-05-25_00:41:35
	./archive/keepalived.conf.master_2013-05-31_20:43:10
	./archive/keepalived.conf.master_2013-05-25_00:25:49
    [...]

# Related Projects #

- Sysadmin-Toolkit ([https://github.com/lpther/SysadminToolkit](https://github.com/lpther/SysadminToolkit))
- Keepalived external parser ([https://github.com/lpther/keepalived-check](https://github.com/lpther/keepalived-check))