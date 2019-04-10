#!/usr/bin/python
# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: luks_device

short_description: Manage encrypted (LUKS) devices

version_added: "2.8"

description:
    - "Module manages L(LUKS,https://en.wikipedia.org/wiki/Linux_Unified_Key_Setup)
      on given device. Supports creating, destroying, opening and closing of
      LUKS container and adding or removing new keys."

options:
    device:
        description:
            - "Device to work with (e.g. C(/dev/sda1)). Needed in most cases.
              Can be omitted only when I(state=closed) together with I(name)
              is provided."
        type: str
    state:
        description:
            - "Desired state of the LUKS container. Based on its value creates,
              destroys, opens or closes the LUKS container on a given device."
            - "I(present) will create LUKS container unless already present.
              Requires I(device) and I(keyfile) options to be provided."
            - "I(absent) will remove existing LUKS container if it exists.
              Requires I(device) or I(name) to be specified."
            - "I(opened) will unlock the LUKS container. If it does not exist
              it will be created first.
              Requires I(device) and I(keyfile) to be specified. Use
              the I(name) option to set the name of the opened container.
              Otherwise the name will be generated automatically and returned
              as a part of the result."
            - "I(closed) will lock the LUKS container. However if the container
              does not exist it will be created.
              Requires I(device) and I(keyfile) options to be provided. If
              container does already exist I(device) or I(name) will suffice."
        type: str
        default: present
        choices: [present, absent, opened, closed]
    name:
        description:
            - "Sets container name when I(state=opened). Can be used
              instead of I(device) when closing the existing container
              (i.e. when I(state=closed))."
        type: str
    keyfile:
        description:
            - "Used to unlock the container and needed for most
              of the operations. Parameter value is the path
              to the keyfile with the passphrase."
            - "BEWARE that working with keyfiles in plaintext is dangerous.
              Make sure that they are protected."
        type: path
    new_keyfile:
        description:
            - "Adds additional key to given container on I(device).
              Needs I(keyfile) option for authorization. LUKS container
              supports up to 8 keys. Parameter value is the path
              to the keyfile with the passphrase."
            - "BEWARE that working with keyfiles in plaintext is dangerous.
              Make sure that they are protected."
        type: path
    remove_keyfile:
        description:
            - "Removes given key from the container on I(device). Does not
              remove the keyfile from filesystem.
              Parameter value is the path to the keyfile with the passphrase."
            - "BEWARE that it is possible to remove even the last key from the
              container. Data in there will be irreversibly lost
              without a warning."
            - "BEWARE that working with keyfiles in plaintext is dangerous.
              Make sure that they are protected."
        type: path

requirements:
    - "cryptsetup"
    - "wipefs"
    - "lsblk"

notes:
    - "This module does not support check mode. The reason being that
      while it is possible to chain several operations together
      (e.g. 'create' and 'open'), the latter usually depends on changes
      to the system done by the previous one. (LUKS cannot be opened,
      when it does not exist.)"

author:
    "Jan Pokorny (@japokorn)"
'''

EXAMPLES = '''

- name: create LUKS container (remains unchanged if it already exists)
  luks_device:
    device: "/dev/loop0"
    state: "present"
    keyfile: "/vault/keyfile"

- name: (create and) open the LUKS container; name it "mycrypt"
  luks_device:
    device: "/dev/loop0"
    state: "opened"
    name: "mycrypt"
    keyfile: "/vault/keyfile"

- name: close the existing LUKS container "mycrypt"
  luks_device:
    state: "closed"
    name: "mycrypt"

- name: make sure LUKS container exists and is closed
  luks_device:
    device: "/dev/loop0"
    state: "closed"
    keyfile: "/vault/keyfile"

- name: create container if it does not exist and add new key to it
  luks_device:
    device: "/dev/loop0"
    state: "present"
    keyfile: "/vault/keyfile"
    new_keyfile: "/vault/keyfile2"

- name: add new key to the LUKS container (container has to exist)
  luks_device:
    device: "/dev/loop0"
    keyfile: "/vault/keyfile"
    new_keyfile: "/vault/keyfile2"

- name: remove existing key from the LUKS container
  luks_device:
    device: "/dev/loop0"
    remove_keyfile: "/vault/keyfile2"

- name: completely remove the LUKS container and its contents
  luks_device:
    device: "/dev/loop0"
    state: "absent"
'''

RETURN = '''
name:
    description:
        When I(state=opened) returns (generated or given) name
        of LUKS container. Returns None if no name is supplied.
    returned: success
    type: str
    sample: "luks-c1da9a58-2fde-4256-9d9f-6ab008b4dd1b"
'''

import re

from ansible.module_utils.basic import AnsibleModule

RETURN_CODE = 0
STDOUT = 1
STDERR = 2

# used to get <luks-name> out of lsblk output in format 'crypt <luks-name>'
# regex takes care of any possible blank characters
LUKS_NAME_REGEX = re.compile(r'\s*crypt\s+([^\s]*)\s*')
# used to get </luks/device> out of lsblk output
# in format 'device: </luks/device>'
LUKS_DEVICE_REGEX = re.compile(r'\s*device:\s+([^\s]*)\s*')


class Handler(object):

    def __init__(self, module):
        self._module = module
        self._lsblk_bin = self._module.get_bin_path('lsblk', True)

    def _run_command(self, command):
        return self._module.run_command(command)

    def generate_luks_name(self, device):
        ''' Generate name for luks based on device UUID ('luks-<UUID>').
            Raises ValueError when obtaining of UUID fails.
        '''
        result = self._run_command([self._lsblk_bin, '-n', device, '-o', 'UUID'])

        if result[RETURN_CODE] != 0:
            raise ValueError('Error while generating LUKS name for %s: %s'
                             % (device, result[STDERR]))
        dev_uuid = result[STDOUT].strip()
        return 'luks-%s' % dev_uuid


class CryptHandler(Handler):

    def __init__(self, module):
        super(CryptHandler, self).__init__(module)
        self._cryptsetup_bin = self._module.get_bin_path('cryptsetup', True)

    def get_container_name_by_device(self, device):
        ''' obtain LUKS container name based on the device where it is located
            return None if not found
            raise ValueError if lsblk command fails
        '''
        result = self._run_command([self._lsblk_bin, device, '-nlo', 'type,name'])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while obtaining LUKS name for %s: %s'
                             % (device, result[STDERR]))

        m = LUKS_NAME_REGEX.search(result[STDOUT])

        try:
            name = m.group(1)
        except AttributeError:
            name = None
        return name

    def get_container_device_by_name(self, name):
        ''' obtain device name based on the LUKS container name
            return None if not found
            raise ValueError if lsblk command fails
        '''
        # apparently each device can have only one LUKS container on it
        result = self._run_command([self._cryptsetup_bin, 'status', name])
        if result[RETURN_CODE] != 0:
            return None

        m = LUKS_DEVICE_REGEX.search(result[STDOUT])
        device = m.group(1)
        return device

    def is_luks(self, device):
        ''' check if the LUKS device does exist
        '''
        result = self._run_command([self._cryptsetup_bin, 'isLuks', device])
        return result[RETURN_CODE] == 0

    def run_luks_create(self, device, keyfile):
        # create a new luks container; use batch mode to auto confirm
        result = self._run_command([self._cryptsetup_bin, 'luksFormat',
                                    '-q', device, keyfile])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while creating LUKS on %s: %s'
                             % (device, result[STDERR]))

    def run_luks_open(self, device, keyfile, name):
        result = self._run_command([self._cryptsetup_bin, '--key-file', keyfile,
                                    'open', '--type', 'luks', device, name])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while opening LUKS container on %s: %s'
                             % (device, result[STDERR]))

    def run_luks_close(self, name):
        result = self._run_command([self._cryptsetup_bin, 'close', name])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while closing LUKS container %s' % (name))

    def run_luks_remove(self, device):
        wipefs_bin = self._module.get_bin_path('wipefs', True)

        name = self.get_container_name_by_device(device)
        if name is not None:
            self.run_luks_close(name)
        result = self._run_command([wipefs_bin, '--all', device])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while wiping luks container %s: %s'
                             % (device, result[STDERR]))

    def run_luks_add_key(self, device, keyfile, new_keyfile):
        ''' Add new key to given 'device'; authentization done using 'keyfile'
            Raises ValueError when command fails
        '''
        result = self._run_command([self._cryptsetup_bin, 'luksAddKey', device,
                                    new_keyfile, '--key-file', keyfile])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while adding new LUKS key to %s: %s'
                             % (device, result[STDERR]))

    def run_luks_remove_key(self, device, keyfile):
        ''' Remove key from given device
            Raises ValueError when command fails
        '''
        result = self._run_command([self._cryptsetup_bin, 'luksRemoveKey', device,
                                    '-q', '--key-file', keyfile])
        if result[RETURN_CODE] != 0:
            raise ValueError('Error while removing LUKS key from %s: %s'
                             % (device, result[STDERR]))


class ConditionsHandler(Handler):

    def __init__(self, module, crypthandler):
        super(ConditionsHandler, self).__init__(module)
        self._crypthandler = crypthandler

    def luks_create(self):
        return (self._module.params['device'] is not None and
                self._module.params['keyfile'] is not None and
                self._module.params['state'] in ('present',
                                                 'opened',
                                                 'closed') and
                not self._crypthandler.is_luks(self._module.params['device']))

    def opened_luks_name(self):
        ''' If luks is already opened, return its name.
            If 'name' parameter is specified and differs
            from obtained value, fail.
            Return None otherwise
        '''
        if self._module.params['state'] != 'opened':
            return None

        # try to obtain luks name - it may be already opened
        name = self._crypthandler.get_container_name_by_device(
            self._module.params['device'])

        if name is None:
            # container is not open
            return None

        if (self._module.params['name'] is None):
            # container is already opened
            return name

        if (name != self._module.params['name']):
            # the container is already open but with different name:
            # suspicious. back off
            self._module.fail_json(msg="LUKS container is already opened "
                                   "under different name '%s'." % name)

        # container is opened and the names match
        return name

    def luks_open(self):
        if (self._module.params['device'] is None or
                self._module.params['keyfile'] is None or
                self._module.params['state'] != 'opened'):
            # conditions for open not fulfilled
            return False

        name = self.opened_luks_name()

        if name is None:
            return True
        return False

    def luks_close(self):
        if ((self._module.params['name'] is None and
                self._module.params['device'] is None) or
                self._module.params['state'] != 'closed'):
            # conditions for close not fulfilled
            return False

        if self._module.params['device'] is not None:
            name = self._crypthandler.get_container_name_by_device(
                self._module.params['device'])
            # successfully getting name based on device means that luks is open
            luks_is_open = name is not None

        if self._module.params['name'] is not None:
            device = self._crypthandler.get_container_device_by_name(
                self._module.params['name'])
            # successfully getting device based on name means that luks is open
            luks_is_open = device is not None

        return luks_is_open

    def luks_add_key(self):
        if (self._module.params['device'] is None or
                self._module.params['keyfile'] is None or
                self._module.params['new_keyfile'] is None):
            # conditions for adding a key not fulfilled
            return False

        if self._module.params['state'] == 'absent':
            self._module.fail_json(msg="Contradiction in setup: Asking to "
                                   "add a key to absent LUKS.")

        return True

    def luks_remove_key(self):
        if (self._module.params['device'] is None or
                self._module.params['remove_keyfile'] is None):
            # conditions for removing a key not fulfilled
            return False

        if self._module.params['state'] == 'absent':
            self._module.fail_json(msg="Contradiction in setup: Asking to "
                                   "remove a key from absent LUKS.")

        return True

    def luks_remove(self):
        return (self._module.params['device'] is not None and
                self._module.params['state'] == 'absent' and
                self._crypthandler.is_luks(self._module.params['device']))


def run_module():
    # available arguments/parameters that a user can pass
    module_args = dict(
        state=dict(type='str', default='present', choices=['present', 'absent', 'opened', 'closed']),
        device=dict(type='str'),
        name=dict(type='str'),
        keyfile=dict(type='path'),
        new_keyfile=dict(type='path'),
        remove_keyfile=dict(type='path')
    )

    # seed the result dict in the object
    result = dict(
        changed=False,
        name=None
    )

    module = AnsibleModule(argument_spec=module_args,
                           supports_check_mode=False)

    crypt = CryptHandler(module)
    conditions = ConditionsHandler(module, crypt)

    # The conditions are in order to allow more operations in one run.
    # (e.g. create luks and add a key to it)

    # luks create
    if conditions.luks_create():
        try:
            crypt.run_luks_create(module.params['device'],
                                  module.params['keyfile'])
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['changed'] = True

    # luks open

    name = conditions.opened_luks_name()
    if name is not None:
        result['name'] = name

    if conditions.luks_open():
        name = module.params['name']
        if name is None:
            try:
                name = crypt.generate_luks_name(module.params['device'])
            except ValueError as e:
                module.fail_json(msg="luks_device error: %s" % e)
        try:
            crypt.run_luks_open(module.params['device'],
                                module.params['keyfile'],
                                name)
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['name'] = name
        result['changed'] = True

    # luks close
    if conditions.luks_close():
        if module.params['device'] is not None:
            try:
                name = crypt.get_container_name_by_device(
                    module.params['device'])
            except ValueError as e:
                module.fail_json(msg="luks_device error: %s" % e)
        else:
            name = module.params['name']
        try:
            crypt.run_luks_close(name)
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['changed'] = True

    # luks add key
    if conditions.luks_add_key():
        try:
            crypt.run_luks_add_key(module.params['device'],
                                   module.params['keyfile'],
                                   module.params['new_keyfile'])
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['changed'] = True

    # luks remove key
    if conditions.luks_remove_key():
        try:
            crypt.run_luks_remove_key(module.params['device'],
                                      module.params['remove_keyfile'])
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['changed'] = True

    # luks remove
    if conditions.luks_remove():
        try:
            crypt.run_luks_remove(module.params['device'])
        except ValueError as e:
            module.fail_json(msg="luks_device error: %s" % e)
        result['changed'] = True

    # Success - return result
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
