# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015 Gluu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import codecs
import json
import os.path
import time

from gluuapi.database import db
from gluuapi.helper.common_helper import exc_traceback
from gluuapi.setup.base import BaseSetup
from gluuapi.setup.oxauth_setup import OxAuthSetup
from gluuapi.setup.oxtrust_setup import OxTrustSetup


class ldapSetup(BaseSetup):
    def write_ldap_pw(self):
        self.logger.info("writing temporary LDAP password")

        local_dest = os.path.join(self.build_dir, ".pw")
        with codecs.open(local_dest, "w", encoding="utf-8") as fp:
            fp.write(self.cluster.decrypted_admin_pw)

        self.salt.cmd(
            self.node.id, "cmd.run",
            ["mkdir -p {}".format(os.path.dirname(self.node.ldapPassFn))],
        )
        self.salt.copy_file(self.node.id, local_dest, self.node.ldapPassFn)

    def delete_ldap_pw(self):
        self.logger.info("deleting temporary LDAP password")
        self.salt.cmd(
            self.node.id,
            'cmd.run',
            ['rm -f {}'.format(self.node.ldapPassFn)],
        )

    def add_ldap_schema(self):
        ctx = {
            "inumOrgFN": self.cluster.inumOrgFN,
        }

        # render schema templates
        for schema_file in self.node.schemaFiles:
            src = schema_file
            dest = os.path.join(self.node.schemaFolder, os.path.basename(src))
            self.render_template(src, dest, ctx)

    def setup_opendj(self):
        src = self.node.ldap_setup_properties
        dest = os.path.join(self.node.ldapBaseFolder, os.path.basename(src))
        ctx = {
            "ldap_hostname": self.node.weave_ip,
            "ldap_port": self.node.ldap_port,
            "ldaps_port": self.node.ldaps_port,
            "ldap_jmx_port": self.node.ldap_jmx_port,
            "ldap_admin_port": self.node.ldap_admin_port,
            "ldap_binddn": self.node.ldap_binddn,
            "ldapPassFn": self.node.ldapPassFn,
        }
        self.render_template(src, dest, ctx)

        setupCmd = " ".join([
            self.node.ldapSetupCommand,
            '--no-prompt', '--cli', '--acceptLicense', '--propertiesFilePath',
            dest,
        ])

        self.logger.info("running opendj setup")
        self.salt.cmd(
            self.node.id,
            'cmd.run',
            ["{}".format(setupCmd)],
        )

        self.logger.info("running dsjavaproperties")
        self.salt.cmd(
            self.node.id,
            'cmd.run',
            [self.node.ldapDsJavaPropCommand],
        )

        # wait for opendj being started before proceeding to next step
        self.logger.info(
            "warming up opendj server; "
            "sleeping for {} seconds".format(self.node.ldapStartTimeOut))
        time.sleep(self.node.ldapStartTimeOut)

    def configure_opendj(self):
        config_changes = [
            ['set-global-configuration-prop', '--set', 'single-structural-objectclass-behavior:accept'],
            ['set-attribute-syntax-prop', '--syntax-name', '"Directory String"', '--set', 'allow-zero-length-values:true'],
            ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'allow-pre-encoded-passwords:true'],
            ['set-log-publisher-prop', '--publisher-name', '"File-Based Audit Logger"', '--set', 'enabled:true'],
            ['create-backend', '--backend-name', 'site', '--set', 'base-dn:o=site', '--type local-db', '--set', 'enabled:true'],
        ]

        for changes in config_changes:
            dsconfigCmd = " ".join([
                self.node.ldapDsconfigCommand, '--trustAll', '--no-prompt',
                '--hostname', self.node.weave_ip,
                '--port', self.node.ldap_admin_port,
                '--bindDN', '"%s"' % self.node.ldap_binddn,
                '--bindPasswordFile', self.node.ldapPassFn,
            ] + changes)
            self.logger.info("configuring opendj config changes: {}".format(dsconfigCmd))
            self.salt.cmd(self.node.id, 'cmd.run', [dsconfigCmd])
            time.sleep(1)

    def index_opendj(self):
        with open(self.node.indexJson, 'r') as fp:
            index_json = json.load(fp)

        if index_json:
            for attrDict in index_json:
                attr_name = attrDict['attribute']
                index_types = attrDict['index']

                for index_type in index_types:
                    self.logger.info("creating %s index for attribute %s" % (index_type, attr_name))
                    indexCmd = " ".join([
                        self.node.ldapDsconfigCommand,
                        'create-local-db-index',
                        '--backend-name', 'userRoot',
                        '--type', 'generic',
                        '--index-name', attr_name,
                        '--set', 'index-type:%s' % index_type,
                        '--set', 'index-entry-limit:4000',
                        '--hostName', self.node.weave_ip,
                        '--port', self.node.ldap_admin_port,
                        '--bindDN', '"%s"' % self.node.ldap_binddn,
                        '-j', self.node.ldapPassFn,
                        '--trustAll', '--noPropertiesFile', '--no-prompt',
                    ])
                    self.salt.cmd(self.node.id, 'cmd.run', [indexCmd])

    def import_ldif(self):
        # template's context
        ctx = {
            "oxauth_client_id": self.cluster.oxauth_client_id,
            "oxauthClient_encoded_pw": self.cluster.oxauth_client_encoded_pw,
            "encoded_ldap_pw": self.cluster.encoded_ldap_pw,
            "encoded_ox_ldap_pw": self.cluster.encoded_ox_ldap_pw,
            "inumAppliance": self.cluster.inumAppliance,
            "hostname": self.node.weave_ip,
            "hostname_oxauth_cluster": self.cluster.hostname_oxauth_cluster,
            "hostname_oxtrust_cluster": self.cluster.hostname_oxtrust_cluster,
            "ldaps_port": self.node.ldaps_port,
            "ldap_binddn": self.node.ldap_binddn,
            "inumOrg": self.cluster.inumOrg,
            "inumOrgFN": self.cluster.inumOrgFN,
            "orgName": self.cluster.orgName,
        }

        ldifFolder = '%s/ldif' % self.node.ldapBaseFolder
        self.salt.cmd(
            self.node.id,
            "cmd.run",
            ["mkdir -p {}".format(ldifFolder)]
        )

        # render templates
        for ldif_file in self.node.ldif_files:
            src = ldif_file
            file_basename = os.path.basename(src)
            dest = os.path.join(ldifFolder, file_basename)
            self.render_template(src, dest, ctx)

            if file_basename == "o_site.ldif":
                backend_id = "site"
            else:
                backend_id = "userRoot"

            importCmd = " ".join([
                self.node.importLdifCommand,
                '--ldifFile', dest,
                '--backendID', backend_id,
                '--hostname', self.node.weave_ip,
                '--port', self.node.ldap_admin_port,
                '--bindDN', '"%s"' % self.node.ldap_binddn,
                '-j', self.node.ldapPassFn,
                '--append', '--trustAll',
            ])
            self.logger.info("importing {}".format(file_basename))
            self.salt.cmd(self.node.id, 'cmd.run', [importCmd])
            time.sleep(1)

    def export_opendj_public_cert(self):
        # Load password to acces OpenDJ truststore
        openDjPinFn = '%s/config/keystore.pin' % self.node.ldapBaseFolder
        openDjTruststoreFn = '%s/config/truststore' % self.node.ldapBaseFolder
        openDjPin = "`cat {}`".format(openDjPinFn)

        self.salt.cmd(
            self.node.id,
            ["cmd.run", "cmd.run"],
            [
                ["mkdir -p {}".format(os.path.dirname(self.node.openDjCertFn))],
                ["touch {}".format(self.node.openDjCertFn)],
            ],
        )

        # Export public OpenDJ certificate
        self.logger.info("exporting OpenDJ certificate")
        cmdsrt = ' '.join([
            self.node.keytoolCommand, '-exportcert',
            '-keystore', openDjTruststoreFn,
            '-storepass', openDjPin,
            '-file', self.node.openDjCertFn,
            '-alias', 'server-cert',
            '-rfc',
        ])
        self.salt.cmd(self.node.id, 'cmd.run', [cmdsrt])

        # Import OpenDJ certificate into java truststore
        cmdstr = ' '.join([
            "/usr/bin/keytool", "-import", "-trustcacerts", "-alias",
            "{}_opendj".format(self.node.weave_ip),
            "-file", self.node.openDjCertFn,
            "-keystore", self.node.defaultTrustStoreFN,
            "-storepass", "changeit", "-noprompt",
        ])
        self.logger.info("importing OpenDJ certificate into Java truststore")
        self.salt.cmd(self.node.id, 'cmd.run', [cmdstr])

    def get_existing_node(self, node_id):
        try:
            self.logger.info("getting existing node {}".format(node_id))
            node = db.get(node_id, "nodes")
            return node
        except IndexError as exc:
            self.logger.warn(exc)

    def replicate_from(self, existing_node):
        setup_obj = ldapSetup(existing_node, self.cluster, logger=self.logger)

        # creates temporary password file
        setup_obj.write_ldap_pw()

        base_dns = ("o=gluu", "o=site",)
        for base_dn in base_dns:
            enable_cmd = " ".join([
                "/opt/opendj/bin/dsreplication", "enable",
                "--host1", existing_node.weave_ip,
                "--port1", existing_node.ldap_admin_port,
                "--bindDN1", "'{}'".format(existing_node.ldap_binddn),
                "--bindPasswordFile1", self.node.ldapPassFn,
                "--replicationPort1", existing_node.ldap_replication_port,
                "--host2", self.node.weave_ip,
                "--port2", self.node.ldap_admin_port,
                "--bindDN2", "'{}'".format(self.node.ldap_binddn),
                "--bindPasswordFile2", self.node.ldapPassFn,
                "--replicationPort2", self.node.ldap_replication_port,
                "--adminUID", "admin",
                "--adminPasswordFile", self.node.ldapPassFn,
                "--baseDN", "'{}'".format(base_dn),
                "--secureReplication1", "--secureReplication2",
                "-X", "-n",
            ])
            self.logger.info("enabling {!r} replication between {} and {}".format(
                base_dn, existing_node.weave_ip, self.node.weave_ip,
            ))
            self.salt.cmd(self.node.id, "cmd.run", [enable_cmd])

            # wait before initializing the replication to ensure it
            # has been enabled
            time.sleep(10)

            # try:
            init_cmd = " ".join([
                "/opt/opendj/bin/dsreplication", "initialize",
                "--baseDN", "'{}'".format(base_dn),
                "--adminUID", "admin",
                "--adminPasswordFile", self.node.ldapPassFn,
                "--hostSource", existing_node.weave_ip,
                "--portSource", existing_node.ldap_admin_port,
                "--hostDestination", self.node.weave_ip,
                "--portDestination", self.node.ldap_admin_port,
                "-X", "-n"
            ])
            self.logger.info("initializing {!r} replication between {} and {}".format(
                base_dn, existing_node.weave_ip, self.node.weave_ip,
            ))
            self.salt.cmd(self.node.id, "cmd.run", [init_cmd])
            time.sleep(5)

        # cleanups temporary password file
        setup_obj.delete_ldap_pw()

    def setup(self):
        self.logger.info("LDAP setup is started")
        start = time.time()

        self.write_ldap_pw()
        self.add_ldap_schema()
        self.setup_opendj()
        self.configure_opendj()
        self.index_opendj()

        if self.cluster.ldap_nodes:
            # Initialize data from existing ldap node.
            # To create fully meshed replication, update the other ldap
            # nodes to use this new ldap node as a master.
            for node_id in self.cluster.ldap_nodes:
                existing_node = self.get_existing_node(node_id)
                if existing_node:
                    self.replicate_from(existing_node)
        else:
            # If no ldap nodes exist, import auto-generated base ldif data
            self.import_ldif()

        self.export_opendj_public_cert()
        self.delete_ldap_pw()

        elapsed = time.time() - start
        self.logger.info("LDAP setup is finished ({} seconds)".format(elapsed))
        return True

    def after_setup(self):
        """Runs post-setup.
        """
        # Currently, we need to update oxAuth and oxTrust LDAP properties
        # TODO: use signals?
        for oxauth in self.cluster.get_oxauth_objects():
            setup_obj = OxAuthSetup(oxauth, self.cluster, logger=self.logger)
            setup_obj.render_ldap_props_template()

        for oxtrust in self.cluster.get_oxtrust_objects():
            setup_obj = OxTrustSetup(oxtrust, self.cluster, logger=self.logger)
            setup_obj.render_ldap_props_template()

    def stop(self):
        try:
            # since LDAP nodes are replicated if there's more than 1 node,
            # we need to disable the replication agreement first before
            # before stopping the opendj server
            if len(self.cluster.ldap_nodes) > 1:
                self.write_ldap_pw()
                disable_repl_cmd = " ".join([
                    "{}/bin/dsreplication".format(self.node.ldapBaseFolder),
                    "disable",
                    "--hostname", self.node.weave_ip,
                    "--port", self.node.ldap_admin_port,
                    "--adminUID", "admin",
                    "--adminPasswordFile", self.node.ldapPassFn,
                    "-X", "-n", "--disableAll",
                ])
                self.salt.cmd(self.node.id, "cmd.run", [disable_repl_cmd])
                self.delete_ldap_pw()

            # stop the server
            stop_cmd = "{}/bin/stop-ds".format(self.node.ldapBaseFolder)
            self.salt.cmd(self.node.id, "cmd.run", [stop_cmd])
        except SystemExit as exc:
            # executable may not exist or minion is unreachable
            if exc.code == 2:
                pass
            else:
                print exc_traceback()
