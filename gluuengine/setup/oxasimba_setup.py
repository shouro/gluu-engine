# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os.path
import time
from glob import iglob

from blinker import signal

from .base import OxSetup


class OxasimbaSetup(OxSetup):  # pragma: no cover
    def setup(self):
        hostname = self.container.hostname

        # render config templates
        self.copy_selector_template()
        self.render_ldap_props_template()
        self.render_server_xml_template()
        self.render_httpd_conf()
        self.configure_vhost()

        # customize asimba and rebuild
        self.unpack_jar()
        self.copy_props_template()
        self.render_config_template()

        self.gen_cert("asimba", self.cluster.decrypted_admin_pw,
                      "tomcat", "tomcat", hostname)
        self.gen_cert("httpd", self.cluster.decrypted_admin_pw,
                      "www-data", "www-data", hostname)

        # Asimba keystore
        self.gen_keystore(
            "asimbaIDP",
            self.cluster.asimba_jks_fn,
            self.cluster.decrypted_admin_pw,
            "{}/asimba.key".format(self.container.cert_folder),
            "{}/asimba.crt".format(self.container.cert_folder),
            "tomcat",
            "tomcat",
            hostname,
        )

        # add auto startup entry
        self.add_auto_startup_entry()
        self.change_cert_access("tomcat", "tomcat")
        self.reconfigure_asimba()
        self.reload_supervisor()
        return True

    def add_auto_startup_entry(self):
        payload = """
[program:tomcat]
command=/opt/tomcat/bin/catalina.sh run
environment=CATALINA_PID=/var/run/tomcat.pid

[program:httpd]
command=/usr/bin/pidproxy /var/run/apache2/apache2.pid /bin/bash -c \\"source /etc/apache2/envvars && /usr/sbin/apache2ctl -DFOREGROUND\\"
"""

        self.logger.info("adding supervisord entry")
        cmd = '''sh -c "echo '{}' >> /etc/supervisor/conf.d/supervisord.conf"'''.format(payload)
        self.docker.exec_cmd(self.container.cid, cmd)

    def render_server_xml_template(self):
        src = "oxasimba/server.xml"
        dest = os.path.join(self.container.tomcat_conf_dir, os.path.basename(src))
        ctx = {
            "asimba_jks_pass": self.cluster.decrypted_admin_pw,
            "asimba_jks_fn": self.cluster.asimba_jks_fn,
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def render_httpd_conf(self):
        src = "oxasimba/gluu_httpd.conf"
        file_basename = os.path.basename(src)
        dest = os.path.join("/etc/apache2/sites-available", file_basename)

        ctx = {
            "hostname": self.container.hostname,
            "httpd_cert_fn": "/etc/certs/httpd.crt",
            "httpd_key_fn": "/etc/certs/httpd.key",
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def unpack_jar(self):
        unpack_cmd = "unzip -qq /opt/tomcat/webapps/oxasimba.war " \
                     "-d /tmp/asimba"
        self.docker.exec_cmd(self.container.cid, unpack_cmd)
        time.sleep(5)

    def copy_selector_template(self):
        src = self.get_template_path("oxasimba/asimba-selector.xml")
        dest = "{}/asimba-selector.xml".format(self.container.tomcat_conf_dir)
        self.docker.copy_to_container(self.container.cid, src, dest)

    def copy_props_template(self):
        src = self.get_template_path("oxasimba/asimba.properties")
        dest = "/tmp/asimba/WEB-INF/asimba.properties"
        self.docker.copy_to_container(self.container.cid, src, dest)

    def render_config_template(self):
        src = self.get_template_path("oxasimba/asimba.xml")
        dest = "/tmp/asimba/WEB-INF/conf/asimba.xml"
        ctx = {
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "asimba_jks_fn": self.cluster.asimba_jks_fn,
            "asimba_jks_pass": self.cluster.decrypted_admin_pw,
            "inum_org_fn": self.cluster.inum_org_fn,
        }
        self.render_template(src, dest, ctx)

    def reconfigure_asimba(self):
        self.logger.info("reconfiguring asimba")

        # rebuild jar
        jar_cmd = "/usr/bin/jar cmf /tmp/asimba/META-INF/MANIFEST.MF " \
                  "/tmp/asimba.war -C /tmp/asimba ."
        self.docker.exec_cmd(self.container.cid, jar_cmd)

        # remove oxasimba.war
        rm_cmd = "rm /opt/tomcat/webapps/oxasimba.war"
        self.docker.exec_cmd(self.container.cid, rm_cmd)

        # install reconfigured asimba.jar
        mv_cmd = "mv /tmp/asimba.war /opt/tomcat/webapps/asimba.war"
        self.docker.exec_cmd(self.container.cid, mv_cmd)

        # remove temporary asimba
        rm_cmd = "rm -rf /tmp/asimba"
        self.docker.exec_cmd(self.container.cid, rm_cmd)

    def pull_idp_metadata(self):
        files = iglob("{}/metadata/*-idp-metadata.xml".format(
            self.app.config["OXIDP_OVERRIDE_DIR"],
        ))

        for src in files:
            fn = os.path.basename(src)
            dest = "/opt/idp/metadata/{}".format(fn)
            self.logger.info("copying {}".format(fn))
            self.docker.copy_to_container(self.container.cid, src, dest)

    def discover_nginx(self):
        """Discovers nginx container.
        """
        self.logger.info("discovering available nginx container")
        with self.app.app_context():
            if self.cluster.count_containers(type_="nginx"):
                self.import_nginx_cert()

    def after_setup(self):
        """Post-setup callback.
        """
        self.pull_idp_metadata()
        self.discover_nginx()
        complete_sgn = signal("ox_setup_completed")
        complete_sgn.send(self)

    def teardown(self):
        """Teardowns the container.
        """
        complete_sgn = signal("ox_teardown_completed")
        complete_sgn.send(self)