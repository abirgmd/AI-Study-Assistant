"""Test HTTP de bout en bout : « Assistant IA 2 » (module 3) et matière des cours (module 5).

Prérequis : installation locale isolée (XAMPP, base importée avec database/schema.sql), serveur PHP ou Apache
actif, et service IA démarré (ai-service, port 8001, même jeton que config/ia-service.php).
Usage : python tests/smoke_ia.py http://localhost/ai-study-assistant-integre/public/

Le script crée deux comptes de test et deux cours. Il n'utilise que la bibliothèque standard Python.
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000/').rstrip('/') + '/'
if urllib.parse.urlsplit(BASE).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise SystemExit('Utilisez uniquement une installation locale isolée.')

PASSWORD = 'Test-only-password-2026'
BOUNDARY = 'IaBoundary' + str(time.time_ns())


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
        assert match, 'Jeton CSRF introuvable'
        return match.group(1)

    def api(self, route):
        code, _, body = self.request(route)
        return code, json.loads(body)

    def post(self, csrf, route, fields):
        code, _, body = self.request(route, fields, {'X-CSRF-Token': csrf})
        return code, json.loads(body)

    def upload(self, csrf, filename, text):
        body = (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="course"; filename="{filename}"\r\n'
                f'Content-Type: text/plain\r\n\r\n{text}\r\n--{BOUNDARY}--\r\n').encode('utf-8')
        return self.request('api.php?action=upload', headers={
            'Content-Type': 'multipart/form-data; boundary=' + BOUNDARY, 'X-CSRF-Token': csrf}, raw=body)


def register(client, email, name):
    token = client.token('signup.php')
    code, url, body = client.request('signup.php', {
        'csrf': token, 'name': name, 'email': email, 'password': PASSWORD, 'confirm': PASSWORD})
    assert code == 200 and url.endswith('index.php'), body


def ai_courses(client):
    code, data = client.api('ia-api.php?action=courses')
    assert code == 200, data
    return {c['id']: c for c in data['courses']}


stamp = str(time.time_ns())
alice, bob, guest = Client(), Client(), Client()
print('Démarrage : ' + BASE)

# --- Accès et sécurité -------------------------------------------------------
assert guest.api('ia-api.php?action=courses')[0] == 401, 'Visiteur : accès refusé'
register(alice, f'ia-alice-{stamp}@example.test', 'Alice IA')
register(bob, f'ia-bob-{stamp}@example.test', 'Bob IA')
csrf_a, csrf_b = alice.token(), bob.token()
code, body = alice.post('', 'ia-api.php?action=ask', {'question': 'Quelle est la question ?', 'course_id': 'all'})
assert code == 403, 'Question sans jeton CSRF : refusée (403)'
print('PASS : accès anonyme refusé, jeton CSRF obligatoire')

# --- Module 3 : import, indexation -------------------------------------------
bug_text = ('Le cycle de vie d un bug comprend cinq etapes : apparition, detection, localisation, correction '
            'et validation. Les outils d intelligence artificielle participent a la detection et a la '
            'correction. Le score F1 combine la precision et le rappel pour evaluer un detecteur de bugs.')
code, _, body = alice.upload(csrf_a, 'cycle-bugs.txt', bug_text)
created = json.loads(body)
assert code == 201, body
assert created['indexed'] is True, f"Indexation attendue après l'import : {body}"
assert 'Assistant IA 2' in created['message'], created
bug_id = created['course_id']
listed = ai_courses(alice)
assert listed[bug_id]['indexed'] is True and listed[bug_id]['chunk_count'] >= 1, listed[bug_id]
print('PASS : import indexé pour l’Assistant IA 2 (blocs : %d)' % listed[bug_id]['chunk_count'])

# --- Module 5 : classification automatique à l'import -------------------------
network_text = ('Le protocole TCP assure un transport fiable grace a la poignee de main en trois temps. '
                'Le routeur choisit le chemin des paquets avec sa table de routage, le pare-feu filtre le '
                'trafic selon les adresses IP et les ports, et le DNS traduit les noms de domaine en adresses IP.')
code, _, body = alice.upload(csrf_a, 'reseaux.txt', network_text)
network_id = json.loads(body)['course_id']
listed = ai_courses(alice)
assert listed[network_id]['type'] == 'Réseaux et sécurité', listed[network_id]
assert listed[network_id]['category_source'] == 'auto' and listed[network_id]['category_confidence'] > 0, listed[network_id]
print('PASS : matière détectée à l’import (Réseaux et sécurité, confiance %.0f %%)' % (listed[network_id]['category_confidence'] * 100))

# Le même cours apparaît dans la liste de l'API d'origine, avec sa matière (le champ « type »).
code, original = alice.api('api.php?action=courses')
assert code == 200 and any(c['id'] == network_id and c['type'] == 'Réseaux et sécurité' for c in original['courses'])
print('PASS : la liste « Mes cours » d’origine affiche la matière détectée')

# --- Module 3 : questions ----------------------------------------------------
question = 'Quelles sont les etapes du cycle de vie d un bug ?'
code, answer = alice.post(csrf_a, 'ia-api.php?action=ask', {'question': question, 'course_id': 'all', 'scope': 'course'})
assert code == 200 and not answer['abstained'], answer
assert answer['sources'] and answer['sources'][0]['title'] == 'cycle-bugs', answer
assert answer['backend'] and answer['latency_ms'] >= 0, answer
print('PASS : réponse sourcée (source : %s, moteur : %s)' % (answer['sources'][0]['title'], answer['backend']))

code, again = alice.post(csrf_a, 'ia-api.php?action=ask', {'question': question, 'course_id': 'all', 'scope': 'course'})
assert code == 200 and again['cache_hit'] is True, again
print('PASS : même question une seconde fois servie depuis le cache')

code, scoped = alice.post(csrf_a, 'ia-api.php?action=ask', {
    'question': 'Que combine le score F1 ?', 'course_id': str(bug_id), 'scope': 'course'})
assert code == 200 and all(s['course_id'] == bug_id for s in scoped['sources']), scoped
print('PASS : question limitée à un seul cours')

code, short = alice.post(csrf_a, 'ia-api.php?action=ask', {'question': 'ab', 'course_id': 'all'})
assert code == 422, short
code, history = alice.api('ia-api.php?action=history')
assert code == 200 and len(history['history']) >= 2, history
print('PASS : question trop courte refusée (422), historique enregistré')

# --- Isolation entre étudiants -------------------------------------------------
code, other = bob.post(csrf_b, 'ia-api.php?action=ask', {'question': question, 'course_id': 'all', 'scope': 'course'})
assert code == 200 and other['abstained'] and other['sources'] == [], f"Bob ne doit voir aucun cours d’Alice : {other}"
assert bob.post(csrf_b, 'ia-api.php?action=ask', {'question': question, 'course_id': str(bug_id)})[0] == 404
assert bob.post(csrf_b, 'ia-api.php?action=category', {'course_id': str(bug_id), 'category': 'Génie logiciel'})[0] == 404
assert bob.post(csrf_b, 'ia-api.php?action=reindex', {'course_id': str(bug_id)})[0] == 404
print('PASS : isolation : Bob ne peut ni interroger, ni reclasser, ni réindexer le cours d’Alice')

# --- Module 5 : correction par l'étudiant -------------------------------------
code, fixed = alice.post(csrf_a, 'ia-api.php?action=category', {'course_id': str(network_id), 'category': 'Génie logiciel'})
assert code == 200, fixed
listed = ai_courses(alice)
assert listed[network_id]['type'] == 'Génie logiciel' and listed[network_id]['category_source'] == 'etudiant', listed[network_id]
assert alice.post(csrf_a, 'ia-api.php?action=category', {'course_id': str(network_id), 'category': 'Inconnue'})[0] == 422
print('PASS : correction de matière enregistrée, catégorie inconnue refusée')

# --- Modules 3 et 5 : réindexation ---------------------------------------------
code, reindexed = alice.post(csrf_a, 'ia-api.php?action=reindex', {'course_id': str(bug_id)})
assert code == 200 and 'prêt' in reindexed['message'], reindexed
print('PASS : réindexation d’un cours')

# --- Suppression d'un cours ----------------------------------------------------
assert bob.post(csrf_b, 'ia-api.php?action=delete', {'course_id': str(network_id)})[0] == 404
code, deleted = alice.post(csrf_a, 'ia-api.php?action=delete', {'course_id': str(network_id)})
assert code == 200 and 'supprimé' in deleted['message'], deleted
assert network_id not in ai_courses(alice), 'le cours supprimé ne doit plus apparaître dans la liste'
print('PASS : suppression d’un cours (refusée pour un autre étudiant, retirée de la liste)')

print('\nTous les tests de bout en bout des modules 3 et 5 sont passés.')
