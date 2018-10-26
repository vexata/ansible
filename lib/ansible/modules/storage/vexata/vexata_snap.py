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
module: vexata_snap
version_added: 2.8
short_description: Manage volume snapshots and clones on Vexata VX100 storage arrays.
description:
    - Create or delete a readonly point-in-time snapshot of a volume.
    - Clone a snapshot to a new writable volume.
    - Restore a volume to the state when the snapshot was created. This will
      undo any changes made to the volume after the snapshot was created.
author: Sandeep Kasargod
options:
  name:
    description:
    - Snapshot name.
    required: true
  volume:
    description:
    - Name of the volume from which the snapshot is created.
    required: true
  state:
    description:
    - Create a readonly snapshot when present, delete when absent.
    - Create a writable clone when clone.
    - Restore a volume to the snapshot's state when restore.
    default: present
    choices: [ present, absent, clone, restore ]
  target:
    description:
    - Name of volume to be cloned from the snapshot.
extends_documentation_fragment:
    - vexata.vx100
'''

EXAMPLES = '''
- name: Create a new snapshot named foosnap from a parent volume named foo.
  vexata_snap:
    name: foosnap
    volume: foo
    state: present
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Delete volume snapshot named foosnap of the parent volume foo.
  vexata_snap:
    name: foosnap
    volume: foo
    state: absent
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Clone a volume snapshot named foosnap to a new volume foosnapclone.
  vexata_snap:
    name: foosnap
    volume: foo
    state: clone
    target: foosnapclone
    array: vx100_ultra.test.com
    user: admin
    password: secret

- name: Restore parent volume foo to the state captured in snapshot foosnap.
  vexata_snap:
    name: foosnap
    volume: foo
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


def get_volume(module, array):
    """Retrieve a named volume if it exists, None if absent."""
    name = module.params['volume']
    try:
        vols = array.list_volumes()
        vol = filter(lambda v: v['name'] == name, vols)
        if len(vol) == 1:
            return vol[0]
        else:
            return None
    except Exception:
        module.fail_json(msg='Error while attempting to retrieve volumes.')


def get_snap(module, array, vol_id):
    """Retrieve a named volume snapshot if it exists, None if absent."""
    name = module.params['name']
    try:
        snaps = array.list_volsnaps(vol_id)
        snap = filter(lambda snap: snap['name'] == name, snaps)
        if len(snap) == 1:
            return snap[0]
        else:
            return None
    except Exception:
        module.fail_json(msg='Error while attempting to retrieve snapshots.')


def create_snap(module, array, volume):
    """"Create a new snapshot."""
    changed = False
    parent_vol_id = volume['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        snap = array.create_volsnap(
            parent_vol_id,
            module.params['name'],
            'Ansible volume snapshot')
        if snap:
            module.log(msg='Created snapshot {0} for parent volume {1}'
                       .format(snap['name'], volume['name']))
            changed = True
        else:
            module.fail_json(msg='Snapshot create failed.')
    except Exception:
        pass
    module.exit_json(changed=changed)


def delete_snap(module, array, snap, volume):
    changed = False
    parent_vol_id = snap['parentVolumeId']
    snap_id = snap['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        ok = array.delete_volsnap(
            parent_vol_id,
            snap_id)
        if ok:
            module.log(msg='Deleted snapshot {0} of parent volume {1}.'
                       .format(snap['name'], volume['name']))
            changed = True
        else:
            raise Exception
    except Exception:
        pass
    module.exit_json(changed=changed)


def clone_snap(module, array, snap):
    changed = False
    snap_id = snap['id']
    tgt_name = module.params['target']
    if not tgt_name:
        module.fail_json('Target volume name for snapshot cloning is required.')
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        clone = array.clone_volsnap_to_new_volume(
            snap_id,
            tgt_name,
            'Ansible volume snapshot clone')
        if clone:
            module.log(msg='Cloned snapshot {0} to new volume {1}.'
                       .format(snap['name'], tgt_name))
            changed = True
        else:
            raise Exception
    except Exception:
        pass
    module.exit_json(changed=changed)


def restore_snap(module, array, snap, volume):
    changed = False
    parent_vol_id = snap['parentVolumeId']
    snap_id = snap['id']
    if module.check_mode:
        module.exit_json(changed=changed)

    try:
        rsp = array.restore_volume_from_volsnap(
            parent_vol_id,
            snap_id)
        if rsp is not None:
            module.log(msg='Restored volume {0} from snapshot {1}.'
                       .format(volume['name'], snap['name']))
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
            volume=dict(type='str', required=True),
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
    volume = get_volume(module, array)
    if not volume:
        module.fail_json(
            msg='Failed to find volume {0} that is the source for snapshot {1}'
                .format(module.params['volume'], module.params['name']))
    parent_vol_id = volume['id']
    snap = get_snap(module, array, parent_vol_id)
    state = module.params['state']

    if state == 'present' and not snap:
        create_snap(module, array, volume)
    elif state == 'absent' and snap:
        delete_snap(module, array, snap, volume)
    elif state == 'clone' and snap:
        clone_snap(module, array, snap)
    elif state == 'restore' and snap:
        restore_snap(module, array, snap, volume)
    else:
        module.exit_json(changed=False)


if __name__ == '__main__':
    main()
