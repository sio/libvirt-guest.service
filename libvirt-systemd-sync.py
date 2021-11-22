#!/usr/bin/env python3
'''
Translation layer for syncing VM status information from libvirtd to systemd
'''

import dbus     # python3-dbus
import libvirt  # python3-libvirt
import logging
import os.path
import re
import threading

from dbus.mainloop.glib import DBusGMainLoop  # python3-dbus
from enum import IntEnum
from gi.repository import GLib  # python3-gi

from pprint import pformat  # debug


logging.basicConfig()
log = logging.getLogger('libvirt-systemd-sync')
log.level = logging.DEBUG  # debug


class LibvirtDomainState(IntEnum):
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


class ThreadSafeKeyValue:
    '''
    Even though Python built-ins should be thread safe thanks to GIL,
    having explicit thread safety is better
    '''

    def __init__(self, *a, **ka):
        self._storage = dict(*a, **ka)
        self._lock = threading.RLock()

    def __getitem__(self, key):
        with self._lock:
            return self._storage[key]

    def get(self, key, **ka):
        with self._lock:
            return self._storage.get(key, **ka)

    def __setitem__(self, key, value):
        with self._lock:
            self._storage[key] = value

    def items(self):
        with self._lock:
            return list(self._storage.items())

    def __in__(self, key):
        with self._lock:
            return key in self._storage

    def __str__(self):
        with self._lock:
            return str(self._storage)

    def __repr__(self):
        with self._lock:
            return f'<{self.__class__.__name__}({self._storage})>'


def systemd_unescape(text):
    '''
    Convert systemd escaped strings into normal strings

    Example: libvirt_2dguest_40three_2eservice -> libvirt-guest@three.service
    More information: https://stackoverflow.com/questions/59333183
    '''
    return text.replace('_', r'\x').encode('latin-1').decode('unicode_escape').encode('latin-1').decode('utf-8')


def systemd_parse_unit_name(unit_name: str):
    '''Split unit name into prefix, suffix and unit type'''
    unit_name, unit_type = os.path.splitext(unit_name)
    if '@' in unit_name:
        prefix, suffix = unit_name.rsplit('@', 1)
    else:
        prefix = unit_name
        suffix = ''
    return prefix, suffix, unit_type


def libvirt_event_watch(template_prefix):
    '''
    Listen for libvirt events
    and translate them into systemd units state changes
    '''
    connection = libvirt.openReadOnly()
    state = libvirt_get_initial_state(connection)
    systemd_unit_watch(template_prefix, libvirt_state=state)
    print(last_known_state)


def libvirt_get_initial_state(connection):
    '''Translate initial libvirt state into systemd units state'''
    state = ThreadSafeKeyValue()
    for domain in connection.listAllDomains():
        name = domain.name()
        state[name] = 'active' if domain.isActive() else 'inactive'
    return state


class SystemdUnitManager:
    '''DBus wrapper for systemd API'''

    def __init__(self, template_prefix: str):
        self.template_prefix = template_prefix
        DBusGMainLoop(set_as_default=True)
        self.event_loop = GLib.MainLoop()
        self.dbus = dbus.SystemBus()
        self.daemon = self.dbus_object('/org/freedesktop/systemd1')
        self.manager = dbus.Interface(self.daemon, 'org.freedesktop.systemd1.Manager')

    def dbus_object(self, path: str):
        return self.dbus.get_object('org.freedesktop.systemd1', path)

    def unit(self, name: str):
        '''Return DBus object for the corresponding unit name'''
        unit = SystemdUnitWrapper(self, name)
        unit.update_properties()
        return unit

    def set_initial_state(self, libvirt_state):
        '''Apply initial state of systemd units'''
        for domain, state in libvirt_state.items():
            unit_name = f'{self.template_prefix}@{domain}.service'
            unit = self.unit(unit_name)
            log.debug(f'Initial systemd state for {unit_name}: {unit["ActiveState"]}')
            if state == unit['ActiveState']:
                continue
            if state == 'active':
                log.debug(f'Systemd state does not match libvirt. Starting unit: {unit_name}')
                unit.Start('fail')
            elif state == 'inactive':
                log.debug(f'Systemd state does not match libvirt. Stopping unit: {unit_name}')
                unit.Stop('fail')
            else:
                raise ValueError('unhandled state for domain {domain}: {state}')
        for unit_info in self.manager.ListUnits():
            name = unit_info[0]
            prefix, domain, _ = systemd_parse_unit_name(name)
            if prefix != self.template_prefix:
                continue
            systemd_status = unit_info[3]
            libvirt_status = libvirt_state.get(domain)
            if systemd_status == libvirt_status:
                continue
            unit = self.unit(name)
            if libvirt_status == 'active':
                log.warn(f'Active domain should have been handled already, fixing: {domain}')
                unit.Start('fail')
            elif libvirt_status == 'inactive':
                log.warn(f'Inactive domain should have been handled already, fixing: {domain}')
                unit.Stop('fail')
            elif libvirt_status is None:
                log.debug(f'There is no libvirt domain for unit {name}. Stopping unit')
                unit.Stop('fail')
            else:
                raise ValueError('unhandled state for domain {domain}: {libvirt_status}')


class SystemdUnitWrapper:
    '''Unit wrapper for systemd DBus API'''

    INTERFACE =  'org.freedesktop.systemd1.Unit'

    def __init__(self, systemd: SystemdUnitManager, name: str):
        self._dbus_object = systemd.dbus_object(systemd.manager.LoadUnit(name))
        self._dbus_iface = dbus.Interface(self._dbus_object, self.INTERFACE)
        self._properties = {}

    def update_properties(self):
        self._properties = self._dbus_iface.GetAll(self.INTERFACE, dbus_interface=dbus.PROPERTIES_IFACE)

    def __getattr__(self, attr):
        return SystemdUnitWrapperMethod(attr, self)

    def __getitem__(self, key):
        return self._properties[key]

    def __in__(self, key):
        return key in self._properties


class SystemdUnitWrapperMethod:
    '''Callable method for SystemdUnitWrapper'''

    def __init__(self, name: str, parent: SystemdUnitWrapper):
        self.parent = parent
        self.name = name

    def __call__(self, *a, **ka):
        return getattr(self.parent._dbus_iface, self.name)(*a, **ka)


def systemd_unit_watch(template_prefix, libvirt_state):
    '''
    Listen for systemd unit state changes
    and translate them into libvirt domain start/stop actions
    '''

    systemd = SystemdUnitManager(template_prefix)
    systemd.set_initial_state(libvirt_state)
    #manager.Subscribe()
    #for unit in manager.ListUnits():
    #    print(unit)

    def dbus_signal_handler(interface_name, changed_properties, invalidated_properties, path, **kwargs):
        if interface_name != 'org.freedesktop.systemd1.Unit':
            return
        if 'ActiveState' not in changed_properties:
            return
        prefix, domain, _ = systemd_parse_unit_name(systemd_unescape(os.path.basename(path)))
        if prefix != template_prefix.rstrip('@'):
            return
        if changed_properties['ActiveState'] == libvirt_state.get(domain):
            return
        print(f'\nReceived signal from DBus:\n{pformat(locals())}')

    systemd.dbus.add_signal_receiver(
        handler_function=dbus_signal_handler,
        signal_name='PropertiesChanged',
        dbus_interface='org.freedesktop.DBus.Properties',
        bus_name=None,
        path=None,
        sender_keyword='sender',
        destination_keyword='destination',
        interface_keyword='interface',
        member_keyword='member',
        path_keyword='path',
        message_keyword='message',
    )
    systemd.event_loop.run()


def main():
    #systemd_unit_watch('libvirt-guest@')
    libvirt_event_watch('libvirt-guest')


if __name__ == '__main__':
    main()


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
