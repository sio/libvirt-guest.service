# Granular control of libvirt guests with systemd

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

#### Event listener

- [Minimal event listener](https://stackoverflow.com/questions/8767834) -
  smaller than in `examples/event-test.py`
- [sd_notify() from Python](https://github.com/stigok/sd-notify/blob/master/sd_notify.py) -
  it's simpler than you may think! Just some bytes sent over Unix socket
