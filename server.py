#!/usr/bin/env python3
"""DAJ : messagerie entre le développeur et ses vendeuses (site installable)."""
import json, os, re, time, hmac, hashlib, base64, secrets, mimetypes, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
PORT = int(os.environ.get("PORT", "8080"))
DEV_PASSWORD = os.environ.get("DAJ_PASSWORD", "")
SECRET = (os.environ.get("DAJ_SECRET") or hashlib.sha256(("daj|" + DEV_PASSWORD).encode()).hexdigest()).encode()
TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1"
DUREE = 12 * 3600 * 2  # 24 h
mimetypes.add_type("application/manifest+json", ".webmanifest")

from store import Store, Refus
STORE = None
HITS = {}
IMG_CACHE = {}


def hits(key, window):
    now = time.time()
    l = [t for t in HITS.get(key, []) if now - t < window]
    HITS[key] = l
    return l


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def faire_jeton(role, uid="", h=""):
    p = b64(json.dumps({"r": role, "u": uid, "g": h[:8], "e": int(time.time()) + DUREE}).encode())
    return p + "." + b64(hmac.new(SECRET, p.encode(), hashlib.sha256).digest())


def lire_jeton(tok):
    """Renvoie (role, uid) si le jeton est valide, sinon None."""
    try:
        p, sig = str(tok).split(".")
        if not hmac.compare_digest(sig, b64(hmac.new(SECRET, p.encode(), hashlib.sha256).digest())):
            return None
        d = json.loads(unb64(p))
        if d["e"] < time.time():
            return None
        if d["r"] == "d":
            return ("d", "") if DEV_PASSWORD else None
        u = STORE.user(d["u"])
        if not u or u["h"][:8] != d["g"]:
            return None
        return ("v", d["u"])
    except Exception:
        return None


def magic_ok(kind, raw):
    if kind == "jpeg":
        return raw[:3] == b"\xff\xd8\xff"
    if kind == "png":
        return raw[:8] == b"\x89PNG\r\n\x1a\n"
    return raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"


def sauver_image(data_url, uid):
    m = re.match(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)$", data_url or "")
    if not m:
        raise ValueError("Photo invalide.")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 900_000:
        raise ValueError("Photo trop lourde.")
    if not magic_ok(m.group(1), raw):
        raise ValueError("Photo invalide.")
    ext = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}[m.group(1)]
    nom = secrets.token_hex(12) + ext
    STORE.image_enregistrer(nom, uid, {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[m.group(1)], raw)
    return nom


class H(BaseHTTPRequestHandler):
    server_version = "DAJ"
    sys_version = ""

    def log_message(self, *a):
        pass

    # ---------- outils ----------
    def ip(self):
        if TRUST_PROXY:
            x = self.headers.get("X-Forwarded-For", "")
            if x:
                return x.split(",")[0].strip()
        return self.client_address[0]

    def entetes(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; connect-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if TRUST_PROXY and self.headers.get("X-Forwarded-Proto") == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000")

    def json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.entetes()
        self.end_headers()
        self.wfile.write(b)

    def auth(self):
        tok = self.headers.get("X-Token", "")
        if not tok:
            tok = (parse_qs(urlparse(self.path).query).get("t") or [""])[0]
        return lire_jeton(tok)

    def corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_700_000:
            raise ValueError("Envoi trop gros.")
        if not n:
            return {}
        d = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(d, dict):
            raise ValueError("Requête invalide.")
        return d

    def cible(self, a, d_ou_q):
        """Pour la vendeuse : sa propre conversation. Pour le développeur : celle qu'il demande."""
        role, uid = a
        if role == "v":
            return uid
        u = str(d_ou_q.get("uid") or "")[:8]
        return u if STORE.user(u) else None

    # ---------- GET ----------
    def do_GET(self):
        try:
            self._get()
        except Exception:
            traceback.print_exc()
            self.json({"erreur": "Petit souci, réessaie."}, 500)

    def _get(self):
        u = urlparse(self.path)
        p, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
        if p == "/healthz":
            return self.json({"ok": True})
        if p == "/api/me":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            nom = "Développeur" if a[0] == "d" else (STORE.user(a[1]) or {}).get("nom", "")
            return self.json({"role": a[0], "uid": a[1], "nom": nom})
        if p == "/api/threads":
            a = self.auth()
            if not a or a[0] != "d":
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            return self.json({"users": STORE.users()})
        if p == "/api/msgs":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            uid = self.cible(a, q)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            try:
                apres = max(0, int(q.get("apres", 0)))
            except ValueError:
                apres = 0
            l = STORE.messages(uid, apres)
            d = STORE.user(uid) or {}
            return self.json({"msgs": l or [], "n": d.get("n", 0), "lu_v": d.get("lu_v", 0), "lu_dev": d.get("lu_dev", 0), "nom": d.get("nom", "")})
        m = re.match(r"^/img/([0-9a-f]{24}\.(?:jpg|png|webp))$", p)
        if m:
            a = self.auth()
            if not a:
                self.send_response(401); self.end_headers(); return
            nom = m.group(1)
            hit = IMG_CACHE.get(nom) or STORE.image_lire(nom)
            if not hit or (a[0] == "v" and hit[0] != a[1]):
                self.send_response(404); self.end_headers(); return
            if nom not in IMG_CACHE:
                if len(IMG_CACHE) >= 40:
                    IMG_CACHE.pop(next(iter(IMG_CACHE)))
                IMG_CACHE[nom] = hit
            self.send_response(200)
            self.send_header("Content-Type", hit[1])
            self.send_header("Content-Length", str(len(hit[2])))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.entetes()
            self.end_headers()
            self.wfile.write(hit[2])
            return
        return self.static(p)

    def static(self, p):
        if p in ("/", ""):
            p = "/index.html"
        full = os.path.realpath(os.path.join(PUBLIC, p.lstrip("/")))
        if not full.startswith(os.path.realpath(PUBLIC) + os.sep) or not os.path.isfile(full):
            self.send_response(404); self.end_headers(); return
        data = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.entetes()
        self.end_headers()
        self.wfile.write(data)

    # ---------- POST / DELETE ----------
    def do_POST(self):
        try:
            self._post()
        except (ValueError, Refus) as e:
            self.json({"erreur": str(e) or "Requête invalide."}, 400)
        except Exception:
            traceback.print_exc()
            self.json({"erreur": "Petit souci, réessaie."}, 500)

    def do_DELETE(self):
        try:
            a = self.auth()
            m = re.match(r"^/api/users/([A-Z0-9]{4})$", urlparse(self.path).path)
            if not a or a[0] != "d":
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            if not m:
                return self.json({"erreur": "Introuvable."}, 404)
            ok = STORE.user_supprimer(m.group(1))
            return self.json({"ok": ok}, 200 if ok else 404)
        except Exception:
            traceback.print_exc()
            self.json({"erreur": "Petit souci, réessaie."}, 500)

    def _post(self):
        p = urlparse(self.path).path
        d = self.corps()
        if p == "/api/login":
            ip = self.ip()
            if len(hits("l:" + ip, 600)) >= 5:
                return self.json({"erreur": "Trop d'essais. Réessaie dans 10 minutes."}, 429)
            if "password" in d:
                if DEV_PASSWORD and hmac.compare_digest(str(d["password"]).encode(), DEV_PASSWORD.encode()):
                    HITS.pop("l:" + ip, None)
                    return self.json({"token": faire_jeton("d"), "role": "d", "nom": "Développeur"})
            else:
                u = STORE.user_verifier(d.get("code", ""))
                if u:
                    HITS.pop("l:" + ip, None)
                    return self.json({"token": faire_jeton("v", u["id"], u["h"]), "role": "v", "uid": u["id"], "nom": u["nom"]})
            HITS.setdefault("l:" + ip, []).append(time.time())
            time.sleep(0.7)
            return self.json({"erreur": "Code ou mot de passe incorrect."}, 401)

        a = self.auth()
        if not a:
            return self.json({"erreur": "Connexion nécessaire."}, 401)

        if p == "/api/send":
            uid = self.cible(a, d)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            if len(hits("s:" + uid + a[0], 60)) >= 30:
                return self.json({"erreur": "Doucement, réessaie dans une minute."}, 429)
            texte = str(d.get("texte") or "").strip()[:2000]
            img = d.get("image")
            if not texte and not img:
                raise ValueError("Message vide.")
            nom = sauver_image(img, uid) if img else ""
            HITS.setdefault("s:" + uid + a[0], []).append(time.time())
            m = STORE.envoyer(uid, a[0], texte, nom)
            return self.json({"msg": m})

        if p == "/api/read":
            uid = self.cible(a, d)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            STORE.lire(uid, a[0])
            return self.json({"ok": True})

        if a[0] != "d":
            return self.json({"erreur": "Réservé au développeur."}, 403)

        if p == "/api/users":
            nom = re.sub(r"\s+", " ", str(d.get("nom") or "")).strip()[:60]
            if len(nom) < 2:
                raise ValueError("Écris le nom de la vendeuse.")
            uid, code = STORE.user_creer(nom)
            return self.json({"id": uid, "code": code, "nom": nom})

        if p == "/api/users/code":
            uid = str(d.get("uid") or "")[:8]
            code = STORE.user_nouveau_code(uid)
            if not code:
                return self.json({"erreur": "Introuvable."}, 404)
            return self.json({"code": code})

        return self.json({"erreur": "Introuvable."}, 404)


if __name__ == "__main__":
    if not DEV_PASSWORD or len(DEV_PASSWORD) < 8:
        raise SystemExit("Définis DAJ_PASSWORD (8 caractères minimum, 12 conseillé) avant de lancer.")
    STORE = Store()
    print("DAJ sur le port", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
