"""HTTP integration checks, isolated local installation only. Creates test accounts/data.
Usage: python tests/smoke.py http://localhost:8000/
"""
import http.cookiejar
import io
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000/').rstrip('/') + '/'
if urllib.parse.urlsplit(BASE).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise SystemExit('Use an isolated localhost installation only.')

class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self, route, fields=None, headers=None, raw=None):
        body = raw if raw is not None else (urllib.parse.urlencode(fields).encode() if fields is not None else None)
        req = urllib.request.Request(BASE + route, data=body, headers=headers or {})
        try:
            with self.http.open(req) as response:
                return response.status, response.geturl(), response.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.geturl(), error.read().decode('utf-8')
    def token(self, route='index.php'):
        code, _, body = self.request(route)
        assert code == 200, body
        match = re.search(r'name="(?:csrf|csrf-token)" (?:value|content)="([a-f0-9]+)"', body)
        assert match, 'CSRF token missing'
        return match.group(1)

a, b, guest = Client(), Client(), Client()
code, url, body = guest.request('index.php')
assert url.endswith('login.php'), 'Anonymous dashboard must redirect'
assert guest.request('api.php?action=courses')[0] == 401
assert guest.request('signup.php', {'name':'Test','email':'test@example.test','password':'Example123'})[0] == 403
stamp = str(time.time_ns())
email_a = 'student-a-' + stamp + '@example.test'
password = 'Test-only-password-2026'

def register(client, email, name):
    token = client.token('signup.php')
    code, url, body = client.request('signup.php', {'csrf':token,'name':name,'email':email,'password':password,'confirm':password})
    assert code == 200 and url.endswith('index.php'), body
    assert name in body

register(a, email_a, 'Student A')
register(b, 'student-b-' + stamp + '@example.test', 'Student B')
# Duplicate email must not create a new account.
token = guest.token('signup.php')
assert 'déjà utilisée' in guest.request('signup.php', {'csrf':token,'name':'Duplicate','email':email_a,'password':password,'confirm':password})[2]
# Student A imports a text course.
csrf_a = a.token()
boundary = 'StudyBoundary' + stamp
payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="course"; filename="test-course.txt"\r\nContent-Type: text/plain\r\n\r\nA simple study document.\r\n--{boundary}--\r\n').encode()
assert a.request('api.php?action=upload', headers={'Content-Type':'multipart/form-data; boundary='+boundary,'X-CSRF-Token':csrf_a}, raw=payload)[0] == 201
import json
courses_a = json.loads(a.request('api.php?action=courses')[2])['courses']
assert len(courses_a) == 1
course_id = courses_a[0]['id']
assert json.loads(b.request('api.php?action=courses')[2])['courses'] == []
assert a.request('download.php?id='+str(course_id))[0] == 200
assert b.request('download.php?id='+str(course_id))[0] == 404
# Invalid CSRF and cross-account goal isolation.
route='api.php?action=goals&date=2026-01-01'
assert a.request(route, {'index':0,'completed':1})[0] == 403
assert a.request(route, {'index':0,'completed':1}, {'X-CSRF-Token':csrf_a})[0] == 200
assert json.loads(a.request(route)[2])['goals'] == [True, False, False]
assert json.loads(b.request(route)[2])['goals'] == [False, False, False]
# Logout is POST-only and login restores the same user's data.
assert a.request('logout.php')[0] == 405
assert a.request('logout.php', {'csrf':csrf_a})[1].endswith('login.php')
assert a.request('api.php?action=courses')[0] == 401
token = a.token('login.php')
assert 'incorrect' in a.request('login.php', {'csrf':token,'email':email_a,'password':'wrong-password'})[2]
code, url, body = a.request('login.php', {'csrf':token,'email':email_a,'password':password})
assert code == 200 and url.endswith('index.php')
assert len(json.loads(a.request('api.php?action=courses')[2])['courses']) == 1
print('PASS: signup, duplicate email, login/logout, CSRF, upload, owner-only download and goal isolation.')
print('Test accounts and file remain in this isolated installation. No automatic deletion is performed.')
