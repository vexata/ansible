#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Sandeep Kasargod (sandeep@vexata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: vexata_sg
version_added: 2.8
short_description: Manage snapshots of volume groups on Vexata VX100 storage arrays
description:
  - Create or delete readonly point-in-time snapshots of a group of volumes. A snapshot
    group may also be referred to as a consistency group.
  - Clone a snapshot group to a set of new writable volumes in a new volume group.
  - Restore a volume group to the state when the snapshot group was created.
    This will undo any changes made to the individual volumes in the volume
    group after the snapshot was created. If the volumes were added or removed
    from the volume group after the snapshot group was created, the restore
    operation will fail.
author: Sandeep Kasargod
options:
  name:
    description:
    - Snapshot group name.
    required: true
  vg:
    description:
    - Name of the volume group parent from which the snapshot group is created.
    required: true
  state:
    description:
    - Create a readonly snapshot group when present, delete when absent.
    - Create a writable clone when clone.
    - Restore a volume group to the snapshot group's state when restore.
    default: present
    choices: [ present, absent, clone, restore ]
  target:
    description:
    - Name of volume group to be cloned from the snapshot.
extends_documentation_fragment:
    - vexata.vx100
'''

EXAMPLES = '''
- name: Create a new snapshot group named testvgnap from a parent vg named testvg.
  vexata_sg:
    name: testvgsnap
    vg: testvg
    state: present
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Delete snapshot group testvgsnap of the parent vg testvg.
  vexata_sg:
    name: testvgsnap
    volume: testvg
    state: absent
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Clone a snapshot group snapshot testvgsnap to a new volume group testvgsnapclone.
  vexata_sg:
    name: testvgsnap
    volume: testvg
    state: clone
    target: testvgsnapclone
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Restore parent volume group testvg to the state captured in snapshot group testvgsnap.
  vexata_sg:
    name: testvgsnap
    volume: testvg
    state: restore
    array: vx100_ultra.test.com
    user: admin
    password: secret
'''

RETURN = '''
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vexata import (
    HAS_VEXATAPI, VXOS_VERSION, argument_spec, get_array, required_together)


def get_vg(module, array):
    """Retrieve a named vg if it exists, None if absent."""
    name = module.params['vg']
    try:
        vgs = array.list_vgs()
        vg = filter(lambda vg: vg['name'] == name, vgs)
        if len(vg) == 1:
            return vg[0]
        else:
            return None
    except Exception:
        module.fail_json(msg='Error while attempting to retrieve volume groups.')


def get_sg(module, array, vg_id):
    """Retrieve a named snapshot group if it exists, None if absent."""
    name = module.params['name']
    try:
        sgs = array.list_vgsnaps(vg_id)
        sg = filter(lambda sg: sg['name'] == name, sgs)
        if len(sg) == 1:
            return sg[0]
        else:
            return None
    except Exception:
        module.fail_json(msg='Error while attempting to retrieve snapshot groups.')


def create_sg(module, array, vg):
    """"Create a new snapshot group."""
    changed = False
    parent_vg_id = vg['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        sg = array.create_vgsnap(
            parent_vg_id,
            module.params['name'],
            'Ansible snapshot group')
        if sg:
            module.log(msg='Created snapshot group {0} for parent vg {1}'
                       .format(sg['name'], vg['name']))
            changed = True
        else:
            module.fail_json(msg='Snapshot group create failed.')
    except Exception:
        pass
    module.exit_json(changed=changed)


def delete_sg(module, array, sg, vg):
    changed = False
    parent_vg_id = sg['parentVolumeGroupId']
    sg_id = sg['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        ok = array.delete_vgsnap(
            parent_vg_id,
            sg_id)
        if ok:
            module.log(msg='Deleted snapshot group {0} of parent vg {1}.'
                       .format(sg['name'], vg['name']))
            changed = True
        else:
            raise Exception
    except Exception:
        pass
    module.exit_json(changed=changed)


def clone_sg(module, array, sg):
    changed = False
    tgt_name = module.params['target']
    if not tgt_name:
        module.fail_json('Target volume group name for snapshot group cloning is required.')

    if module.check_mode:
        module.exit_json(changed=changed)

    sg_id = sg['id']
    try:
        clone = array.clone_vgsnap_to_new_vg(
            sg_id,
            tgt_name,
            'Ansible snapshot goup clone')
        if clone:
            module.log(msg='Cloned snapshot group {0} to new vg {1}.'
                       .format(sg['name'], tgt_name))
            changed = True
        else:
            raise Exception
    except Exception:
        pass
    module.exit_json(changed=changed)


def restore_sg(module, array, sg, vg):
    changed = False
    parent_vg_id = sg['parentVolumeGroupId']
    sg_id = sg['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        rsp = array.restore_vg_from_vgsnap(
            parent_vg_id,
            sg_id)
        if rsp is not None:
            module.log(msg='Restored volume group {0} from snapshot group {1}.'
                       .format(vg['name'], sg['name']))
            changed = True
        else:
            raise Exception
    except Exception:
        pass
    module.exit_json(changed=changed)


def main():
    arg_spec = argument_spec()
    arg_spec.update(
        dict(
            name=dict(type='str', required=True),
            vg=dict(type='str', required=True),
            state=dict(default='present', choices=['present', 'absent', 'clone', 'restore']),
            target=dict(type='str')
        )
    )

    module = AnsibleModule(arg_spec,
                           supports_check_mode=True,
                           required_together=required_together())

    if not HAS_VEXATAPI:
        module.fail_json(msg='vexatapi library is required for this module. '
                             'To install, use `pip install vexatapi`')

    array = get_array(module)
    vg = get_vg(module, array)
    if not vg:
        module.fail_json(
            msg='Failed to find volume group {0} that is the parent for snapshot group {1}'
                .format(module.params['vg'], module.params['name']))
    parent_vg_id = vg['id']
    sg = get_sg(module, array, parent_vg_id)
    state = module.params['state']

    if state == 'present' and not sg:
        create_sg(module, array, vg)
    elif state == 'absent' and sg:
        delete_sg(module, array, sg, vg)
    elif state == 'clone' and sg:
        clone_sg(module, array, sg)
    elif state == 'restore' and sg:
        restore_sg(module, array, sg, vg)
    else:
        module.exit_json(changed=False)


if __name__ == '__main__':
    main()
