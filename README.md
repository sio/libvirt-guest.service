# Granular control of libvirt guests with systemd

This service aims to provide better integration of Libvirt guests into systemd
service hierarchy. If you want to define a particular guest startup order or
make sure that guests competing for the same physical resources (e.g. GPU) are
never launched at the same time or that a particular service is bound to a
Libvirt VM state - this project will be helpful.
