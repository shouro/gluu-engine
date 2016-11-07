# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import uuid

from .base import BaseModel
from .base import STATE_SUCCESS
from ..database import db


class Node(BaseModel):
    resource_fields = dict.fromkeys([
        'id',
        'name',
        'type',
        'provider_id',
    ])

    def count_containers(self, type_="", state=STATE_SUCCESS):
        """Counts available containers objects (models).

        :param state: State of the container (one of SUCCESS, DISABLED,
                      FAILED, IN_PROGRESS).
        :param type_: Type of the container.
        :returns: A list of container objects.
        """
        condition = {"node_id": self.id}
        if state:
            condition["state"] = state
        if type_:
            condition["type"] = type_
        return db.count_from_table("containers", condition)

    def get_containers(self, type_="", state=STATE_SUCCESS):
        """Gets available container objects (models).

        :param state: State of the container (one of SUCCESS, DISABLED,
                      FAILED, IN_PROGRESS).
        :param type_: Type of the container.
        :returns: A list of container objects.
        """
        condition = {"node_id": self.id}
        if state:
            condition["state"] = state
        if type_:
            condition["type"] = type_
        return db.search_from_table("containers", condition)


class DiscoveryNode(Node):
    state_fields = dict.fromkeys([
        'state_node_create',
        'state_install_consul',
        'state_complete'
    ], False)
    resource_fields = dict(Node.resource_fields.items() + state_fields.items())

    def __init__(self, fields=None):
        self.id = str(uuid.uuid4())
        self.state_node_create = False
        self.state_install_consul = False
        self.state_complete = False
        self.type = 'discovery'
        self.populate(fields)

    def populate(self, fields=None):
        fields = fields or {}
        self.name = fields.get("name", "gluu.discovery")
        self.provider_id = fields.get('provider_id', '')


class MasterNode(Node):
    state_fields = dict.fromkeys([
        'state_node_create',
        'state_install_weave',
        'state_weave_permission',
        'state_weave_launch',
        'state_registry_cert',
        'state_docker_cert',
        'state_fswatcher',
        'state_recovery',
        'state_complete',
        "state_rng_tools",
        "state_pull_images",
    ], False)
    resource_fields = dict(Node.resource_fields.items() + state_fields.items())

    def __init__(self, fields=None):
        self.id = str(uuid.uuid4())
        self.state_node_create = False
        self.state_install_weave = False
        self.state_weave_permission = False
        self.state_weave_launch = False
        self.state_registry_cert = False
        self.state_docker_cert = False
        self.state_fswatcher = False
        self.state_recovery = False
        self.state_complete = False
        self.state_rng_tools = False
        self.state_pull_images = False
        self.type = 'master'
        self.populate(fields)

    def populate(self, fields=None):
        fields = fields or {}
        self.name = fields.get('name', '')
        #self.type = fields.get('type', '')
        self.provider_id = fields.get('provider_id', '')

class WorkerNode(Node):
    state_fields = dict.fromkeys([
        'state_node_create',
        'state_install_weave',
        'state_weave_permission',
        'state_weave_launch',
        'state_registry_cert',
        'state_recovery',
        'state_complete',
        "state_rng_tools",
        "state_pull_images",
    ], False)
    resource_fields = dict(Node.resource_fields.items() + state_fields.items())

    def __init__(self, fields=None):
        self.id = str(uuid.uuid4())
        self.state_node_create = False
        self.state_install_weave = False
        self.state_weave_permission = False
        self.state_weave_launch = False
        self.state_registry_cert = False
        self.state_recovery = False
        self.state_complete = False
        self.state_rng_tools = False
        self.state_pull_images = False
        self.type = 'worker'
        self.populate(fields)

    def populate(self, fields=None):
        fields = fields or {}
        self.name = fields.get('name', '')
        self.provider_id = fields.get('provider_id', '')
