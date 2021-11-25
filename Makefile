BIN?=/usr/local/bin
SYSTEMD?=/etc/systemd/system
PY?=/usr/bin/env python3


VIRSH=$(shell command -v virsh)


.PHONY: check-requirements
check-requirements:
	@$(PY) -c 'import libvirt'
	@$(PY) -c 'import dbus'
	@virsh --version >/dev/null
	@sed --version >/dev/null


.PHONY: install
install: check-requirements
	mkdir -p $(BIN)
	mkdir -p $(SYSTEMD)

	cp libvirt-guest-manager $(BIN)/libvirt-guest-manager
	chown root:root $(BIN)/libvirt-guest-manager
	chmod 755 $(BIN)/libvirt-guest-manager

	sed 's|/usr/bin/virsh|$(VIRSH)|g' \
		libvirt-guest@.service > $(SYSTEMD)/libvirt-guest@.service
	chown root:root $(SYSTEMD)/libvirt-guest@.service
	chmod 644 $(SYSTEMD)/libvirt-guest@.service

	sed 's|/usr/local/bin/libvirt-guest-manager|$(BIN)/libvirt-guest-manager|g' \
		libvirt-guest-manager.service > $(SYSTEMD)/libvirt-guest-manager.service
	chown root:root $(SYSTEMD)/libvirt-guest-manager.service
	chmod 644 $(SYSTEMD)/libvirt-guest-manager.service

	systemctl daemon-reload
