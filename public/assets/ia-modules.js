'use strict';
// Modules 3 et 5 : bouton « Assistant IA 2 », questions sur ses cours avec sources (RAG),
// et matière de chaque cours avec correction par l'étudiant (classification).
// Le bouton et la fenêtre sont créés ici, comme pour le module Évaluation : aucun autre fichier JS n'est modifié.
// Tout texte venant du serveur ou de l'IA est inséré avec textContent (jamais en HTML brut).
(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;

  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = 'assets/ia-modules.css';
  document.head.append(css);

  const el = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  };
  const labelled = (text, control) => {
    const label = el('label', undefined, 'ia2-label');
    label.append(el('span', text), control);
    return label;
  };
  const pct = value => Math.round(Number(value) * 100);

  async function call(action, options = {}) {
    const res = await fetch(`ia-api.php?action=${action}`, {
      ...options, headers: { 'X-CSRF-Token': csrf, ...(options.headers || {}) },
    });
    if (res.status === 401) { location.href = 'login.php'; throw new Error('Veuillez vous reconnecter.'); }
    let data;
    try { data = await res.json(); } catch { throw new Error('Réponse serveur invalide.'); }
    if (!res.ok) throw new Error(data.error || 'Une erreur est survenue.');
    return data;
  }
  const post = (action, fields) => call(action, { method: 'POST', body: new URLSearchParams(fields) });

  // ---------- Bouton dans le menu, juste après « Assistant IA » ----------
  const navBtn = el('button');
  navBtn.type = 'button';
  navBtn.append('▣ ', el('span', 'Assistant IA 2'));
  const existing = document.querySelector('nav [data-tool="Assistant de cours"]');
  if (existing) existing.after(navBtn); else document.querySelector('nav').append(navBtn);

  // ---------- Fenêtre ----------
  const dlg = el('dialog'); dlg.id = 'ia2-modal';
  const close = el('button', '×', 'close'); close.setAttribute('aria-label', 'Fermer'); close.type = 'button';
  const status = el('p'); status.setAttribute('aria-live', 'polite');
  const setStatus = (text, isError = false) => { status.textContent = text; status.className = isError ? 'err' : ''; };

  // Section 1 : question (RAG)
  const askSec = el('section', undefined, 'ia2-sec');
  askSec.append(el('h3', '1. Poser une question'));
  const scope = el('select'); scope.setAttribute('aria-label', 'Mode de réponse');
  scope.add(new Option('Mes cours', 'course'));
  scope.add(new Option('Connaissance générale (Ollama)', 'general'));
  const courseSel = el('select'); courseSel.setAttribute('aria-label', 'Cours à interroger');
  const question = el('textarea'); question.rows = 3; question.maxLength = 500;
  question.placeholder = 'Ex. : quelles sont les étapes du cycle de vie d’un bug ?';
  question.setAttribute('aria-label', 'Votre question');
  const askBtn = el('button', 'Poser la question', 'btn'); askBtn.type = 'button';
  const hint = el('p', undefined, 'ia2-help');
  const answer = el('div', undefined, 'ia2-answer'); answer.setAttribute('aria-live', 'polite');
  const historyBox = el('div', undefined, 'ia2-history');
  askSec.append(labelled('Mode de réponse', scope), labelled('Cours', courseSel), labelled('Votre question', question), askBtn, hint, answer, historyBox);

  // Section 2 : matière des cours (classification)
  const catSec = el('section', undefined, 'ia2-sec');
  catSec.append(el('h3', '2. Matière de mes cours'),
    el('p', 'L’IA détecte la matière de chaque cours à l’import. Corrigez-la si besoin : votre choix est enregistré et aide à améliorer le modèle.', 'ia2-help'));
  const courseList = el('div', undefined, 'ia2-courses');
  catSec.append(courseList);

  dlg.append(close, el('h2', 'Assistant IA 2'),
    el('p', 'Posez une question sur vos cours : la réponse est construite uniquement à partir de vos documents, avec les sources citées.'),
    status, askSec, catSec);
  document.body.append(dlg);

  let state = { courses: [], categories: { categories: [], unclassified: 'À classer' } };

  // ---------- Données ----------
  async function refresh() {
    const [courses, categories] = await Promise.all([call('courses'), call('categories')]);
    state = { courses: courses.courses, categories };
    fillCourseOptions();
    renderCourses();
  }

  function fillCourseOptions() {
    const keep = courseSel.value;
    const ready = state.courses.filter(c => c.indexed);
    courseSel.replaceChildren();
    courseSel.add(new Option('Tous mes cours indexés', 'all'));
    ready.forEach(c => courseSel.add(new Option(c.name, String(c.id))));
    if ([...courseSel.options].some(o => o.value === keep)) courseSel.value = keep;
    updateAskState();
  }

  /** « Poser la question » n'est actif que s'il existe un cours indexé (sauf en connaissance générale). */
  function updateAskState() {
    const generalMode = scope.value === 'general';
    const ready = state.courses.some(c => c.indexed);
    askBtn.disabled = !generalMode && !ready;
    if (!generalMode && !state.courses.length) hint.textContent = 'Importez un cours (TXT, DOCX ou PDF) pour poser vos questions.';
    else if (!generalMode && !ready) hint.textContent = 'Aucun cours n’est encore indexé. Utilisez le bouton « Indexer » dans la section 2.';
    else hint.textContent = '';
  }

  // ---------- Question (module 3) ----------
  scope.onchange = () => {
    courseSel.disabled = scope.value === 'general';
    updateAskState();
  };

  function renderAnswer(data) {
    answer.replaceChildren();
    answer.append(el('div', data.answer, data.abstained ? 'ia2-text abstained' : 'ia2-text'));
    if (data.sources && data.sources.length && !data.abstained) {
      const list = el('ul', undefined, 'ia2-sources');
      list.setAttribute('aria-label', 'Sources');
      data.sources.forEach(s => {
        const item = el('li');
        item.append(
          el('b', `[Source ${s.number}] ${s.title}${s.page ? ` — p. ${s.page}` : ''}`),
          el('span', s.excerpt),
          el('small', `Pertinence : ${pct(s.score)} %`)
        );
        list.append(item);
      });
      answer.append(list);
    }
    const meta = [`Modèle : ${data.backend}`, `${(data.latency_ms / 1000).toFixed(2)} s`];
    if (data.cache_hit) meta.push('réponse en cache');
    answer.append(el('p', meta.join(' · '), 'ia2-meta'));
  }

  async function loadHistory() {
    try {
      const data = await call('history');
      historyBox.replaceChildren();
      if (!data.history.length) return;
      historyBox.append(el('h4', 'Vos dernières questions'));
      data.history.forEach(h => {
        const b = el('button', `${h.question}${h.course ? ` — ${h.course}` : ''}`, 'textbtn');
        b.type = 'button';
        b.title = h.answer;
        b.onclick = () => { question.value = h.question; question.focus(); };
        historyBox.append(b);
      });
    } catch {
      historyBox.replaceChildren();
    }
  }

  askBtn.onclick = async () => {
    const text = question.value.trim();
    if (text.length < 3) { setStatus('Saisissez une question d’au moins 3 caractères.', true); return; }
    askBtn.disabled = true;
    setStatus('');
    answer.replaceChildren(el('p', 'Recherche dans vos cours et rédaction de la réponse…', 'ia2-help'));
    try {
      const data = await post('ask', { question: text, course_id: courseSel.value, scope: scope.value });
      renderAnswer(data);
      loadHistory();
    } catch (e) {
      answer.replaceChildren();
      setStatus(e.message, true);
    } finally {
      updateAskState();
    }
  };

  // ---------- Matière des cours (module 5) ----------
  function categoryHint(c) {
    const unclassified = state.categories.unclassified;
    if (c.category_source === 'etudiant') return 'Matière choisie par vous.';
    if (c.type !== unclassified && c.category_source === 'auto') {
      return `Matière détectée : ${c.type} (confiance ${pct(c.category_confidence)} %).`;
    }
    if (c.suggestion && c.category_confidence !== null) {
      return `Le modèle hésite : suggestion « ${c.suggestion} » (confiance ${pct(c.category_confidence)} %), trop faible pour être appliquée.`;
    }
    return 'Matière non déterminée. Choisissez-la ci-dessous.';
  }

  function courseRow(c) {
    const row = el('div', undefined, 'ia2-course');
    const head = el('div', undefined, 'ia2-course-head');
    head.append(el('b', c.name), el('span', c.indexed ? '✓ Prêt pour l’assistant' : 'Non indexé', c.indexed ? 'ia2-chip ok' : 'ia2-chip warn'));
    row.append(head, el('p', categoryHint(c), 'ia2-help'));

    if (!c.indexed) {
      const retry = el('button', 'Indexer', 'mini'); retry.type = 'button';
      retry.onclick = () => reindex(c, retry);
      row.append(retry);
    }

    const categories = state.categories.categories;
    const select = el('select'); select.setAttribute('aria-label', `Matière de ${c.name}`);
    const preset = categories.includes(c.type) ? c.type : (categories.includes(c.suggestion) ? c.suggestion : '');
    if (!preset) select.add(new Option('Choisissez une matière…', '', true, true));
    categories.forEach(name => select.add(new Option(name, name)));
    if (preset) select.value = preset;

    const save = el('button', 'Enregistrer la matière', 'mini'); save.type = 'button';
    save.onclick = () => saveCategory(c, select.value, save);
    const controls = el('div', undefined, 'ia2-row');
    controls.append(labelled('Matière', select), save);
    row.append(controls);

    const remove = el('button', 'Supprimer ce cours', 'mini ia2-delete'); remove.type = 'button';
    remove.onclick = () => removeCourse(c, remove);
    row.append(remove);
    return row;
  }

  function renderCourses() {
    courseList.replaceChildren();
    if (!state.courses.length) {
      courseList.append(el('p', 'Aucun cours pour l’instant.', 'ia2-help'));
      return;
    }
    state.courses.forEach(c => courseList.append(courseRow(c)));
  }

  async function saveCategory(course, value, button) {
    if (!value) { setStatus('Choisissez une matière dans la liste.', true); return; }
    button.disabled = true;
    try {
      const data = await post('category', { course_id: String(course.id), category: value });
      setStatus(data.message);
      await refresh();
    } catch (e) {
      setStatus(e.message, true);
      button.disabled = false;
    }
  }

  async function reindex(course, button) {
    button.disabled = true;
    setStatus('Indexation du cours en cours…');
    try {
      const data = await post('reindex', { course_id: String(course.id) });
      setStatus(data.message);
      await refresh();
    } catch (e) {
      setStatus(e.message, true);
      button.disabled = false;
    }
  }

  async function removeCourse(course, button) {
    if (!window.confirm(`Supprimer définitivement « ${course.name} » ? Son index et le document seront effacés.`)) return;
    button.disabled = true;
    try {
      const data = await post('delete', { course_id: String(course.id) });
      setStatus(data.message);
      await refresh();
      // La liste principale (app.js) est mise à jour aussi.
      if (typeof window.loadCourses === 'function') window.loadCourses().catch(() => {});
    } catch (e) {
      setStatus(e.message, true);
      button.disabled = false;
    }
  }

  // ---------- Ouverture et fermeture ----------
  navBtn.onclick = () => {
    setStatus('');
    answer.replaceChildren();
    dlg.showModal();
    refresh().catch(e => setStatus(e.message, true));
    loadHistory();
    question.focus();
  };
  close.onclick = () => dlg.close();
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
})();
