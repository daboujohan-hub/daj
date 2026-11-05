"""store.py : toutes les données de DAJ (messagerie) dans Firestore.

Variables : FIREBASE_KEY (contenu du .json) ou FIREBASE_KEY_FILE (chemin), FIREBASE_DB (nom de la base).
"""
import os, json, time, copy, secrets, hashlib, threading, datetime as dt
from google.cloud import firestore
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:
    FieldFilter = None

USERS, MSGS, IMGS = "daj_users", "daj_msgs", "daj_images"
ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TTL = 120


class Refus(Exception):
    """Message à montrer à l'utilisateur."""


def maintenant():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _w(q, champ, op, val):
    if FieldFilter is not None:
        return q.where(filter=FieldFilter(champ, op, val))
    return q.where(champ, op, val)


def _hash(secret, salt):
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt), 100_000).hex()


def _rand(n):
    return "".join(secrets.choice(ALPHA) for _ in range(n))


def norm_code(c):
    c = "".join(ch for ch in str(c).upper() if ch.isalnum())
    return c if len(c) == 12 else ""


def joli(code12):
    return "-".join(code12[i:i + 4] for i in (0, 4, 8))


def make_client():
    cle = os.environ.get("FIREBASE_KEY", "").strip()
    fichier = os.environ.get("FIREBASE_KEY_FILE", "").strip()
    base = os.environ.get("FIREBASE_DB", "").strip()
    kw = {"database": base} if base else {}
    if cle:
        return firestore.Client.from_service_account_info(json.loads(cle), **kw)
    if fichier:
        return firestore.Client.from_service_account_json(fichier, **kw)
    raise SystemExit("Clé Firebase manquante : définis FIREBASE_KEY_FILE (chemin du .json) ou FIREBASE_KEY.")


def _pub(d):
    """Vue d'une vendeuse sans secret."""
    return {k: d.get(k) for k in ("id", "nom", "created", "n", "last_text", "last_ts", "last_from",
                                  "unread_dev", "unread_v", "lu_v", "lu_dev")}


class Store:
    def __init__(self, client=None):
        self.db = client or make_client()
        self._lock = threading.RLock()
        self._u = None      # uid -> document (cache)
        self._u_t = 0.0

    # ---------- cache des vendeuses ----------
    def _tous(self):
        with self._lock:
            if self._u is None or time.time() - self._u_t > TTL:
                self._u = {s.id: s.to_dict() for s in self.db.collection(USERS).stream()}
                self._u_t = time.time()
            return self._u

    def _maj(self, uid, d):
        with self._lock:
            self._tous()[uid] = d

    # ---------- vendeuses ----------
    def users(self):
        l = [_pub(d) for d in self._tous().values()]
        l.sort(key=lambda d: d.get("last_ts") or "", reverse=True)
        return copy.deepcopy(l)

    def user(self, uid):
        d = self._tous().get(uid)
        return copy.deepcopy(d) if d else None

    def user_creer(self, nom):
        if len(self._tous()) >= 300:
            raise Refus("Trop de vendeuses.")
        ts = maintenant()
        for _ in range(20):
            uid, secret = _rand(4), _rand(8)
            salt = secrets.token_hex(16)
            d = {"id": uid, "nom": nom, "salt": salt, "h": _hash(secret, salt), "created": ts, "n": 0,
                 "last_text": "", "last_ts": ts, "last_from": "", "unread_dev": 0, "unread_v": 0, "lu_v": 0, "lu_dev": 0}
            try:
                self.db.collection(USERS).document(uid).create(d)
            except Exception as e:
                if "xist" in type(e).__name__ or "xist" in str(e):
                    continue
                raise
            self._maj(uid, d)
            return uid, joli(uid + secret)
        raise Refus("Réessaie.")

    def user_nouveau_code(self, uid):
        d = self.user(uid)
        if not d:
            return None
        secret = _rand(8)
        salt = secrets.token_hex(16)
        d["salt"], d["h"] = salt, _hash(secret, salt)
        self.db.collection(USERS).document(uid).update({"salt": salt, "h": d["h"]})
        self._maj(uid, d)
        return joli(uid + secret)

    def user_verifier(self, code):
        """Renvoie la vendeuse si le code est bon. Prend toujours le même temps."""
        c = norm_code(code)
        d = self._tous().get(c[:4]) if c else None
        salt = d["salt"] if d else "00" * 16
        ok = _hash(c[4:] if c else "x", salt)
        if d and secrets.compare_digest(ok, d["h"]):
            return copy.deepcopy(d)
        return None

    def user_supprimer(self, uid):
        if uid not in self._tous():
            return False
        lot = self.db.collection(MSGS)
        while True:
            q = _w(_w(lot, "k", ">=", uid + "|"), "k", "<", uid + "|~").limit(200).stream()
            snaps = list(q)
            for s in snaps:
                lot.document(s.id).delete()
            if len(snaps) < 200:
                break
        for s in list(_w(self.db.collection(IMGS), "uid", "==", uid).stream()):
            self.db.collection(IMGS).document(s.id).delete()
        self.db.collection(USERS).document(uid).delete()
        with self._lock:
            self._tous().pop(uid, None)
        return True

    # ---------- messages ----------
    def envoyer(self, uid, de, texte, image):
        ref = self.db.collection(USERS).document(uid)
        msgs = self.db.collection(MSGS)
        ts = maintenant()

        @firestore.transactional
        def run(tx):
            s = ref.get(transaction=tx)
            if not s.exists:
                raise Refus("Conversation introuvable.")
            d = s.to_dict()
            seq = int(d.get("n", 0)) + 1
            m = {"k": "%s|%012d" % (uid, seq), "uid": uid, "seq": seq, "de": de, "t": texte, "img": image, "ts": ts}
            maj = {"n": seq, "last_text": (texte[:80] if texte else "Photo"), "last_ts": ts, "last_from": de}
            if de == "v":
                maj.update(unread_dev=int(d.get("unread_dev", 0)) + 1, unread_v=0, lu_v=seq)
            else:
                maj.update(unread_v=int(d.get("unread_v", 0)) + 1, unread_dev=0, lu_dev=seq)
            tx.set(msgs.document("%s_%012d" % (uid, seq)), m)
            tx.update(ref, maj)
            d.update(maj)
            return m, d

        m, d = run(self.db.transaction())
        self._maj(uid, d)
        return m

    def messages(self, uid, apres=0, limite=100):
        d = self._tous().get(uid)
        if not d:
            return None
        if apres >= int(d.get("n", 0)):
            return []
        q = _w(_w(self.db.collection(MSGS), "k", ">=", "%s|%012d" % (uid, apres + 1)), "k", "<", uid + "|~")
        if apres <= 0:
            q = q.order_by("k", direction=firestore.Query.DESCENDING).limit(limite)
            l = [s.to_dict() for s in q.stream()]
            l.reverse()
        else:
            l = [s.to_dict() for s in q.order_by("k").limit(300).stream()]
        return l

    def lire(self, uid, role):
        d = self.user(uid)
        if not d:
            return
        n = int(d.get("n", 0))
        maj = {"lu_dev": n, "unread_dev": 0} if role == "d" else {"lu_v": n, "unread_v": 0}
        if all(d.get(k) == v for k, v in maj.items()):
            return
        self.db.collection(USERS).document(uid).update(maj)
        d.update(maj)
        self._maj(uid, d)

    # ---------- photos ----------
    def image_enregistrer(self, nom, uid, mime, data):
        self.db.collection(IMGS).document(nom).set({"uid": uid, "mime": mime, "data": data, "ts": maintenant()})

    def image_lire(self, nom):
        s = self.db.collection(IMGS).document(nom).get()
        if not s.exists:
            return None
        d = s.to_dict()
        return d.get("uid"), d.get("mime", "image/jpeg"), bytes(d["data"])
