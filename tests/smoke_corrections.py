#!/usr/bin/env python3
"""Test HTTP d'intégration (bibliothèque standard uniquement).

Usage : python tests/smoke.py http://localhost:8000/
À lancer sur une installation de TEST (base importée, serveur actif).
Crée deux comptes et un document ; ne supprime rien.
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/").rstrip("/") + "/"
failures = 0


def check(ok, label):
    global failures
    print(("PASS" if ok else "FAIL") + ": " + label)
    if not ok:
        failures += 1


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())
        self.csrf = ""

    def request(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method=method)
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)

    def page_csrf(self, path):
        status, body, _ = self.request(path)
        m = re.search(r'name="csrf"[^>]*value="([0-9a-f]{64})"', body) or re.search(r'name="csrf-token" content="([0-9a-f]{64})"', body)
        self.csrf = m.group(1) if m else ""
        return status, body

    def post_form(self, path, fields):
        fields = dict(fields, csrf=self.csrf)
        return self.request(path, urllib.parse.urlencode(fields).encode(), {"Content-Type": "application/x-www-form-urlencoded"})

    def api(self, action, fields=None, method="GET"):
        headers = {"X-CSRF-Token": self.csrf}
        data = None
        if method == "POST":
            data = urllib.parse.urlencode(fields or {}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        status, body, _ = self.request("api.php?action=" + action, data, headers, method)
        try:
            return status, json.loads(body)
        except ValueError:
            return status, {"raw": body}

    def upload(self, filename, content, mime="text/plain"):
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"course\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        status, text, _ = self.request("api.php?action=upload", body, {"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": self.csrf})
        return status, json.loads(text)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def signup(client, name, email, password):
    client.page_csrf("signup.php")
    status, _, headers = client.post_form("signup.php", {"full_name": name, "name": name, "email": email, "password": password, "password_confirm": password, "confirm": password})
    client.page_csrf("index.php")
    return status, headers


stamp = str(int(time.time()))
a, b = Client(), Client()

status, _, headers = a.request("index.php")
check(status in (301, 302, 303) and "login.php" in headers.get("Location", ""), "Sans session : redirection vers la connexion")

status, _ = a.api("courses")
check(status == 401, "API sans session : 401")

signup(a, "Étudiant A", f"a{stamp}@test.local", "MotDePasse!123")
status, data = a.api("courses")
check(status == 200 and data.get("courses") == [], "Compte A créé et connecté, aucun cours")

status, _, _ = a.request("api.php?action=goals&date=2026-01-01", urllib.parse.urlencode({"index": 0, "completed": 1}).encode(), {"Content-Type": "application/x-www-form-urlencoded"})
check(status == 403, "POST sans jeton CSRF refusé (403)")

status, data = a.upload("cours.txt", "La régression prédit une valeur continue. Contact : prof@esprit.tn".encode())
check(status == 201, "Import d'un cours TXT (201)")
status, data = a.upload("faux.pdf", b"ceci n'est pas un pdf")
check(status == 422, "Faux PDF refusé (422)")

status, data = a.api("courses")
course_id = data["courses"][0]["id"] if data.get("courses") else 0
check(len(data.get("courses", [])) == 1, "Le cours apparaît dans la liste de A")

status, data = a.api("search&q=" + urllib.parse.quote("regression"))
check(status == 200 and len(data.get("results", [])) == 1, "Recherche sans accent trouve « régression »")

status, data = a.api("assistant", {"course_id": course_id, "question": "Que prédit la régression ?"}, "POST")
check(status in (200, 502, 503, 504), f"Assistant : réponse ou erreur IA explicite ({status})")
if status != 200:
    check(bool(data.get("error")), "Assistant : message d'erreur lisible")

status, data = a.api("stats")
check(status == 200 and "average" in data, "Statistiques disponibles")

signup(b, "Étudiant B", f"b{stamp}@test.local", "MotDePasse!456")
status, data = b.api("courses")
check(status == 200 and data.get("courses") == [], "Compte B : ne voit pas les cours de A")
status, _, _ = b.request(f"download.php?id={course_id}")
check(status == 404, "Compte B : téléchargement du cours de A refusé (404)")
status, data = b.api("assistant", {"course_id": course_id, "question": "Que prédit la régression ?"}, "POST")
check(status == 404, "Compte B : assistant sur le cours de A refusé (404)")

print()
print("Tous les tests HTTP sont passés." if failures == 0 else f"{failures} test(s) HTTP en échec.")
sys.exit(1 if failures else 0)
