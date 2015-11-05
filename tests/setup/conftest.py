import pytest


@pytest.fixture()
def ldap_setup(request, app, ldap_node, cluster):
    from gluuapi.setup import LdapSetup

    setup_obj = LdapSetup(ldap_node, cluster, app)

    def teardown():
        setup_obj.remove_build_dir()

    request.addfinalizer(teardown)
    return setup_obj


@pytest.fixture()
def oxauth_setup(request, app, oxauth_node, cluster):
    from gluuapi.setup import OxauthSetup

    setup_obj = OxauthSetup(oxauth_node, cluster, app)

    def teardown():
        setup_obj.remove_build_dir()

    request.addfinalizer(teardown)
    return setup_obj


@pytest.fixture()
def oxtrust_setup(request, app, oxtrust_node, cluster):
    from gluuapi.setup import OxtrustSetup

    setup_obj = OxtrustSetup(oxtrust_node, cluster, app)

    def teardown():
        setup_obj.remove_build_dir()

    request.addfinalizer(teardown)
    return setup_obj


@pytest.fixture()
def httpd_setup(request, app, httpd_node, cluster):
    from gluuapi.setup import HttpdSetup

    setup_obj = HttpdSetup(httpd_node, cluster, app)

    def teardown():
        setup_obj.remove_build_dir()

    request.addfinalizer(teardown)
    return setup_obj


@pytest.fixture()
def oxidp_setup(request, app, oxidp_node, cluster):
    from gluuapi.setup import OxidpSetup

    setup_obj = OxidpSetup(oxidp_node, cluster, app)

    def teardown():
        setup_obj.remove_build_dir()

    request.addfinalizer(teardown)
    return setup_obj
