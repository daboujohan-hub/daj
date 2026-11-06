#!/usr/bin/env python3
"""DAJ : messagerie entre le développeur et ses vendeuses (site installable)."""
import json, os, re, time, hmac, hashlib, base64, secrets, mimetypes, traceback, threading, calendar
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
        if u.get("exp") and time.time() > u["exp"]:
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


# LOT1_V1 : notifications, rappels, message d'absence
DEFAUT_CFG = {"rappel_h": 3, "absence_on": False,
              "absence_txt": "Bonjour ! Je suis indisponible pour le moment. Je réponds à tes messages dès que possible.",
              "rapides": ["Envoie-moi tes photos.", "C'est corrigé, tu peux vérifier.", "Je m'en occupe aujourd'hui.",
                          "Peux-tu préciser le prix ?", "Merci, bien reçu."]}
FMT = "%Y-%m-%d %H:%M:%S"
EMOJIS = ("👍", "✅", "🙏", "😊")
TYPING = {}


def reglages():
    c = dict(DEFAUT_CFG)
    c.update(STORE.cfg())
    return c


def push_dispo():
    try:
        import pywebpush  # noqa: F401
        return True
    except Exception:
        return False


def envoyer_push(sub, payload):
    from pywebpush import webpush
    priv, _ = STORE.vapid()
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    claim = os.environ.get("VAPID_SUB") or ("https://" + host if host else "mailto:contact@example.com")
    webpush(subscription_info=sub, data=json.dumps(payload, ensure_ascii=False), vapid_private_key=priv,
            vapid_claims={"sub": claim}, ttl=86400)


def _diffuser(role, uid, payload):
    n, erreurs = 0, []
    for cid, sub in STORE.push_liste(role, uid):
        try:
            envoyer_push(sub, payload)
            n += 1
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if code in (404, 410):
                STORE.push_supprimer(cid)
            else:
                erreurs.append("%s %s" % (type(e).__name__, code or ""))
    return n, erreurs


def pousser(role, uid, titre, corps, tag):
    """Notification sur tous les appareils d'une personne (en arriere-plan)."""
    if not push_dispo():
        return
    payload = {"title": titre, "body": corps, "tag": tag, "url": "/"}

    def run():
        try:
            _diffuser(role, uid, payload)
        except Exception:
            traceback.print_exc()
    if os.environ.get("DAJ_PUSH_SYNC") == "1":
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


def apres_envoi(uid, de, texte):
    u = STORE.user(uid) or {}
    apercu = texte[:90] if texte else "📷 Photo"
    if de == "v":
        if not u.get("muet"):
            pousser("d", "", u.get("nom", "Vendeuse"), apercu, "v" + uid)
        c = reglages()
        if c.get("absence_on") and c.get("absence_txt") and time.time() - float(u.get("auto_ts") or 0) > 6 * 3600:
            STORE.user_maj(uid, {"auto_ts": time.time()})
            STORE.envoyer(uid, "d", c["absence_txt"], "", auto=True)
            pousser("v", uid, "DAJ", c["absence_txt"][:90], "d" + uid)
    else:
        pousser("v", uid, "DAJ", apercu, "d" + uid)


def faire_rappels(maintenant=None):
    """Previent le developpeur quand une vendeuse attend une reponse depuis trop longtemps."""
    t = maintenant or time.time()
    h = int(reglages().get("rappel_h") or 0)
    hr = time.gmtime(t).tm_hour
    if not h or hr >= 22 or hr < 7:
        return 0
    n = 0
    for u in STORE.users():
        d = STORE.user(u["id"]) or {}
        if d.get("muet") or not d.get("unread_dev") or d.get("last_from") != "v":
            continue
        if d.get("rappel_seq") == d.get("n"):
            continue
        if calendar.timegm(time.strptime(d["last_ts"], FMT)) > t - h * 3600:
            continue
        STORE.user_maj(d["id"], {"rappel_seq": d.get("n")})
        pousser("d", "", "Rappel : " + d["nom"], "Attend ta réponse depuis plus de %d h." % h, "r" + d["id"])
        n += 1
    return n


def boucle_rappels():
    while True:
        time.sleep(600)
        try:
            faire_rappels()
        except Exception:
            traceback.print_exc()


STATUTS = ("prospect", "test", "active", "pause")


def jours_ok(v):
    try:
        j = int(v or 0)
    except (TypeError, ValueError):
        raise ValueError("Durée invalide.")
    if j not in (0, 7, 30, 90):
        raise ValueError("Durée invalide.")
    return j


def propre(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def champs_fiche(d):
    """Vérifie ce que le développeur modifie sur la fiche d'une vendeuse."""
    c = {}
    if "nom" in d:
        c["nom"] = propre(d["nom"], 60)
        if len(c["nom"]) < 2:
            raise ValueError("Le nom est trop court.")
    if "wa" in d:
        c["wa"] = re.sub(r"\D", "", str(d["wa"] or ""))[:20]
    if "ville" in d:
        c["ville"] = propre(d["ville"], 60)
    if "boutique" in d:
        b = str(d["boutique"] or "").strip()[:200]
        if b and not re.match(r"^https?://[^\s]+$", b):
            raise ValueError("Le lien de la boutique doit commencer par https://")
        c["boutique"] = b
    if "statut" in d:
        if d["statut"] not in STATUTS:
            raise ValueError("Statut inconnu.")
        c["statut"] = d["statut"]
    if "notes" in d:
        c["notes"] = str(d["notes"] or "").strip()[:2000]
    if "tags" in d:
        t = d["tags"] if isinstance(d["tags"], list) else str(d["tags"] or "").split(",")
        vus = []
        for x in t:
            x = propre(x, 24)
            if x and x.lower() not in [y.lower() for y in vus]:
                vus.append(x)
        c["tags"] = vus[:8]
    if "muet" in d:
        c["muet"] = bool(d["muet"])
    return c
def texte_export(nom, msgs):
    jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    l = ["Conversation DAJ avec " + nom, "Export du " + time.strftime("%d/%m/%Y %H:%M UTC", time.gmtime()), ""]
    for m in msgs:
        qui = "Développeur" if m["de"] == "d" else nom
        corps = "[message supprimé]" if m.get("del") else (m.get("t") or "") + (" [photo]" if m.get("img") else "")
        l.append("[%s] %s : %s" % (m["ts"], qui, corps.strip()))
    return "\n".join(l) + "\n"


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
        if p == "/api/user":
            a = self.auth()
            if not a or a[0] != "d":
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            f = STORE.fiche(str(q.get("uid") or "")[:8])
            return self.json({"user": f}) if f else self.json({"erreur": "Introuvable."}, 404)
        if p == "/api/push/key":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            return self.json({"key": STORE.vapid()[1], "dispo": push_dispo()})
        if p == "/api/settings":
            a = self.auth()
            if not a or a[0] != "d":
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            return self.json({"reglages": reglages()})
        if p == "/api/log":
            a = self.auth()
            if not a or a[0] != "d":
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            noms = {u["id"]: u["nom"] for u in STORE.users()}
            l = [dict(e, nom=noms.get(e.get("uid"), "")) for e in STORE.journal(100)]
            return self.json({"log": l})
        if p == "/api/pins":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            uid = self.cible(a, q)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            return self.json({"msgs": STORE.pins_msgs(uid)})
        if p == "/api/search":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            uid = self.cible(a, q)
            mot = str(q.get("q") or "").strip()[:60]
            if not uid or len(mot) < 2:
                return self.json({"res": []})
            if len(hits("r:" + uid + a[0], 60)) >= 20:
                return self.json({"erreur": "Doucement, réessaie dans une minute."}, 429)
            HITS.setdefault("r:" + uid + a[0], []).append(time.time())
            return self.json({"res": STORE.rechercher(uid, mot) or []})
        if p == "/api/export":
            a = self.auth()
            if not a:
                return self.json({"erreur": "Connexion nécessaire."}, 401)
            uid = self.cible(a, q)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            nom = (STORE.user(uid) or {}).get("nom", "")
            b = texte_export(nom, STORE.tout(uid) or []).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Content-Disposition", 'attachment; filename="conversation-daj.txt"')
            self.send_header("Cache-Control", "no-store")
            self.entetes()
            self.end_headers()
            self.wfile.write(b)
            return
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
            try:
                mv = max(0, int(q.get("mv", 0)))
            except ValueError:
                mv = 0
            autre = "v" if a[0] == "d" else "d"
            return self.json({"msgs": l or [], "n": d.get("n", 0), "lu_v": d.get("lu_v", 0), "lu_dev": d.get("lu_dev", 0), "nom": d.get("nom", ""),
                              "mv": d.get("mv", 0), "maj": STORE.modifs(uid, mv) if (mv or apres) else [], "pins": list(d.get("pins") or []),
                              "ecrit": time.time() - TYPING.get((uid, autre), 0) < 6})
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
                    STORE.journal_ajouter("d", "", ip, True)
                    return self.json({"token": faire_jeton("d"), "role": "d", "nom": "Développeur"})
            else:
                u = STORE.user_verifier(d.get("code", ""))
                if u and u.get("exp") and time.time() > u["exp"]:
                    STORE.journal_ajouter("v", u["id"], ip, False)
                    return self.json({"erreur": "Ce code a expiré. Demande-en un nouveau à ton développeur."}, 401)
                if u:
                    HITS.pop("l:" + ip, None)
                    STORE.journal_ajouter("v", u["id"], ip, True)
                    return self.json({"token": faire_jeton("v", u["id"], u["h"]), "role": "v", "uid": u["id"], "nom": u["nom"]})
            HITS.setdefault("l:" + ip, []).append(time.time())
            STORE.journal_ajouter("?", "", ip, False)
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
            cite = None
            if d.get("re"):
                try:
                    rs = int(d["re"])
                except (TypeError, ValueError):
                    raise ValueError("Réponse invalide.")
                orig = STORE.msg_get(uid, rs)
                if not orig or orig.get("del"):
                    raise ValueError("Le message auquel tu réponds n'existe plus.")
                cite = {"re": rs, "re_de": orig["de"], "re_t": (orig.get("t") or "Photo")[:80]}
            nom = sauver_image(img, uid) if img else ""
            HITS.setdefault("s:" + uid + a[0], []).append(time.time())
            m = STORE.envoyer(uid, a[0], texte, nom, cite=cite)
            try:
                apres_envoi(uid, a[0], texte)
            except Exception:
                traceback.print_exc()
            return self.json({"msg": m})

        if p == "/api/read":
            uid = self.cible(a, d)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            STORE.lire(uid, a[0])
            return self.json({"ok": True})

        if p == "/api/push/sub":
            s = d.get("sub") or {}
            k = s.get("keys") or {}
            ep = str(s.get("endpoint") or "")
            if not (ep.startswith("https://") and len(ep) < 700 and isinstance(k, dict)
                    and 10 < len(str(k.get("p256dh") or "")) < 200 and 10 < len(str(k.get("auth") or "")) < 100):
                raise ValueError("Abonnement invalide.")
            deja = STORE.push_liste(a[0], a[1])
            if len(deja) >= 8 and ep not in [x[1].get("endpoint") for x in deja]:
                raise ValueError("Trop d'appareils enregistrés.")
            STORE.push_ajouter(a[0], a[1], {"endpoint": ep, "keys": {"p256dh": str(k["p256dh"]), "auth": str(k["auth"])}})
            return self.json({"ok": True})

        if p == "/api/push/unsub":
            STORE.push_retirer(str(d.get("endpoint") or ""), a[0], a[1])
            return self.json({"ok": True})

        if p == "/api/typing":
            uid = self.cible(a, d)
            if uid:
                TYPING[(uid, a[0])] = time.time()
            return self.json({"ok": True})

        if p in ("/api/msg/edit", "/api/msg/del", "/api/msg/react"):
            uid = self.cible(a, d)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            if len(hits("e:" + uid + a[0], 60)) >= 60:
                return self.json({"erreur": "Doucement, réessaie dans une minute."}, 429)
            HITS.setdefault("e:" + uid + a[0], []).append(time.time())
            try:
                seq = int(d.get("seq"))
            except (TypeError, ValueError):
                raise ValueError("Message invalide.")
            if p == "/api/msg/edit":
                texte = str(d.get("texte") or "").strip()[:2000]
                if not texte:
                    raise ValueError("Écris le message.")
                m = STORE.msg_modifier(uid, seq, a[0], "edit", texte)
            elif p == "/api/msg/del":
                avant = STORE.msg_get(uid, seq)
                m = STORE.msg_modifier(uid, seq, a[0], "del")
                if m and avant and avant.get("img"):
                    STORE.image_supprimer(avant["img"])
                    IMG_CACHE.pop(avant["img"], None)
            else:
                e = str(d.get("emoji") or "")
                if e and e not in EMOJIS:
                    raise ValueError("Réaction inconnue.")
                m = STORE.msg_modifier(uid, seq, a[0], "rx", e)
            if not m:
                return self.json({"erreur": "Message introuvable."}, 404)
            return self.json({"msg": m})

        if a[0] != "d":
            return self.json({"erreur": "Réservé au développeur."}, 403)

        if p == "/api/pin":
            uid = self.cible(a, d)
            if not uid:
                return self.json({"erreur": "Conversation introuvable."}, 404)
            try:
                seq = int(d.get("seq"))
            except (TypeError, ValueError):
                raise ValueError("Message invalide.")
            return self.json({"pins": STORE.epingler(uid, seq, bool(d.get("on")))})

        if p == "/api/settings":
            c = {}
            if "rappel_h" in d:
                try:
                    hh = int(d["rappel_h"])
                except (TypeError, ValueError):
                    raise ValueError("Durée invalide.")
                if hh not in (0, 1, 3, 6, 12, 24):
                    raise ValueError("Durée invalide.")
                c["rappel_h"] = hh
            if "absence_on" in d:
                c["absence_on"] = bool(d["absence_on"])
            if "absence_txt" in d:
                c["absence_txt"] = str(d["absence_txt"] or "").strip()[:300]
            if "rapides" in d:
                r = d["rapides"] if isinstance(d["rapides"], list) else []
                c["rapides"] = [propre(x, 200) for x in r if propre(x, 200)][:12]
            fin = reglages()
            fin.update(c)
            if fin["absence_on"] and not fin["absence_txt"]:
                raise ValueError("Écris le message d'absence.")
            STORE.cfg_maj(c)
            return self.json({"reglages": reglages()})

        if p == "/api/push/test":
            if not push_dispo():
                return self.json({"erreur": "Notifications non installées sur le serveur (pywebpush manquant)."}, 400)
            n, er = _diffuser("d", "", {"title": "DAJ", "body": "Notification test", "tag": "test", "url": "/"})
            return self.json({"envoyes": n, "erreurs": er})

        if p == "/api/users":
            nom = re.sub(r"\s+", " ", str(d.get("nom") or "")).strip()[:60]
            if len(nom) < 2:
                raise ValueError("Écris le nom de la vendeuse.")
            uid, code = STORE.user_creer(nom, jours_ok(d.get("jours")))
            return self.json({"id": uid, "code": code, "nom": nom})

        if p == "/api/users/code":
            uid = str(d.get("uid") or "")[:8]
            code = STORE.user_nouveau_code(uid, jours_ok(d.get("jours")))
            if not code:
                return self.json({"erreur": "Introuvable."}, 404)
            return self.json({"code": code})

        if p == "/api/users/update":
            uid = str(d.get("uid") or "")[:8]
            f = STORE.user_maj(uid, champs_fiche(d)) if STORE.user(uid) else None
            if not f:
                return self.json({"erreur": "Introuvable."}, 404)
            return self.json({"user": f})

        if p == "/api/broadcast":
            texte = str(d.get("texte") or "").strip()[:2000]
            if not texte:
                raise ValueError("Écris le message.")
            if len(hits("b:d", 60)) >= 2:
                return self.json({"erreur": "Une annonce par minute au maximum."}, 429)
            HITS.setdefault("b:d", []).append(time.time())
            ids = [u["id"] for u in STORE.users()]
            for i in ids:
                STORE.envoyer(i, "d", texte, "")
                pousser("v", i, "DAJ", texte[:90], "d" + i)
            return self.json({"envoye": len(ids)})

        return self.json({"erreur": "Introuvable."}, 404)


if __name__ == "__main__":
    if not DEV_PASSWORD or len(DEV_PASSWORD) < 8:
        raise SystemExit("Définis DAJ_PASSWORD (8 caractères minimum, 12 conseillé) avant de lancer.")
    STORE = Store()
    threading.Thread(target=boucle_rappels, daemon=True).start()
    print("DAJ sur le port", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
