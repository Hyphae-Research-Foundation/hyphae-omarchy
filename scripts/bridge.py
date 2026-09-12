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
OPERATIONS = frozenset(('status', 'projects', 'recall', 'list', 'store', 'forget', 'backups', 'backup'))
TOKEN = re.compile(r'hypm1_[0-9a-f]{64}\Z')
MESSAGES = {
    'connection_required': 'Set up the dedicated Hyphae memory connection independently first.',
    'unavailable': 'The memory service is unavailable. Check it in Hyphae.',
    'unauthorized': 'The service rejected the dedicated memory credential.',
    'invalid_request': 'The memory request is invalid.',
    'forbidden_operation': 'This connection grants only memory data operations.',
    'busy': 'The memory service is busy. Try again shortly.',
    'timeout': 'The memory service did not finish within its deadline.',
    'limit_exceeded': 'The request or its proof exceeds the memory service limit.',
    'protocol_error': 'The endpoint does not provide the expected memory interface.',
}


def fail(code: str, request_id=None) -> dict:
    return {'schema': SCHEMA, 'id': request_id, 'ok': False,
            'error': {'code': code, 'message': MESSAGES.get(code, 'The memory operation could not be completed.')}}


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


def execute(request: dict) -> dict:
    request_id = request.get('id') if isinstance(request, dict) else None
    if (not isinstance(request, dict) or set(request) != {'schema', 'id', 'operation', 'arguments'}
            or request['schema'] != SCHEMA or type(request_id) is not int or not 0 <= request_id < 2**64
            or not isinstance(request['operation'], str) or request['operation'] not in OPERATIONS
            or not isinstance(request['arguments'], dict)):
        return fail('invalid_request', request_id)
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
    payload = json.dumps({**request, 'token': connection['token']}, ensure_ascii=False).encode('utf-8')
    if len(payload) > MAX_REQUEST:
        return fail('limit_exceeded', request_id)
    deadline = time.monotonic() + 130
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(5)
            stream.connect(connection['endpoint'])
            if hasattr(socket, 'SO_PEERCRED'):
                _, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    return fail('unauthorized', request_id)
            stream.sendall(payload)
            stream.shutdown(socket.SHUT_WR)
            reply = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return fail('timeout', request_id)
                stream.settimeout(remaining)
                chunk = stream.recv(min(65536, MAX_RESPONSE + 1 - len(reply)))
                if not chunk:
                    break
                reply.extend(chunk)
                if len(reply) > MAX_RESPONSE:
                    return fail('limit_exceeded', request_id)
        value = json.loads(reply)
        if (not isinstance(value, dict) or value.get('schema') != SCHEMA or type(value.get('ok')) is not bool
                or set(value) - {'schema', 'id', 'ok', 'result', 'error'}):
            return fail('protocol_error', request_id)
        if not value['ok']:
            code = value.get('error', {}).get('code', 'protocol_error')
            if value.get('id') not in (None, request_id) or not isinstance(code, str):
                return fail('protocol_error', request_id)
            return fail(code, request_id)
        if type(value.get('id')) is not int or value['id'] != request_id or not isinstance(value.get('result'), dict) or 'error' in value:
            return fail('protocol_error', request_id)
        return value
    except TimeoutError:
        return fail('timeout', request_id)
    except (OSError, ConnectionError):
        return fail('unavailable', request_id)
    except (ValueError, TypeError, AttributeError):
        return fail('protocol_error', request_id)


def main() -> None:
    request_id = None
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            response = fail('limit_exceeded')
        else:
            request = json.loads(raw)
            request_id = request.get('id') if isinstance(request, dict) else None
            response = execute(request)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        response = fail('invalid_request', request_id)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    main()
