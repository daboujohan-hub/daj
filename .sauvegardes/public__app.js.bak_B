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
    contenu.forEach(function (c) { s.appendChild(c); });
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
      h('button', { class: 'alt', onclick: function () { vueLogin(!dev); } }, dev ? 'Je suis une vendeuse' : 'Espace développeur')));
    setTimeout(function () { champ.focus(); }, 50);
  }

  /* ---------- discussion ---------- */
  function vueChat(o) {
    stopTimers(); root.innerHTML = '';
    var seen = {}, dernier = 0, lu_v = 0, lu_dev = 0, jourPrec = '', img = '', enCours = false;
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
      if (m.img) {
        var src = m.img.indexOf('data:') === 0 ? m.img : '/img/' + m.img + '?t=' + encodeURIComponent(S.tok);
        var im = h('img', { src: src, alt: 'Photo', loading: 'lazy' });
        im.addEventListener('click', function () {
          var v = h('div', { class: 'viewer', onclick: function () { v.parentNode.removeChild(v); } }, h('img', { src: src, alt: '' }));
          document.body.appendChild(v);
        });
        b.appendChild(im);
      }
      if (m.t) b.appendChild(document.createTextNode(m.t));
      b.appendChild(h('span', { class: 'mt' }, (m.ts ? heure(m.ts) : 'envoi…') + (m.ts ? vu(m) : '')));
      zone.appendChild(b);
      return b;
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
    function q(apres) { return '/api/msgs?apres=' + apres + (o.uid ? '&uid=' + encodeURIComponent(o.uid) : ''); }
    function charger(apres, premier) {
      return api(q(apres)).then(function (r) {
        if (!r.ok) { if (premier) toast(r.d.erreur || 'Erreur'); return; }
        lu_v = r.d.lu_v; lu_dev = r.d.lu_dev;
        var nouveaux = (r.d.msgs || []).filter(function (m) { return !seen[m.seq]; });
        ajouter(r.d.msgs || []); ticks();
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
    ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 130) + 'px'; });
    function envoyer() {
      var t = ta.value.trim(), im = img;
      if ((!t && !im) || enCours) return;
      enCours = true; env.disabled = true;
      if (vide.parentNode) vide.parentNode.removeChild(vide);
      var p = bulle({ de: o.moi, t: t, img: im }, true); bas();
      ta.value = ''; ta.style.height = 'auto'; img = ''; montrerPrev();
      var body = { texte: t, image: im || undefined }; if (o.uid) body.uid = o.uid;
      api('/api/send', { body: body }).then(function (r) {
        enCours = false; env.disabled = false;
        if (p.parentNode) p.parentNode.removeChild(p);
        if (!r.ok) { toast(r.d.erreur || 'Pas envoyé'); ta.value = t; img = im; montrerPrev(); if (!dernier) zone.appendChild(vide); return; }
        ajouter([r.d.msg]); bas();
      });
    }
    env.addEventListener('click', envoyer);

    var tete = h('div', { class: 'bar' },
      o.retour ? h('button', { class: 'ib', 'aria-label': 'Retour', onclick: o.retour }, '←') : null,
      h('div', { class: 'av' }, o.moi === 'v' ? 'D' : initiale(o.titre)),
      h('div', { class: 't' }, h('b', {}, o.titre), h('small', {}, o.sous || '')),
      o.menu ? h('button', { class: 'ib', 'aria-label': 'Menu', onclick: o.menu }, '⋮') : null,
      o.quitter ? h('button', { class: 'ib', 'aria-label': 'Quitter', onclick: o.quitter }, '⎋') : null);
    root.appendChild(tete); root.appendChild(zone); root.appendChild(prev);
    root.appendChild(h('div', { class: 'compose' }, cam, fic, ta, env));
    charger(0, true);
    timers.push(setInterval(function () { if (!document.hidden) charger(dernier, false); }, 4000));
    document.onvisibilitychange = function () { if (!document.hidden) { charger(dernier, false); marquer(); } };
  }

  /* ---------- vendeuse ---------- */
  function vueVendeuse() {
    vueChat({
      moi: 'v', uid: '', titre: 'DAJ', sous: 'Abou Johan · développeur',
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
  function nouvelle(apres) {
    var champ = h('input', { type: 'text', placeholder: 'Nom de la vendeuse ou de la boutique', maxlength: '60' });
    var fermer = feuille([h('h2', {}, 'Nouvelle vendeuse'), h('p', {}, 'Un code d\'accès est créé pour elle.'), champ,
      h('button', { class: 'btn', onclick: function () {
        var nom = champ.value.trim(); if (nom.length < 2) { toast('Écris le nom'); return; }
        api('/api/users', { body: { nom: nom } }).then(function (r) {
          if (!r.ok) { toast(r.d.erreur || 'Erreur'); return; }
          fermer(); afficherCode(r.d.nom, r.d.code); apres();
        });
      } }, 'Créer')]);
    setTimeout(function () { champ.focus(); }, 60);
  }
  function vueListe() {
    stopTimers(); root.innerHTML = ''; document.onvisibilitychange = null;
    var liste = h('div', { class: 'list' });
    var fab = h('button', { class: 'fab', onclick: function () { nouvelle(charge); } }, '+ Vendeuse');
    root.appendChild(h('div', { class: 'bar' }, h('div', { class: 'av' }, 'D'),
      h('div', { class: 't' }, h('b', {}, 'DAJ'), h('small', {}, 'Mes vendeuses')),
      h('button', { class: 'ib', 'aria-label': 'Quitter', onclick: function () { if (confirm('Te déconnecter ?')) sortir(); } }, '⎋')));
    root.appendChild(h('div', { class: 'wrap' }, liste, fab));
    function charge() {
      api('/api/threads').then(function (r) {
        if (!r.ok) return;
        var us = r.d.users || [], tot = 0;
        liste.innerHTML = '';
        if (!us.length) liste.appendChild(h('div', { class: 'vide' }, 'Aucune vendeuse pour le moment. Appuie sur « + Vendeuse ».'));
        us.forEach(function (u) {
          tot += u.unread_dev || 0;
          liste.appendChild(h('button', { class: 'row', onclick: function () { ouvrir(u); } },
            h('div', { class: 'av' }, initiale(u.nom)),
            h('div', { class: 'm' }, h('b', {}, u.nom),
              h('span', {}, u.last_text ? (u.last_from === 'd' ? 'Toi : ' : '') + u.last_text : 'Aucun message')),
            h('div', { class: 'r' }, h('span', {}, u.last_text ? courtLe(u.last_ts) : ''),
              u.unread_dev > 0 ? h('div', { class: 'badge' }, u.unread_dev) : null)));
        });
        titre(tot);
      });
    }
    function ouvrir(u) {
      vueChat({
        moi: 'd', uid: u.id, titre: u.nom, sous: 'Code ' + u.id + '-••••-••••',
        retour: function () { vueListe(); },
        menu: function () {
          var fermer = feuille([h('h2', {}, u.nom),
            h('button', { class: 'btn lt', onclick: function () {
              fermer(); if (!confirm('Créer un nouveau code ? L\'ancien ne marchera plus.')) return;
              api('/api/users/code', { body: { uid: u.id } }).then(function (r) { if (r.ok) afficherCode(u.nom, r.d.code); else toast(r.d.erreur || 'Erreur'); });
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
    if (S.role === 'd') vueListe(); else vueVendeuse();
  }

  if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}); }); }
  if (S.tok) {
    api('/api/me').then(function (r) { if (r.ok) { S.role = r.d.role; S.uid = r.d.uid; S.nom = r.d.nom; save(); demarrer(); } else if (r.s === 0) { demarrer(); } });
  } else { vueLogin(); }
})();
