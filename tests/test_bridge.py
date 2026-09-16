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
import types
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


class RecordingListener:
    """Bound Unix listener that records the single exchange it accepts.

    Fixture support for MemoryPathBindingTests. Each listener names itself in its reply and keeps
    the (st_dev, st_ino) identity of the socket file it is bound to, so a test can name the object
    a connect actually reached rather than the pathname it was asked for.
    """

    def __init__(self, path, reply, timeout=20.0):
        self.path = Path(path)
        self.reply = reply
        self.accepted = False
        self.closing = False
        self.payload = None
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.path))
        self.path.chmod(0o600)
        self.socket.listen(4)
        self.socket.settimeout(timeout)
        metadata = self.path.lstat()
        self.identity = (metadata.st_dev, metadata.st_ino)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        try:
            connection, _ = self.socket.accept()
        except OSError:
            return
        with connection:
            if self.closing:
                return
            self.accepted = True
            connection.settimeout(10)
            data = bytearray()
            try:
                while chunk := connection.recv(65536):
                    data.extend(chunk)
                self.payload = bytes(data)
                connection.sendall(self.reply)
            except OSError:
                self.payload = bytes(data)

    def close(self):
        self.closing = True
        if self.thread.is_alive():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as waker:
                    waker.settimeout(2)
                    waker.connect(str(self.path))
            except OSError:
                pass
        self.thread.join(timeout=10)
        self.socket.close()


class MemoryPathBindingTests(unittest.TestCase):
    """Bug condition exploration for unbound credential and socket path validation.

    Property 1: Bug Condition - unsafe paths and unbound uses are refused before transmission.
    The fixture chain is <tmp>/outer/inner with inner at 0700 and owner-owned, which satisfies the
    current private_parent, so each case varies only the ancestor above it or the binding between a
    check and its use. Every test encodes the behaviour the fix must deliver, so all six are
    expected to FAIL against the unfixed client; those failures are the counterexamples.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.10**
    """

    token = 'hypm1_' + 'ab' * 32
    decoy_token = 'hypm1_' + 'cd' * 32

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hpb-')
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.outer = self.root / 'outer'
        self.inner = self.outer / 'inner'
        self.inner.mkdir(parents=True)
        self.outer.chmod(0o755)
        self.inner.chmod(0o700)
        self.safe = self.root / 'safe'
        self.safe.mkdir()
        self.safe.chmod(0o700)
        self.decoy = self.root / 'decoy'
        self.decoy.mkdir()
        self.decoy.chmod(0o700)
        self.preserved = self.outer / 'preserved'
        self.config = self.inner / 'client.json'
        self.endpoint = self.inner / 'memory.sock'
        self.safe_config = self.safe / 'client.json'
        self.safe_endpoint = self.safe / 'memory.sock'
        self.redirected = False
        self.identity_at_check = None
        self.identity_at_use = None
        self.listeners = []
        self.environment = None

    def tearDown(self):
        for listener in self.listeners:
            listener.close()
        if self.environment is not None:
            self.environment.stop()
        self.outer.chmod(0o700)
        self.temporary.cleanup()

    def configure(self, path):
        self.environment = patch.dict(os.environ, {'HYPHAE_MEMORY_PANEL_CONFIG': str(path)})
        self.environment.start()

    def credential(self, path, endpoint, token):
        path.write_text(json.dumps({'schema': bridge.CONNECTION_SCHEMA, 'endpoint': str(endpoint),
                                    'token': token}))
        path.chmod(0o600)
        return path

    def listen(self, path, label):
        reply = json.dumps({'schema': bridge.SCHEMA, 'id': 1, 'ok': True,
                            'result': {'listener': label}}).encode('ascii')
        listener = RecordingListener(path, reply)
        self.listeners.append(listener)
        return listener

    def request(self, operation='status'):
        return {'schema': bridge.SCHEMA, 'id': 1, 'operation': operation, 'arguments': {}}

    def identity(self, path):
        metadata = os.stat(path)
        return (metadata.st_dev, metadata.st_ino)

    def redirect(self):
        """Substitute the validated directory, which a writable ancestor permits.

        Driven from a patched seam rather than a racing thread so the counterexample is
        deterministic. Idempotent: only the first check-to-use window redirects.
        """
        if self.redirected:
            return
        self.identity_at_check = self.identity(self.inner)
        self.inner.rename(self.preserved)
        self.inner.symlink_to(self.decoy)
        self.identity_at_use = self.identity(self.inner)
        self.redirected = True

    def redirecting_open(self, name):
        """Redirect the parent directory immediately before the named final component is opened."""
        opened = os.open

        def opener(target, *arguments, **keywords):
            if not isinstance(target, int) and os.path.basename(os.fsdecode(target)) == name:
                self.redirect()
            return opened(target, *arguments, **keywords)

        return patch.object(bridge.os, 'open', opener)

    def socket_module(self, *, factory=None, peercred=True):
        """Copy of the socket module carrying only what execute touches.

        unittest.mock cannot delete an attribute, so an interpreter without SO_PEERCRED is
        modelled by omitting it from this copy.
        """
        names = ['AF_UNIX', 'SOCK_STREAM', 'SOL_SOCKET', 'SHUT_WR']
        if peercred:
            names.append('SO_PEERCRED')
        values = {name: getattr(socket, name) for name in names}
        values['socket'] = socket.socket if factory is None else factory
        return types.SimpleNamespace(**values)

    def redirecting_socket(self):
        """Socket module copy whose client socket redirects the endpoint's parent before connect."""
        test = self

        class RedirectingSocket(socket.socket):
            def connect(self, address):
                test.redirect()
                return super().connect(address)

        return self.socket_module(factory=RedirectingSocket)

    def assert_refused(self, result, submission, listener=None):
        self.assertEqual(result.get('error', {}).get('code'), 'unauthorized',
                         f'expected an unauthorized refusal, observed {result}')
        self.assertIs(result['ok'], False)
        self.assertIs(submission['possibly_sent'], False,
                      'a refused request must stay definitely unsent')
        if listener is not None:
            self.assertIsNone(listener.payload,
                              'no credential byte may reach a listener on a refused request')

    def test_world_writable_credential_ancestor_is_refused_before_transmission(self):
        """Case 1: outer is 0777 non-sticky above the credential's private parent."""
        self.credential(self.config, self.safe_endpoint, self.token)
        listener = self.listen(self.safe_endpoint, 'safe')
        self.outer.chmod(0o777)
        self.configure(self.config)
        submission = {}
        result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_world_writable_endpoint_ancestor_is_refused_before_transmission(self):
        """Case 2: outer is 0777 non-sticky above the endpoint's private parent."""
        self.credential(self.safe_config, self.endpoint, self.token)
        listener = self.listen(self.endpoint, 'inner')
        self.outer.chmod(0o777)
        self.configure(self.safe_config)
        submission = {}
        result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_group_writable_ancestor_is_refused_before_transmission(self):
        """Case 3: outer is 0770 non-sticky above both private parents."""
        self.credential(self.config, self.endpoint, self.token)
        listener = self.listen(self.endpoint, 'inner')
        self.outer.chmod(0o770)
        self.configure(self.config)
        submission = {}
        result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_credential_redirected_after_its_check_is_never_transmitted(self):
        """Case 4: inner becomes a symlink to a decoy between private_parent and the open."""
        self.credential(self.config, self.safe_endpoint, self.token)
        self.credential(self.decoy / 'client.json', self.safe_endpoint, self.decoy_token)
        listener = self.listen(self.safe_endpoint, 'safe')
        self.configure(self.config)
        submission = {}
        with self.redirecting_open('client.json'):
            result = bridge.execute(self.request(), submission=submission)
        self.assertTrue(self.redirected, 'the redirection seam never fired')
        detail = (f'parent checked {self.identity_at_check}, parent reached at use '
                  f'{self.identity_at_use}')
        self.assertNotIn(self.decoy_token.encode('ascii'), listener.payload or b'',
                         f'the decoy credential was transmitted: {detail}')
        self.assertNotIn(self.decoy_token, json.dumps(result),
                         f'the decoy credential reached the response: {detail}')

    def test_endpoint_redirected_after_its_check_is_never_connected_to(self):
        """Case 5: inner becomes a symlink to a decoy between the endpoint lstat and connect."""
        self.credential(self.config, self.endpoint, self.token)
        validated = self.listen(self.endpoint, 'inner')
        decoy = self.listen(self.decoy / 'memory.sock', 'decoy')
        self.configure(self.config)
        submission = {}
        with patch.object(bridge, 'socket', self.redirecting_socket()):
            result = bridge.execute(self.request(), submission=submission)
        self.assertTrue(self.redirected, 'the redirection seam never fired')
        reached = next((entry.identity for entry in (validated, decoy) if entry.accepted), None)
        detail = (f'endpoint checked {validated.identity}, endpoint reached at use {reached}, '
                  f'parent checked {self.identity_at_check}, parent reached at use '
                  f'{self.identity_at_use}, response {result}')
        self.assertIsNone(decoy.payload, f'the substituted listener received a request: {detail}')
        self.assertFalse(decoy.accepted, f'the substituted listener was connected to: {detail}')
        self.assertEqual(reached, validated.identity,
                         f'the socket used is not the socket checked: {detail}')

    def test_absent_peer_credential_support_is_refused_before_transmission(self):
        """Case 6: SO_PEERCRED is unavailable, so no peer identity check can be performed."""
        self.credential(self.config, self.endpoint, self.token)
        listener = self.listen(self.endpoint, 'inner')
        self.configure(self.config)
        submission = {}
        with patch.object(bridge, 'socket', self.socket_module(peercred=False)):
            result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_foreign_owned_ancestor_metadata_is_refused_before_transmission(self):
        """Every opened component must be owned by this user or root."""
        self.credential(self.config, self.endpoint, self.token)
        listener = self.listen(self.endpoint, 'inner')
        self.configure(self.config)
        target = self.identity(self.outer)
        real_metadata = bridge.component_metadata

        def foreign_metadata(descriptor):
            metadata = real_metadata(descriptor)
            if (metadata.st_dev, metadata.st_ino) == target:
                fields = list(metadata)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return metadata

        submission = {}
        with patch.object(bridge, 'component_metadata', side_effect=foreign_metadata):
            result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_preexisting_symlinked_ancestor_is_refused_before_transmission(self):
        """O_NOFOLLOW applies to every directory component, not only the final object."""
        self.credential(self.config, self.endpoint, self.token)
        listener = self.listen(self.endpoint, 'inner')
        self.inner.rename(self.preserved)
        self.inner.symlink_to(self.preserved)
        self.configure(self.config)
        submission = {}
        result = bridge.execute(self.request(), submission=submission)
        self.assert_refused(result, submission, listener)

    def test_endpoint_binding_pins_the_parent_and_releases_idempotently(self):
        """The /proc address names the held directory and release closes it exactly once."""
        listener = self.listen(self.safe_endpoint, 'safe')
        connection = {'endpoint': str(self.safe_endpoint)}
        binding = {}
        before = len(os.listdir('/proc/self/fd'))
        returned = bridge.validate_endpoint(connection, binding=binding)
        self.assertIs(returned, binding)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before + 1)
        self.assertTrue(connection['endpoint'].startswith(
            f"/proc/self/fd/{binding['parent']}/"))
        opened = os.fstat(binding['parent'])
        expected = self.safe.stat()
        self.assertEqual((opened.st_dev, opened.st_ino), (expected.st_dev, expected.st_ino))
        bridge.release_binding(binding)
        bridge.release_binding(binding)
        self.assertEqual(binding, {})
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        self.assertIsNone(listener.payload)

    def test_execute_releases_the_binding_on_success_and_before_connect(self):
        """No held path descriptor survives either an exchange or a request-size rejection."""
        self.credential(self.safe_config, self.safe_endpoint, self.token)
        listener = self.listen(self.safe_endpoint, 'safe')
        self.configure(self.safe_config)
        before = len(os.listdir('/proc/self/fd'))
        self.assertTrue(bridge.execute(self.request())['ok'])
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        with patch.object(bridge, 'MAX_REQUEST', 64):
            result = bridge.execute(self.request('store'))
        self.assertEqual(result['error']['code'], 'limit_exceeded')
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        self.assertIn(self.token.encode('ascii'), listener.payload or b'')


# Recorded by running the MemoryPathPreservationTests case_* fixtures below against the unfixed
# scripts/bridge.py at commit ae68f24 and printing the observation each one produced. Every value is
# measured, and two consecutive recording runs were byte-identical. This is the baseline the fix must
# not move: task 3.7 re-runs the same tests against the fixed client and compares against these.
PRESERVED_RESULTS = {
    'sticky': {
        'ok': True, 'code': None, 'result': {'listener': 'sticky'},
        'mutating': False, 'possibly_sent': True, 'token_in_response': False,
        'received': 'sticky', 'token_transmitted': True,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o600', 'endpoint': '0o600'}},
    'config-home': {
        'ok': True, 'code': None, 'result': {'listener': 'config-home'},
        'mutating': False, 'possibly_sent': True, 'token_in_response': False,
        'received': 'config-home', 'token_transmitted': True,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o600', 'endpoint': '0o600'}},
    'search-only': {
        'ok': True, 'code': None, 'result': {'listener': 'search-only'},
        'mutating': False, 'possibly_sent': True, 'token_in_response': False,
        'received': 'search-only', 'token_transmitted': True,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o600', 'endpoint': '0o600'}},
    'missing-connection': {
        'ok': False, 'code': 'connection_required', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': None, 'endpoint': 'socket'},
        'permissions': {'credential': None, 'endpoint': '0o600'}},
    'missing-endpoint': {
        'ok': False, 'code': 'unavailable', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': None},
        'permissions': {'credential': '0o600', 'endpoint': None}},
    'generic-token': {
        'ok': False, 'code': 'unauthorized', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o600', 'endpoint': '0o600'}},
    'group-readable': {
        'ok': False, 'code': 'unauthorized', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o640', 'endpoint': '0o600'}},
    'symlinked': {
        'ok': False, 'code': 'unauthorized', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'preserved': True, 'endpoint': True},
        'kinds': {'credential': 'link', 'preserved': 'file', 'endpoint': 'socket'},
        'permissions': {'credential': '0o777', 'preserved': '0o600', 'endpoint': '0o600'}},
    'non-socket': {
        'ok': False, 'code': 'unauthorized', 'result': None,
        'mutating': False, 'possibly_sent': False, 'token_in_response': False,
        'received': None, 'token_transmitted': False,
        'unchanged': {'credential': True, 'endpoint': True},
        'kinds': {'credential': 'file', 'endpoint': 'file'},
        'permissions': {'credential': '0o600', 'endpoint': '0o600'}},
}

# Recorded the same way for the mutating 'store' operation, as
# (code, mutating, possibly_sent, token_transmitted).
PRESERVED_SUBMISSION = {
    'missing-connection': ('connection_required', True, False, False),
    'missing-endpoint': ('unavailable', True, False, False),
    'generic-token': ('unauthorized', True, False, False),
    'group-readable': ('unauthorized', True, False, False),
    'symlinked': ('unauthorized', True, False, False),
    'non-socket': ('unauthorized', True, False, False),
    'connect-timeout': ('timeout', True, False, False),
    'foreign-peer': ('unauthorized', True, False, False),
    'sticky': (None, True, True, True),
}


class MemoryPathPreservationTests(unittest.TestCase):
    """Preservation baseline for owner-controlled credential and socket paths.

    Property 2: Preservation - identical behaviour on owner-controlled paths.

    Observation-first. Every value in PRESERVED_RESULTS and PRESERVED_SUBMISSION was produced by
    running the case_* fixtures below against the unfixed client and printing what it actually
    returned; nothing here is assumed behaviour. The guard cases come first because they are what a
    naive policy breaks: real root-owned sticky 1777 /tmp as an ancestor component, a 0755
    owner-owned ~/.config-shaped chain, and a 0311 search-only intermediate the invoking user cannot
    read. Task 3.7 re-runs these same tests against the fixed client, so any value that moves is a
    preservation regression.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.7**
    """

    token = 'hypm1_' + 'ab' * 32
    generic_token = 'hyp1_' + 'ab' * 32
    formats = {0o100000: 'file', 0o140000: 'socket', 0o120000: 'link', 0o040000: 'directory'}

    def setUp(self):
        # dir='/tmp' so the real root-owned sticky 1777 /tmp is an ancestor component of every
        # fixture path, rather than a private subdirectory standing in for it.
        self.temporary = tempfile.TemporaryDirectory(prefix='hpp-', dir='/tmp')
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.listeners = []
        self.restore = []
        self.environment = None

    def tearDown(self):
        for _, listener in self.listeners:
            listener.close()
        if self.environment is not None:
            self.environment.stop()
        for path in self.restore:
            path.chmod(0o700)
        self.temporary.cleanup()

    def directory(self, *names, mode=0o700):
        """Create a nested fixture directory, chmod its final component and record it for restore."""
        path = self.root
        for name in names:
            path = path / name
            if not path.exists():
                path.mkdir()
                self.restore.append(path)
        path.chmod(mode)
        return path

    def credential(self, path, endpoint, token):
        path.write_text(json.dumps({'schema': bridge.CONNECTION_SCHEMA, 'endpoint': str(endpoint),
                                    'token': token}))
        path.chmod(0o600)
        return path

    def listen(self, path, label):
        reply = json.dumps({'schema': bridge.SCHEMA, 'id': 1, 'ok': True,
                            'result': {'listener': label}}).encode('ascii')
        listener = RecordingListener(path, reply)
        self.listeners.append((label, listener))
        return listener

    def configure(self, *, config=None, config_home=None):
        if self.environment is not None:
            self.environment.stop()
        values = {}
        if config is not None:
            values['HYPHAE_MEMORY_PANEL_CONFIG'] = str(config)
        if config_home is not None:
            values['XDG_CONFIG_HOME'] = str(config_home)
        self.environment = patch.dict(os.environ, values)
        self.environment.start()
        if config is None:
            os.environ.pop('HYPHAE_MEMORY_PANEL_CONFIG', None)

    def request(self, operation):
        arguments = {'store': {'project': 'fixture', 'text': 'A short note.', 'kind': 'fact'}}
        return {'schema': bridge.SCHEMA, 'id': 1, 'operation': operation,
                'arguments': arguments.get(operation, {})}

    def socket_copy(self, factory):
        """Copy of the socket module carrying only what execute touches, with a chosen factory."""
        names = ('AF_UNIX', 'SOCK_STREAM', 'SOL_SOCKET', 'SHUT_WR', 'SO_PEERCRED')
        values = {name: getattr(socket, name) for name in names}
        values['socket'] = factory
        return types.SimpleNamespace(**values)

    def timing_out_socket(self):
        """Client socket whose connect reports the kernel deadline, leaving nothing transmitted."""
        class TimingOutSocket(socket.socket):
            def connect(self, address):
                raise TimeoutError('Private fixture detail')

        return self.socket_copy(TimingOutSocket)

    def foreign_peer_socket(self, uid):
        """Client socket reporting a peer uid other than the invoking user's, per clause 3.5.

        A listener owned by a second account cannot be created without privilege, so only the one
        SO_PEERCRED read is substituted; the connect, the socket and the paths stay real.
        """
        class ForeignPeerSocket(socket.socket):
            def getsockopt(self, level, option, *arguments):
                if level == socket.SOL_SOCKET and option == socket.SO_PEERCRED:
                    return struct.pack('3i', 123, uid, 0)
                return super().getsockopt(level, option, *arguments)

        return self.socket_copy(ForeignPeerSocket)

    def state(self, path):
        """Deterministic on-disk facts for one path: kind, permission bits, identity and content."""
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return None
        kind = self.formats.get(metadata.st_mode & 0o170000, 'other')
        return {'kind': kind, 'permissions': metadata.st_mode & 0o7777,
                'identity': (metadata.st_dev, metadata.st_ino),
                'content': Path(path).read_bytes() if kind == 'file' else None}

    def settle(self):
        """Close every fixture listener so each recorded payload and on-disk state is final."""
        for _, listener in self.listeners:
            listener.close()

    def observe(self, *, paths, operation='status', socket_module=None):
        """Run the client once and return only deterministic, comparable facts about the outcome."""
        before = {label: self.state(path) for label, path in paths.items()}
        submission = {}
        request = self.request(operation)
        if socket_module is None:
            result = bridge.execute(request, submission=submission)
        else:
            with patch.object(bridge, 'socket', socket_module):
                result = bridge.execute(request, submission=submission)
        self.settle()
        after = {label: self.state(path) for label, path in paths.items()}
        encoded = self.token.encode('ascii')
        return {
            'ok': result['ok'],
            'code': result.get('error', {}).get('code'),
            'result': result.get('result'),
            'mutating': submission['mutating'],
            'possibly_sent': submission['possibly_sent'],
            'token_in_response': self.token in json.dumps(result),
            # Only bytes are recorded, not whether accept() returned: a rejection after connect
            # races the listener's accept, so accepted is not a reproducible baseline value.
            'received': next((label for label, entry in self.listeners if entry.payload), None),
            'token_transmitted': any(encoded in (entry.payload or b'')
                                     for _, entry in self.listeners),
            'unchanged': {label: before[label] == after[label] for label in paths},
            'kinds': {label: None if after[label] is None else after[label]['kind']
                      for label in paths},
            'permissions': {label: None if after[label] is None else oct(after[label]['permissions'])
                            for label in paths},
        }

    def submission_state(self, observed):
        return (observed['code'], observed['mutating'], observed['possibly_sent'],
                observed['token_transmitted'])

    def case_sticky_root(self, *, operation='status'):
        """Guard case: real root-owned sticky 1777 /tmp is an ancestor of the fixture chain."""
        directory = self.directory('sticky')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'sticky')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_config_home(self, *, operation='status'):
        """Guard case: a 0755 owner-owned ~/.config-shaped chain under a 0700 immediate parent."""
        config_home = self.directory('xdg', mode=0o755)
        panel = self.directory('xdg', 'hyphae-panel')
        config = panel / 'client.json'
        endpoint = panel / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'config-home')
        self.configure(config_home=config_home)
        self.assertEqual(bridge.connection_path(), config)
        self.assertEqual(config_home.lstat().st_mode & 0o7777, 0o755)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_search_only(self, *, operation='status'):
        """Guard case: a 0711 intermediate and a 0311 intermediate the invoking user cannot read."""
        wide = self.directory('wide')
        search = self.directory('wide', 'search')
        inner = self.directory('wide', 'search', 'inner')
        config = inner / 'client.json'
        endpoint = inner / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'search-only')
        search.chmod(0o311)
        wide.chmod(0o711)
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_missing_connection(self, *, operation='status'):
        """Clause 3.2: the connection file is absent and none may be created."""
        directory = self.directory('missing-connection')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'missing-connection')
        config.unlink()
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_missing_endpoint(self, *, operation='status'):
        """Clause 3.3: the service is stopped, so the endpoint never exists."""
        directory = self.directory('missing-endpoint')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_generic_token(self, *, operation='status'):
        """Clause 3.4: a generic rather than dedicated credential."""
        directory = self.directory('generic-token')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.generic_token)
        self.listen(endpoint, 'generic-token')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_group_readable(self, *, operation='status'):
        """Clause 3.4: a group-readable credential file, preserved with its mode."""
        directory = self.directory('group-readable')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        config.chmod(0o640)
        self.listen(endpoint, 'group-readable')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_symlinked_credential(self, *, operation='status'):
        """Clause 3.4: the connection file is a symbolic link and its target stays intact."""
        directory = self.directory('symlinked')
        preserved = directory / 'preserved.json'
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(preserved, endpoint, self.token)
        config.symlink_to(preserved)
        self.listen(endpoint, 'symlinked')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'preserved': preserved,
                                   'endpoint': endpoint}, operation=operation)

    def case_non_socket_endpoint(self, *, operation='status'):
        """Clause 3.4: the endpoint is a regular file, preserved byte for byte."""
        directory = self.directory('non-socket')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        endpoint.write_text('preserve this file')
        endpoint.chmod(0o600)
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation)

    def case_connect_timeout(self, *, operation='status'):
        """Clause 3.7: the connect deadline expires, so nothing is transmitted."""
        directory = self.directory('connect-timeout')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'connect-timeout')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation,
                            socket_module=self.timing_out_socket())

    def case_foreign_peer(self, *, operation='status'):
        """Clause 3.5: the listener's peer uid differs from the invoking user's."""
        directory = self.directory('foreign-peer')
        config = directory / 'client.json'
        endpoint = directory / 'memory.sock'
        self.credential(config, endpoint, self.token)
        self.listen(endpoint, 'foreign-peer')
        self.configure(config=config)
        return self.observe(paths={'credential': config, 'endpoint': endpoint}, operation=operation,
                            socket_module=self.foreign_peer_socket(os.getuid() + 1))

    def test_sticky_root_ancestor_keeps_the_recorded_success(self):
        """Guard: a blanket world-writable rejection would break the real /tmp every fixture uses."""
        metadata = os.lstat('/tmp')
        self.assertEqual(self.root.parent, Path('/tmp'),
                         'the guard needs real /tmp as an ancestor component')
        self.assertEqual(metadata.st_uid, 0, 'the /tmp guard needs a root-owned ancestor')
        self.assertEqual(metadata.st_mode & 0o777, 0o777,
                         'the /tmp guard needs a world-writable ancestor')
        self.assertTrue(metadata.st_mode & 0o1000, 'the /tmp guard needs the sticky bit')
        self.assertEqual(self.case_sticky_root(), PRESERVED_RESULTS['sticky'])

    def test_config_home_chain_keeps_the_recorded_success(self):
        """Guard: an over-strict mode & 0o077 ancestor rule would break a 0755 ~/.config."""
        self.assertEqual(self.case_config_home(), PRESERVED_RESULTS['config-home'])

    def test_search_only_intermediate_keeps_the_recorded_success(self):
        """Guard: this is the case that forces O_PATH over O_RDONLY in the component walk."""
        self.assertEqual(self.case_search_only(), PRESERVED_RESULTS['search-only'])
        wide = self.root / 'wide'
        search = wide / 'search'
        self.assertEqual(wide.lstat().st_mode & 0o7777, 0o711)
        self.assertEqual(search.lstat().st_mode & 0o7777, 0o311)
        self.assertTrue(hasattr(os, 'O_PATH'), 'the component walk needs O_PATH on Linux')
        if os.getuid() != 0:
            # Root bypasses the read permission, so only an unprivileged run can prove the point.
            with self.assertRaises(PermissionError,
                                   msg='a search-only component must deny the owner a read open'):
                os.close(os.open(search, os.O_RDONLY | os.O_DIRECTORY))
        os.close(os.open(search, os.O_PATH | os.O_DIRECTORY))

    def test_recorded_rejections_keep_their_codes_and_leave_the_fixtures_unchanged(self):
        """Clauses 3.2, 3.3, 3.4: the existing mapping, with the credential and endpoint intact."""
        for name in ('missing-connection', 'missing-endpoint', 'generic-token', 'group-readable',
                     'symlinked', 'non-socket'):
            with self.subTest(case=name):
                self.assertEqual(self.case(name), PRESERVED_RESULTS[name])

    def test_recorded_submission_state_survives_every_rejection(self):
        """Clauses 3.5, 3.7: possibly_sent stays false until a connect and peer check succeed."""
        for name in ('missing-connection', 'missing-endpoint', 'generic-token', 'group-readable',
                     'symlinked', 'non-socket', 'connect-timeout', 'foreign-peer', 'sticky'):
            with self.subTest(case=name):
                observed = self.case(name, operation='store')
                self.assertEqual(self.submission_state(observed), PRESERVED_SUBMISSION[name])

    def case(self, name, *, operation='status'):
        cases = {'sticky': self.case_sticky_root,
                 'config-home': self.case_config_home,
                 'search-only': self.case_search_only,
                 'missing-connection': self.case_missing_connection,
                 'missing-endpoint': self.case_missing_endpoint,
                 'generic-token': self.case_generic_token,
                 'group-readable': self.case_group_readable,
                 'symlinked': self.case_symlinked_credential,
                 'non-socket': self.case_non_socket_endpoint,
                 'connect-timeout': self.case_connect_timeout,
                 'foreign-peer': self.case_foreign_peer}
        return cases[name](operation=operation)


if __name__ == '__main__':
    unittest.main()
