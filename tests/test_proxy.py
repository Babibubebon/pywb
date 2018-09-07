from pywb.warcserver.test.testutils import BaseTestClass, TempDirTests, HttpBinLiveTests

from .base_config_test import CollsDirMixin
from pywb.utils.geventserver import GeventServer, RequestURIWSGIHandler
from pywb.apps.frontendapp import FrontEndApp
from pywb.manager.manager import main as manager

import os
import requests
import pytest


# ============================================================================
@pytest.fixture(params=['http', 'https'])
def scheme(request):
    return request.param


# ============================================================================
class BaseTestProxy(TempDirTests, BaseTestClass):
    @classmethod
    def setup_class(cls, coll='pywb', config_file='config_test.yaml', recording=False,
                    extra_opts={}):

        super(BaseTestProxy, cls).setup_class()
        config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), config_file)

        cls.root_ca_file = os.path.join(cls.root_dir, 'pywb-ca-test.pem')

        opts = {'ca_name': 'pywb test HTTPS Proxy CA',
                'ca_file_cache': cls.root_ca_file,
                'coll': coll,
                'recording': recording,
               }

        opts.update(extra_opts)

        cls.app = FrontEndApp(config_file=config_file,
                              custom_config={'proxy': opts})

        cls.server = GeventServer(cls.app, handler_class=RequestURIWSGIHandler)
        cls.proxies = cls.proxy_dict(cls.server.port)

    @classmethod
    def teardown_class(cls):
        cls.server.stop()

        super(BaseTestProxy, cls).teardown_class()

    @classmethod
    def proxy_dict(cls, port, host='localhost'):
        return {'http': 'http://{0}:{1}'.format(host, port),
                'https': 'https://{0}:{1}'.format(host, port)
               }


# ============================================================================
class TestProxy(BaseTestProxy):
    def test_proxy_replay(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        assert 'Example Domain' in res.text

        # wb insert
        assert 'WB Insert' in res.text

        # no wombat.js and wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' not in res.text

        # no redirect check
        assert 'window == window.top' not in res.text

        assert res.headers['Link'] == '<http://example.com>; rel="memento"; datetime="Mon, 27 Jan 2014 17:12:51 GMT"; collection="pywb"'
        assert res.headers['Memento-Datetime'] == 'Mon, 27 Jan 2014 17:12:51 GMT'

    def test_proxy_replay_change_dt(self, scheme):
        headers = {'Accept-Datetime':  'Mon, 26 Dec 2011 17:12:51 GMT'}
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           headers=headers,
                           verify=self.root_ca_file)

        assert 'WB Insert' in res.text
        assert 'Example Domain' in res.text

        # no wombat.js and wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' not in res.text

        # banner
        assert 'default_banner.js' in res.text

        # no redirect check
        assert 'window == window.top' not in res.text

        assert res.headers['Link'] == '<http://test@example.com/>; rel="memento"; datetime="Mon, 29 Jul 2013 19:51:51 GMT"; collection="pywb"'
        assert res.headers['Memento-Datetime'] == 'Mon, 29 Jul 2013 19:51:51 GMT'


# ============================================================================
class TestRecordingProxy(HttpBinLiveTests, CollsDirMixin, BaseTestProxy):
    @classmethod
    def setup_class(cls, coll='pywb', config_file='config_test.yaml'):
        super(TestRecordingProxy, cls).setup_class('test', 'config_test_record.yaml', recording=True)
        manager(['init', 'test'])

    @classmethod
    def teardown_class(cls):
        if cls.app.recorder:
            cls.app.recorder.writer.close()
        super(TestRecordingProxy, cls).teardown_class()

    def test_proxy_record(self, scheme):
        archive_dir = os.path.join(self.root_dir, '_test_colls', 'test', 'archive')
        assert os.path.isdir(archive_dir)

        res = requests.get('{0}://httpbin.org/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        assert 'is_live = true' in res.text
        assert 'httpbin(1)' in res.text

        assert len(os.listdir(archive_dir)) == 1

    def test_proxy_replay_recorded(self, scheme):
        manager(['reindex', 'test'])

        self.app.proxy_prefix = '/test/bn_/'

        res = requests.get('{0}://httpbin.org/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        assert 'is_live = false' in res.text
        assert 'httpbin(1)' in res.text

    def test_proxy_record_keep_percent(self, scheme):
        self.app.proxy_prefix = '/test/record/bn_/'

        res = requests.get('{0}://example.com/path/%2A%2Ftest'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # ensure %-encoded url stays as is
        assert '"{0}://example.com/path/%2A%2Ftest"'.format(scheme) in res.text


# ============================================================================
class TestProxyNoBanner(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyNoBanner, cls).setup_class(extra_opts={'use_banner': False})

    def test_proxy_replay(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # content
        assert 'Example Domain' in res.text

        # head insert
        assert 'WB Insert' in res.text

        # no banner
        assert 'default_banner.js' not in res.text

        # no wombat.js and wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' not in res.text

        # no redirect check
        assert 'window == window.top' not in res.text

        assert res.headers['Link'] == '<http://example.com>; rel="memento"; datetime="Mon, 27 Jan 2014 17:12:51 GMT"; collection="pywb"'
        assert res.headers['Memento-Datetime'] == 'Mon, 27 Jan 2014 17:12:51 GMT'


# ============================================================================
class TestProxyNoHeadInsert(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyNoHeadInsert, cls).setup_class(extra_opts={'use_head_insert': False})

    def test_proxy_replay(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # content
        assert 'Example Domain' in res.text

        # no head insert
        assert 'WB Insert' not in res.text

        # no banner
        assert 'default_banner.js' not in res.text

        # no wombat.js and wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' not in res.text

        # no redirect check
        assert 'window == window.top' not in res.text

        assert res.headers['Link'] == '<http://example.com>; rel="memento"; datetime="Mon, 27 Jan 2014 17:12:51 GMT"; collection="pywb"'
        assert res.headers['Memento-Datetime'] == 'Mon, 27 Jan 2014 17:12:51 GMT'


class TestProxyIncludeBothWombatPreservationWorker(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyIncludeBothWombatPreservationWorker, cls).setup_class(
            extra_opts={'use_wombat': True, 'use_preserve_worker': True}
        )

    def test_include_both_wombat_preservation_worker(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # content
        assert 'Example Domain' in res.text

        # yes head insert
        assert 'WB Insert' in res.text

        # no wombat.js, yes wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' in res.text
        assert 'wbinfo.wombat_mode = "wp";' in res.text


class TestProxyIncludeWombatNotPreservationWorker(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyIncludeWombatNotPreservationWorker, cls).setup_class(
            extra_opts={'use_wombat': True, 'use_preserve_worker': False}
        )

    def test_include_wombat_not_preservation_worker(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # content
        assert 'Example Domain' in res.text

        # yes head insert
        assert 'WB Insert' in res.text

        # no wombat.js, yes wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' in res.text
        assert 'wbinfo.wombat_mode = "w";' in res.text


class TestProxyIncludePreservationWorkerNotWombat(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyIncludePreservationWorkerNotWombat, cls).setup_class(
            extra_opts={'use_wombat': False, 'use_preserve_worker': True}
        )

    def test_include_preservation_worker_not_wombat(self, scheme):
        res = requests.get('{0}://example.com/'.format(scheme),
                           proxies=self.proxies,
                           verify=self.root_ca_file)

        # content
        assert 'Example Domain' in res.text

        # yes head insert
        assert 'WB Insert' in res.text

        # no wombat.js, yes wombatProxyMode.js
        assert 'wombat.js' not in res.text
        assert 'wombatProxyMode.js' in res.text
        assert 'wbinfo.wombat_mode = "p";' in res.text


class TestProxyPreservationWorkerEndPoints(BaseTestProxy):
    @classmethod
    def setup_class(cls):
        super(TestProxyPreservationWorkerEndPoints, cls).setup_class(
            extra_opts={'use_wombat': True, 'use_preserve_worker': True}
        )

    def test_proxy_root_route_options_request(self, scheme):
        expected_origin = '{0}://example.com'.format(scheme)
        res = requests.options('{0}://pywb.proxy/'.format(scheme),
                               headers=dict(Origin=expected_origin),
                               proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert res.headers.get('Access-Control-Allow-Origin') == expected_origin

    def test_proxy_fetch_options_request(self, scheme):
        expected_origin = '{0}://example.com'.format(scheme)
        res = requests.options('{0}://pywb.proxy/proxy-fetch/{1}'.format(scheme, expected_origin),
                               headers=dict(Origin=expected_origin),
                               proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert res.headers.get('Access-Control-Allow-Origin') == expected_origin

    def test_proxy_fetch(self, scheme):
        expected_origin = '{0}://example.com'.format(scheme)
        res = requests.get('{0}://pywb.proxy/proxy-fetch/{1}'.format(scheme, expected_origin),
                           headers=dict(Origin='{0}://example.com'.format(scheme)),
                           proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert 'Example Domain' in res.text
        assert res.headers.get('Access-Control-Allow-Origin') == expected_origin

        res = requests.get('{0}://pywb.proxy/proxy-fetch/{1}'.format(scheme, expected_origin),
                           proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert 'Example Domain' in res.text
        assert res.headers.get('Access-Control-Allow-Origin') == '*'

    def test_proxy_worker_options_request(self, scheme):
        expected_origin = '{0}://example.com'.format(scheme)
        res = requests.options('{0}://pywb.proxy/proxy-worker'.format(scheme),
                               headers=dict(Origin=expected_origin),
                               proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert res.headers.get('Access-Control-Allow-Origin') == expected_origin

    def test_proxy_worker_fetch(self, scheme):
        origin = '{0}://example.com'.format(scheme)
        res = requests.get('{0}://pywb.proxy/proxy-worker'.format(scheme),
                           headers=dict(Origin=origin),
                           proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert res.headers.get('Content-Type') == 'application/javascript'
        assert res.headers.get('Access-Control-Allow-Origin') == origin
        assert 'Preserver.prototype.safeResolve' in res.text

        res = requests.get('{0}://pywb.proxy/proxy-worker'.format(scheme),
                           proxies=self.proxies, verify=self.root_ca_file)

        assert res.ok
        assert res.headers.get('Content-Type') == 'application/javascript'
        assert res.headers.get('Access-Control-Allow-Origin') == '*'
        assert 'Preserver.prototype.safeResolve' in res.text
