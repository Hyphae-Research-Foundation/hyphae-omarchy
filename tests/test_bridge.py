# SPDX-License-Identifier: Apache-2.0
"""Exercise the real Unix client framing, credential handling and failure paths."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/bridge.py'
spec = importlib.util.spec_from_file_location('memory_client', SOURCE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class MemoryClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hmc-')
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.endpoint = self.root / 'memory.sock'
        self.config = self.root / 'client.json'
        self.token = 'hypm1_' + 'ab' * 32
        self.config.write_text(json.dumps({'schema':bridge.CONNECTION_SCHEMA, 'endpoint':str(self.endpoint), 'token':self.token}))
        self.config.chmod(0o600)
        self.environment = patch.dict(os.environ, {'HYPHAE_MEMORY_PANEL_CONFIG':str(self.config)})
        self.environment.start()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.endpoint))
        self.endpoint.chmod(0o600)
        self.listener.listen(4)
        self.received = []
        self.threads = []

    def tearDown(self):
        self.listener.close()
        for worker in self.threads:
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        self.environment.stop()
        self.temporary.cleanup()

    def server(self, reply):
        def respond():
            connection, _ = self.listener.accept()
            with connection:
                data = bytearray()
                while chunk := connection.recv(65536):
                    data.extend(chunk)
                self.received.append(json.loads(data))
                encoded = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
                try:
                    connection.sendall(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        worker = threading.Thread(target=respond, daemon=True)
        self.threads.append(worker)
        worker.start()

    def request(self, operation='status', arguments=None):
        return {'schema':bridge.SCHEMA, 'id':1, 'operation':operation, 'arguments':arguments or {}}

    def success(self, result=None):
        return {'schema':bridge.SCHEMA, 'id':1, 'ok':True, 'result':result or {'connected':True}}

    def test_authenticated_unix_exchange_exposes_only_result_to_ui(self):
        self.server(self.success())
        result = bridge.execute(self.request())
        self.assertTrue(result['ok'])
        self.threads[-1].join(timeout=2)
        self.assertEqual(self.received[0]['token'], self.token)
        self.assertEqual(self.received[0]['operation'], 'status')
        self.assertNotIn(self.token, json.dumps(result))

    def test_operator_requests_never_reach_socket(self):
        for operation in ('configure', 'disconnect', 'setup', 'service_start', 'remove', 'restore', 'install', 'semantic', 'proxy'):
            with self.subTest(operation=operation):
                self.assertFalse(bridge.execute(self.request(operation))['ok'])
        self.listener.settimeout(.05)
        with self.assertRaises(TimeoutError):
            self.listener.accept()

    def test_generic_or_reused_credentials_are_rejected(self):
        value = json.loads(self.config.read_text())
        value['token'] = 'hyp1_' + 'ab' * 32
        self.config.write_text(json.dumps(value))
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'unauthorized')

    def test_group_readable_credentials_are_preserved_and_rejected(self):
        self.config.chmod(0o640)
        before = self.config.read_bytes()
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'unauthorized')
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)

    def test_symlinked_connection_file_is_rejected(self):
        preserved = self.root / 'preserved.json'
        self.config.rename(preserved)
        self.config.symlink_to(preserved)
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'unauthorized')
        self.assertTrue(preserved.is_file())

    def test_stopped_service_is_unavailable_without_requiring_new_credentials(self):
        self.listener.close()
        self.endpoint.unlink()
        before = self.config.read_bytes()
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'unavailable')
        self.assertEqual(self.config.read_bytes(), before)

    def test_non_socket_endpoint_is_preserved(self):
        self.listener.close()
        self.endpoint.unlink()
        self.endpoint.write_text('preserve this file')
        self.endpoint.chmod(0o600)
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'unauthorized')
        self.assertEqual(self.endpoint.read_text(), 'preserve this file')

    def test_wrong_response_identity_is_rejected(self):
        for change in ({'schema':'hyphae-omarchy-control-v1'}, {'id':2}, {'id':True}):
            with self.subTest(change=change):
                self.server({**self.success(), **change})
                self.assertEqual(bridge.execute(self.request())['error']['code'], 'protocol_error')

    def test_invalid_response_and_unexpected_fields_are_rejected(self):
        for value in (b'not JSON', b'[]', {**self.success(), 'token':self.token}):
            with self.subTest(value=type(value).__name__):
                self.server(value)
                self.assertEqual(bridge.execute(self.request())['error']['code'], 'protocol_error')

    def test_oversized_response_is_bounded(self):
        self.server(b' ' * (bridge.MAX_RESPONSE + 1))
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'limit_exceeded')

    def test_remote_errors_do_not_echo_credentials(self):
        self.server({'schema':bridge.SCHEMA,'id':1,'ok':False,'error':{'code':'unauthorized','message':self.token}})
        result = bridge.execute(self.request())
        self.assertEqual(result['error']['code'], 'unauthorized')
        self.assertNotIn(self.token, json.dumps(result))

    def test_busy_response_without_request_id_remains_correlated(self):
        self.server({'schema':bridge.SCHEMA,'id':None,'ok':False,'error':{'code':'busy','message':'busy'}})
        result = bridge.execute(self.request())
        self.assertEqual(result['id'], 1)
        self.assertEqual(result['error']['code'], 'busy')

    def test_missing_connection_is_reported_without_creating_files(self):
        self.config.unlink()
        self.assertEqual(bridge.execute(self.request())['error']['code'], 'connection_required')
        self.assertFalse(self.config.exists())

    def test_request_limit_and_unknown_fields_are_rejected(self):
        self.assertFalse(bridge.execute({**self.request(), 'command':'arbitrary'})['ok'])
        self.assertFalse(bridge.execute({**self.request(), 'id':True})['ok'])
        result = bridge.execute(self.request('store', {'text':'x' * bridge.MAX_REQUEST}))
        self.assertEqual(result['error']['code'], 'limit_exceeded')


if __name__ == '__main__':
    unittest.main()
