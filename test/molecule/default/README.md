# Tests implementation

## Writing test cases

Test cases are written as sequences of Ansible tasks and are saved to the
`test_cases/` directory. Prefixing file names with sequential numbers is not
required but is helpful at current stage while the number of test cases is
relatively low.

To include new test case into Molecule runs it has to be imported from
`verify.yml`. A value for `test_name` variable MUST be set (using the filename
is a good default):

```yaml
    - import_tasks: test_cases/01_libvirt_start.yml
      vars:
        test_name: 01_libvirt_start
```

Each test case MUST start with importing `test_fixtures/begin.yml` and end
with `test_fixtures/end.yml`. These files are used to keep track of started
test cases and to store their status on completion.

To indicate the test result test case MUST set `test_status` variable either
to 'success' or to 'failed' before importing `test_fixtures/end.yml`.

Test cases may use `test_fixtures/setup.yml` and `test_fixtures/teardown.yml`.
Tasks in `setup.yml` enforce desired state of test instance before starting
the test and `teardown.yml` cleans up the test instance afterwards.

## Example

- Commit adding a new test case:
  <https://github.com/sio/libvirt-guest.service/commit/e750e017e0365d216f5ce0b2ffb45bec78dba357>
- Test case: [test_cases/01_libvirt_start.yml](test_cases/01_libvirt_start.yml)

## Variables used by test cases

- `test_name`: must be set while importing the test case from `verify.yml`
- `test_status`: must be set to "success" or "failed" before importing `end.yml`
- `setup.yml` inputs:
    - `test_start_guests`: list of domain names for guests that must be
      started before beginning the test
    - `test_start_units`: list of domain names for guests whose systemd units
      must be started before beginning the test
    - `test_start_manager`: boolean (default: False) that shows whether
      `libvirt-guest-manager` must be started at the beginning of the test
    - `test_start_logger`: boolean (default: True) that indicates whether
      Libvirt and Systemd events need to be logged during the test
- `teardown.yml` outputs:
    - `test_events`: if 'test_start_logger' was previously set to True, this
      variable will contain the list of Libvirt and Systemd events related to
      our project. This may be used to calculate the outcome of the test
      (success/failed)
