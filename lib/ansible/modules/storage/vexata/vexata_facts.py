#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Sandeep Kasargod (sandeep@vexata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: vexata_facts
version_added: 2.8
short_description: Retrieve facts about Vexata VX100 storage arrays
description:
  - Collect facts from a Vexata VX100 storage array.
author:
  - Sandeep Kasargod (@vexata)
options:
  gather_subset:
    description:
      - List of fact categories to be gathered. Allowed values are all,
        capacity, controllers, drivegroups, drives, exportgroups, initiators,
        initiatorgroups, node, ports, portgroups, sensors, volumes,
        volumegroups.
    default: capacity
extends_documentation_fragment:
    - vexata.vx100
'''

EXAMPLES = '''
- name: Collect facts from the storage array.
  vexata_facts:
    array: vx100_ultra.test.com
    user: admin
    password: secret
'''

RETURN = '''
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vexata import (
    argument_spec, get_array, required_together)


def _exclude_dict(d, excluded):
    ex = frozenset(excluded)
    return {k: d[k] for k in d if k not in ex}


def get_capacity(module, array):
    try:
        sa = array.sa_info()
        info = {
            'totalCapacity': sa['totalCapacity'],
            'usedCapacity': sa['usedCapacity'],
            'provisionedCapacity': sa['provisionedCapacity'],
            'provisionedCapacityLeft': sa['provisionCapacityLeft'],
            'maxOverProvisioningFactor': sa['maxOverProvisioningFactor'],
            'maxProvisionLimit': sa['maxProvisionLimit'],
            'warningThresholdPercent': sa['thresholdPercentage'],
            'volumeCount': sa['entityCounts']['volumeCount'],
            'volumeGroupCount': sa['entityCounts']['volumeGroupCount'],
            'initiatorCount': sa['entityCounts']['initiatorCount'],
            'initiatorGroupCount': sa['entityCounts']['initiatorGroupCount'],
            'portCount': sa['entityCounts']['portCount'],
            'portGroupCount': sa['entityCounts']['portGroupCount'],
            'exportGroupCount': sa['entityCounts']['exportGroupCount'],
        }
        if 'totalMetadata' in sa:
            info['totalMetadata'] = sa['totalMetadata']
            info['usedMetadata'] = sa['usedMetadata']
            info['metadataWarningThresholdPercent'] = sa['metadataThresholdPercentage']
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve capacity info.')


def get_controllers(module, array):
    try:
        iocs = array.iocs()
        return iocs
    except Exception:
        module.fail_json(msg='Error attempting to retrieve controller info.')


def get_drivegroups(module, array):
    try:
        dgs = array.drivegroups()
        info = []
        excluded = ('_links', 'addDrives', 'drives', 'nodeId', 'nodeUuid')
        for dg in dgs:
            facts = _exclude_dict(dg, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve drivegroup info.')


def get_drives(module, array):
    try:
        dgs = array.drivegroups()
        info = []
        excluded = ('_links', 'location', 'nodeUuid', 'ready')
        for dg in dgs:
            for drv in dg['drives']:
                facts = _exclude_dict(drv, excluded)
                info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve drive info.')


def get_exportgroups(module, array):
    try:
        egs = array.list_egs()
        info = []
        excluded = ('_links', 'storageArrayId')
        for eg in egs:
            facts = _exclude_dict(eg, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve exportgroup info.')


def get_initiators(module, array):
    try:
        inis = array.list_initiators()
        info = []
        excluded = ('_links', 'initiatorGroupsCountBeta', 'loggedInPort',
                    'storageArrayId')
        for ini in inis:
            facts = _exclude_dict(ini, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve initiator info.')


def get_initiatorgroups(module, array):
    try:
        igs = array.list_igs()
        info = []
        excluded = ('_links', 'addInitiators', 'deleteInitiators', 'portCount',
                    'volumeCount', 'storageArrayId')
        for ig in igs:
            facts = _exclude_dict(ig, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve initiatorgroup info.')


def get_node(module, array):
    try:
        node = array.node()
        excluded = ('_links', 'fans', 'ioControllers', 'sensors',
                    'storageServiceReady')
        facts = _exclude_dict(node, excluded)
        return facts
    except Exception:
        module.fail_json(msg='Error attempting to retrieve node info.')


def get_ports(module, array):
    try:
        sa = array.sa_info()
        info = []
        for port in sa['ports']:
            facts = {
                'id': port['id'],
                'type': port['type'],
                'state': port['state'],
                'address': port['name'],
                'controller': port['phyIoControllerId'],
                'controllerPort': port['phyPortId']
            }
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve port info.')


def get_portgroups(module, array):
    try:
        pgs = array.list_pgs()
        info = []
        excluded = ('_links', 'addPorts', 'deletePorts', 'initiatorCount',
                    'volumeCount', 'storageArrayId')
        for pg in pgs:
            facts = _exclude_dict(pg, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve portgroup info.')


def get_sensors(module, array):
    try:
        sns = array.sensors()
        return sns
    except Exception:
        module.fail_json(msg='Error attempting to retrieve sensor info.')


def get_volumes(module, array):
    try:
        vols = array.list_volumes()
        info = []
        excluded = ('_links', 'blkSize', 'storageArrayId', 'stats',
                    'storagePool', 'voluuid', 'volumeType')
        for vol in vols:
            facts = _exclude_dict(vol, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve volume info.')


def get_volumegroups(module, array):
    try:
        vgs = array.list_vgs()
        info = []
        excluded = ('_links', 'addVolumes', 'deleteVolumes', 'initiatorCount',
                    'portCount', 'storageArrayId')
        for vg in vgs:
            facts = _exclude_dict(vg, excluded)
            info.append(facts)
        return info
    except Exception:
        module.fail_json(msg='Error attempting to retrieve volumegroup info.')


def main():
    arg_spec = argument_spec()
    arg_spec.update(
        dict(
            gather_subset=dict(default='capacity', type='list',),
        )
    )
    module = AnsibleModule(arg_spec,
                           supports_check_mode=True,
                           required_together=required_together())

    types = module.params['gather_subset']
    allowed_types = [
        'all', 'capacity', 'controllers', 'drivegroups', 'drives',
        'exportgroups', 'initiators', 'initiatorgroups', 'node', 'ports',
        'portgroups', 'sensors', 'volumes', 'volumegroups',
    ]

    if any(t not in allowed_types for t in types):
        module.fail_json(msg='One or more values for gather_subset is not '
                         'valid. Allowed types are: {0}'.format(allowed_types))

    array = get_array(module)
    facts = {}
    if 'capacity' in types or 'all' in types:
        facts['capacity'] = get_capacity(module, array)
    if 'controllers' in types or 'all' in types:
        facts['controllers'] = get_controllers(module, array)
    if 'drivegroups' in types or 'all' in types:
        facts['drivegroups'] = get_drivegroups(module, array)
    if 'drives' in types or 'all' in types:
        facts['drives'] = get_drives(module, array)
    if 'exportgroups' in types or 'all' in types:
        facts['exportgroups'] = get_exportgroups(module, array)
    if 'initiators' in types or 'all' in types:
        facts['initiators'] = get_initiators(module, array)
    if 'initiatorgroups' in types or 'all' in types:
        facts['initiatorgroups'] = get_initiatorgroups(module, array)
    if 'node' in types or 'all' in types:
        facts['node'] = get_node(module, array)
    if 'ports' in types or 'all' in types:
        facts['ports'] = get_ports(module, array)
    if 'portgroups' in types or 'all' in types:
        facts['portgroups'] = get_portgroups(module, array)
    if 'sensors' in types or 'all' in types:
        facts['sensors'] = get_sensors(module, array)
    if 'volumes' in types or 'all' in types:
        facts['volumes'] = get_volumes(module, array)
    if 'volumegroups' in types or 'all' in types:
        facts['volumegroups'] = get_volumegroups(module, array)
    result = dict(ansible_facts=facts)
    module.exit_json(**result)


if __name__ == '__main__':
    main()
