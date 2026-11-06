/* LOT1_V1 */
(function () {
  'use strict';
  var root = document.getElementById('root');
  var S = { tok: '', role: '', uid: '', nom: '' };
  var timers = [];
  try { S.tok = localStorage.getItem('daj_tok') || ''; S.role = localStorage.getItem('daj_role') || ''; S.uid = localStorage.getItem('daj_uid') || ''; S.nom = localStorage.getItem('daj_nom') || ''; } catch (e) {}

  /* ---------- outils ---------- */
  function h(tag, a) {
    var el = document.createElement(tag), i = 2;
    a = a || {};
    for (var k in a) {
      if (k === 'class') el.className = a[k];
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), a[k]);
      else if (a[k] !== false && a[k] != null) el.setAttribute(k, a[k]);
    }
    for (; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      el.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return el;
  }
  function stopTimers() { timers.forEach(clearInterval); timers = []; }
  function toast(t) {
    var x = h('div', { class: 'toast' }, t); document.body.appendChild(x);
    setTimeout(function () { if (x.parentNode) x.parentNode.removeChild(x); }, 2600);
  }
  function save() {
    try { localStorage.setItem('daj_tok', S.tok); localStorage.setItem('daj_role', S.role); localStorage.setItem('daj_uid', S.uid); localStorage.setItem('daj_nom', S.nom); } catch (e) {}
  }
  function sortir() {
    oublierAppareil(S.tok);
    S = { tok: '', role: '', uid: '', nom: '' }; save(); stopTimers(); titre(0); vueLogin();
  }
  function api(path, o) {
    o = o || {};
    var hd = { 'X-Token': S.tok };
    if (o.body) hd['Content-Type'] = 'application/json';
    return fetch(path, { method: o.method || (o.body ? 'POST' : 'GET'), headers: hd, body: o.body ? JSON.stringify(o.body) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (r.status === 401 && S.tok && !o.nolog) { sortir(); }
          return { s: r.status, ok: r.ok, d: d };
        });
      }, function () { return { s: 0, ok: false, d: { erreur: 'Pas de connexion.' } }; });
  }
  function heure(ts) { var d = new Date(ts.replace(' ', 'T') + 'Z'); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function jour(ts) {
    var d = new Date(ts.replace(' ', 'T') + 'Z'), n = new Date(), y = new Date(Date.now() - 864e5);
    var m = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
    if (d.toDateString() === n.toDateString()) return "Aujourd'hui";
    if (d.toDateString() === y.toDateString()) return 'Hier';
    return d.getDate() + ' ' + m[d.getMonth()] + (d.getFullYear() !== n.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  function courtLe(ts) { return jour(ts) === "Aujourd'hui" ? heure(ts) : jour(ts); }
  function titre(n) {
    document.title = n > 0 ? '(' + n + ') DAJ' : 'DAJ';
    try { if (navigator.setAppBadge) { n > 0 ? navigator.setAppBadge(n) : navigator.clearAppBadge(); } } catch (e) {}
  }
  function initiale(s) { return (s || '?').trim().charAt(0).toUpperCase(); }
  function feuille(contenu) {
    var ov = h('div', { class: 'ov' }), s = h('div', { class: 'sheet' });
    contenu.forEach(function (c) { if (c) s.appendChild(c); });
    ov.appendChild(s);
    ov.addEventListener('click', function (e) { if (e.target === ov) fermer(); });
    function fermer() { if (ov.parentNode) ov.parentNode.removeChild(ov); }
    document.body.appendChild(ov);
    return fermer;
  }
  function copier(t) {
    if (navigator.clipboard && navigator.clipboard.writeText) { return navigator.clipboard.writeText(t).then(function () { toast('Copié'); }, function () { toast('Copie impossible'); }); }
    var ta = h('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); toast('Copié'); } catch (e) { toast('Copie impossible'); }
    document.body.removeChild(ta);
  }

  /* ---------- son et notifications (LOT1_V1) ---------- */
  var SON = true, AC = null;
  try { SON = localStorage.getItem('daj_son') !== '0'; } catch (e) {}
  function bip() {
    if (!SON) return;
    try { if (navigator.vibrate) navigator.vibrate([90, 60, 90]); } catch (e) {}
    try {
      AC = AC || new (window.AudioContext || window.webkitAudioContext)();
      if (AC.state === 'suspended') AC.resume();
      var o = AC.createOscillator(), g = AC.createGain(), t = AC.currentTime;
      o.type = 'sine'; o.frequency.value = 880;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.15, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.28);
      o.connect(g); g.connect(AC.destination); o.start(t); o.stop(t + 0.3);
    } catch (e) {}
  }
  function b64v(s) {
    var p = '='.repeat((4 - s.length % 4) % 4), r = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')), a = new Uint8Array(r.length);
    for (var i = 0; i < r.length; i++) a[i] = r.charCodeAt(i);
    return a;
  }
  function pushDispo() { return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window; }
  function swPret() {
    if (!('serviceWorker' in navigator)) return Promise.resolve(null);
    return Promise.race([navigator.serviceWorker.ready, new Promise(function (r) { setTimeout(function () { r(null); }, 2500); })]);
  }
  function pushEtat() {
    if (!pushDispo()) return Promise.resolve('non');
    if (Notification.permission === 'denied') return Promise.resolve('bloque');
    return swPret().then(function (reg) {
      if (!reg) return 'non';
      return reg.pushManager.getSubscription().then(function (s) { return s && Notification.permission === 'granted' ? 'actif' : 'inactif'; });
    }).catch(function () { return 'non'; });
  }
  function pushEnregistrer(s) { return api('/api/push/sub', { body: { sub: s.toJSON() } }); }
  function pushActiver() {
    var cle = '';
    return Notification.requestPermission().then(function (p) {
      if (p !== 'granted') throw new Error('refus');
      return api('/api/push/key');
    }).then(function (r) {
      if (!r.ok || !r.d.dispo) throw new Error('serveur');
      cle = r.d.key;
      return swPret();
    }).then(function (reg) {
      if (!reg) throw new Error('sw');
      return reg.pushManager.getSubscription().then(function (s) {
        return s || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64v(cle) });
      });
    }).then(function (s) { return pushEnregistrer(s); }).then(function (r) { if (!r.ok) throw new Error('serveur'); });
  }
  function pushCouper() {
    return swPret().then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; }).then(function (s) {
      if (!s) return;
      return api('/api/push/unsub', { body: { endpoint: s.endpoint } }).then(function () { return s.unsubscribe(); });
    });
  }
  function pushSilencieux() {
    if (!pushDispo() || Notification.permission !== 'granted') return;
    swPret().then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; })
      .then(function (s) { if (s && S.tok) pushEnregistrer(s); }).catch(function () {});
  }
  function oublierAppareil(tok) {
    if (!tok || !pushDispo()) return;
    swPret().then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; }).then(function (s) {
      if (s) fetch('/api/push/unsub', { method: 'POST', headers: { 'X-Token': tok, 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: s.endpoint }) });
    }).catch(function () {});
  }
  function blocNotifs(etat, rouvrir) {
    var txt = {
      non: "Les notifications ne sont pas possibles ici. Sur iPhone, ajoute d'abord DAJ à l'écran d'accueil.",
      bloque: 'Les notifications sont bloquées. Autorise-les dans les réglages du navigateur pour ce site.',
      actif: 'Notifications activées sur cet appareil.',
      inactif: 'Active les notifications pour être prévenu même quand DAJ est fermé.'
    }[etat];
    var l = [h('p', {}, txt)];
    if (etat === 'inactif') l.push(h('button', { class: 'btn', onclick: function () {
      pushActiver().then(function () { toast('Notifications activées'); rouvrir(); }, function () { toast('Activation impossible'); });
    } }, 'Activer les notifications'));
    if (etat === 'actif') l.push(h('button', { class: 'btn lt', onclick: function () {
      pushCouper().then(function () { toast('Notifications coupées'); rouvrir(); });
    } }, 'Couper les notifications'));
    return l;
  }
  function boutonSon() {
    function lib() { return SON ? 'Son et vibration : activés' : 'Son et vibration : coupés'; }
    var b = h('button', { class: 'btn lt' }, lib());
    b.addEventListener('click', function () {
      SON = !SON;
      try { localStorage.setItem('daj_son', SON ? '1' : '0'); } catch (e) {}
      b.textContent = lib(); if (SON) bip();
    });
    return b;
  }
  function reglagesV() {
    pushEtat().then(function (e) {
      var f = feuille([h('h2', {}, 'Notifications')].concat(blocNotifs(e, function () { f(); reglagesV(); }),
        [boutonSon(), h('button', { class: 'btn lt', onclick: function () { f(); } }, 'Fermer')]));
    });
  }
  function reglagesDev() {
    Promise.all([pushEtat(), api('/api/settings')]).then(function (v) {
      var etat = v[0], r = v[1];
      if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
      var c = r.d.reglages;
      var rap = h('select', { class: 'sel' });
      [[0, 'Pas de rappel'], [1, 'Rappel après 1 h'], [3, 'Rappel après 3 h'], [6, 'Rappel après 6 h'], [12, 'Rappel après 12 h'], [24, 'Rappel après 24 h']].forEach(function (x) {
        var o = h('option', { value: String(x[0]) }, x[1]); if (+c.rappel_h === x[0]) o.selected = true; rap.appendChild(o);
      });
      var ab = h('select', { class: 'sel' }, h('option', { value: '0' }, 'Message d\'absence : désactivé'), h('option', { value: '1' }, 'Message d\'absence : activé'));
      ab.value = c.absence_on ? '1' : '0';
      var tx = h('textarea', { class: 'ta', rows: '3', maxlength: '300' }); tx.value = c.absence_txt || '';
      var fermer = feuille([h('h2', {}, 'Réglages')].concat(blocNotifs(etat, function () { fermer(); reglagesDev(); }), [
        etat === 'actif' ? h('button', { class: 'btn lt', onclick: function () {
          api('/api/push/test', { body: {} }).then(function (x) {
            toast(x.ok ? (x.d.envoyes ? 'Test envoyé (' + x.d.envoyes + ')' : 'Aucun appareil enregistré') : (x.d.erreur || 'Erreur'));
          });
        } }, 'Envoyer une notification test') : null,
        boutonSon(),
        h('p', {}, 'Quand une vendeuse attend ta réponse (pas entre 22 h et 7 h) :'), rap,
        h('p', {}, 'Réponse automatique quand tu es absent (une fois toutes les 6 h par vendeuse) :'), ab, tx,
        h('button', { class: 'btn', onclick: function () {
          api('/api/settings', { body: { rappel_h: +rap.value, absence_on: ab.value === '1', absence_txt: tx.value } }).then(function (x) {
            if (x.ok) { toast('Enregistré'); fermer(); } else toast(x.d.erreur || 'Erreur');
          });
        } }, 'Enregistrer'),
        h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]));
    });
  }

  /* ---------- connexion ---------- */
  function succesAnim(fin) {
    var svg = '<svg viewBox="0 0 96 96"><circle cx="48" cy="48" r="27"/><path d="M36 49l9 9 16-18"/></svg>';
    var o = h('div', { class: 'ok' }); o.innerHTML = svg; o.appendChild(h('b', {}, 'Accès accepté'));
    document.body.appendChild(o);
    setTimeout(function () { if (o.parentNode) o.parentNode.removeChild(o); fin(); }, 1300);
  }
  function vueLogin(dev) {
    stopTimers(); root.innerHTML = '';
    var err = h('div', { class: 'err' });
    var champ = dev
      ? h('input', { class: 'pw', type: 'password', placeholder: 'Mot de passe', autocomplete: 'current-password' })
      : h('input', { type: 'text', placeholder: 'XXXX-XXXX-XXXX', autocomplete: 'off', autocapitalize: 'characters', maxlength: '14', spellcheck: 'false' });
    if (!dev) champ.addEventListener('input', function () {
      var v = champ.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12);
      champ.value = v.replace(/(.{4})(?=.)/g, '$1-');
    });
    var btn = h('button', { class: 'go' }, 'Entrer');
    function go() {
      var v = champ.value.trim(); if (!v) return;
      btn.disabled = true; err.textContent = '';
      api('/api/login', { body: dev ? { password: v } : { code: v }, nolog: true }).then(function (r) {
        btn.disabled = false;
        if (!r.ok) {
          err.textContent = r.d.erreur || 'Erreur';
          champ.classList.remove('shake'); void champ.offsetWidth; champ.classList.add('shake'); return;
        }
        S = { tok: r.d.token, role: r.d.role, uid: r.d.uid || '', nom: r.d.nom || '' }; save();
        succesAnim(demarrer);
      });
    }
    btn.addEventListener('click', go);
    champ.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    root.appendChild(h('div', { class: 'login' },
      h('div', { class: 'logo' }, 'D'),
      h('h1', {}, dev ? 'Espace développeur' : 'DAJ'),
      h('p', {}, dev ? 'Entre ton mot de passe.' : 'Entre le code que ton développeur t\'a donné.'),
      h('div', { class: 'fld' }, champ), err, btn,
      h('button', { class: 'alt', onclick: function () { vueLogin(!dev); } }, dev ? 'Je suis une vendeuse' : 'Espace développeur'),
      h('a', { href: '/politique.html', class: 'politique', target: '_blank' }, 'Politique de communication')));
    setTimeout(function () { champ.focus(); }, 50);
  }

  /* ---------- discussion ---------- */
  function vueChat(o) {
    stopTimers(); root.innerHTML = '';
    var seen = {}, dernier = 0, lu_v = 0, lu_dev = 0, jourPrec = '', img = '', enCours = false;
    var mv = 0, msgs = {}, els = {}, citer = null, pinsSeq = [], dernierTyping = 0;
    var sousEl = h('small', {}, o.sous || '');
    var zone = h('div', { class: 'chat' });
    var vide = h('div', { class: 'vide' }, 'Écris ton premier message ici.');
    var ta = h('textarea', { rows: '1', placeholder: 'Écris un message', maxlength: '2000' });
    var prev = h('div', { class: 'prev hide' });
    var fic = h('input', { type: 'file', accept: 'image/*', class: 'hide' });
    var env = h('button', { class: 'send', 'aria-label': 'Envoyer' }, '➤');
    var cam = h('button', { class: 'cam', 'aria-label': 'Photo' }, '📷');
    function proche() { return zone.scrollHeight - zone.scrollTop - zone.clientHeight < 120; }
    function bas() { zone.scrollTop = zone.scrollHeight; }
    function vu(m) {
      var moi = m.de === o.moi;
      if (!moi) return '';
      return m.seq <= (o.moi === 'v' ? lu_dev : lu_v) ? ' · Vu' : '';
    }
    function bulle(m, pend) {
      var moi = m.de === o.moi;
      if (m.ts && !pend) {
        var j = jour(m.ts);
        if (j !== jourPrec) { zone.appendChild(h('div', { class: 'day' }, j)); jourPrec = j; }
      }
      var b = h('div', { class: 'b' + (moi ? ' me' : '') + (pend ? ' pend' : ''), 'data-seq': m.seq || '' });
      remplir(b, m, pend);
      if (m.seq && !pend) {
        msgs[m.seq] = m; els[m.seq] = b;
        b.addEventListener('click', function (e) { if (e.target.tagName !== 'IMG' && !e.target.closest('.quote')) actions(msgs[m.seq]); });
      }
      zone.appendChild(b);
      return b;
    }
    function remplir(b, m, pend) {
      b.innerHTML = '';
      if (m.re) {
        b.appendChild(h('div', { class: 'quote', onclick: function (e) { e.stopPropagation(); aller(m.re); } },
          h('b', {}, m.re_de === o.moi ? 'Toi' : (o.moi === 'v' ? 'DAJ' : o.titre)), h('span', {}, m.re_t || 'Photo')));
      }
      if (m.img) {
        var src = m.img.indexOf('data:') === 0 ? m.img : '/img/' + m.img + '?t=' + encodeURIComponent(S.tok);
        var im = h('img', { src: src, alt: 'Photo', loading: 'lazy' });
        im.addEventListener('click', function () {
          var v = h('div', { class: 'viewer', onclick: function () { v.parentNode.removeChild(v); } }, h('img', { src: src, alt: '' }));
          document.body.appendChild(v);
        });
        b.appendChild(im);
      }
      if (m.auto) b.appendChild(h('div', { class: 'auto' }, 'Message automatique'));
      if (m.del) b.appendChild(h('i', { class: 'del' }, 'Message supprimé'));
      else if (m.t) b.appendChild(document.createTextNode(m.t));
      var rx = m.rx ? Object.keys(m.rx).map(function (k) { return m.rx[k]; }) : [];
      if (rx.length) b.appendChild(h('div', { class: 'rx' }, rx.join(' ')));
      b.appendChild(h('span', { class: 'mt' }, (pinsSeq.indexOf(m.seq) >= 0 ? '📌 ' : '') + (m.ts ? heure(m.ts) : 'envoi…') + (m.ed && !m.del ? ' · modifié' : '') + (m.ts ? vu(m) : '')));
    }
    function maj(m) {
      msgs[m.seq] = m;
      if (els[m.seq]) remplir(els[m.seq], m, false);
      ticks();
    }
    function aller(seq) {
      var b = els[seq];
      if (!b) { toast('Message plus ancien'); return; }
      b.scrollIntoView({ block: 'center' }); b.classList.add('flash');
      setTimeout(function () { b.classList.remove('flash'); }, 1300);
    }
    function nomDe(m) { return m.de === o.moi ? 'Toi' : (o.moi === 'v' ? 'DAJ' : o.titre); }
    function corps(x) { if (o.uid) x.uid = o.uid; return x; }
    function reagir(m, e) {
      api('/api/msg/react', { body: corps({ seq: m.seq, emoji: e }) }).then(function (r) { if (r.ok) maj(r.d.msg); else toast(r.d.erreur || 'Erreur'); });
    }
    function supprimer(m) {
      api('/api/msg/del', { body: corps({ seq: m.seq }) }).then(function (r) { if (r.ok) maj(r.d.msg); else toast(r.d.erreur || 'Erreur'); });
    }
    function modifier(m) {
      var t = h('textarea', { class: 'ta', rows: '4', maxlength: '2000' }); t.value = m.t;
      var fermer = feuille([h('h2', {}, 'Modifier le message'), t,
        h('button', { class: 'btn', onclick: function () {
          var v = t.value.trim(); if (!v) { toast('Écris le message'); return; }
          api('/api/msg/edit', { body: corps({ seq: m.seq, texte: v }) }).then(function (r) { if (r.ok) { fermer(); maj(r.d.msg); } else toast(r.d.erreur || 'Erreur'); });
        } }, 'Enregistrer'),
        h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Annuler')]);
      setTimeout(function () { t.focus(); }, 60);
    }
    function epingler(m, on) {
      api('/api/pin', { body: { uid: o.uid, seq: m.seq, on: on } }).then(function (r) {
        if (r.ok) { pinsChange(r.d.pins || []); toast(on ? 'Message épinglé' : 'Message détaché'); } else toast(r.d.erreur || 'Erreur');
      });
    }
    function actions(m) {
      if (!m || !m.seq || m.del) return;
      var fermer, ligne = h('div', { class: 'emo' });
      ['👍', '✅', '🙏', '😊'].forEach(function (e) {
        var mien = m.rx && m.rx[o.moi] === e;
        ligne.appendChild(h('button', { class: mien ? 'on' : '', onclick: function () { fermer(); reagir(m, mien ? '' : e); } }, e));
      });
      var l = [ligne, h('button', { class: 'btn lt', onclick: function () { fermer(); citer = m; montrerCiter(); ta.focus(); } }, 'Répondre')];
      if (m.t) l.push(h('button', { class: 'btn lt', onclick: function () { fermer(); copier(m.t); } }, 'Copier'));
      if (o.moi === 'd') {
        var pin = pinsSeq.indexOf(m.seq) >= 0;
        l.push(h('button', { class: 'btn lt', onclick: function () { fermer(); epingler(m, !pin); } }, pin ? 'Détacher' : 'Épingler'));
      }
      if (m.de === o.moi && m.t) l.push(h('button', { class: 'btn lt', onclick: function () { fermer(); modifier(m); } }, 'Modifier'));
      if (m.de === o.moi) l.push(h('button', { class: 'btn rd', onclick: function () { fermer(); if (confirm('Supprimer ce message ?')) supprimer(m); } }, 'Supprimer'));
      l.push(h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer'));
      fermer = feuille(l);
    }
    // LOT2A_V1
    var pinbar = h('div', { class: 'pinbar hide' });
    var replybar = h('div', { class: 'replybar hide' });
    function montrerCiter() {
      replybar.innerHTML = '';
      if (!citer) { replybar.classList.add('hide'); return; }
      replybar.classList.remove('hide');
      replybar.appendChild(h('div', { class: 'qt' }, h('b', {}, nomDe(citer)), h('span', {}, citer.t || 'Photo')));
      replybar.appendChild(h('button', { 'aria-label': 'Annuler', onclick: function () { citer = null; montrerCiter(); } }, '✕'));
    }
    function pinsChange(l) {
      if (JSON.stringify(l) === JSON.stringify(pinsSeq)) return;
      var avant = pinsSeq; pinsSeq = l.slice();
      avant.concat(l).forEach(function (s) { if (msgs[s] && els[s]) remplir(els[s], msgs[s], false); });
      pinbar.innerHTML = '';
      if (!pinsSeq.length) { pinbar.classList.add('hide'); return; }
      pinbar.classList.remove('hide');
      pinbar.appendChild(document.createTextNode('📌 ' + pinsSeq.length + (pinsSeq.length > 1 ? ' messages épinglés' : ' message épinglé') + ' · Voir'));
      ticks();
    }
    pinbar.addEventListener('click', function () {
      api('/api/pins' + (o.uid ? '?uid=' + encodeURIComponent(o.uid) : '')).then(function (r) {
        if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
        var l = h('div', { class: 'lgs' });
        (r.d.msgs || []).forEach(function (m) {
          l.appendChild(h('div', { class: 'lg', onclick: function () { fermer(); aller(m.seq); } },
            h('b', {}, nomDe(m) + ' · ' + jour(m.ts) + ' ' + heure(m.ts)), h('span', {}, m.t || 'Photo')));
        });
        if (!l.childNodes.length) l.appendChild(h('div', { class: 'vide' }, 'Rien d\'épinglé.'));
        var fermer = feuille([h('h2', {}, 'Messages épinglés'), l, h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
      });
    });
    var eclair = h('button', { class: 'cam', 'aria-label': 'Réponses rapides', onclick: function () { rapides(); } }, '⚡');
    function rapides() {
      api('/api/settings').then(function (r) {
        if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
        var l = r.d.reglages.rapides || [];
        var fermer = feuille([h('h2', {}, 'Réponses rapides')].concat(l.map(function (t) {
          return h('button', { class: 'btn lt rp', onclick: function () {
            fermer(); ta.value = (ta.value ? ta.value + ' ' : '') + t; ta.dispatchEvent(new Event('input')); ta.focus();
          } }, t);
        }), [h('button', { class: 'btn', onclick: function () { fermer(); gererRapides(l); } }, 'Modifier la liste'),
          h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]));
      });
    }
    function gererRapides(l) {
      var t = h('textarea', { class: 'ta', rows: '8', maxlength: '2400', placeholder: 'Une réponse par ligne' }); t.value = l.join('\n');
      var fermer = feuille([h('h2', {}, 'Mes réponses rapides'), h('p', {}, 'Une réponse par ligne (12 maximum).'), t,
        h('button', { class: 'btn', onclick: function () {
          api('/api/settings', { body: { rapides: t.value.split('\n') } }).then(function (r) { if (r.ok) { fermer(); toast('Enregistré'); } else toast(r.d.erreur || 'Erreur'); });
        } }, 'Enregistrer'),
        h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Annuler')]);
    }
    function ecrire() {
      var n = Date.now(); if (n - dernierTyping < 3000) return; dernierTyping = n;
      api('/api/typing', { body: o.uid ? { uid: o.uid } : {}, nolog: true });
    }
    function ajouter(l) {
      var coll = proche();
      l.forEach(function (m) {
        if (seen[m.seq]) return;
        seen[m.seq] = 1; if (vide.parentNode) vide.parentNode.removeChild(vide);
        bulle(m); if (m.seq > dernier) dernier = m.seq;
      });
      if (coll || !dernier) bas();
    }
    function ticks() {
      zone.querySelectorAll('.b.me[data-seq]').forEach(function (b) {
        var s = +b.getAttribute('data-seq'); if (!s) return;
        var mt = b.querySelector('.mt'); var base = mt.textContent.replace(' · Vu', '');
        mt.textContent = base + (s <= (o.moi === 'v' ? lu_dev : lu_v) ? ' · Vu' : '');
      });
    }
    function marquer() { if (!document.hidden) api('/api/read', { body: o.uid ? { uid: o.uid } : {} }); }
    function q(apres) { return '/api/msgs?apres=' + apres + '&mv=' + mv + (o.uid ? '&uid=' + encodeURIComponent(o.uid) : ''); }
    function charger(apres, premier) {
      return api(q(apres)).then(function (r) {
        if (!r.ok) { if (premier) toast(r.d.erreur || 'Erreur'); return; }
        lu_v = r.d.lu_v; lu_dev = r.d.lu_dev;
        (r.d.maj || []).forEach(maj); mv = r.d.mv || mv;
        pinsChange(r.d.pins || []);
        sousEl.textContent = r.d.ecrit ? 'écrit…' : (o.sous || '');
        var nouveaux = (r.d.msgs || []).filter(function (m) { return !seen[m.seq]; });
        ajouter(r.d.msgs || []); ticks();
        if (!premier && !o.muet && nouveaux.some(function (m) { return m.de !== o.moi; })) bip();
        if (premier || nouveaux.some(function (m) { return m.de !== o.moi; })) marquer();
        if (premier && !dernier) zone.appendChild(vide);
      });
    }
    function redim(file, fin) {
      var rd = new FileReader();
      rd.onload = function () {
        var im = new Image();
        im.onload = function () {
          var max = 1000, w = im.width, hh = im.height, k = Math.min(1, max / Math.max(w, hh));
          var c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(hh * k);
          c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
          var d = c.toDataURL('image/jpeg', 0.8);
          if (d.length > 1150000) d = c.toDataURL('image/jpeg', 0.6);
          fin(d);
        };
        im.onerror = function () { toast('Photo illisible'); };
        im.src = rd.result;
      };
      rd.readAsDataURL(file);
    }
    function montrerPrev() {
      prev.innerHTML = '';
      if (!img) { prev.classList.add('hide'); return; }
      prev.classList.remove('hide');
      prev.appendChild(h('img', { src: img, alt: '' })); prev.appendChild(h('span', {}, 'Photo prête'));
      prev.appendChild(h('button', { 'aria-label': 'Retirer', onclick: function () { img = ''; montrerPrev(); } }, '✕'));
    }
    fic.addEventListener('change', function () {
      var f = fic.files && fic.files[0]; fic.value = ''; if (!f) return;
      redim(f, function (d) { img = d; montrerPrev(); });
    });
    cam.addEventListener('click', function () { fic.click(); });
    ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 130) + 'px'; ecrire(); });
    function envoyer() {
      var t = ta.value.trim(), im = img;
      if ((!t && !im) || enCours) return;
      enCours = true; env.disabled = true;
      if (vide.parentNode) vide.parentNode.removeChild(vide);
      var c0 = citer;
      var p = bulle({ de: o.moi, t: t, img: im, re: c0 ? c0.seq : 0, re_t: c0 ? (c0.t || 'Photo').slice(0, 80) : '', re_de: c0 ? c0.de : '' }, true); bas();
      ta.value = ''; ta.style.height = 'auto'; img = ''; montrerPrev(); citer = null; montrerCiter();
      var body = { texte: t, image: im || undefined, re: c0 ? c0.seq : undefined }; if (o.uid) body.uid = o.uid;
      api('/api/send', { body: body }).then(function (r) {
        enCours = false; env.disabled = false;
        if (p.parentNode) p.parentNode.removeChild(p);
        if (!r.ok) { toast(r.d.erreur || 'Pas envoyé'); ta.value = t; img = im; citer = c0; montrerPrev(); montrerCiter(); if (!dernier) zone.appendChild(vide); return; }
        ajouter([r.d.msg]); bas();
      });
    }
    env.addEventListener('click', envoyer);

    var tete = h('div', { class: 'bar' },
      o.retour ? h('button', { class: 'ib', 'aria-label': 'Retour', onclick: o.retour }, '←') : null,
      h('div', { class: 'av' }, o.moi === 'v' ? 'D' : initiale(o.titre)),
      h('div', { class: 't' }, h('b', {}, o.titre), sousEl),
      o.cloche ? h('button', { class: 'ib', 'aria-label': 'Notifications', onclick: o.cloche }, '🔔') : null,
      o.menu ? h('button', { class: 'ib', 'aria-label': 'Menu', onclick: o.menu }, '⋮') : null,
      o.quitter ? h('button', { class: 'ib', 'aria-label': 'Quitter', onclick: o.quitter }, '⎋') : null);
    root.appendChild(tete); root.appendChild(pinbar); root.appendChild(zone); root.appendChild(prev); root.appendChild(replybar);
    root.appendChild(h('div', { class: 'compose' }, o.moi === 'd' ? eclair : null, cam, fic, ta, env));
    charger(0, true);
    timers.push(setInterval(function () { if (!document.hidden) charger(dernier, false); }, 2500));
    document.onvisibilitychange = function () { if (!document.hidden) { charger(dernier, false); marquer(); } };
  }

  /* ---------- vendeuse ---------- */
  function vueVendeuse() {
    vueChat({
      moi: 'v', uid: '', titre: 'DAJ', sous: 'Abou Johan · développeur',
      cloche: function () { reglagesV(); },
      quitter: function () { if (confirm('Te déconnecter ?')) sortir(); }
    });
  }

  /* ---------- développeur ---------- */
  function afficherCode(nom, code) {
    var fermer = feuille([
      h('h2', {}, 'Accès de ' + nom),
      h('p', {}, 'Donne-lui ce code. Il ne sera plus affiché : garde-le ou envoie-le maintenant.'),
      h('div', { class: 'code' }, code),
      h('button', { class: 'btn', onclick: function () { copier(code); } }, 'Copier le code'),
      h('button', { class: 'btn lt', onclick: function () {
        var t = 'Bonjour ' + nom + ' ! Voici ton accès DAJ pour m\'écrire : ' + location.origin + '\nTon code : ' + code;
        window.open('https://wa.me/?text=' + encodeURIComponent(t), '_blank', 'noopener');
      } }, 'Envoyer sur WhatsApp'),
      h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
  }
  function choixDuree() {
    return h('select', { class: 'sel' },
      h('option', { value: '0' }, 'Code sans limite de durée'),
      h('option', { value: '7' }, 'Code valable 7 jours'),
      h('option', { value: '30' }, 'Code valable 30 jours'),
      h('option', { value: '90' }, 'Code valable 90 jours'));
  }
  var LIB = { prospect: 'Prospect', test: 'En test', active: 'Active', pause: 'En pause' };
  function waLien(wa, txt) {
    var n = String(wa || '').replace(/\D/g, ''); if (n.length === 10) n = '225' + n;
    return 'https://wa.me/' + n + (txt ? '?text=' + encodeURIComponent(txt) : '');
  }
  function nouvelle(apres) {
    var champ = h('input', { type: 'text', placeholder: 'Nom de la vendeuse ou de la boutique', maxlength: '60' });
    var duree = choixDuree();
    var fermer = feuille([h('h2', {}, 'Nouvelle vendeuse'), h('p', {}, 'Un code d\'accès est créé pour elle.'), champ, duree,
      h('button', { class: 'btn', onclick: function () {
        var nom = champ.value.trim(); if (nom.length < 2) { toast('Écris le nom'); return; }
        api('/api/users', { body: { nom: nom, jours: +duree.value } }).then(function (r) {
          if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
          fermer(); afficherCode(r.d.nom, r.d.code); apres();
        });
      } }, 'Créer')]);
    setTimeout(function () { champ.focus(); }, 60);
  }
  function fiche(u, apres) {
    api('/api/user?uid=' + encodeURIComponent(u.id)).then(function (r) {
      if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
      var f = r.d.user;
      var nom = h('input', { type: 'text', value: f.nom, maxlength: '60', placeholder: 'Nom' });
      var wa = h('input', { type: 'tel', value: f.wa || '', placeholder: 'WhatsApp (ex : 0707070707)' });
      var ville = h('input', { type: 'text', value: f.ville || '', maxlength: '60', placeholder: 'Ville' });
      var bq = h('input', { type: 'url', value: f.boutique || '', maxlength: '200', placeholder: 'Lien de sa boutique (https://…)' });
      var st = h('select', { class: 'sel' });
      Object.keys(LIB).forEach(function (k) { var o = h('option', { value: k }, LIB[k]); if (k === f.statut) o.selected = true; st.appendChild(o); });
      var tg = h('input', { type: 'text', value: (f.tags || []).join(', '), placeholder: 'Étiquettes séparées par des virgules' });
      var nt = h('textarea', { class: 'ta', rows: '4', maxlength: '2000', placeholder: 'Notes privées (toi seul les vois)' }); nt.value = f.notes || '';
      var exp = f.exp ? 'Code valable jusqu\'au ' + new Date(f.exp * 1000).toLocaleDateString('fr-FR') : 'Code sans limite de durée';
      var fermer = feuille([h('h2', {}, 'Fiche : ' + f.nom), nom, wa, ville, bq, st, tg, nt, h('p', {}, exp),
        h('button', { class: 'btn', onclick: function () {
          api('/api/users/update', { body: { uid: f.id, nom: nom.value, wa: wa.value, ville: ville.value, boutique: bq.value, statut: st.value, tags: tg.value, notes: nt.value } })
            .then(function (x) { if (x.ok) { toast('Enregistré'); fermer(); apres(x.d.user); } else toast(x.d.erreur || 'Erreur'); });
        } }, 'Enregistrer'),
        f.wa ? h('button', { class: 'btn lt', onclick: function () { window.open(waLien(f.wa), '_blank', 'noopener'); } }, 'Ouvrir son WhatsApp') : null,
        f.boutique ? h('button', { class: 'btn lt', onclick: function () { window.open(f.boutique, '_blank', 'noopener'); } }, 'Ouvrir sa boutique') : null,
        h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
    });
  }
  function annonce(nb, apres) {
    var ta = h('textarea', { class: 'ta', rows: '5', maxlength: '2000', placeholder: 'Ton message pour toutes les vendeuses' });
    var fermer = feuille([h('h2', {}, 'Annonce à toutes'), h('p', {}, 'Le message sera envoyé dans la discussion de chaque vendeuse (' + nb + ').'), ta,
      h('button', { class: 'btn', onclick: function () {
        var t = ta.value.trim(); if (!t) { toast('Écris le message'); return; }
        if (!confirm('Envoyer à ' + nb + ' vendeuse(s) ?')) return;
        api('/api/broadcast', { body: { texte: t } }).then(function (r) {
          if (r.ok) { fermer(); toast('Envoyé à ' + r.d.envoye); apres(); } else toast(r.d.erreur || 'Erreur');
        });
      } }, 'Envoyer à toutes'),
      h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Annuler')]);
  }
  function journal() {
    api('/api/log').then(function (r) {
      if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
      var l = h('div', { class: 'lgs' });
      (r.d.log || []).forEach(function (e) {
        var qui = e.role === 'd' ? 'Toi' : (e.role === 'v' ? (e.nom || 'Vendeuse') : 'Inconnu');
        l.appendChild(h('div', { class: 'lg ' + (e.ok ? 'ok' : 'ko') },
          h('b', {}, (e.ok ? '✓ ' : '✗ ') + qui), h('span', {}, jour(e.ts) + ' ' + heure(e.ts) + ' · ' + (e.ip || ''))));
      });
      if (!l.childNodes.length) l.appendChild(h('div', { class: 'vide' }, 'Aucune connexion enregistrée.'));
      var fermer = feuille([h('h2', {}, 'Connexions récentes'), l, h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
    });
  }
  function chercher(u) {
    var champ = h('input', { type: 'search', placeholder: 'Mot à chercher dans la conversation', maxlength: '60' });
    var res = h('div', { class: 'lgs' });
    function go() {
      var t = champ.value.trim(); if (t.length < 2) { toast('Au moins 2 lettres'); return; }
      api('/api/search?uid=' + encodeURIComponent(u.id) + '&q=' + encodeURIComponent(t)).then(function (r) {
        res.innerHTML = '';
        if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
        if (!r.d.res.length) res.appendChild(h('div', { class: 'vide' }, 'Rien trouvé.'));
        r.d.res.slice().reverse().forEach(function (m) {
          res.appendChild(h('div', { class: 'lg' }, h('b', {}, (m.de === 'd' ? 'Toi' : u.nom) + ' · ' + jour(m.ts) + ' ' + heure(m.ts)), h('span', {}, m.t)));
        });
      });
    }
    champ.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    var fermer = feuille([h('h2', {}, 'Chercher'), champ, h('button', { class: 'btn', onclick: go }, 'Chercher'), res,
      h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
    setTimeout(function () { champ.focus(); }, 60);
  }
  function exporter(u) {
    fetch('/api/export?uid=' + encodeURIComponent(u.id), { headers: { 'X-Token': S.tok } }).then(function (r) {
      if (!r.ok) throw 0; return r.blob();
    }).then(function (b) {
      var url = URL.createObjectURL(b), a = h('a', { href: url, download: 'conversation-' + u.nom.replace(/[^a-z0-9]+/gi, '-') + '.txt' });
      document.body.appendChild(a); a.click(); document.body.removeChild(a); setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    }).catch(function () { toast('Export impossible'); });
  }
  function vueListe() {
    stopTimers(); root.innerHTML = ''; document.onvisibilitychange = null;
    var cache = [], filtre = '', precedent = null;
    var liste = h('div', { class: 'list' });
    var rech = h('input', { class: 'srch', type: 'search', placeholder: 'Chercher une vendeuse, un statut, une étiquette' });
    var fab = h('button', { class: 'fab', onclick: function () { nouvelle(charge); } }, '+ Vendeuse');
    root.appendChild(h('div', { class: 'bar' }, h('div', { class: 'av' }, 'D'),
      h('div', { class: 't' }, h('b', {}, 'DAJ'), h('small', {}, 'Mes vendeuses')),
      h('button', { class: 'ib', 'aria-label': 'Annonce à toutes', onclick: function () { if (!cache.length) { toast('Aucune vendeuse'); return; } annonce(cache.length, charge); } }, '📢'),
      h('button', { class: 'ib', 'aria-label': 'Réglages', onclick: reglagesDev }, '⚙️'),
      h('button', { class: 'ib', 'aria-label': 'Connexions', onclick: journal }, '📋'),
      h('button', { class: 'ib', 'aria-label': 'Quitter', onclick: function () { if (confirm('Te déconnecter ?')) sortir(); } }, '⎋')));
    root.appendChild(h('div', { class: 'wrap' }, h('div', { class: 'sb' }, rech), liste, fab));
    rech.addEventListener('input', function () { filtre = rech.value.trim().toLowerCase(); dessiner(); });
    function dessiner() {
      liste.innerHTML = '';
      var us = cache.filter(function (u) {
        if (!filtre) return true;
        return (u.nom + ' ' + (LIB[u.statut] || '') + ' ' + (u.ville || '') + ' ' + (u.tags || []).join(' ') + ' ' + (u.last_text || '')).toLowerCase().indexOf(filtre) >= 0;
      });
      if (!cache.length) liste.appendChild(h('div', { class: 'vide' }, 'Aucune vendeuse pour le moment. Appuie sur « + Vendeuse ».'));
      else if (!us.length) liste.appendChild(h('div', { class: 'vide' }, 'Aucun résultat.'));
      us.forEach(function (u) {
        var bas = [LIB[u.statut] || 'Prospect'].concat(u.ville ? [u.ville] : [], u.tags || []).join(' · ');
        liste.appendChild(h('button', { class: 'row', onclick: function () { ouvrir(u); } },
          h('div', { class: 'av' }, initiale(u.nom)),
          h('div', { class: 'm' }, h('b', {}, (u.muet ? '🔕 ' : '') + u.nom),
            h('span', {}, u.last_text ? (u.last_from === 'd' ? 'Toi : ' : '') + u.last_text : 'Aucun message'),
            h('span', { class: 'tg st-' + u.statut }, bas)),
          h('div', { class: 'r' }, h('span', {}, u.last_text ? courtLe(u.last_ts) : ''),
            u.unread_dev > 0 ? h('div', { class: 'badge' }, u.unread_dev) : null)));
      });
    }
    function charge() {
      api('/api/threads').then(function (r) {
        if (!r.ok) return;
        var avant = precedent; precedent = {};
        (r.d.users || []).forEach(function (u) { precedent[u.id] = u.unread_dev || 0; });
        cache = r.d.users || [];
        dessiner();
        titre(cache.reduce(function (t, u) { return t + (u.muet ? 0 : (u.unread_dev || 0)); }, 0));
        if (avant && cache.some(function (u) { return !u.muet && (u.unread_dev || 0) > (avant[u.id] || 0); })) bip();
      });
    }
    function ouvrir(u) {
      vueChat({
        moi: 'd', uid: u.id, titre: u.nom, sous: 'Code ' + u.id + '-••••-••••',
        get muet() { return u.muet; },
        retour: function () { vueListe(); },
        menu: function () {
          var fermer = feuille([h('h2', {}, u.nom),
            h('button', { class: 'btn lt', onclick: function () { fermer(); fiche(u, function (f) { if (f) u.nom = f.nom; }); } }, 'Fiche de la vendeuse'),
            h('button', { class: 'btn lt', onclick: function () {
              fermer();
              api('/api/users/update', { body: { uid: u.id, muet: !u.muet } }).then(function (x) {
                if (x.ok) { u.muet = !u.muet; toast(u.muet ? 'Mise en silence' : 'Notifications réactivées'); } else toast(x.d.erreur || 'Erreur');
              });
            } }, u.muet ? 'Réactiver les notifications' : 'Mettre en silence'),
            h('button', { class: 'btn lt', onclick: function () { fermer(); chercher(u); } }, 'Chercher dans la conversation'),
            h('button', { class: 'btn lt', onclick: function () { fermer(); exporter(u); } }, 'Exporter la conversation'),
            h('button', { class: 'btn lt', onclick: function () {
              fermer();
              var duree = choixDuree();
              var f2 = feuille([h('h2', {}, 'Nouveau code pour ' + u.nom), h('p', {}, 'L\'ancien code ne marchera plus.'), duree,
                h('button', { class: 'btn', onclick: function () {
                  api('/api/users/code', { body: { uid: u.id, jours: +duree.value } }).then(function (r) { f2(); if (r.ok) afficherCode(u.nom, r.d.code); else toast(r.d.erreur || 'Erreur'); });
                } }, 'Créer le nouveau code'),
                h('button', { class: 'btn lt', onclick: function () { f2(); } }, 'Annuler')]);
            } }, 'Nouveau code d\'accès'),
            h('button', { class: 'btn rd', onclick: function () {
              fermer(); if (!confirm('Supprimer ' + u.nom + ' et toute la conversation ?')) return;
              api('/api/users/' + encodeURIComponent(u.id), { method: 'DELETE' }).then(function (r) { if (r.ok) vueListe(); else toast('Erreur'); });
            } }, 'Supprimer la conversation'),
            h('button', { class: 'btn lt', onclick: function () { fermer(); } }, 'Fermer')]);
        }
      });
    }
    charge();
    timers.push(setInterval(function () { if (!document.hidden) charge(); }, 8000));
    document.onvisibilitychange = function () { if (!document.hidden) charge(); };
  }

  function demarrer() {
    if (!S.tok) return vueLogin();
    pushSilencieux();
    if (S.role === 'd') vueListe(); else vueVendeuse();
  }

  if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}); }); }
  if (S.tok) {
    api('/api/me').then(function (r) { if (r.ok) { S.role = r.d.role; S.uid = r.d.uid; S.nom = r.d.nom; save(); demarrer(); } else if (r.s === 0) { demarrer(); } });
  } else { vueLogin(); }
})();
