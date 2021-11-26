#!/usr/bin/env python3
'''
Libvirt and Systemd event logger used to record events happening on test instances

Wherever possible this script aims to avoid reusing the same event information
source as in libvirt-guest-manager
'''


import argparse
import subprocess
import threading
import time


class LibvirtSystemdLogger:

    MIN_REPEAT_DELAY_SEC = 2

    def __init__(self, template_prefix: str, domains: list):
        self.template_prefix = template_prefix
        self.domains = domains
        self.lock = threading.RLock()
        self.threads = []
        self.threads.append(threading.Thread(
            target=self.libvirt_reboot,
            name='libvirt_reboot',
            daemon=True,
        ))
        for domain in self.domains:
            self.threads.append(threading.Thread(
                target=self.libvirt_start_stop,
                args=(domain,),
                name=f'libvirt_start_stop_{domain}',
                daemon=True,
            ))

    def start(self):
        for thread in self.threads:
            thread.start()

    def record(self, subsystem: str, action: str, domain: str):
        with self.lock:
            print(dict(
                timestamp=self.timestamp(),
                subsystem=subsystem,
                action=action,
                domain=domain,
            ))

    def timestamp(self):
        return time.monotonic()

    def libvirt_start_stop(self, domain):
        '''Listen to libvirt domain start/stop events (no reboot events here)'''
        markers = {
            'start': ': starting up',
            'stop': ': shutting down',
        }
        for line in tail(f'/var/log/libvirt/qemu/{domain}.log'):
            for action, marker in markers.items():
                if marker in line.lower():
                    self.record('libvirt', action, domain)
                    continue

    def libvirt_reboot(self):
        '''
        Listen to libvirt reboot events

        Virsh buffers stdout when it detects that it is connected to pipe,
        so we need 'stdbuf' to regain realtime output.
        Thanks to:
            https://stackoverflow.com/a/52851238
            https://unix.stackexchange.com/questions/25372
        '''
        command = 'stdbuf -o0 virsh event --event reboot --loop'.split()
        prev_event = 0
        for line in stdout(command):
            if self.timestamp() - prev_event <= self.MIN_REPEAT_DELAY_SEC:
                continue
            prev_event = self.timestamp()
            domain = line.split("'")[3]
            self.record('libvirt', 'restart', domain)


def tail(filepath: str):
    '''Yield new lines from text file as they are appended to it'''
    command = 'tail -n0 -F'.split()
    command.append(filepath)
    yield from stdout(command)


def stdout(command: list):
    '''Yield stdout lines from subprocess as they arrive'''
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in process.stdout:
        yield line.decode()


def parse_args(*a, **ka):
    parser = argparse.ArgumentParser(
        description='Log Libvirt and Systemd events',
        epilog='Used during testing of https://github.com/sio/libvirt-guest.service',
    )
    parser.add_argument(
        'template_prefix',
        metavar='SYSTEMD_SERVICE_PREFIX',
        help='Systemd service prefix, e.g. libvirt-guest',
    )
    parser.add_argument(
        'domains',
        metavar='DOMAIN',
        nargs='+',
        help='Name of Libvirt domains to monitor',
    )
    args = parser.parse_args(*a, **ka)
    return args


def main():
    args = parse_args()
    logger = LibvirtSystemdLogger(args.template_prefix, args.domains)
    logger.start()
    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
