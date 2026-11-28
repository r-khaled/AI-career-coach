"""Bounded external course evidence. All remote content is untrusted data."""
import datetime
import hashlib
import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import time
import threading
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .config import DEFAULTS

# Only reviewed generic concepts are sent to the provider, never learner text.
TOPICS = {
    'rag_retrieval': 'retrieval augmented generation evidence retrieval course',
    'ai_fundamentals': 'artificial intelligence fundamentals course',
    'cloud_deployment': 'cloud application deployment fundamentals course',
    'backend_apis': 'backend API development fundamentals course',
    'data_analysis': 'data analysis fundamentals course',
}
_DNS_SLOTS = threading.BoundedSemaphore(8)
_SECRET_ARN = re.compile(r'^arn:[a-z0-9-]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+$')


class ExternalError(Exception):
    pass


def _safe_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ExternalError('Invalid URL')
    try:
        p = urlsplit(url)
        port = p.port
        host = p.hostname
    except ValueError:
        raise ExternalError('Invalid URL') from None
    if p.scheme.lower() != 'https' or not host or p.username is not None or p.password is not None or port not in (None, 443):
        raise ExternalError('Invalid URL')
    host = host.lower().rstrip('.')
    if not host or host == 'localhost' or host.endswith('.localhost') or '%' in host:
        raise ExternalError('Invalid destination')
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[a-z0-9.-]+', host) or any(not x or len(x) > 63 or x.startswith('-') or x.endswith('-') for x in host.split('.')):
            raise ExternalError('Invalid destination') from None
    else:
        if not ip.is_global:
            raise ExternalError('Invalid destination')
    authority = f'[{host}]' if ':' in host else host
    return urlunsplit(('https', authority, p.path or '/', p.query, ''))


def _resolve(host):
    return sorted({row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


def _public_addresses(host, resolver, timeout):
    # getaddrinfo has no timeout API; a daemon worker limits how long the
    # request waits, without permitting a hostname redial on connection.
    result = []
    finished = threading.Event()
    slots = _DNS_SLOTS
    if not slots.acquire(blocking=False):
        raise ExternalError('DNS capacity unavailable')
    def resolve():
        try:
            result.append(list(resolver(host)))
        except Exception:
            result.append(None)
        finally:
            slots.release()
            finished.set()
    try:
        threading.Thread(target=resolve, daemon=True).start()
    except Exception:
        slots.release()
        raise ExternalError('DNS unavailable') from None
    if not finished.wait(timeout) or not result or result[0] is None:
        raise ExternalError('DNS unavailable')
    try:
        addresses = result[0]
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            raise ExternalError('Invalid destination')
        return addresses
    except (OSError, ValueError, TypeError):
        raise ExternalError('DNS unavailable') from None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, ip, timeout, expired):
        super().__init__(hostname, 443, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip
        self._expired = expired
        self.deadline_sock = None

    def connect(self):
        # Publish the socket before connect or TLS handshake so the deadline
        # timer can interrupt either operation; DNS is never repeated here.
        family = socket.AF_INET6 if ':' in self._ip else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        self.sock = raw
        self.deadline_sock = raw
        try:
            if self._expired.is_set():
                raise ExternalError('Deadline exceeded')
            raw.settimeout(self.timeout)
            raw.connect((self._ip, 443))
            if self._expired.is_set():
                raise ExternalError('Deadline exceeded')
            tls = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            self.sock = tls
            self.deadline_sock = tls
            if self._expired.is_set():
                raise ExternalError('Deadline exceeded')
            tls.do_handshake()
            if self._expired.is_set():
                raise ExternalError('Deadline exceeded')
        except Exception:
            self.close()
            raise


def _transport(method, url, headers, body, ip, timeout, max_bytes):
    p = urlsplit(url)
    deadline = time.monotonic() + timeout
    expired = threading.Event()
    conn = _PinnedHTTPSConnection(p.hostname, ip, timeout, expired)
    timer = None
    try:
        # Abort even a slow-drip header/body at the absolute deadline.
        def abort():
            expired.set()
            sock = getattr(conn, 'deadline_sock', None) or conn.sock
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
        timer = threading.Timer(timeout, abort)
        timer.daemon = True
        timer.start()
        path = p.path or '/'
        if p.query:
            path += '?' + p.query
        conn.request(method, path, body=body, headers={**headers, 'Host': p.netloc, 'Accept-Encoding': 'identity'})
        res = conn.getresponse()
        if expired.is_set() or time.monotonic() >= deadline:
            raise ExternalError('Deadline exceeded')
        encoding = res.getheader('Content-Encoding', 'identity').strip().lower()
        if encoding not in ('', 'identity'):
            raise ExternalError('Unsupported content encoding')
        length = res.getheader('Content-Length')
        if length and (not length.isdigit() or int(length) > max_bytes):
            raise ExternalError('Response too large')
        chunks, total = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExternalError('Deadline exceeded')
            sock = getattr(conn, 'deadline_sock', None) or conn.sock
            if sock:
                sock.settimeout(remaining)
            chunk = res.read1(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ExternalError('Response too large')
            chunks.append(chunk)
        return res.status, dict(res.getheaders()), b''.join(chunks)
    finally:
        if timer:
            timer.cancel()
        conn.close()


def _read_url(url, resolver, transport, clock, *, method='GET', headers=None, body=None):
    deadline = clock() + DEFAULTS.page_timeout_seconds
    current = _safe_url(url)
    remaining_bytes = DEFAULTS.page_max_bytes
    for redirect in range(DEFAULTS.page_max_redirects + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            raise ExternalError('Deadline exceeded')
        host = urlsplit(current).hostname
        addresses = _public_addresses(host, resolver, remaining)
        remaining = deadline - clock()
        if remaining <= 0:
            raise ExternalError('Deadline exceeded')
        status, response_headers, content = transport(method, current, headers or {}, body, addresses[0], remaining, remaining_bytes)
        if clock() > deadline or len(content) > remaining_bytes:
            raise ExternalError('Response limits exceeded')
        remaining_bytes -= len(content)
        headers_lower = {k.lower(): v for k, v in response_headers.items()}
        if headers_lower.get('content-encoding', 'identity').lower() not in ('', 'identity'):
            raise ExternalError('Unsupported content encoding')
        if status in (301, 302, 303, 307, 308):
            if redirect == DEFAULTS.page_max_redirects or not headers_lower.get('location') or method != 'GET':
                raise ExternalError('Redirect rejected')
            current = _safe_url(urljoin(current, headers_lower['location']))
            continue
        if status != 200:
            raise ExternalError('Page unavailable')
        return current, headers_lower, content
    raise ExternalError('Redirect limit')


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = []
        self.in_jsonld = False
        self.jsonld = []
        self._script = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self.in_title = True
        if tag.lower() == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.in_jsonld = True
            self._script = []

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
        if tag.lower() == 'script' and self.in_jsonld:
            self.in_jsonld = False
            if len(self.jsonld) < 10:
                self.jsonld.append(''.join(self._script)[:65537])

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.in_jsonld and sum(map(len, self._script)) <= 65536:
            self._script.append(data[:65537])


def _jsonld_fields(scripts, page_title, page_url):
    """Extract only structured values from a matching Course, never execute it."""
    def duration_hours(value):
        if not isinstance(value, str):
            return None
        match = re.fullmatch(r'P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?', value)
        if not match or not any(match.groups()):
            return None
        try:
            d, h, m, sec = (float(x or 0) for x in match.groups())
            result = d * 24 + h + m / 60 + sec / 3600
            return result if math.isfinite(result) and 0 < result <= 100000 else None
        except (OverflowError, ValueError):
            return None

    queue = []
    for script in scripts:
        if len(script) > 65536:
            continue
        try:
            queue.append(json.loads(script))
        except (ValueError, RecursionError):
            continue
    count = 0
    while queue and count < 200:
        node = queue.pop(0); count += 1
        if isinstance(node, list):
            queue.extend(node[:200]); continue
        if not isinstance(node, dict):
            continue
        graph = node.get('@graph')
        if isinstance(graph, list):
            queue.extend(graph[:200])
        kind = node.get('@type')
        if kind != 'Course' and not (isinstance(kind, list) and 'Course' in kind):
            continue
        name = _text(node.get('name'), 300)
        link = node.get('url')
        try:
            matched_url = isinstance(link, str) and _safe_url(urljoin(page_url, link)) == page_url
        except ExternalError:
            matched_url = False
        if link is not None and not matched_url:
            continue
        if not matched_url and (not name or name.casefold() != page_title.casefold()):
            continue
        fields = {}
        duration = duration_hours(node.get('timeRequired'))
        if duration is not None:
            fields['duration_hours'] = duration
        language = _text(node.get('inLanguage'), 100)
        if language:
            fields['language'] = language
        provider = node.get('provider')
        if isinstance(provider, dict):
            provider = _text(provider.get('name'), 200)
            if provider: fields['provider'] = provider
        offer = node.get('offers')
        if isinstance(offer, dict):
            price, currency = offer.get('price'), _text(offer.get('priceCurrency'), 16)
            if (isinstance(price, (str, int, float)) and not isinstance(price, bool)
                    and len(str(price)) <= 40 and currency):
                try:
                    amount = float(price)
                    if math.isfinite(amount) and amount >= 0:
                        fields['price'] = {'amount': str(price), 'currency': currency}
                except ValueError:
                    pass
        for key, target in (('teaches', 'skills'), ('coursePrerequisites', 'prerequisites')):
            value = node.get(key)
            if isinstance(value, str): value = [value]
            if isinstance(value, list):
                value = [_text(x, 300) for x in value[:20] if isinstance(x, str)]
                if value and all(value): fields[target] = value
        return fields
    return {}


def _text(value, limit):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def _id(prefix, value):
    return prefix + hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


class ExternalSearch:
    def __init__(self, secret_arn, secret_client, search_client=None, resolver=_resolve,
                 transport=_transport, clock=time.monotonic, now=None):
        if not isinstance(secret_arn, str) or not _SECRET_ARN.fullmatch(secret_arn):
            raise ValueError('A Secrets Manager ARN is required')
        self.secret_arn, self.secret_client, self.search_client = secret_arn, secret_client, search_client
        self.resolver, self.transport, self.clock = resolver, transport, clock
        self.now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.search_attempts = 0
        self.page_reads = 0

    def _search(self, query, key):
        if self.search_client is not None:
            return self.search_client(query, key)
        body = json.dumps({'q': query, 'num': DEFAULTS.search_candidates_per_request}).encode('utf-8')
        _, _, response = _read_url('https://google.serper.dev/search', self.resolver, self.transport, self.clock,
                                   method='POST', headers={'Content-Type': 'application/json', 'X-API-KEY': key}, body=body)
        return json.loads(response)

    def search(self, topic_ids, language='en'):
        if not isinstance(topic_ids, list) or len(topic_ids) > 32 or any(not isinstance(x, str) or len(x) > 100 for x in topic_ids) or language not in ('en', 'ar'):
            raise ValueError('Invalid search input')
        resources, evidence, records, gaps = [], [], [], []
        seen = set()
        seen_final = set()
        known = []
        for topic in topic_ids:
            if topic not in TOPICS:
                if 'Unrecognized topic; external coverage unavailable' not in gaps:
                    gaps.append('Unrecognized topic; external coverage unavailable')
            elif topic not in known:
                known.append(topic)
        if not known:
            return self._bundle(resources, evidence, records, gaps)
        try:
            secret = self.secret_client.get_secret_value(SecretId=self.secret_arn)
            key = secret['SecretString']
            if isinstance(key, str) and key.lstrip().startswith('{'):
                key = json.loads(key).get('api_key')
            if not isinstance(key, str) or not key or len(key) > 4096:
                raise ExternalError('Secret unavailable')
        except Exception:
            gaps.append('Search unavailable')
            return self._bundle(resources, evidence, records, gaps)
        for topic in known:
            query = TOPICS[topic] + (' Arabic' if language == 'ar' else ' English')
            results = None
            while self.search_attempts < DEFAULTS.search_max_requests:
                self.search_attempts += 1
                try:
                    response = self._search(query, key)
                    results = response.get('organic', [])
                    if not isinstance(results, list):
                        raise ExternalError('Invalid search response')
                    break
                except Exception:
                    continue
            if results is None:
                gaps.append('Search unavailable or request budget exhausted')
                continue
            for result in results[:DEFAULTS.search_candidates_per_request]:
                if not isinstance(result, dict):
                    continue
                try:
                    url = _safe_url(result.get('link'))
                except ExternalError:
                    continue
                title = _text(result.get('title'), 300)
                if not title or url in seen:
                    continue
                seen.add(url)
                stamp = self.now().astimezone(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
                evidence_id = _id('snippet:', url)
                resource = {'resource_id': _id('external:', url), 'kind': 'external', 'course_id': None,
                            'title': title, 'url': url, 'duration_hours': None, 'prerequisite_status': 'unresolved',
                            'reason': 'Search result for a requested learning topic; verify suitability', 'evidence_ids': [evidence_id]}
                evidence.append({'evidence_id': evidence_id, 'source': 'search_snippet', 'uri': url,
                                 'retrieved_at': stamp, 'catalog_version': None, 'parsed_source_sha256': None,
                                 'course_id': None, 'supported_fields': ['title', 'url']})
                records.append({'evidence_id': evidence_id, 'topic_id': topic, 'excerpt': _text(result.get('snippet'), 500),
                                'supported_fields': ['title', 'url'], 'field_values': {'title': title, 'url': url}})
                resources.append(resource)
                if self.page_reads >= DEFAULTS.search_max_page_reads:
                    gaps.append('Page-read budget exhausted; snippet-only evidence remains')
                    continue
                self.page_reads += 1
                try:
                    final_url, headers, content = _read_url(url, self.resolver, self.transport, self.clock)
                    if 'text/html' not in headers.get('content-type', '').lower():
                        raise ExternalError('Not an HTML page')
                    html = content.decode('utf-8', errors='replace')
                    # Do not bypass login, bot challenges or CAPTCHA pages.
                    if re.search(r'(?i)captcha|type\s*=\s*[\"\']?password|<title[^>]*>\s*(?:sign in|log in|login)\b', html):
                        raise ExternalError('Page requires authentication')
                    parser = _Page(); parser.feed(html)
                    page_title = _text(' '.join(parser.title), 300)
                    if final_url in seen_final:
                        # The candidate was appended before the page read. A
                        # duplicate redirect must not leave orphan snippet data.
                        resources.pop()
                        evidence.pop()
                        records.pop()
                        gaps.append('Duplicate external destination omitted')
                        continue
                    seen_final.add(final_url)
                    if not page_title:
                        raise ExternalError('No page title')
                    page_id = _id('page:', final_url)
                    fields = {'title': page_title, 'url': final_url}
                    fields.update(_jsonld_fields(parser.jsonld, page_title, final_url))
                    evidence.append({'evidence_id': page_id, 'source': 'course_page', 'uri': final_url,
                                     'retrieved_at': stamp, 'catalog_version': None, 'parsed_source_sha256': None,
                                     'course_id': None, 'supported_fields': list(fields)})
                    records.append({'evidence_id': page_id, 'topic_id': topic, 'excerpt': page_title,
                                    'supported_fields': list(fields), 'field_values': fields})
                    resource.update(title=page_title, url=final_url)
                    if 'duration_hours' in fields:
                        resource['duration_hours'] = fields['duration_hours']
                    resource['evidence_ids'].append(page_id)
                except Exception:
                    gaps.append('A page was unavailable; only search-snippet evidence remains')
        if resources:
            gaps.append('External course details are provider-declared and may be incomplete or outdated')
        return self._bundle(resources, evidence, records, list(dict.fromkeys(gaps)))

    def _bundle(self, resources, evidence, records, gaps):
        field_provenance = {}
        for resource in resources:
            fields = {}
            for field in ('title', 'url', 'duration_hours'):
                fields[field] = [r['evidence_id'] for r in records
                                 if r['evidence_id'] in resource['evidence_ids'] and
                                 r['field_values'].get(field) == resource[field]]
            for record in records:
                if record['evidence_id'] in resource['evidence_ids']:
                    for field in record['field_values']:
                        if field not in ('title', 'url', 'duration_hours'):
                            fields.setdefault(field, []).append(record['evidence_id'])
            field_provenance[resource['resource_id']] = fields
        return {'resources': resources, 'evidence': evidence, 'records': records,
                'field_provenance': field_provenance, 'gaps': gaps,
                'budget': {'search_attempts': self.search_attempts, 'page_reads': self.page_reads,
                           'max_search_attempts': DEFAULTS.search_max_requests,
                           'max_page_reads': DEFAULTS.search_max_page_reads}}
