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
import time

from collections.abc import Mapping, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from dbus.mainloop.glib import DBusGMainLoop  # python3-dbus
from enum import IntEnum
from gi.repository import GLib  # python3-gi
from queue import Queue

from pprint import pformat  # debug


logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%b %d %H:%M:%S')
log = logging.getLogger('libvirt-systemd-sync')
log.level = logging.DEBUG  # debug


class ThreadSafeKeyValue(MutableMapping):
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

    def __setitem__(self, key, value):
        with self._lock:
            self._storage[key] = value

    def __delitem__(self, key):
        with self._lock:
            self._storage.pop(key)

    def __len__(self):
        with self._lock:
            return len(self._storage)

    def __iter__(self):
        with self._lock:
            return iter(self._storage)

    def __contains__(self, key):
        with self._lock:
            return key in self._storage

    def __str__(self):
        with self._lock:
            return str(self._storage)

    def __repr__(self):
        with self._lock:
            return f'<{self.__class__.__name__}({self._storage})>'


class ReadOnlyDict(Mapping):
    '''A dictionary-like object wrapper that prevents accidental modification'''

    def __init__(self, dictionary):
        self._storage = dictionary

    def __getitem__(self, key):
        return self._storage[key]

    def __len__(self):
        return len(self._storage)

    def __iter__(self):
        return iter(self._storage)

    def __repr__(self):
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


class SystemdUnitManager:
    '''DBus wrapper for systemd API'''

    def __init__(self, template_prefix: str):
        self.template_prefix = template_prefix
        DBusGMainLoop(set_as_default=True)
        self.event_loop = GLib.MainLoop()
        self.dbus = dbus.SystemBus()
        self.daemon = self.dbus_object('/org/freedesktop/systemd1')
        self.manager = dbus.Interface(self.daemon, 'org.freedesktop.systemd1.Manager')

    def _unit_name(self, domain_name: str):
        '''Translate Libvirt domain name to Systemd unit name'''
        return f'{self.template_prefix}@{domain_name}.service'

    def start(self, domain_name: str):
        '''Start systemd unit that corresponds to Libvirt domain'''
        unit = self.unit(self._unit_name(domain_name))
        if unit['ActiveState'] != 'active':
            unit.Start('fail')

    def restart(self, domain_name: str):
        '''Restart systemd unit that corresponds to Libvirt domain'''
        unit = self.unit(self._unit_name(domain_name))
        unit.Restart('fail')

    def stop(self, domain_name: str):
        '''Stop systemd unit that corresponds to Libvirt domain'''
        unit = self.unit(self._unit_name(domain_name))
        if unit['ActiveState'] != 'inactive':
            unit.Stop('fail')

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
            unit_name = self._unit_name(domain)
            unit = self.unit(unit_name)
            log.debug(f'{self.__class__.__name__}: initial state for {unit_name}: {unit["ActiveState"]}')
            if state == unit['ActiveState']:
                continue
            if state == 'active':
                log.debug(f'{self.__class__.__name__}: starting {unit_name} to match libvirt state')
                unit.Start('fail')
            elif state == 'inactive':
                log.debug(f'{self.__class__.__name__}: stopping {unit_name} to match libvirt state')
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
                log.warn(f'{self.__class__.__name__}: unexpected inactive unit, fixing: {name}')
                unit.Start('fail')
            elif libvirt_status == 'inactive':
                log.warn(f'{self.__class__.__name__}: unexpected active unit, fixing: {name}')
                unit.Stop('fail')
            elif libvirt_status is None:
                log.debug(f'{self.__class__.__name__}: there is no libvirt domain for {name}. Stopping unit')
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


class LibvirtActionLog:
    '''In-memory log of past Libvirt actions'''

    def __init__(self, max_length_seconds=60):
        self._max_length_seconds = max_length_seconds
        self._log = ThreadSafeKeyValue()
        self._lock = threading.RLock()
        self._last_update = 0
        self._clear()

    def now(self):
        return time.monotonic()

    def new(self, key):
        '''Record a new timestamp for key'''
        with self._lock:
            if key in self._log:
                self._log[key].append(self.now())
            else:
                self._log[key] = [self.now(),]
            self._update()

    def prev(self, key):
        '''Previous (the one before latest) timestamp for key'''
        with self._lock:
            timestamps = self._log.get(key, [])
            if len(timestamps) < 2:
                return 0
            else:
                return timestamps[-2]

    def last(self, key):
        '''Latest timestamp for key'''
        with self._lock:
            return self._log.get(key, [0])[-1]

    def _cleanup(self):
        '''Remove outdated log entries'''
        with self._lock:
            if self.now() - self._last_update > self._max_length_seconds:
                self._clear()

    def _update(self, cleanup=True):
        '''Save last update timestamp'''
        with self._lock:
            if cleanup:
                self._cleanup()
            self._last_update = self.now()

    def _clear(self):
        with self._lock:
            self._log.clear()
            self._update(cleanup=False)


def libvirt_eventloop_start():
    libvirt.virEventRegisterDefaultImpl()
    while True:
        libvirt.virEventRunDefaultImpl()


class LibvirtDomainManager:
    '''Wrapper for Libvirt API'''

    TIMEOUT_SEC = 120
    CHECK_DELAY_SEC = 1
    CONSECUTIVE_ACTION_THRESHOLD_SEC = 3

    def __init__(self):
        self.event_thread = threading.Thread(target=libvirt_eventloop_start, daemon=True)
        self.event_thread.start()
        self.connection = libvirt.open()
        self._state = ThreadSafeKeyValue()
        self._lock = threading.RLock()
        self._action_queue = Queue()
        self._action_log = LibvirtActionLog()
        self.reload_state()
        self.action_thread = threading.Thread(target=self.action_loop, daemon=True)
        self.action_thread.start()

    @property
    def state(self):
        '''Mapping of domain names to status strings'''
        return ReadOnlyDict(self._state)

    def reload_state(self):
        '''Reload all domains state from scratch'''
        state = self._state
        with self._lock:      # no domain actions are to be performed
            with state._lock: # no state reads either
                state.clear()
                for domain in self.connection.listAllDomains():
                    self._update_state(domain)

    def _update_state(self, domain):
        '''Store the state of Libvirt domain'''
        with self._lock:
            self._state[domain.name()] = 'active' if domain.isActive() else 'inactive'

    def action_loop(self):
        '''
        Loop forever executing queued actions as they are added to
        self._action_queue
        '''
        with ThreadPoolExecutor(max_workers=5) as executor:
            for action, domain_name in iter(self._action_queue.get, None):  # endless loop
                action_log = self._action_log
                action_log.new(domain_name)
                if action_log.now() - action_log.prev(domain_name) <= self.CONSECUTIVE_ACTION_THRESHOLD_SEC:
                    log.debug(f'{self.__class__.__name__}: ignoring action because of repetition threshold: {action} {domain_name}')
                    continue
                log.debug(f'{self.__class__.__name__}: adding action to queue: {action} {domain_name}')
                executor.submit(self._action, action, domain_name)

    def start(self, domain_name: str):
        '''
        Start Libvirt domain
        (non-blocking, all work is done in background thread)
        '''
        args = ('start', domain_name)
        self._action_queue.put(args)

    def restart(self, domain_name: str):
        '''
        Restart Libvirt domain
        (non-blocking, all work is done in background thread)
        '''
        args = ('restart', domain_name)
        self._action_queue.put(args)

    def stop(self, domain_name: str):
        '''
        Stop Libvirt domain
        (non-blocking, all work is done in background thread)
        '''
        args = ('stop', domain_name)
        self._action_queue.put(args)

    def _start(self, domain_name: str):
        '''
        Initiate Libvirt domain startup
        This function is almost always non-blocking
        '''
        with self._lock:
            domain = self.connection.lookupByName(domain_name)
            self._update_state(domain)
            if self.state[domain_name] == 'active':
                return
            log.info(f'{self.__class__.__name__}: sending start command for {domain_name}')
            if domain.create() == 0:
                return
            raise RuntimeError(f'failed to create domain: {domain_name}')

    def _stop(self, domain_name: str):
        '''
        Initiate Libvirt domain shutdown
        This function is almost always non-blocking, but it does not ensure
        that domain have reached desired state.
        '''
        with self._lock:
            domain = self.connection.lookupByName(domain_name)
            self._update_state(domain)
            if self.state[domain_name] == 'inactive':
                return
            log.info(f'{self.__class__.__name__}: sending shutdown signal for {domain_name}')
            if domain.shutdown() == 0:
                return
            raise RuntimeError(f'failed to shutdown domain: {domain_name}')

    def _action(self, action: str, domain_name: str):
        '''
        Initiate start/stop domain and wait for the action to complete.
        This function blocks until domain reaches the desired state, so it may
        be benefitial to spawn it off in a separate thread.
        '''
        target = {
            'start': 'active',
            'stop': 'inactive',
            'restart': 'special',
        }
        if action not in target:
            raise ValueError(f'invalid action: {action}')
        if action == 'restart':
            self._action('stop', domain_name)
            self._action('start', domain_name)
            log.info(f'{self.__class__.__name__}: {domain_name} has been restarted')
            return

        execute = getattr(self, f'_{action}')
        start = time.monotonic()
        execute(domain_name)
        while not self.state[domain_name] == target[action]:
            if time.monotonic() > start + self.TIMEOUT_SEC:
                raise RuntimeError(f'domain {action} took longer than {self.TIMEOUT_SEC} seconds: {domain_name}')
            time.sleep(self.CHECK_DELAY_SEC)
            if action == 'stop':  # guest may have been not ready to process ACPI events before
                execute(domain_name)
        log.info(f'{self.__class__.__name__}: {domain_name} has reached target state: {target[action]}')




def main():
    template_prefix = 'libvirt-guest'
    libvirtd = LibvirtDomainManager()
    systemd = SystemdUnitManager(template_prefix)
    systemd.set_initial_state(libvirtd.state)

    def dbus_signal_handler(interface_name, changed_properties, invalidated_properties, path, **kwargs):
        if interface_name != 'org.freedesktop.systemd1.Unit':
            return
        if 'ActiveState' not in changed_properties:
            return
        prefix, domain, _ = systemd_parse_unit_name(systemd_unescape(os.path.basename(path)))
        if prefix != template_prefix:
            return
        systemd_state = changed_properties['ActiveState']
        state = {
            'activating': 'active',
            'active': 'active',
            'inactive': 'inactive',
        }
        if systemd_state not in state:
            log.error(f'dbus_signal_handler received unknown unit state: {systemd_state}')
            return
        if state[systemd_state] == libvirtd.state.get(domain):
            return
        log.debug(f'Systemd event: {systemd_state} {domain}')
        if state[systemd_state] == 'active':
            libvirtd.start(domain)
        elif state[systemd_state] == 'inactive':
            libvirtd.stop(domain)
        else:
            raise RuntimeError(f'impossible branching with state: {state[systemd_state]} ({systemd_state})')


    systemd.dbus.add_signal_receiver(
        handler_function=dbus_signal_handler,
        signal_name='PropertiesChanged',
        dbus_interface='org.freedesktop.DBus.Properties',
        bus_name=None,
        path=None,
        path_keyword='path',
    )

    def libvirt_event_lifecycle(conn, dom, state: int, reason: int, *a, **ka):
        libvirtd._update_state(dom)
        if state == libvirt.VIR_DOMAIN_EVENT_STARTED:
            libvirtd._action_log.new(dom.name())
            systemd.start(dom.name())
            log.debug(f'Libvirt start event for {dom.name()}, updating systemd unit state')
        elif state == libvirt.VIR_DOMAIN_EVENT_STOPPED:
            libvirtd._action_log.new(dom.name())
            systemd.stop(dom.name())
            log.debug(f'Libvirt stop event for {dom.name()}, updating systemd unit state')

    def libvirt_event_reboot(conn, dom, opaque, *a, **ka):
        libvirtd._update_state(dom)
        libvirtd._action_log.new(dom.name())
        systemd.restart(dom.name())
        log.info(f'Libvirt reboot event for {dom.name()}, triggering systemd unit restart')

    libvirtd.connection.domainEventRegisterAny(
        dom=None,
        eventID=libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
        cb=libvirt_event_lifecycle,
        opaque=2,
    )
    libvirtd.connection.domainEventRegisterAny(
        dom=None,
        eventID=libvirt.VIR_DOMAIN_EVENT_ID_REBOOT,
        cb=libvirt_event_reboot,
        opaque=None,
    )

    systemd.event_loop.run()




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
