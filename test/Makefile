.DEFAULT_GOAL=test
PY?=/usr/bin/python3


export PY_COLORS=1
export ANSIBLE_FORCE_COLOR=1
export ANSIBLE_STDOUT_CALLBACK=yaml


MOLECULE_ACTIONS=\
	cleanup \
	converge \
	create \
	dependency \
	destroy \
	idempotence \
	lint \
	login \
	prepare \
	side_effect \
	syntax \
	test \
	verify


.PHONY: $(MOLECULE_ACTIONS)
$(MOLECULE_ACTIONS): host-requirements molecule-version | venv
	$(VENV)/molecule $@ $(MOLECULE_ARGS)


.PHONY: molecule-version
molecule-version: | venv
	$(VENV)/molecule --version
	$(VENV)/ansible --version


.PHONY: host-requirements
host-requirements: kvm-requirements
	@$(PY) -c 'import venv; import ensurepip'  # check for python3-venv package
	@vagrant --version >/dev/null
	@vagrant plugin list | grep -q libvirt || { \
		echo 'Vagrant plugin for Libvirt not installed'; \
		false; \
	}


.PHONY: kvm-requirements
KVM_NESTED=/sys/module/kvm_*/parameters/nested
KVM_NESTED_STATUS=$(shell cat $(KVM_NESTED))
KVM_NESTED_OK=$(findstring $(KVM_NESTED_STATUS),"1Yy")
KVM_NESTED_HELP=https://docs.fedoraproject.org/en-US/quick-docs/using-nested-virtualization-in-kvm/
kvm-requirements:
	@[ -n "$(KVM_NESTED_OK)" ] || { \
		echo "Nested virtualization not supported, see $(KVM_NESTED_HELP)"; \
		false; \
	}


include Makefile.venv
Makefile.venv:
	curl \
		-o Makefile.fetched \
		-L "https://github.com/sio/Makefile.venv/raw/v2020.08.14/Makefile.venv"
	echo "5afbcf51a82f629cd65ff23185acde90ebe4dec889ef80bbdc12562fbd0b2611 *Makefile.fetched" \
		| sha256sum --check - \
		&& mv Makefile.fetched Makefile.venv


export PATH:=$(VENV):$(PATH)
