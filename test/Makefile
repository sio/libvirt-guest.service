PY=/usr/bin/python3


.PHONY: host-requirements
host-requirements: kvm-requirements
	@$(PY) -c 'import venv; import ensurepip'  # check for python3-venv package


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
