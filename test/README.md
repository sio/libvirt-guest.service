# Automated tests for libvirt-guest@.service

All tests are performed in Libvirt/KVM virtual machines brought up using
Molecule. Test runner must support nested virtualization because test
instances will be running some lightweight guests of their own.

Use `make test` to execute full test sequence which is guaranteed to leave the
test runner in a clean state.

During development to be able to iterate faster one might use `make quicktest`
which will not destroy test instances after each run and will reuse instances
if they already exist. `make quicktest-cleanup` will bring test runner to a
clean state.
