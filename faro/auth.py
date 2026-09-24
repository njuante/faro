"""Password login with server-side sessions. Standard library only.

Hashes use PBKDF2-SHA256 ("pbkdf2_sha256$iterations$salt$hash"), generated
with `faro hash-password`. Sessions are random tokens in an HttpOnly cookie,
stored hashed on disk so a leaked sessions file cannot be replayed.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

ITERATIONS = 600_000
COOKIE = 'faro_session'
MAX_FAILS = 5            # per IP ...
FAIL_WINDOW = 300        # ... in 5 minutes


def hash_password(password, iterations=ITERATIONS):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    b64 = lambda b: base64.b64encode(b).decode().rstrip('=')   # noqa: E731
    return f'pbkdf2_sha256${iterations}${b64(salt)}${b64(dk)}'


def verify_password(password, stored):
    try:
        algo, iterations, salt, digest = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        pad = lambda s: base64.b64decode(s + '=' * (-len(s) % 4))   # noqa: E731
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), pad(salt), int(iterations))
        return hmac.compare_digest(dk, pad(digest))
    except (ValueError, TypeError):
        return False


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, conf):
        self.mode = conf['auth']['mode']
        self.hash = conf['auth']['password_hash']
        self.ttl = conf['auth']['session_days'] * 86400
        self.path = os.path.join(conf['server']['data_dir'], 'sessions.json')
        self.lock = threading.Lock()
        self.fails = {}                  # ip -> [timestamps]
        try:
            with open(self.path) as f:
                self.sessions = json.load(f)
        except (OSError, ValueError):
            self.sessions = {}          # sha256(token) -> expiry
        if self.mode == 'password' and not self.hash:
            print('WARNING: auth.mode is "password" but auth.password_hash is empty: nobody can log in.\n'
                  '         Run `faro hash-password` and put the result in the config.', flush=True)

    @property
    def required(self):
        return self.mode == 'password'

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.sessions, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def throttled(self, ip):
        now = time.time()
        with self.lock:
            recent = [t for t in self.fails.get(ip, []) if now - t < FAIL_WINDOW]
            self.fails[ip] = recent
            return len(recent) >= MAX_FAILS

    def login(self, ip, password):
        """Returns a new session token, or None."""
        if self.throttled(ip):
            return None
        if not self.hash or not verify_password(password or '', self.hash):
            with self.lock:
                self.fails.setdefault(ip, []).append(time.time())
            return None
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            self.sessions[_digest(token)] = now + self.ttl
            self._save()
        return token

    def logout(self, token):
        with self.lock:
            if self.sessions.pop(_digest(token or ''), None):
                self._save()

    def valid(self, token):
        if not self.required:
            return True
        if not token:
            return False
        with self.lock:
            exp = self.sessions.get(_digest(token))
        return bool(exp and exp > time.time())
