#!/usr/bin/env python3
'''
Translation layer for syncing VM status information from libvirtd to systemd
'''


from enum import IntEnum


class DomainState(IntEnum):
    '''
    Integer based domain state
    https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainState
    '''
    NOSTATE     = 0
    RUNNING     = 1
    BLOCKED     = 2
    PAUSED      = 3
    SHUTDOWN    = 4
    SHUTOFF     = 5
    CRASHED     = 6
    PMSUSPENDED = 7
    LAST        = 8

#
# HOW THIS WILL WORK
#
# Main loop: listen for libvirt events and fire some callbacks
# Callbacks: when a VM changes state from/to active, start/stop the corresponding systemd unit@
#

#
# SNIPPETS
#

#connection = libvirt.openReadOnly()

#    for domain in connection.listAllDomains():
#        if domain.isActive():
#            print(f'Domain is running: {domain.name()}')
#        else:
#            print(f'Domain is inactive: {domain.name()}')
#    print(args)
