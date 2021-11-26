#!/usr/bin/env python3
'''
Libvirt and Systemd event logger used to record events happening on test instances

Wherever possible this script aims to avoid reusing the same event information
source as in libvirt-guest-manager
'''


import argparse
import os
import subprocess
import threading
import time


class LibvirtSystemdLogger:

    MIN_REPEAT_DELAY_SEC = 2

    def __init__(self, template_prefix: str, domains: list, control_fifo: str):
        self.template_prefix = template_prefix
        self.domains = domains
        self.control_fifo = control_fifo
        self.lock = threading.RLock()
        self.threads = []
        self.threads.append(threading.Thread(
            target=self.listen_fifo,
            name='listen_fifo',
            daemon=True,
        ))
        self.threads.append(threading.Thread(
            target=self.systemd_start_stop,
            name='systemd_start_stop',
            daemon=True,
        ))
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

    def run(self):
        self.start()
        while not self.stop:
            if not self.healthy():
                raise RuntimeError(f'One of {self.__class__.__name__} subprocesses exited early')
            time.sleep(1)

    def start(self):
        self.stop = False
        for thread in self.threads:
            if not thread.is_alive():
                thread.start()

    def healthy(self):
        for thread in self.threads:
            if not thread.is_alive():
                return False
        return True

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

    def listen_fifo(self):
        '''Listen for STOP message on control FIFO'''
        os.mkfifo(self.control_fifo)
        with open(self.control_fifo) as fifo:
            for line in fifo:
                if line.strip() == 'STOP':
                    self.stop = True
                    break
        os.unlink(self.control_fifo)

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

    def systemd_start_stop(self):
        '''Listen to systemd unit start/stop events (no restarts here)'''
        markers = {
            'start': 'systemd[1]: Started Libvirt Guest Domain: ',
            'stop': 'systemd[1]: Stopped Libvirt Guest Domain: ',
        }
        for line in tail('/var/log/daemon.log'):
            for action, marker in markers.items():
                if marker.lower() in line.lower():
                    marker_start = line.lower().find(marker.lower())
                    domain = line[marker_start+len(marker):].strip().rstrip('.')
                    self.record('systemd', action, domain)


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
        '--control-fifo',
        metavar='FIFO',
        default='logger.fifo',
        help='A FIFO path on which to listen for \'STOP\' message (default: logger.fifo)',
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
    logger = LibvirtSystemdLogger(args.template_prefix, args.domains, args.control_fifo)
    logger.run()


if __name__ == '__main__':
    main()
