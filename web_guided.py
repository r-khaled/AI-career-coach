"""Same-origin guided API proxy; session proof remains in the HttpOnly cookie."""
import json
import os
import re
import uuid
from urllib.parse import urlsplit, urlunsplit

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from flask import Blueprint, current_app, jsonify, make_response, request

from career_coach.contracts import validate
from career_coach.downloads import export_plan

bp = Blueprint('guided', __name__)
COOKIE = 'guided_session'
MAX_AGE = 7 * 24 * 60 * 60
_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_PROOF = re.compile(r'^[A-Za-z0-9_-]{32,128}$')


def _settings():
    env = current_app.config.get('GUIDED_ENV', os.environ.get('GUIDED_ENV', 'production'))
    origin = current_app.config.get('PUBLIC_ORIGIN', os.environ.get('PUBLIC_ORIGIN', ''))
    api = current_app.config.get('API_BASE_URL', os.environ.get('API_BASE_URL', ''))
    legacy = current_app.config.get('API_URL', os.environ.get('API_URL', ''))
    if not api and legacy.endswith('/generate-plan'):
        api = legacy[:-len('/generate-plan')]
    if env not in ('production', 'development') or not isinstance(origin, str) or not isinstance(api, str):
        raise ValueError('configuration')
    o, a = urlsplit(origin), urlsplit(api)
    if (not o.hostname or o.username or o.password or o.path not in ('', '/') or o.query or o.fragment or
            not a.hostname or a.username or a.password or a.query or a.fragment):
        raise ValueError('configuration')
    local_origin = o.scheme == 'http' and o.hostname in ('localhost', '127.0.0.1', '::1')
    local_api = a.scheme == 'http' and a.hostname in ('localhost', '127.0.0.1', '::1')
    if not (o.scheme == 'https' or (env == 'development' and local_origin)):
        raise ValueError('configuration')
    if not (a.scheme == 'https' or (env == 'development' and local_api)):
        raise ValueError('configuration')
    # Origin comparisons are exact and never depend on untrusted Host headers.
    if origin.endswith('/'):
        origin = origin[:-1]
    return origin, api.rstrip('/'), not local_origin


def _error(status, code, message):
    response = jsonify({'error': {'code': code, 'message': message, 'request_id': uuid.uuid4().hex}})
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def _cookie():
    raw = request.cookies.get(COOKIE, '')
    parts = raw.split('.')
    if len(parts) != 2 or not _ID.fullmatch(parts[0]) or not _PROOF.fullmatch(parts[1]):
        return None
    return parts


def _set_cookie(response, sid, proof, secure):
    response.set_cookie(COOKIE, sid + '.' + proof, max_age=MAX_AGE, httponly=True,
                        secure=secure, samesite='Lax', path='/')


def _clear(response, secure):
    response.delete_cookie(COOKIE, httponly=True, secure=secure, samesite='Lax', path='/')
    return response


def signed_call(method, url, payload, proof):
    """Sign the exact request bytes and URL; no browser-provided auth is forwarded."""
    session = boto3.Session()
    credentials = session.get_credentials()
    if not credentials or not session.region_name:
        raise RuntimeError('Credentials unavailable')
    headers = {'Content-Type': 'application/json'}
    if proof:
        headers['x-session-token'] = proof
    signed = AWSRequest(method=method, url=url, data=payload, headers=headers)
    SigV4Auth(credentials.get_frozen_credentials(), 'execute-api', session.region_name).add_auth(signed)
    return requests.request(method, url, data=payload, headers=dict(signed.headers),
                            timeout=35, allow_redirects=False)


def _backend(method, path, body, proof, api):
    payload = json.dumps(body, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8') if method == 'POST' else b''
    call = current_app.config.get('GUIDED_TRANSPORT', signed_call)
    return call(method, api + path, payload, proof)


def _json(response):
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError('backend response')
    return data


def _check_success(data, kind, sid=None):
    if kind == 'session':
        if set(data) != {'session_id', 'state', 'profile'} or not _ID.fullmatch(data['session_id']) or (sid and data['session_id'] != sid):
            raise ValueError('backend response')
        validate('dialogue-response', data['state']); validate('profile', data['profile'])
    elif kind == 'job':
        validate('job', data)
    elif kind == 'plan':
        validate('career-plan', data)
    elif kind == 'processing':
        if set(data) != {'status','request_id'} or data['status'] != 'processing' or not isinstance(data['request_id'], str) or len(data['request_id']) > 128:
            raise ValueError('backend response')


def _forward(method, path, kind, body=None, sid=None, download=None):
    try:
        origin, api, secure = _settings()
    except Exception:
        return _error(503, 'not_configured', 'Guided planning is unavailable')
    if method == 'POST' and request.headers.get('Origin') != origin:
        return _error(403, 'invalid_origin', 'Request origin is not allowed')
    cookie = _cookie()
    creating = path == '/v2/sessions' and method == 'POST'
    if not creating and (not cookie or (sid is not None and sid != cookie[0])):
        return _clear(_error(403, 'no_session', 'Session unavailable'), secure)
    proof = None if creating else cookie[1]
    try:
        result = _backend(method, path, body or {}, proof, api)
        status = result.status_code
        data = _json(result)
        if status not in (200, 201, 202):
            if status not in (400, 403, 404, 409, 410, 429, 503):
                status = 503
            remote = data.get('error')
            code = remote.get('code') if isinstance(remote, dict) else None
            code = code if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,64}', code) else 'temporarily_unavailable'
            response = _error(status, code, 'The request could not be completed')
            return _clear(response, secure) if status in (403, 410) else response
        actual_kind = 'processing' if kind == 'session' and status == 202 else kind
        _check_success(data, actual_kind, sid)
        if creating:
            token = result.headers.get('X-Session-Token', '')
            if not isinstance(token, str) or not _PROOF.fullmatch(token):
                raise ValueError('backend response')
        # Do not relay a misbehaving backend's accidental proof disclosure.
        if (token if creating else proof) in json.dumps(data, ensure_ascii=False):
            raise ValueError('backend response')
        if download:
            content, content_type, filename = export_plan(data, download)
            response = make_response(content)
            response.headers['Content-Type'] = content_type
            response.headers['Content-Disposition'] = 'attachment; filename="' + filename + '"'
        else:
            response = jsonify(data); response.status_code = status
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if creating:
            _set_cookie(response, data['session_id'], token, secure)
        else:
            _set_cookie(response, cookie[0], cookie[1], secure)
        return response
    except Exception:
        return _error(503, 'temporarily_unavailable', 'Guided planning is temporarily unavailable')


def _body(contract=None):
    if not request.is_json:
        raise ValueError('input')
    if request.content_length is not None and request.content_length > 16000:
        raise ValueError('input')
    raw = request.stream.read(16001)
    if len(raw) > 16000:
        raise ValueError('input')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('input') from None
    if not isinstance(data, dict):
        raise ValueError('input')
    if contract:
        validate(contract, data)
    return data


def _revision():
    if set(request.args) - {'revision'} or len(request.args.getlist('revision')) > 1:
        raise ValueError('revision')
    revision = request.args.get('revision')
    if revision is not None and (not re.fullmatch(r'[1-9][0-9]{0,5}', revision)):
        raise ValueError('revision')
    return '?revision=' + revision if revision else ''


@bp.post('/api/v2/sessions')
def create():
    try:
        if _body(): raise ValueError('input')
        return _forward('POST', '/v2/sessions', 'session')
    except ValueError:
        return _error(400, 'invalid_input', 'Invalid request')


@bp.get('/api/v2/session')
def resume():
    cookie = _cookie()
    if not cookie:
        return _error(403, 'no_session', 'Session unavailable')
    return _forward('GET', '/v2/sessions/' + cookie[0], 'session', sid=cookie[0])


@bp.get('/api/v2/sessions/<sid>')
def read(sid):
    if not _ID.fullmatch(sid): return _error(404, 'not_found', 'Resource not found')
    return _forward('GET', '/v2/sessions/' + sid, 'session', sid=sid)


@bp.post('/api/v2/sessions/<sid>/<action>')
def write(sid, action):
    contracts = {'answers': ('answer-request', 'session'), 'review': ('review-request', 'session'), 'plans': ('generate-request', 'job')}
    if not _ID.fullmatch(sid) or action not in contracts: return _error(404, 'not_found', 'Resource not found')
    try:
        body = _body(contracts[action][0])
    except ValueError:
        return _error(400, 'invalid_input', 'Invalid request')
    return _forward('POST', '/v2/sessions/' + sid + '/' + action, contracts[action][1], body, sid)


@bp.get('/api/v2/sessions/<sid>/jobs/<jid>')
def job(sid, jid):
    if not _ID.fullmatch(sid) or not _ID.fullmatch(jid): return _error(404, 'not_found', 'Resource not found')
    return _forward('GET', '/v2/sessions/' + sid + '/jobs/' + jid, 'job', sid=sid)


@bp.get('/api/v2/sessions/<sid>/plans/<pid>')
def plan(sid, pid):
    if not _ID.fullmatch(sid) or not _ID.fullmatch(pid): return _error(404, 'not_found', 'Resource not found')
    try: revision = _revision()
    except ValueError: return _error(400, 'invalid_input', 'Invalid request')
    return _forward('GET', '/v2/sessions/' + sid + '/plans/' + pid + revision, 'plan', sid=sid)


@bp.get('/api/v2/sessions/<sid>/plans/<pid>/download')
def download(sid, pid):
    if not _ID.fullmatch(sid) or not _ID.fullmatch(pid): return _error(404, 'not_found', 'Resource not found')
    if set(request.args) - {'revision', 'format'} or len(request.args.getlist('format')) != 1:
        return _error(400, 'invalid_input', 'Invalid request')
    fmt = request.args.get('format')
    if fmt not in ('json', 'markdown') or len(request.args.getlist('revision')) > 1:
        return _error(400, 'invalid_input', 'Invalid request')
    rev = request.args.get('revision')
    if rev is not None and not re.fullmatch(r'[1-9][0-9]{0,5}', rev): return _error(400, 'invalid_input', 'Invalid request')
    path = '/v2/sessions/' + sid + '/plans/' + pid + ('?revision=' + rev if rev else '')
    return _forward('GET', path, 'plan', sid=sid, download=fmt)


@bp.post('/api/v2/sessions/<sid>/plans/<pid>/revisions')
def revise(sid, pid):
    if not _ID.fullmatch(sid) or not _ID.fullmatch(pid): return _error(404, 'not_found', 'Resource not found')
    try: body = _body('revision-request')
    except ValueError: return _error(400, 'invalid_input', 'Invalid request')
    return _forward('POST', '/v2/sessions/' + sid + '/plans/' + pid + '/revisions', 'job', body, sid)
