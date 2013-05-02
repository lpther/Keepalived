==========
Keepalived
==========

 [keepalived]
# Live configuration file for keepalived. This must
# be the same on all keepalived nodes.
# Note: Never edit this file directly, as it will be 
# overwritten by this interface.
live-config-file = /etc/keepalived/keepalived.cfg

# Directory that will contain the master config file,
# node specific generated files and archive subdirectory
master-config-dir = /etc/keepalived/master-config

# Keepalived is available in 2 configurations
# lvs: configures the kernel loadbalancing 
# vrrp: ip failover and high availability
mode = lvs, vrrp

admin:
# show ip vrrp status
# show loadbalancer server real healtcheck
# show loadbalancer logs

config:
# edit keepalived
# show pending-diff keepalived
# commit keepalived

