# SPDX-License-Identifier: Apache-2.0
"""Exercise the real Unix client framing, credential handling and failure paths."""
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, call, patch

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

    def test_isolated_bridge_subprocess_round_trips_unicode_without_stderr(self):
        expected = self.success({'memories': [{'id': '1', 'text': 'Café 東京 😀\nA second line.'}]})
        self.server(expected)
        result = subprocess.run(
            ['/usr/bin/python3', '-I', '-S', '-B', str(SOURCE)],
            input=json.dumps(self.request('list', {'project': 'fixture'})).encode('ascii'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.root,
            env={'HOME': str(self.root), 'LC_ALL': 'C.UTF-8',
                 'HYPHAE_MEMORY_PANEL_CONFIG': str(self.config)},
            timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b'')
        self.assertTrue(result.stdout.isascii())
        self.assertEqual(result.stdout.count(b'\n'), 1)
        self.assertTrue(result.stdout.endswith(b'\n'))
        self.assertLessEqual(len(result.stdout), bridge.MAX_STDOUT + 1)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertNotIn(self.token.encode('ascii'), result.stdout)
        self.threads[-1].join(timeout=2)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0]['operation'], 'list')

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


class MemoryOutputTests(unittest.TestCase):
    limit = 512

    def response(self, text):
        return {'schema': bridge.SCHEMA, 'id': 1, 'ok': True, 'result': {'text': text}}

    def encode(self, response, submission=None):
        output = MagicMock()
        with patch.object(bridge, 'MAX_STDOUT', self.limit), patch.object(bridge.sys, 'stdout', output):
            encoded = bridge.encode_response(response, submission=submission)
        self.assertEqual(output.mock_calls, [], 'Encoding must not write a partial response')
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded.isascii())
        self.assertEqual(encoded.count(b'\n'), 1)
        self.assertTrue(encoded.endswith(b'\n'))
        self.assertLessEqual(len(encoded), self.limit + 1)
        return encoded

    def test_compact_ascii_output_preserves_unicode_and_embedded_newlines(self):
        response = self.response('Café 東京 😀\nA second line.\t')
        encoded = self.encode(response)
        self.assertEqual(json.loads(encoded), response)
        self.assertNotIn(b'": ', encoded)
        self.assertNotIn(b', "', encoded)

    def test_output_allows_exact_body_limit_and_one_framing_newline(self):
        self.assertEqual(bridge.MAX_STDOUT, 2 * 1024 * 1024)
        empty_size = len(json.dumps(self.response(''), separators=(',', ':')).encode('ascii'))
        response = self.response('x' * (self.limit - empty_size))
        encoded = self.encode(response)
        self.assertEqual(len(encoded), self.limit + 1)
        self.assertEqual(json.loads(encoded), response)

    def test_one_byte_over_output_limit_returns_only_a_bounded_error(self):
        empty_size = len(json.dumps(self.response(''), separators=(',', ':')).encode('ascii'))
        response = self.response('x' * (self.limit - empty_size + 1))
        encoded = self.encode(response)
        self.assertEqual(json.loads(encoded), bridge.fail('limit_exceeded', 1))
        self.assertNotIn(b'"result"', encoded)

    def test_unicode_expansion_overflow_uses_submission_state(self):
        response = self.response('é' * 96)
        self.assertLess(len(json.dumps(response, ensure_ascii=False).encode('utf-8')), self.limit)
        for submission, code in (
            (None, 'limit_exceeded'),
            ({'mutating': False, 'possibly_sent': False}, 'limit_exceeded'),
            ({'mutating': False, 'possibly_sent': True}, 'limit_exceeded'),
            ({'mutating': True, 'possibly_sent': False}, 'limit_exceeded'),
            ({'mutating': True, 'possibly_sent': True}, 'outcome_unknown'),
        ):
            with self.subTest(submission=submission):
                self.assertEqual(json.loads(self.encode(response, submission)), bridge.fail(code, 1))

    def test_unserializable_results_return_sanitized_bounded_errors(self):
        cycle = []
        cycle.append(cycle)
        for value in (float('nan'), float('inf'), object(), cycle):
            for possibly_sent in (False, True):
                with self.subTest(value=type(value).__name__, possibly_sent=possibly_sent):
                    submission = {'mutating': True, 'possibly_sent': possibly_sent}
                    code = 'outcome_unknown' if possibly_sent else 'protocol_error'
                    encoded = self.encode(self.response(value), submission)
                    self.assertEqual(json.loads(encoded), bridge.fail(code, 1))

    def test_main_writes_one_complete_response_after_output_overflow(self):
        for operation, code in (('status', 'limit_exceeded'), ('store', 'outcome_unknown')):
            with self.subTest(operation=operation):
                request = {'schema': bridge.SCHEMA, 'id': 1, 'operation': operation, 'arguments': {}}
                input_stream = MagicMock()
                input_stream.buffer = io.BytesIO(json.dumps(request).encode('ascii'))
                output_stream = MagicMock()

                def execute_fixture(request, *, submission):
                    submission.update(mutating=request['operation'] == 'store', possibly_sent=True)
                    return self.response('é' * 96)

                with (patch.object(bridge, 'MAX_STDOUT', self.limit),
                      patch.object(bridge, 'execute', side_effect=execute_fixture) as execute,
                      patch.object(bridge.sys, 'stdin', input_stream),
                      patch.object(bridge.sys, 'stdout', output_stream)):
                    bridge.main()
                execute.assert_called_once()
                output_stream.write.assert_not_called()
                output_stream.buffer.write.assert_called_once()
                encoded = output_stream.buffer.write.call_args.args[0]
                self.assertEqual(json.loads(encoded), bridge.fail(code, 1))
                self.assertTrue(encoded.isascii())
                self.assertEqual(encoded.count(b'\n'), 1)
                self.assertLessEqual(len(encoded), self.limit + 1)


class MemorySubmissionTests(unittest.TestCase):
    mutations = ('store', 'forget', 'backup')
    response_limit = 512

    def request(self, operation):
        arguments = {
            'store': {'project': 'fixture', 'text': 'A short note.', 'kind': 'fact'},
            'forget': {'project': 'fixture', 'id': '123'},
        }.get(operation, {})
        return {'schema': bridge.SCHEMA, 'id': 1, 'operation': operation, 'arguments': arguments}

    def stream(self):
        stream = MagicMock(spec=socket.socket)
        stream.__enter__.return_value = stream
        stream.__exit__.return_value = False
        stream.getsockopt.return_value = struct.pack('3i', 123, os.getuid(), 0)
        return stream

    def remote_error(self, code, request_id=1):
        return json.dumps({'schema': bridge.SCHEMA, 'id': request_id, 'ok': False,
                           'error': {'code': code, 'message': 'Private fixture detail'}}).encode('ascii')

    def execute(self, operation, stream, *, submission=None, clock=None):
        submission = {} if submission is None else submission
        connection = {'endpoint': '/unused/memory.sock', 'token': 'hypm1_' + 'ab' * 32}
        with (patch.object(bridge, 'load_connection', return_value=connection),
              patch.object(bridge, 'validate_endpoint'),
              patch.object(bridge.socket, 'socket', return_value=stream) as factory,
              patch.object(bridge.time, 'monotonic', side_effect=clock, return_value=100.0),
              patch.object(bridge, 'MAX_RESPONSE', self.response_limit)):
            response = bridge.execute(self.request(operation), submission=submission)
        return response, submission, factory

    def assert_one_submission(self, stream, factory):
        factory.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.connect.assert_called_once_with('/unused/memory.sock')
        stream.sendall.assert_called_once()

    def test_successful_mutations_send_once(self):
        for operation in self.mutations:
            with self.subTest(operation=operation):
                stream = self.stream()
                expected = {'schema': bridge.SCHEMA, 'id': 1, 'ok': True, 'result': {'message': 'Completed.'}}
                stream.recv.side_effect = [json.dumps(expected).encode('ascii'), b'']
                response, submission, factory = self.execute(operation, stream)
                self.assertEqual(response, expected)
                self.assertEqual(submission, {'mutating': True, 'possibly_sent': True})
                self.assert_one_submission(stream, factory)

    def test_ambiguous_mutation_acknowledgements_are_never_retried(self):
        cases = ('receive_timeout', 'receive_disconnect', 'closed_ack', 'invalid_ack', 'response_limit',
                 'boolean_error_id', 'float_error_id',
                 'remote_timeout', 'remote_unavailable', 'remote_protocol_error', 'remote_limit_exceeded',
                 'remote_unknown_error')
        for operation in self.mutations:
            for case in cases:
                with self.subTest(operation=operation, case=case):
                    stream = self.stream()
                    if case == 'receive_timeout':
                        stream.recv.side_effect = TimeoutError('Private fixture detail')
                    elif case == 'receive_disconnect':
                        stream.recv.side_effect = ConnectionResetError('Private fixture detail')
                    elif case == 'closed_ack':
                        stream.recv.side_effect = [b'']
                    elif case == 'invalid_ack':
                        stream.recv.side_effect = [b'{', b'']
                    elif case == 'response_limit':
                        stream.recv.side_effect = [b' ' * (self.response_limit + 1)]
                    elif case in ('boolean_error_id', 'float_error_id'):
                        request_id = True if case == 'boolean_error_id' else 1.0
                        stream.recv.side_effect = [self.remote_error('busy', request_id), b'']
                    else:
                        stream.recv.side_effect = [self.remote_error(case.removeprefix('remote_')), b'']
                    response, submission, factory = self.execute(operation, stream)
                    self.assertEqual(response, bridge.fail('outcome_unknown', 1))
                    self.assertEqual(submission, {'mutating': True, 'possibly_sent': True})
                    self.assert_one_submission(stream, factory)

    def test_send_failure_marks_mutation_possible_before_sendall(self):
        for operation in self.mutations:
            for exception in (TimeoutError, BrokenPipeError):
                with self.subTest(operation=operation, exception=exception.__name__):
                    stream = self.stream()
                    submission = {}

                    def interrupted_send(payload):
                        self.assertEqual(submission, {'mutating': True, 'possibly_sent': True})
                        self.assertEqual(json.loads(payload)['operation'], operation)
                        raise exception('Private fixture detail')

                    stream.sendall.side_effect = interrupted_send
                    response, _, factory = self.execute(operation, stream, submission=submission)
                    self.assertEqual(response, bridge.fail('outcome_unknown', 1))
                    self.assert_one_submission(stream, factory)
                    stream.recv.assert_not_called()

    def test_known_mutation_rejections_keep_their_error_codes(self):
        for operation in self.mutations:
            for code in ('unauthorized', 'busy', 'invalid_request'):
                with self.subTest(operation=operation, code=code):
                    stream = self.stream()
                    stream.recv.side_effect = [self.remote_error(code), b'']
                    response, _, factory = self.execute(operation, stream)
                    self.assertEqual(response, bridge.fail(code, 1))
                    self.assert_one_submission(stream, factory)

    def test_read_acknowledgement_failures_keep_their_error_codes(self):
        for code in ('timeout', 'unavailable', 'protocol_error', 'limit_exceeded'):
            with self.subTest(code=code):
                stream = self.stream()
                stream.recv.side_effect = [self.remote_error(code), b'']
                response, submission, factory = self.execute('status', stream)
                self.assertEqual(response, bridge.fail(code, 1))
                self.assertEqual(submission, {'mutating': False, 'possibly_sent': True})
                self.assert_one_submission(stream, factory)

    def test_connect_timeout_leaves_mutation_definitely_unsent(self):
        for operation in self.mutations:
            with self.subTest(operation=operation):
                stream = self.stream()
                stream.connect.side_effect = TimeoutError('Private fixture detail')
                response, submission, factory = self.execute(operation, stream)
                self.assertEqual(response, bridge.fail('timeout', 1))
                self.assertEqual(submission, {'mutating': True, 'possibly_sent': False})
                factory.assert_called_once()
                stream.connect.assert_called_once()
                stream.sendall.assert_not_called()

    def test_request_limit_leaves_mutation_unsent_without_opening_socket(self):
        for operation in self.mutations:
            with self.subTest(operation=operation), patch.object(bridge, 'MAX_REQUEST', 64):
                stream = self.stream()
                response, submission, factory = self.execute(operation, stream)
                self.assertEqual(response, bridge.fail('limit_exceeded', 1))
                self.assertEqual(submission, {'mutating': True, 'possibly_sent': False})
                factory.assert_not_called()
                stream.sendall.assert_not_called()

    def test_socket_deadline_is_135_seconds_and_does_not_restart_after_a_chunk(self):
        self.assertEqual(bridge.SOCKET_DEADLINE, 135)
        for operation, code in (('status', 'timeout'), ('store', 'outcome_unknown')):
            with self.subTest(operation=operation):
                stream = self.stream()
                stream.recv.side_effect = [b' ']
                response, _, factory = self.execute(operation, stream, clock=[100.0, 232.0, 235.0])
                self.assertEqual(response, bridge.fail(code, 1))
                self.assertEqual(stream.settimeout.call_args_list, [call(5), call(3.0)])
                stream.recv.assert_called_once()
                self.assert_one_submission(stream, factory)


if __name__ == '__main__':
    unittest.main()
