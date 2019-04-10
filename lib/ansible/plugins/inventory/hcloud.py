# Copyright (c) 2019 Hetzner Cloud GmbH <info@hetzner-cloud.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r"""
    name: hcloud
    plugin_type: inventory
    authors:
      - Lukas Kaemmerling (@lkaemmerling)
    short_description: Ansible dynamic inventory plugin for the Hetzner Cloud.
    version_added: "2.8"
    requirements:
        - python >= 2.7
        - hcloud-python >= 1.0.0
    description:
        - Reads inventories from the Hetzner Cloud API.
        - Uses a YAML configuration file that ends with hcloud.(yml|yaml).
    options:
        plugin:
            description: marks this as an instance of the "hcloud" plugin
            required: true
            choices: ["hcloud"]
        token:
            description: The Hetzner Cloud API Token.
            required: true
            env:
                - name: HCLOUD_TOKEN
        connect_with:
            description: Connect to the server using the value from this field.
            default: public_ipv4
            type: str
            choices:
                - public_ipv4
                - hostname
                - ipv4_dns_ptr
        locations:
          description: Populate inventory with instances in this location.
          default: []
          type: list
          required: false
        types:
          description: Populate inventory with instances with this type.
          default: []
          type: list
          required: false
        images:
          description: Populate inventory with instances with this image name, only available for system images.
          default: []
          type: list
          required: false
        label_selector:
          description: Populate inventory with instances with this label.
          default: ""
          type: str
          required: false
"""

EXAMPLES = r"""
# Minimal example. `HCLOUD_TOKEN` is exposed in environment.
plugin: hcloud

# Example with locations, types, groups and token
plugin: hcloud
token: foobar
locations:
  - nbg1
types:
  - cx11
"""

import os
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.release import __version__

try:
    from hcloud import hcloud
except ImportError:
    raise AnsibleError("The Hetzner Cloud dynamic inventory plugin requires hcloud-python.")


class InventoryModule(BaseInventoryPlugin):
    NAME = "hcloud"

    def _configure_hcloud_client(self):
        self.api_token = self.get_option("token")
        if self.api_token is None:
            raise AnsibleError(
                "Please specify a token, via the option token or via environment variable HCLOUD_TOKEN")

        self.endpoint = os.getenv("HCLOUD_ENDPOINT") or "https://api.hetzner.cloud/v1"

        self.client = hcloud.Client(token=self.api_token,
                                    api_endpoint=self.endpoint,
                                    application_name="ansible-inventory",
                                    application_version=__version__)

    def _test_hcloud_token(self):
        try:
            # We test the API Token against the location API, because this is the API with the smallest result
            # and not controllable from the customer.
            self.client.locations.get_all()
        except hcloud.APIException:
            raise AnsibleError("Invalid Hetzner Cloud API Token.")

    def _add_groups(self):
        locations = self.client.locations.get_all()
        for location in locations:
            self.inventory.add_group(to_native("location_" + location.name))

        images = self.client.images.get_all(type="system")
        for image in images:
            self.inventory.add_group(to_native("image_" + image.os_flavor))

        server_types = self.client.server_types.get_all()
        for server_type in server_types:
            self.inventory.add_group(to_native("server_type_" + server_type.name))

    def _get_servers(self):
        if len(self.get_option("label_selector")) > 0:
            self.servers = self.client.servers.get_all(label_selector=self.get_option("label_selector"))
        else:
            self.servers = self.client.servers.get_all()

    def _filter_servers(self):
        if self.get_option("locations"):
            tmp = []
            for server in self.servers:
                if server.datacenter.location.name in self.get_option("locations"):
                    tmp.append(server)
            self.servers = tmp

        if self.get_option("types"):
            tmp = []
            for server in self.servers:
                if server.server_type.name in self.get_option("types"):
                    tmp.append(server)
            self.servers = tmp

        if self.get_option("images"):
            tmp = []
            for server in self.servers:
                if server.image is not None and server.image.os_flavor in self.get_option("images"):
                    tmp.append(server)
            self.servers = tmp

    def _set_server_attributes(self, server):
        self.inventory.set_variable(server.name, "id", to_native(server.id))
        self.inventory.set_variable(server.name, "name", to_native(server.name))
        self.inventory.set_variable(server.name, "status", to_native(server.status))

        # Network
        self.inventory.set_variable(server.name, "ipv4", to_native(server.public_net.ipv4.ip))
        self.inventory.set_variable(server.name, "ipv6_network", to_native(server.public_net.ipv6.network))
        self.inventory.set_variable(server.name, "ipv6_network_mask", to_native(server.public_net.ipv6.network_mask))

        if self.get_option("connect_with") == "public_ipv4":
            self.inventory.set_variable(server.name, "ansible_host", to_native(server.public_net.ipv4.ip))
        elif self.get_option("connect_with") == "hostname":
            self.inventory.set_variable(server.name, "ansible_host", to_native(server.name))
        elif self.get_option("connect_with") == "ipv4_dns_ptr":
            self.inventory.set_variable(server.name, "ansible_host", to_native(server.public_net.ipv4.dns_ptr))

        # Server Type
        self.inventory.set_variable(server.name, "server_type", to_native(server.image.name))

        # Datacenter
        self.inventory.set_variable(server.name, "datacenter", to_native(server.datacenter.name))
        self.inventory.set_variable(server.name, "location", to_native(server.datacenter.location.name))

        # Image
        self.inventory.set_variable(server.name, "image_id", to_native(server.image.id))
        self.inventory.set_variable(server.name, "image_name", to_native(server.image.name))

    def verify_file(self, path):
        """Return the possibly of a file being consumable by this plugin."""
        return (
            super(InventoryModule, self).verify_file(path) and
            path.endswith((self.NAME + ".yaml", self.NAME + ".yml"))
        )

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        self._read_config_data(path)
        self._configure_hcloud_client()
        self._test_hcloud_token()
        self._add_groups()
        self._get_servers()
        self._filter_servers()
        for server in self.servers:
            self.inventory.add_host(server.name)
            self.inventory.add_host(server.name, group="location_" + server.datacenter.location.name)
            self.inventory.add_host(server.name, group="image_" + server.image.os_flavor)
            self.inventory.add_host(server.name, group="server_type_" + server.server_type.name)
            self._set_server_attributes(server)
