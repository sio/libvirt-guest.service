#!/usr/bin/env python3
'''
An idempotent replacement for 'virsh start/shutdown' that actually makes sure
the domain has reached desired state

This script will be used to translate management actions from systemd to libvirtd
'''


import argparse
import libvirt
import os
import time


ENV = {
    'timeout': 'WAIT_ACTION_SECONDS',
    'delay': 'WAIT_CHECK_DELAY',
}


def parse_args(*a, **ka):
    parser = argparse.ArgumentParser(
        description='Simple libvirt client that can start and stop guests',
        epilog='Licensed under the Apache License, version 2.0',
    )
    actions = [
        'start',
        'stop',
    ]
    parser.add_argument(
        'action',
        metavar='ACTION',
        help=f'Virtual machine management action ({"|".join(sorted(actions))})',
        type=str.lower,
        choices=actions,
    )
    parser.add_argument(
        'domain',
        metavar='DOMAIN',
        help='Libvirt domain name for the guest',
    )
    parser.add_argument(
        '--timeout',
        default=os.getenv(ENV['timeout'], 120),
        metavar='SECONDS',
        help=(
            f'timeout (in seconds) before action is considered failed. '
            f'Default: ${ENV["timeout"]} or 120'
        )
    )
    parser.add_argument(
        '--delay',
        default=os.getenv(ENV['delay'], 1),
        metavar='SECONDS',
        help=(
            f'delay (in seconds) before repeating status checks. '
            f'Default: ${ENV["delay"]} or 1'
        )
    )
    args = parser.parse_args(*a, **ka)
    return args


def main():
    args = parse_args()
    connection = libvirt.open()
    domain = connection.lookupByName(args.domain)
    workers = {
        'start': domain.create,
        'stop': domain.shutdown,
    }
    success = {
        'start': domain.isActive,
        'stop': lambda: not domain.isActive(),
    }
    repeat = {
        'start': False,
        'stop': True,
    }
    def execute():
        if not success[args.action]():
            if workers[args.action]() != 0:
                raise RuntimeError(f'failed to {args.action} domain: {args.domain}')
    start = time.monotonic()
    execute()
    while not success[args.action]():
        if time.monotonic() > start + args.timeout:
            raise RuntimeError(f'domain {args.action} took longer than {args.timeout} seconds: {args.domain}')
        time.sleep(args.delay)
        if repeat[args.action]:
            execute()


if __name__ == '__main__':
    main()
