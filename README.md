# Granular control of libvirt guests with systemd

## Project status

In development. Not usable yet. Not currently looking for contributors.

## Overview

This service aims to provide better integration of Libvirt guests into systemd
service hierarchy. If you want to define a particular guest startup order or
make sure that guests competing for the same physical resources (e.g. GPU) are
never launched at the same time or that a particular service is bound to a
Libvirt VM state - this project will be helpful.

## Useful links

#### API

- [Libvirt Python API](https://libvirt.org/python.html)
- [libvirt-python examples](https://gitlab.com/libvirt/libvirt-python/-/tree/master/examples)
- [Libvirt Domain Module](https://libvirt.org/html/libvirt-libvirt-domain.html)
- [Libvirt Application Development Guide Using Python](https://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html/)

#### Event listener

- [Minimal event listener](https://stackoverflow.com/questions/8767834) -
  smaller than in `examples/event-test.py`
- [sd_notify() from Python](https://github.com/stigok/sd-notify/blob/master/sd_notify.py) -
  it's simpler than you may think! Just some bytes sent over Unix socket
- [Systemd DBus API](https://wiki.freedesktop.org/www/Software/systemd/dbus/)
- [python3-dbus tutorial](https://dbus.freedesktop.org/doc/dbus-python/tutorial.html),
  [example](https://stackoverflow.com/questions/42088406/starting-a-users-systemd-service-via-python-and-dbus)
- [Other event listeners for Systemd](https://stackoverflow.com/questions/44946465)
