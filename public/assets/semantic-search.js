'use strict';
// Module 2 : bouton « Recherche sémantique » dans le menu et fenêtre de recherche.
// Le bouton, la fenêtre et le style sont créés ici : aucun autre fichier JS n'est modifié.
// Les textes renvoyés par le serveur sont insérés avec textContent, jamais en HTML brut.
(() => {
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = 'assets/semantic-search.css';
  document.head.append(css);

  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const labelled = (text, control) => {
    const label = el('label', undefined, 'ss-label');
    label.append(el('span', text), control);
    return label;
  };

  // ---------- Bouton dans le menu, juste après « Recherche » ----------
  const navBtn = el('button');
  navBtn.type = 'button';
  navBtn.append('⌕ ', el('span', 'Recherche sémantique'));
  const existing = document.querySelector('nav [data-tool="Recherche intelligente"]');
  if (existing) existing.after(navBtn); else document.querySelector('nav').append(navBtn);

  // ---------- Fenêtre ----------
  const dlg = el('dialog');
  dlg.id = 'semantic-search-modal';
  const heading = el('h2', 'Recherche sémantique');
  heading.id = 'semantic-search-title';
  dlg.setAttribute('aria-labelledby', heading.id);

  const close = el('button', '×', 'close');
  close.type = 'button';
  close.setAttribute('aria-label', 'Fermer');

  const intro = el(
    'p',
    'Cherchez par le sens dans vos cours TXT et DOCX. Le service local classe les passages les plus proches de votre question, même si les mots exacts sont différents.'
  );
  const note = el(
    'p',
    'Les PDF ne sont pas encore lus par ce module. Le premier appel peut charger le modèle local (quelques dizaines de secondes).',
    'ss-note'
  );

  const form = el('form');
  form.id = 'semantic-search-form';
  const query = el('input');
  query.type = 'search';
  query.id = 'semantic-search-query';
  query.name = 'q';
  query.maxLength = 200;
  query.minLength = 2;
  query.required = true;
  query.autocomplete = 'off';
  query.placeholder = 'Ex. : comment éviter le sur-apprentissage ?';
  const topk = el('select');
  topk.id = 'semantic-search-topk';
  topk.name = 'top_k';
  [5, 3, 10].forEach(value => topk.add(new Option(`${value} passages`, String(value))));
  const submit = el('button', 'Rechercher', 'btn');
  submit.type = 'submit';
  form.append(
    labelled('Votre question', query),
    labelled('Nombre de passages', topk),
    submit
  );

  const status = el('p', undefined, 'ss-status');
  status.setAttribute('aria-live', 'polite');
  const results = el('div', undefined, 'ss-results');
  const setStatus = (text, isError = false) => {
    status.textContent = text;
    status.className = isError ? 'ss-status ss-error' : 'ss-status';
  };

  dlg.append(close, heading, intro, note, form, status, results);
  document.body.append(dlg);

  const open = () => {
    if (!dlg.open) dlg.showModal();
    query.focus();
  };
  navBtn.addEventListener('click', open);
  close.addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', event => {
    if (event.target === dlg) dlg.close();
  });

  const render = data => {
    results.replaceChildren();
    const found = Array.isArray(data.results) ? data.results : [];
    const parts = [found.length === 0 ? 'Aucun passage trouvé.' : `${found.length} passage(s) trouvé(s).`];
    if (Number(data.skipped) > 0) parts.push(`${Number(data.skipped)} cours non lisible(s) ignoré(s).`);
    if (data.backend) parts.push(`Moteur : ${String(data.backend).toUpperCase()}.`);
    if (Number(data.passages) > 0) parts.push(`${Number(data.passages)} passage(s) indexé(s).`);
    setStatus(parts.join(' '));

    found.forEach(hit => {
      const card = el('article', undefined, 'ss-hit');
      const head = el('div', undefined, 'ss-hit-head');
      head.append(el('b', hit.course_name || 'Cours'));
      head.append(el('span', `Similarité ${Number(hit.score || 0).toFixed(3)}`, 'ss-score'));
      const passage = el('p', hit.passage || '');
      passage.className = 'ss-passage';
      card.append(head, passage);
      results.append(card);
    });
  };

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const question = query.value.trim();
    if (question.length < 2) {
      setStatus('Saisissez au moins 2 caractères.', true);
      query.focus();
      return;
    }
    submit.disabled = true;
    results.replaceChildren();
    setStatus('Recherche en cours… Le premier appel peut charger le modèle local.');
    try {
      const url = `semantic-search-api.php?q=${encodeURIComponent(question)}&top_k=${encodeURIComponent(topk.value)}`;
      const response = await fetch(url, { headers: { Accept: 'application/json' } });
      if (response.status === 401) {
        location.href = 'login.php';
        return;
      }
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error('Réponse serveur invalide.');
      }
      if (!response.ok) throw new Error(data.error || 'Une erreur est survenue.');
      render(data);
    } catch (error) {
      setStatus(error.message || 'Recherche impossible.', true);
    } finally {
      submit.disabled = false;
    }
  });
})();
