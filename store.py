"""store.py : toutes les données de DAJ (messagerie) dans Firestore.

Variables : FIREBASE_KEY (contenu du .json) ou FIREBASE_KEY_FILE (chemin), FIREBASE_DB (nom de la base).
"""
import os, json, time, copy, secrets, hashlib, threading, datetime as dt
from google.cloud import firestore
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:
    FieldFilter = None

USERS, MSGS, IMGS, LOG = "daj_users", "daj_msgs", "daj_images", "daj_log"
CFG, PUSH = "daj_cfg", "daj_push"  # LOT1_V1
STATUTS = ("prospect", "test", "active", "pause")
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
    p = {k: d.get(k) for k in ("id", "nom", "created", "n", "last_text", "last_ts", "last_from",
                               "unread_dev", "unread_v", "lu_v", "lu_dev", "wa", "ville", "exp")}
    p["statut"] = d.get("statut") or "prospect"
    p["muet"] = bool(d.get("muet"))
    p["tags"] = list(d.get("tags") or [])
    return p


def _fiche(d):
    """Toute la fiche d'une vendeuse, sans les secrets (pour le développeur)."""
    p = _pub(d)
    p["boutique"] = d.get("boutique", "")
    p["notes"] = d.get("notes", "")
    return p


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

    def user_creer(self, nom, jours=0):
        if len(self._tous()) >= 300:
            raise Refus("Trop de vendeuses.")
        ts = maintenant()
        for _ in range(20):
            uid, secret = _rand(4), _rand(8)
            salt = secrets.token_hex(16)
            d = {"id": uid, "nom": nom, "salt": salt, "h": _hash(secret, salt), "created": ts, "n": 0,
                 "last_text": "", "last_ts": ts, "last_from": "", "unread_dev": 0, "unread_v": 0, "lu_v": 0, "lu_dev": 0,
                 "wa": "", "ville": "", "boutique": "", "statut": "prospect", "notes": "", "tags": [],
                 "exp": int(time.time() + jours * 86400) if jours else 0}
            try:
                self.db.collection(USERS).document(uid).create(d)
            except Exception as e:
                if "xist" in type(e).__name__ or "xist" in str(e):
                    continue
                raise
            self._maj(uid, d)
            return uid, joli(uid + secret)
        raise Refus("Réessaie.")

    def user_nouveau_code(self, uid, jours=0):
        d = self.user(uid)
        if not d:
            return None
        secret = _rand(8)
        salt = secrets.token_hex(16)
        d["salt"], d["h"] = salt, _hash(secret, salt)
        d["exp"] = int(time.time() + jours * 86400) if jours else 0
        self.db.collection(USERS).document(uid).update({"salt": salt, "h": d["h"], "exp": d["exp"]})
        self._maj(uid, d)
        self.push_vider(uid)
        return joli(uid + secret)

    def fiche(self, uid):
        d = self._tous().get(uid)
        return copy.deepcopy(_fiche(d)) if d else None

    def user_maj(self, uid, champs):
        d = self.user(uid)
        if not d:
            return None
        self.db.collection(USERS).document(uid).update(champs)
        d.update(champs)
        self._maj(uid, d)
        return copy.deepcopy(_fiche(d))

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
        self.push_vider(uid)
        self.db.collection(USERS).document(uid).delete()
        with self._lock:
            self._tous().pop(uid, None)
        return True

    # ---------- messages ----------
    def envoyer(self, uid, de, texte, image, auto=False, cite=None):
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
            if cite:
                m.update(cite)
            if auto:
                m["auto"] = True
                maj = {"n": seq, "unread_v": int(d.get("unread_v", 0)) + 1}
            elif de == "v":
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

    # LOT2A_V1 : citation, modification, suppression, reactions, epingles
    def msg_get(self, uid, seq):
        s = self.db.collection(MSGS).document("%s_%012d" % (uid, seq)).get()
        return s.to_dict() if s.exists else None

    def msg_modifier(self, uid, seq, qui, action, valeur=None):
        """action : edit, del ou rx. qui : 'd' ou 'v'. Renvoie le message a jour, ou None."""
        ref_u = self.db.collection(USERS).document(uid)
        ref_m = self.db.collection(MSGS).document("%s_%012d" % (uid, seq))

        @firestore.transactional
        def run(tx):
            su = ref_u.get(transaction=tx)
            sm = ref_m.get(transaction=tx)
            if not su.exists or not sm.exists:
                return None
            d, m = su.to_dict(), sm.to_dict()
            if m.get("del"):
                raise Refus("Ce message est supprimé.")
            if action in ("edit", "del") and m.get("de") != qui:
                raise Refus("Tu peux modifier seulement tes messages.")
            if action == "edit":
                age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)).total_seconds()
                if age > 86400:
                    raise Refus("Ce message est trop ancien pour être modifié.")
                ch = {"t": valeur, "ed": maintenant()}
            elif action == "del":
                ch = {"t": "", "img": "", "del": True, "rx": {}, "re": 0, "re_t": "", "re_de": ""}
            else:
                rx = dict(m.get("rx") or {})
                if valeur:
                    rx[qui] = valeur
                else:
                    rx.pop(qui, None)
                ch = {"rx": rx}
            mv = int(d.get("mv", 0)) + 1
            mods = [x for x in (d.get("mods") or []) if x.get("s") != seq][-59:] + [{"s": seq, "v": mv}]
            maj = {"mv": mv, "mods": mods}
            if seq == int(d.get("n", 0)) and action in ("edit", "del"):
                maj["last_text"] = "Message supprimé" if action == "del" else valeur[:80]
            if action == "del" and seq in (d.get("pins") or []):
                maj["pins"] = [p for p in d["pins"] if p != seq]
            tx.update(ref_m, ch)
            tx.update(ref_u, maj)
            m.update(ch)
            d.update(maj)
            return m, d

        r = run(self.db.transaction())
        if not r:
            return None
        m, d = r
        self._maj(uid, d)
        return m

    def modifs(self, uid, depuis):
        """Messages modifies (modifies, supprimes, reactions) depuis la version donnee."""
        d = self._tous().get(uid) or {}
        out = []
        for x in d.get("mods") or []:
            if x.get("v", 0) > depuis:
                m = self.msg_get(uid, int(x["s"]))
                if m:
                    out.append(m)
        return out

    def epingler(self, uid, seq, on):
        d = self.user(uid)
        if not d:
            return None
        pins = [p for p in (d.get("pins") or []) if p != seq]
        if on:
            m = self.msg_get(uid, seq)
            if not m or m.get("del"):
                raise Refus("Message introuvable.")
            if len(pins) >= 5:
                raise Refus("5 messages épinglés au maximum.")
            pins.append(seq)
        self.db.collection(USERS).document(uid).update({"pins": pins})
        d["pins"] = pins
        self._maj(uid, d)
        return pins

    def pins_msgs(self, uid):
        d = self._tous().get(uid) or {}
        out = []
        for s in d.get("pins") or []:
            m = self.msg_get(uid, int(s))
            if m and not m.get("del"):
                out.append(m)
        return out

    def rechercher(self, uid, mot, limite=30):
        if uid not in self._tous():
            return None
        mot = mot.lower()
        q = _w(_w(self.db.collection(MSGS), "k", ">=", uid + "|"), "k", "<", uid + "|~").order_by("k").limit(2000)
        sortie = []
        for s in q.stream():
            m = s.to_dict()
            if mot in (m.get("t") or "").lower():
                sortie.append({"seq": m["seq"], "t": m["t"], "ts": m["ts"], "de": m["de"]})
        return sortie[-limite:]

    def tout(self, uid):
        """Toute la conversation, dans l'ordre (pour l'export)."""
        if uid not in self._tous():
            return None
        q = _w(_w(self.db.collection(MSGS), "k", ">=", uid + "|"), "k", "<", uid + "|~").order_by("k").limit(5000)
        return [s.to_dict() for s in q.stream()]

    # ---------- reglages et notifications ----------
    def cfg(self):
        with self._lock:
            if getattr(self, "_cfg", None) is None:
                s = self.db.collection(CFG).document("settings").get()
                self._cfg = s.to_dict() if s.exists else {}
            return copy.deepcopy(self._cfg)

    def cfg_maj(self, champs):
        c = self.cfg()
        c.update(champs)
        self.db.collection(CFG).document("settings").set(c)
        with self._lock:
            self._cfg = c
        return copy.deepcopy(c)

    def vapid(self):
        """Cles VAPID (identite des notifications). Creees une fois, gardees dans Firestore."""
        import base64
        pr, pu = os.environ.get("VAPID_PRIVATE", "").strip(), os.environ.get("VAPID_PUBLIC", "").strip()
        if pr and pu:
            return pr, pu
        with self._lock:
            if getattr(self, "_vap", None):
                return self._vap
            ref = self.db.collection(CFG).document("vapid")
            s = ref.get()
            if s.exists:
                d = s.to_dict()
            else:
                from cryptography.hazmat.primitives.asymmetric import ec
                from cryptography.hazmat.primitives import serialization as ser
                k = ec.generate_private_key(ec.SECP256R1())

                def b(x):
                    return base64.urlsafe_b64encode(x).rstrip(b"=").decode()
                d = {"priv": b(k.private_numbers().private_value.to_bytes(32, "big")),
                     "pub": b(k.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint))}
                try:
                    ref.create(d)
                except Exception:
                    d = ref.get().to_dict()
            self._vap = (d["priv"], d["pub"])
            return self._vap

    def push_ajouter(self, role, uid, sub):
        cid = hashlib.sha256(sub["endpoint"].encode()).hexdigest()[:32]
        self.db.collection(PUSH).document(cid).set({"role": role, "uid": uid or "", "sub": sub, "ts": maintenant()})

    def push_retirer(self, endpoint, role, uid):
        ref = self.db.collection(PUSH).document(hashlib.sha256(endpoint.encode()).hexdigest()[:32])
        s = ref.get()
        if s.exists:
            d = s.to_dict()
            if d.get("role") == role and d.get("uid", "") == (uid or ""):
                ref.delete()
                return True
        return False

    def push_liste(self, role, uid=""):
        q = _w(self.db.collection(PUSH), "role", "==", role)
        if role == "v":
            q = _w(q, "uid", "==", uid)
        return [(s.id, s.to_dict()["sub"]) for s in q.stream()]

    def push_supprimer(self, cid):
        self.db.collection(PUSH).document(cid).delete()

    def push_vider(self, uid):
        for s in list(_w(self.db.collection(PUSH), "uid", "==", uid).stream()):
            self.db.collection(PUSH).document(s.id).delete()

    # ---------- journal ----------
    def journal_ajouter(self, role, uid, ip, ok):
        try:
            self.db.collection(LOG).document(secrets.token_hex(8)).set(
                {"ts": maintenant(), "role": role, "uid": uid or "", "ip": ip or "", "ok": bool(ok)})
        except Exception:
            pass

    def journal(self, n=100):
        q = self.db.collection(LOG).order_by("ts", direction=firestore.Query.DESCENDING).limit(n)
        return [s.to_dict() for s in q.stream()]

    # ---------- photos ----------
    def image_enregistrer(self, nom, uid, mime, data):
        self.db.collection(IMGS).document(nom).set({"uid": uid, "mime": mime, "data": data, "ts": maintenant()})

    def image_supprimer(self, nom):
        self.db.collection(IMGS).document(nom).delete()

    def image_lire(self, nom):
        s = self.db.collection(IMGS).document(nom).get()
        if not s.exists:
            return None
        d = s.to_dict()
        return d.get("uid"), d.get("mime", "image/jpeg"), bytes(d["data"])
