'use strict';
// Module Évaluation : bouton « Mon bilan », import du PDF de quiz, affichage du bilan IA.
// Tout le texte venant de l'IA est inséré avec textContent (jamais en HTML brut).
(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const MAX_BYTES = 5 * 1024 * 1024;

  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = 'assets/feedback.css';
  document.head.append(css);

  const el = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };

  // ---------- Bouton dans le menu ----------
  const navBtn = el('button');
  navBtn.append('✦ ', el('span', 'Mon bilan'));
  document.querySelector('nav').append(navBtn);

  // ---------- Fenêtre ----------
  const dlg = el('dialog'); dlg.id = 'fb-modal';
  const close = el('button', '×', 'close'); close.setAttribute('aria-label', 'Fermer');

  const input = el('input', undefined, 'fb-sr');
  input.type = 'file'; input.accept = 'application/pdf,.pdf';
  const drop = el('label', undefined, 'fb-drop');
  const dropTitle = el('strong', 'Déposez votre PDF ici');
  const dropHint = el('small', 'ou cliquez pour le choisir · 5 Mo maximum');
  drop.append(input, el('span', '▤', 'fb-drop-icon'), dropTitle, dropHint);

  const go = el('button', 'Analyser mon quiz', 'btn');
  const status = el('p'); status.setAttribute('aria-live', 'polite');
  const out = el('div'); out.id = 'fb-out';

  dlg.append(
    close,
    el('h2', 'Mon bilan de quiz'),
    el('p', 'Importez le PDF obtenu avec « Exporter en PDF » après un quiz. L’IA analyse vos erreurs et propose un plan de révision.'),
    drop, go, status, out
  );
  document.body.append(dlg);

  navBtn.onclick = () => dlg.showModal();
  close.onclick = () => dlg.close();

  // ---------- Choix du fichier (clic ou glisser-déposer) ----------
  function showFile(f) {
    if (!f) {
      dropTitle.textContent = 'Déposez votre PDF ici';
      dropHint.textContent = 'ou cliquez pour le choisir · 5 Mo maximum';
      drop.classList.remove('has-file');
      return;
    }
    dropTitle.textContent = f.name;
    dropHint.textContent = Math.max(1, Math.round(f.size / 1024)) + ' Ko · prêt à analyser';
    drop.classList.add('has-file');
  }
  input.onchange = () => showFile(input.files[0]);
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => {
    const f = e.dataTransfer && e.dataTransfer.files[0];
    if (!f) return;
    try { const dt = new DataTransfer(); dt.items.add(f); input.files = dt.files; } catch { /* navigateur ancien */ }
    showFile(f);
  });

  function setStatus(text, isError) {
    status.textContent = text;
    status.className = isError ? 'err' : '';
  }

  // ---------- Affichage du bilan ----------
  const list = items => { const ul = el('ul'); items.forEach(i => ul.append(el('li', String(i)))); return ul; };
  const percent = score => { const m = /(\d+)\s*\/\s*(\d+)/.exec(String(score)); return m && +m[2] ? Math.round(100 * m[1] / m[2]) : 0; };
  const tone = level => { const l = String(level).toLowerCase(); return l.includes('avanc') ? 'high' : l.includes('inter') ? 'mid' : 'low'; };
  const verdict = p => p >= 80 ? 'Excellent travail !' : p >= 50 ? 'Bonne base, quelques points à consolider.' : 'Il reste du chemin : voici par où commencer.';

  function section(label, cls, node) {
    const s = el('div', undefined, 'fb-sec ' + cls);
    s.append(el('h3', label), node);
    out.append(s);
  }

  function render(d) {
    out.replaceChildren();
    const p = percent(d.score);

    const head = el('div', undefined, 'fb-head');
    const ring = el('div', undefined, 'fb-ring');
    ring.style.setProperty('--p', String(p));
    ring.append(el('b', String(d.score)));
    const meta = el('div', undefined, 'fb-meta');
    meta.append(
      el('span', 'Votre résultat', 'fb-kicker'),
      el('strong', verdict(p)),
      el('span', 'Niveau : ' + d.niveau, 'fb-level ' + tone(d.niveau))
    );
    head.append(ring, meta);
    out.append(head);

    if (d.points_forts?.length) section('Points forts', 'fb-good', list(d.points_forts));

    if (d.points_faibles?.length) {
      const box = el('div');
      d.points_faibles.forEach(w => {
        const card = el('div', undefined, 'fb-weak');
        const top = el('div', undefined, 'fb-weak-top');
        top.append(el('b', String(w.sujet || 'Sujet')));
        if (w.reussite) top.append(el('span', String(w.reussite), 'fb-chip'));
        card.append(top, el('p', String(w.explication || '')));
        box.append(card);
      });
      section('À retravailler', 'fb-bad', box);
    }

    if (d.erreurs_recurrentes?.length) section('Erreurs récurrentes', 'fb-err', list(d.erreurs_recurrentes));
    if (d.conseils?.length) section('Conseils', 'fb-tips', list(d.conseils));

    if (d.plan_revision?.length) {
      const ol = el('ol', undefined, 'fb-steps');
      let total = 0;
      d.plan_revision.forEach((s, i) => {
        const minutes = Number(s.duree_min) || 0;
        total += minutes;
        const li = el('li');
        const body = el('div');
        body.append(el('p', String(s.action || '')));
        if (minutes) body.append(el('span', '≈ ' + minutes + ' min', 'fb-chip'));
        li.append(el('span', String(s.etape || i + 1), 'fb-num'), body);
        ol.append(li);
      });
      const wrap = el('div');
      wrap.append(ol);
      if (total) wrap.append(el('p', 'Durée totale estimée : ' + total + ' min', 'fb-total'));
      section('Plan de révision', 'fb-plan', wrap);
    }

    const again = el('button', '↺ Analyser un autre quiz', 'fb-again');
    again.onclick = () => {
      out.replaceChildren(); input.value = ''; showFile(null); setStatus('');
      dlg.scrollTo({ top: 0, behavior: 'smooth' });
    };
    out.append(again);
  }

  // ---------- Envoi au serveur ----------
  go.onclick = async () => {
    out.replaceChildren();
    const f = input.files[0];
    if (!f) { setStatus('Choisissez d’abord un PDF.', true); return; }
    if (f.size > MAX_BYTES) { setStatus('PDF trop lourd (5 Mo maximum).', true); return; }

    const body = new FormData();
    body.append('quizpdf', f);
    go.disabled = true;
    setStatus('Analyse en cours… (10 à 30 secondes)');
    try {
      const res = await fetch('feedback-api.php', { method: 'POST', body, headers: { 'X-CSRF-Token': csrf } });
      let data;
      try { data = await res.json(); } catch { throw new Error('Réponse serveur invalide.'); }
      if (!res.ok) throw new Error(data.error || 'Une erreur est survenue.');
      setStatus('');
      render(data.feedback);
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
      setStatus(e.message, true);
    } finally {
      go.disabled = false;
    }
  };
})();
