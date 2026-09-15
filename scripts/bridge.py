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


def private_parent(path: Path) -> None:
    parent = path.parent
    metadata = parent.lstat()
    if (not path.is_absolute() or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077
            or parent.resolve(strict=True) != parent):
        raise ValueError('A private owner-controlled directory is required')


def load_connection() -> dict:
    path = connection_path()
    private_parent(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
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


def validate_endpoint(connection: dict) -> None:
    endpoint = Path(connection['endpoint'])
    private_parent(endpoint)
    metadata = endpoint.lstat()
    if (not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077):
        raise ValueError('Invalid memory socket')


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
    try:
        validate_endpoint(connection)
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
            if hasattr(socket, 'SO_PEERCRED'):
                _, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
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
        if (not isinstance(value, dict) or value.get('schema') != SCHEMA or type(value.get('ok')) is not bool
                or set(value) - {'schema', 'id', 'ok', 'result', 'error'}):
            return reject('protocol_error')
        if not value['ok']:
            code = value.get('error', {}).get('code', 'protocol_error')
            response_id = value.get('id')
            if ((response_id is not None and (type(response_id) is not int or response_id != request_id))
                    or not isinstance(code, str) or code not in MESSAGES):
                return reject('protocol_error')
            return reject(code)
        if type(value.get('id')) is not int or value['id'] != request_id or not isinstance(value.get('result'), dict) or 'error' in value:
            return reject('protocol_error')
        return value
    except TimeoutError:
        return reject('timeout')
    except (OSError, ConnectionError):
        return reject('unavailable')
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        return reject('protocol_error')


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
