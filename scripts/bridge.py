#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded client for the independently provisioned Hyphae memory panel socket."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import time

sys.dont_write_bytecode = True
SCHEMA = 'hyphae-memory-panel-v1'
CONNECTION_SCHEMA = 'hyphae-memory-panel-connection-v1'
MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 1024 * 1024
MAX_STDOUT = 2 * 1024 * 1024
SOCKET_DEADLINE = 135
SOCKET_PATH_BYTES = 107
# Flags for every directory component of a validated path. O_PATH rather than O_RDONLY because a
# search-only directory such as 0311 is traversable today and must stay traversable, while
# O_RDONLY | O_DIRECTORY fails on it with EACCES. An O_PATH descriptor still supports os.fstat,
# serves as dir_fd for os.open and os.lstat, and resolves through /proc/self/fd, which is
# everything the walk and the binding need. The fallback keeps import working without O_PATH.
COMPONENT_FLAGS = getattr(os, 'O_PATH', os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW
OPERATIONS = frozenset(('status', 'projects', 'recall', 'list', 'store', 'forget', 'backups', 'backup'))
MUTATIONS = frozenset(('store', 'forget', 'backup'))
UNCERTAIN_ERRORS = frozenset(('timeout', 'unavailable', 'protocol_error', 'limit_exceeded'))
TOKEN = re.compile(r'hypm1_[0-9a-f]{64}\Z')
MESSAGES = {
    'connection_required': 'Set up the dedicated Hyphae memory connection independently first.',
    'unavailable': 'The memory service is unavailable. Check it in Hyphae.',
    'unauthorized': 'The service rejected the dedicated memory credential.',
    'invalid_request': 'The memory request is invalid.',
    'forbidden_operation': 'This connection grants only memory data operations.',
    'busy': 'The memory service is busy. Try again shortly.',
    'timeout': 'The memory service did not finish within its deadline.',
    'limit_exceeded': 'The memory request or response exceeds its size limit.',
    'protocol_error': 'The endpoint does not provide the expected memory interface.',
    'outcome_unknown': ('The result could not be confirmed. This change may have completed. '
                        'Check current memories or backups before submitting it again.'),
}


def fail(code: str, request_id=None) -> dict:
    if type(request_id) is not int or not 0 <= request_id < 2**64:
        request_id = None
    return {'schema': SCHEMA, 'id': request_id, 'ok': False,
            'error': {'code': code, 'message': MESSAGES.get(code, 'The memory operation could not be completed.')}}


def failure(code: str, request_id=None, submission: dict | None = None) -> dict:
    if (submission and submission.get('mutating') and submission.get('possibly_sent')
            and code in UNCERTAIN_ERRORS):
        code = 'outcome_unknown'
    return fail(code, request_id)


def encode_response(response: dict, *, submission: dict | None = None) -> bytes:
    """Return one bounded ASCII JSON response; never write a partial response.

    The service's UTF-8 wire limit does not bound ASCII JSON expansion. Check
    the final encoded body before adding the one allowed framing newline.
    """
    request_id = response.get('id') if isinstance(response, dict) else None
    code = 'limit_exceeded'
    try:
        encoded = json.dumps(response, ensure_ascii=True, separators=(',', ':'),
                             allow_nan=False).encode('ascii')
        if len(encoded) <= MAX_STDOUT:
            return encoded + b'\n'
    except (ValueError, TypeError, OverflowError, RecursionError):
        code = 'protocol_error'
    bounded = failure(code, request_id, submission)
    encoded = json.dumps(bounded, ensure_ascii=True, separators=(',', ':'),
                         allow_nan=False).encode('ascii')
    if len(encoded) > MAX_STDOUT:
        raise ValueError('Output budget is too small for a bounded error')
    return encoded + b'\n'


def connection_path() -> Path:
    override = os.environ.get('HYPHAE_MEMORY_PANEL_CONFIG')
    if override:
        return Path(override)
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return root / 'hyphae-panel/client.json'


def component_metadata(descriptor: int) -> os.stat_result:
    """Read one opened component's metadata. A seam a test substitutes to vary st_uid."""
    return os.fstat(descriptor)


def private_component(descriptor: int) -> None:
    """Require an opened component to be a directory owned by this user or root, not writable
    by group or other unless the sticky bit is set."""
    metadata = component_metadata(descriptor)
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in (os.getuid(), 0)
            or (metadata.st_mode & 0o022 and not metadata.st_mode & stat.S_ISVTX)):
        raise ValueError('Every path component must be an owner-controlled directory')


def open_parent(path: Path) -> tuple[int, str]:
    """Walk an absolute path component by component and return (parent descriptor, final name).

    Each directory component is opened relative to the descriptor of the one before it, so the
    returned descriptor is the only route to the final component and no pathname is re-walked
    between check and use. The final component is never opened here: it is the credential file or
    the socket, reached through the returned pair. At most two descriptors are held at once and
    every one of them is closed before this raises.
    """
    parts = path.parts
    if not path.is_absolute() or len(parts) < 2 or '..' in parts:
        raise ValueError('An absolute path without parent references is required')
    # parts[0] is the POSIX root, '/' or '//', which name the same inode. pathlib has already
    # dropped empty and '.' components, so the walk never sees them.
    descriptor = os.open(parts[0], COMPONENT_FLAGS)
    try:
        private_component(descriptor)
        for name in parts[1:-1]:
            successor = os.open(name, COMPONENT_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = successor
            private_component(descriptor)
        metadata = component_metadata(descriptor)
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError('A private owner-controlled directory is required')
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, parts[-1]


def release_binding(binding: dict) -> None:
    """Close and forget a held endpoint-parent descriptor, once."""
    descriptor = binding.pop('parent', None)
    if descriptor is not None:
        os.close(descriptor)


def load_connection() -> dict:
    # The walk validates every component and the returned descriptor is the only route to the
    # credential, so no pathname is re-walked between the check and the open. The parent descriptor
    # is released as soon as the open has used it; the fstat below then describes exactly the
    # object opened through it.
    parent, name = open_parent(connection_path())
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077 or metadata.st_size > 4096):
            raise ValueError('Invalid memory connection file')
        value = json.loads(stream.read(4097))
    if (not isinstance(value, dict) or set(value) != {'schema', 'endpoint', 'token'}
            or value['schema'] != CONNECTION_SCHEMA or not isinstance(value['token'], str)
            or TOKEN.fullmatch(value['token']) is None or not isinstance(value['endpoint'], str)):
        raise ValueError('A dedicated memory connection is required')
    return value


def validate_endpoint(connection: dict, *, binding: dict | None = None) -> dict:
    """Validate the endpoint relative to a held parent and replace its path with that binding.

    Linux has no connectat(2). /proc/self/fd resolves the final socket name through the held
    O_PATH directory descriptor, so replacing any component of the original pathname after this
    check cannot redirect connect(). The caller keeps the returned binding alive through connect.
    """
    binding = {} if binding is None else binding
    if binding:
        raise ValueError('An empty endpoint binding is required')
    endpoint = Path(connection['endpoint'])
    parent, name = open_parent(endpoint)
    try:
        metadata = os.lstat(name, dir_fd=parent)
        if (not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077):
            raise ValueError('Invalid memory socket')
        address = f'/proc/self/fd/{parent}/{name}'
        if len(os.fsencode(address)) > SOCKET_PATH_BYTES:
            raise ValueError('The bound memory socket path is too long')
        connection['endpoint'] = address
        binding['parent'] = parent
    except BaseException:
        os.close(parent)
        raise
    return binding


def execute(request: dict, *, submission: dict | None = None) -> dict:
    submission = {} if submission is None else submission
    submission.update(mutating=False, possibly_sent=False)
    request_id = request.get('id') if isinstance(request, dict) else None
    if (not isinstance(request, dict) or set(request) != {'schema', 'id', 'operation', 'arguments'}
            or request['schema'] != SCHEMA or type(request_id) is not int or not 0 <= request_id < 2**64
            or not isinstance(request['operation'], str) or request['operation'] not in OPERATIONS
            or not isinstance(request['arguments'], dict)):
        return fail('invalid_request', request_id)
    submission['mutating'] = request['operation'] in MUTATIONS

    def reject(code: str) -> dict:
        return failure(code, request_id, submission)

    try:
        connection = load_connection()
    except FileNotFoundError:
        return fail('connection_required', request_id)
    except (OSError, ValueError, TypeError):
        return fail('unauthorized', request_id)
    binding = {}
    try:
        try:
            validate_endpoint(connection, binding=binding)
        except FileNotFoundError:
            return fail('unavailable', request_id)
        except (OSError, ValueError):
            return fail('unauthorized', request_id)
        try:
            payload = json.dumps({**request, 'token': connection['token']}, ensure_ascii=False,
                                 separators=(',', ':'), allow_nan=False).encode('utf-8')
        except (ValueError, TypeError, OverflowError, RecursionError):
            return fail('invalid_request', request_id)
        if len(payload) > MAX_REQUEST:
            return fail('limit_exceeded', request_id)
        deadline = time.monotonic() + SOCKET_DEADLINE
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(5)
                stream.connect(connection['endpoint'])
                release_binding(binding)
                peer_option = getattr(socket, 'SO_PEERCRED', None)
                if peer_option is None:
                    return fail('unauthorized', request_id)
                try:
                    _, uid, _ = struct.unpack(
                        '3i', stream.getsockopt(socket.SOL_SOCKET, peer_option, 12))
                except (OSError, struct.error, TypeError, ValueError):
                    return fail('unauthorized', request_id)
                if uid != os.getuid():
                    return fail('unauthorized', request_id)
                # sendall may raise after transmitting some or all of a request.
                # A missing acknowledgement never authorizes a mutation retry.
                submission['possibly_sent'] = True
                stream.sendall(payload)
                stream.shutdown(socket.SHUT_WR)
                reply = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return reject('timeout')
                    stream.settimeout(remaining)
                    chunk = stream.recv(min(65536, MAX_RESPONSE + 1 - len(reply)))
                    if not chunk:
                        break
                    if len(chunk) > MAX_RESPONSE - len(reply):
                        return reject('limit_exceeded')
                    reply.extend(chunk)
            value = json.loads(reply)
            if (not isinstance(value, dict) or value.get('schema') != SCHEMA
                    or type(value.get('ok')) is not bool
                    or set(value) - {'schema', 'id', 'ok', 'result', 'error'}):
                return reject('protocol_error')
            if not value['ok']:
                code = value.get('error', {}).get('code', 'protocol_error')
                response_id = value.get('id')
                if ((response_id is not None
                     and (type(response_id) is not int or response_id != request_id))
                        or not isinstance(code, str) or code not in MESSAGES):
                    return reject('protocol_error')
                return reject(code)
            if (type(value.get('id')) is not int or value['id'] != request_id
                    or not isinstance(value.get('result'), dict) or 'error' in value):
                return reject('protocol_error')
            return value
        except TimeoutError:
            return reject('timeout')
        except (OSError, ConnectionError):
            return reject('unavailable')
        except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
            return reject('protocol_error')
    finally:
        release_binding(binding)


def main() -> None:
    request_id = None
    submission = {}
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            response = fail('limit_exceeded')
        else:
            request = json.loads(raw)
            request_id = request.get('id') if isinstance(request, dict) else None
            response = execute(request, submission=submission)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        code = 'protocol_error' if submission.get('possibly_sent') else 'invalid_request'
        response = failure(code, request_id, submission)
    sys.stdout.buffer.write(encode_response(response, submission=submission))


if __name__ == '__main__':
    main()
