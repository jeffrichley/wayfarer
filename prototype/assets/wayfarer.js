/* Wayfarer · shared data and shell
   Sample content: the Galley repo, with two efforts on the line.
   Frozen reference: every screen renders one fixed moment, and nothing
   a click does is remembered. */
(function () {
  'use strict';

  const esc = (str) => String(str).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* ─── efforts ────────────────────────────────────────────────────── */
  const EFFORTS = {
    acx: {
      id: 'acx', name: 'ACX compliance before delivery', map: 112, charted: '3 Sep',
      destination: 'A spec for pre-delivery checks that catch ACX rejections before an author submits.',
      spec: { n: 124, name: 'Pre-delivery compliance checks' },
    },
    casting: {
      id: 'casting', name: 'Per-chapter voice casting', map: 147, charted: '9 Sep',
      destination: "A spec for letting a character's voice change between chapters, ready for /to-spec.",
    },
    sample: {
      id: 'sample', name: 'Choosing the retail sample', map: 160, charted: '10 Sep',
      destination: 'A spec for helping an author choose their ACX retail sample, ready for /to-spec.',
      spec: { n: 168, name: 'Retail sample suggestions' },
      last: { n: 166, name: 'Does the sample follow later edits to its chapter?' },
    },
  };

  /* Map decisions for ACX, referenced by name from the spec and tickets. */
  const ACX_DECISIONS = {
    113: 'What does ACX reject?',
    114: 'Can loudness be measured in the browser, or only in the render worker?',
    115: 'Build fixture chapters that each break one ACX rule',
    116: 'Which checks block delivery, and which only warn?',
    117: 'Does Galley fix problems, or only report them?',
    121: 'Where do checks run — on render or on demand?',
    122: 'How should a failing chapter explain itself?',
  };

  /* ─── tickets from /to-tickets ───────────────────────────────────── */
  const TICKETS = {
    125: {
      name: 'Extract the audio analysis pass from the render worker', short: 'Extract the analysis pass',
      prefactor: true, blockedBy: [], state: 'landed', pr: 134, wt: 'analysis-pass', landedAt: 'yesterday 16:40',
      build: "Rendering a chapter produces an analysis result beside the audio, measured in one pass and cached against the rendered audio's hash. Nothing reads it yet; renders behave exactly as before.",
      criteria: [
        { text: 'Every render produces an analysis result for each chapter', done: true, test: 'produces an analysis result per rendered chapter' },
        { text: 'Re-rendering unchanged audio reuses the cached result', done: true, test: 'reuses analysis when the audio hash is unchanged' },
        { text: 'Render output is unchanged for existing books', done: true, test: 'renders the sample book byte-identical to main' },
      ],
      stories: [1, 10, 15], decisions: [114, 121],
    },
    126: {
      name: 'Flag loudness outside −23 to −18 dB RMS', short: 'Flag loudness',
      blockedBy: [125], state: 'landed', pr: 136, wt: 'loudness-rms', landedAt: 'yesterday 22:14',
      build: "An author opens Compliance and sees each chapter's RMS loudness against ACX's range, with a plain-language reason and a timestamp for chapters that fall outside it.",
      criteria: [
        { text: 'Chapters outside −23 to −18 dB RMS fail, showing the measured value and the range', done: true, test: 'flags the quiet and loud fixtures' },
        { text: 'The Compliance page lists the loudness check for every chapter', done: true, test: 'lists loudness per chapter' },
        { text: 'Failures read in plain language, without audio jargon', done: true, test: 'explains loudness failures for authors' },
      ],
      stories: [1, 2, 9], decisions: [113, 122],
    },
    127: {
      name: 'Flag peaks above −3 dB', short: 'Flag peaks',
      blockedBy: [126], state: 'review', pr: 141, wt: 'peak-ceiling',
      build: 'A chapter whose loudest moment rises above −3 dB fails, and the failure says when that moment happens so the author can listen to it.',
      criteria: [
        { text: 'Chapters with a peak above −3 dB fail the check', done: true, test: 'flags the clipped fixture above -3 dB' },
        { text: 'The clean fixture passes', done: true, test: 'passes the clean fixture' },
        { text: 'A failure names the timestamp of the loudest peak', done: 'part', test: 'reports when the loudest peak happens' },
        { text: 'The Compliance page shows the reason in plain language', done: true, test: 'renders the peak reason' },
      ],
      stories: [3, 4], decisions: [113, 122],
    },
    128: {
      name: 'Flag a noise floor above −60 dB', short: 'Flag noise floor',
      blockedBy: [126], state: 'building', wt: 'noise-floor',
      build: 'A chapter with hiss or room noise above −60 dB fails, with the measured floor, the limit, and where the noise is loudest.',
      criteria: [
        { text: 'Measure the noise floor of every chapter', done: true, test: 'measures noise floor of the hiss fixture' },
        { text: 'Chapters above −60 dB fail the check', done: true, test: 'flags the hiss fixture at -54 dB' },
        { text: 'Failures explain the value, the limit, and the timestamp', done: true, test: 'explains a noise floor failure' },
        { text: 'The clean fixture passes', done: false, test: 'passes the clean fixture' },
      ],
      stories: [5], decisions: [113, 122],
    },
    129: {
      name: 'Flag chapters longer than 120 minutes', short: 'Flag long chapters',
      blockedBy: [125], state: 'building', wt: 'chapter-duration',
      build: "A chapter over 120 minutes fails with its length against ACX's limit and a note to split it at a scene break before submitting.",
      criteria: [
        { text: 'Chapters over 120 minutes fail the check', done: true, test: 'flags the 124-minute fixture' },
        { text: "The failure shows the chapter's length against the limit", done: false, test: 'shows length against the limit' },
        { text: 'A 119-minute chapter passes', done: false, test: 'passes a chapter just under the limit' },
      ],
      stories: [7], decisions: [113],
    },
    130: {
      name: 'Require opening and closing credits', short: 'Require credits',
      blockedBy: [], state: 'asking', wt: 'credits',
      build: 'A book without opening or closing credits fails a check that names which credit is missing.',
      criteria: [
        { text: 'EPUB books without credits in front or back matter fail', done: true, test: 'flags an EPUB with no closing credits' },
        { text: 'The failure names which credit is missing', done: true, test: 'names the missing credit' },
        { text: 'DOCX books follow the agreed rule', done: false, test: 'waiting on your answer' },
      ],
      stories: [8], decisions: [113],
      question: {
        asked: '09:18',
        text: "DOCX manuscripts don't mark front and back matter, so for those books I can only guess where credits would be. Should a DOCX book with no credits I can find fail like EPUB, or warn so the author can confirm?",
        options: [
          { value: 'fail', title: 'Fail, same as EPUB', sub: 'Stricter. Some DOCX books with real credits may fail until the author marks them.' },
          { value: 'warn', title: 'Warn, and ask the author to confirm', sub: "Export stays unlocked for this check once they confirm credits are there." },
        ],
      },
    },
    131: {
      name: 'Check room tone at the head and tail of each chapter', short: 'Check room tone',
      blockedBy: [128], state: 'blocked',
      build: 'Chapters without 0.5–1 second of room tone at the head, or 1–5 seconds at the tail, fail with how much tone was found.',
      criteria: [
        { text: 'Measure room tone at the head and tail of every chapter', done: false },
        { text: 'Chapters outside the head or tail range fail, showing what was found', done: false },
        { text: 'Room tone is not counted as noise by the noise floor check', done: false },
      ],
      stories: [6], decisions: [113],
    },
    132: {
      name: 'Show compliance status on My Books', short: 'Status on My Books',
      blockedBy: [126], state: 'takeable', wt: 'books-status',
      build: 'Each book on My Books shows whether every chapter passes the checks built so far, and how many chapters fail.',
      criteria: [
        { text: 'A book whose chapters all pass shows as ready', done: false },
        { text: 'A book with failures shows how many chapters fail', done: false },
        { text: 'A book still rendering shows its checks as pending', done: false },
      ],
      stories: [13], decisions: [116],
    },
    133: {
      name: 'Block ACX export while any chapter fails a check', short: 'Block ACX export',
      blockedBy: [127, 128, 129, 130, 131], state: 'blocked',
      build: 'The ACX export stays locked until every blocking check passes, and lists exactly what still blocks it.',
      criteria: [
        { text: 'Export is locked while any blocking check fails', done: false },
        { text: 'The locked export lists each failing check by chapter', done: false },
        { text: 'A missing retail sample warns but does not lock export', done: false },
      ],
      stories: [11, 12], decisions: [116, 117],
    },
  };
  const ORDER = [125, 126, 127, 128, 129, 130, 131, 132, 133];

  const STATES = {
    landed:   { glyph: 'st-done',     word: 'Landed' },
    review:   { glyph: 'st-review',   word: 'In review' },
    building: { glyph: 'st-building', word: 'Building' },
    asking:   { glyph: 'st-ask',      word: 'Waiting on you' },
    takeable: { glyph: 'st-take',     word: 'Takeable now' },
    blocked:  { glyph: 'st-blocked',  word: 'Blocked' },
  };

  function ticket(n) {
    const base = TICKETS[n];
    if (!base) return null;
    const t = Object.assign({ n: n }, base);
    if (t.state === 'blocked' && t.blockedBy.every((b) => ticket(b).state === 'landed')) t.state = 'takeable';
    return t;
  }
  function tickets() { return ORDER.map(ticket); }
  function blocks(n) { return ORDER.filter((m) => TICKETS[m].blockedBy.indexOf(n) !== -1); }
  function counts() {
    const c = { landed: 0, review: 0, building: 0, asking: 0, takeable: 0, blocked: 0 };
    tickets().forEach((t) => { c[t.state]++; });
    return c;
  }
  function glyph(state, extra) { return '<span class="st ' + STATES[state].glyph + (extra ? ' ' + extra : '') + '" aria-hidden="true"></span>'; }

  /* Casting map's one HITL ticket that can be answered from the desk. */
  const CASTING_GRILL = {
    n: 152,
    name: 'What happens to chapters already rendered when an override changes?',
    opener: "Start with the simple case. An author has rendered the whole book, then overrides Eliot's voice from chapter 7 onward. Should chapters 7 and later re-render straight away, or wait until the author asks?",
    followUp: "That settles re-rendering for chapters Eliot speaks in. What about chapters where he only appears inside the narrator's lines — do those count as changed?",
  };

  function needsYou(opts) {
    opts = opts || {};
    const items = [];
    const t127 = ticket(127), t130 = ticket(130);
    if (t127.state === 'review') items.push({ key: 'pr-141', kind: 'Review', effort: 'acx', ticket: 127, name: t127.name, ask: '/code-review found one gap against the spec', unblocks: 1 });
    if (t130.state === 'asking') items.push({ key: 'q-130', kind: 'Question', effort: 'acx', ticket: 130, name: t130.name, ask: 'Should DOCX books without credits fail or warn?', unblocks: 1 });
    if (!opts.grilled) items.push({ key: 'g-152', kind: 'Grilling', effort: 'casting', ticket: 152, name: CASTING_GRILL.name, ask: 'HITL grilling ticket at the frontier', unblocks: 2, fog: true });
    const stage = opts.sampleStage || 'last';
    if (stage === 'last') items.push({ key: 'w-166', kind: 'Grilling', effort: 'sample', ticket: 166, name: EFFORTS.sample.last.name, ask: 'In session with you. The last open ticket on its map', unblocks: 1.5, unblocksText: 'Clears the way', href: 'wayfinder-map.html?effort=sample#166' });
    if (stage === 'clear') items.push({ key: 's-seam', kind: 'Seam', effort: 'sample', name: EFFORTS.sample.name, ask: '/to-spec needs you to agree the seam before it writes', unblocks: 1.5, unblocksText: 'Unblocks the spec', href: 'wayfinder-map.html?effort=sample' });
    return items;
  }

  /* ─── theme: light chart or night chart ──────────────────────────────
     Follows the system until the reader picks one, then remembers it.
     The <head> of every page applies the saved choice before first paint. */
  const THEME_KEY = 'wayfarer.theme';
  const systemDark = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  let onSystemTheme = null;
  function savedTheme() { try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; } }
  function currentTheme() { return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
  function setTheme(theme, remember) {
    const root = document.documentElement;
    root.classList.add('theme-fade');
    if (theme === 'dark') root.setAttribute('data-theme', 'dark');
    else root.removeAttribute('data-theme');
    if (remember) { try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* storage blocked */ } }
    clearTimeout(setTheme.t);
    setTheme.t = setTimeout(() => root.classList.remove('theme-fade'), 350);
  }
  if (systemDark) systemDark.addEventListener('change', (e) => {
    if (savedTheme()) return;
    setTheme(e.matches ? 'dark' : 'light', false);
    if (onSystemTheme) onSystemTheme();
  });
  const SUN = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="3"/><path d="M8 1.2v1.7M8 13.1v1.7M1.2 8h1.7M13.1 8h1.7M3.2 3.2l1.2 1.2M11.6 11.6l1.2 1.2M3.2 12.8l1.2-1.2M11.6 4.4l1.2-1.2"/></svg>';
  const MOON = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M13.4 10.2A5.8 5.8 0 0 1 5.8 2.6a5.8 5.8 0 1 0 7.6 7.6z"/></svg>';

  /* ─── shell: topbar ──────────────────────────────────────────────── */
  const MARK = '<svg class="wordmark-mark" viewBox="0 0 18 18" fill="none" aria-hidden="true"><circle cx="3.5" cy="9" r="2.5" fill="currentColor"/><path d="M6 9h6" stroke="currentColor" stroke-width="1.5"/><circle cx="14.5" cy="9" r="2.4" stroke="currentColor" stroke-width="1.5"/></svg>';
  const CARET = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';

  function effortHref(id, page) {
    if (id === 'casting') return 'wayfinder-map.html?effort=casting';
    if (id === 'sample') return 'wayfinder-map.html?effort=sample';
    if (page === 'wayfinder') return 'wayfinder-map.html?effort=acx';
    if (page && page !== 'index') return { spec: 'spec-reader.html', tickets: 'ticket-graph.html', build: 'live-build.html', review: 'review-desk.html' }[page];
    return 'live-build.html';
  }

  /* The retail sample map is one ticket from a clear way. Its page moves it
     forward as you close that ticket, agree the seam and slice the spec, and
     passes the stage it reached as opts.sampleStage. */
  function renderTopbar(opts) {
    const el = document.getElementById('topbar');
    if (!el) return;
    const effort = opts.effort ? EFFORTS[opts.effort] : null;
    const c = counts();
    const needs = needsYou(opts).length;
    const working = c.building + 1; /* + the research subagent on the casting map */
    const acxMeta = c.landed + ' of 9 landed · ' + c.building + ' building';
    const repo = opts.repo || 'galley';
    const sampleMenu = {
      last: ['asking', 'Charting the way · one ticket left, in session with you'],
      clear: ['asking', 'The way is clear · /to-spec waiting on you'],
      written: ['landed', 'Spec written · ready to slice into tickets'],
      slicing: ['building', 'Slicing into tickets'],
    }[opts.sampleStage || 'last'];
    let html = '<a class="wordmark" href="index.html">' + MARK + 'Waystation</a>' +
      '<span class="crumb-sep" aria-hidden="true">/</span>' +
      '<div class="switch"><button class="repo-btn" type="button" aria-haspopup="true" aria-expanded="false" data-piece="repo-switcher"><span>' + repo + '</span>' + CARET + '</button>' +
      '<div class="menu" role="menu">' +
      '<a role="menuitem" href="index.html"' + (repo === 'galley' ? ' aria-current="true"' : '') + '><span class="m-mark mono">g</span><span class="m-name">galley</span><span class="m-meta">3 efforts on the line</span></a>' +
      '<a role="menuitem" href="first-run.html"' + (repo === 'madrigal' ? ' aria-current="true"' : '') + '><span class="m-mark mono">m</span><span class="m-name">madrigal</span><span class="m-meta">' + (opts.charted ? 'Connected today · 1 map charted' : 'Connected today · no maps yet') + '</span></a>' +
      '</div></div>';
    if (effort) {
      html += '<span class="crumb-sep" aria-hidden="true">/</span>' +
        '<div class="switch effort-switch"><button class="effort-btn" type="button" aria-haspopup="true" aria-expanded="false" data-piece="effort-switcher"><span>' + esc(effort.name) + '</span>' + CARET + '</button>' +
        '<div class="menu" role="menu">' +
        '<a role="menuitem" href="' + effortHref('acx', opts.page) + '"' + (effort.id === 'acx' ? ' aria-current="true"' : '') + '>' + glyph('building') + '<span class="m-name">ACX compliance before delivery</span><span class="m-meta">Building · ' + acxMeta + '</span></a>' +
        '<a role="menuitem" href="' + effortHref('casting', opts.page) + '"' + (effort.id === 'casting' ? ' aria-current="true"' : '') + '>' + glyph('building') + '<span class="m-name">Per-chapter voice casting</span><span class="m-meta">Charting the way · 3 decided, 3 patches of fog</span></a>' +
        '<a role="menuitem" href="' + effortHref('sample', opts.page) + '"' + (effort.id === 'sample' ? ' aria-current="true"' : '') + '>' + glyph(sampleMenu[0]) + '<span class="m-name">Choosing the retail sample</span><span class="m-meta">' + sampleMenu[1] + '</span></a>' +
        '<div class="menu-sep"></div>' +
        '<div class="menu-static">' + glyph('landed') + '<span class="m-name">Manuscript upload states</span><span class="m-meta">Landed 2 Sep · 6 tickets</span></div>' +
        '</div></div>';
    }
    html += '<div class="topbar-right">' +
      '<a class="live" href="live-build.html" data-piece="agents-working">' + glyph('building') + '<span class="label">' + working + ' agents working</span></a>' +
      '<a class="needs" href="review-desk.html" data-piece="needs-you">Needs you <span class="count' + (needs ? '' : ' zero') + '">' + needs + '</span></a>' +
      '<button type="button" class="theme-btn" id="theme-btn" data-piece="theme-toggle"></button>' +
      '</div>';
    el.className = 'topbar' + (effort ? ' has-effort' : '');
    el.setAttribute('data-piece', 'topbar');
    el.innerHTML = html;

    const themeBtn = el.querySelector('#theme-btn');
    const paintThemeBtn = () => {
      const dark = currentTheme() === 'dark';
      themeBtn.innerHTML = dark ? SUN : MOON;
      themeBtn.setAttribute('aria-label', dark ? 'Switch to the light chart' : 'Switch to the night chart');
      themeBtn.title = dark ? 'Light chart' : 'Night chart';
    };
    paintThemeBtn();
    themeBtn.addEventListener('click', () => {
      setTheme(currentTheme() === 'dark' ? 'light' : 'dark', true);
      paintThemeBtn();
    });
    onSystemTheme = paintThemeBtn;

    el.querySelectorAll('.switch').forEach((sw) => {
      const btn = sw.querySelector('button');
      const menu = sw.querySelector('.menu');
      const close = () => { menu.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); };
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = !menu.classList.contains('open');
        el.querySelectorAll('.menu.open').forEach((m) => { if (m !== menu) { m.classList.remove('open'); m.previousElementSibling.setAttribute('aria-expanded', 'false'); } });
        menu.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', String(open));
      });
      document.addEventListener('click', (e) => { if (!menu.contains(e.target)) close(); });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && menu.classList.contains('open')) { close(); btn.focus(); } });
    });
  }

  /* ─── shell: route band (the skill line) ─────────────────────────── */
  const STATIONS = [
    { key: 'wayfinder', skill: '/wayfinder', name: 'Chart the way', href: 'wayfinder-map.html' },
    { key: 'spec', skill: '/to-spec', name: 'Write the spec', href: 'spec-reader.html' },
    { key: 'tickets', skill: '/to-tickets', name: 'Slice into tickets', href: 'ticket-graph.html' },
    { key: 'build', skill: '/tdd', name: 'Build', href: 'live-build.html' },
    { key: 'review', skill: '/code-review', name: 'Review', href: 'review-desk.html' },
    { key: 'landed', skill: 'merge', name: 'Landed' },
  ];

  function renderRoute(opts) {
    const el = document.getElementById('route');
    if (!el) return;
    const c = counts();
    let plan;
    const off = (out) => ({ state: 'pending', out: out || '—' });
    if (opts.effort === 'madrigal') {
      /* first run: nothing walked yet, so each station reports whether its skill is installed */
      const charted = !!opts.charted;
      const research = opts.research || 0;
      plan = {
        wayfinder: charted ? { state: 'active', glyph: research ? 'building' : 'asking', out: 'Map #38' + (research ? ' · ' + research + ' researching' : ' charted') } : { state: 'pending', out: 'Installed' },
        spec: off('Installed'),
        tickets: off('Installed'),
        build: off('Installed'),
        review: { state: 'missing', out: 'Not installed' },
        landed: off('GitHub · main'),
      };
    } else if (opts.effort === 'sample') {
      const st = opts.sampleStage || 'last';
      plan = {
        wayfinder: st === 'last' ? { state: 'active', glyph: 'building', out: '5 decided · 1 in session' } : { state: 'done', out: '6 decisions · way clear' },
        spec: st === 'last' ? off('After the way is clear') : st === 'clear' ? { state: 'active', glyph: 'asking', out: 'Agree the seam' } : { state: 'done', out: 'Spec #168 · 12 stories' },
        tickets: st === 'written' ? { state: 'next', out: 'Ready to slice' } : st === 'slicing' ? { state: 'active', glyph: 'building', out: '/to-tickets drafting' } : off(),
        build: off(), review: off(), landed: off(),
      };
    } else if (opts.effort === 'casting') {
      plan = {
        wayfinder: { state: 'active', out: '3 decided · 3 patches of fog', glyph: 'building' },
        spec: { state: 'pending', out: 'After the way is clear' },
        tickets: { state: 'pending', out: '—' },
        build: { state: 'pending', out: '—' },
        review: { state: 'pending', out: '—' },
        landed: { state: 'pending', out: '—' },
      };
    } else {
      const buildBusy = c.building + c.asking;
      plan = {
        wayfinder: { state: 'done', out: '7 decisions' },
        spec: { state: 'done', out: '16 stories · 2 without a ticket' },
        tickets: { state: 'done', out: '9 tickets · ' + (c.takeable ? c.takeable + ' takeable' : 'frontier claimed') },
        build: buildBusy ? { state: 'active', out: c.building + ' building' + (c.asking ? ' · ' + c.asking + ' asking' : ''), glyph: c.asking ? 'asking' : 'building' } : { state: 'done', out: 'Nothing building' },
        review: c.review ? { state: 'active', out: c.review + ' PR waiting on you', glyph: 'review' } : { state: c.landed ? 'done' : 'pending', out: 'Nothing waiting' },
        landed: { state: 'dest', out: c.landed + ' of 9' },
      };
    }
    let html = '';
    STATIONS.forEach((s, i) => {
      const p = plan[s.key];
      const next = STATIONS[i + 1] ? plan[STATIONS[i + 1].key] : null;
      const trackPending = !next || next.state === 'pending' || next.state === 'next' || next.state === 'missing' || (next.state === 'dest' && c.landed === 0);
      const offMap = opts.effort === 'casting' || opts.effort === 'sample' || opts.effort === 'madrigal';
      const disabled = offMap && s.key !== 'wayfinder';
      let node;
      if (p.state === 'done') node = glyph('landed');
      else if (p.state === 'active') node = glyph(p.glyph || 'building');
      else if (p.state === 'next') node = glyph('takeable');
      else if (p.state === 'missing') node = glyph('blocked');
      else if (p.state === 'dest') node = '<span class="s-flag" aria-hidden="true"></span>';
      else node = '<span class="st st-pending" aria-hidden="true"></span>';
      let out = esc(p.out);
      if (s.key === 'landed' && !offMap) {
        out = '<span class="s-dots" aria-hidden="true">' + tickets().map((t) => '<i class="' + (t.state === 'landed' ? 'on' : '') + '"></i>').join('') + '</span>' + out;
      }
      const inner = '<span class="s-skill">' + s.skill + '</span>' +
        '<span class="s-node">' + node + '<span class="s-track' + (trackPending ? ' pending' : '') + '"></span></span>' +
        '<span class="s-name">' + s.name + '</span><span class="s-out">' + out + '</span>';
      const current = opts.page === s.key ? ' aria-current="page"' : '';
      const piece = ' data-piece="station-' + s.key + '"';
      if (!s.href) html += '<div class="station' + (p.state === 'missing' ? ' missing' : '') + '"' + piece + '>' + inner + '</div>';
      else if (disabled || opts.effort === 'madrigal') {
        const why = opts.effort === 'madrigal' ? (p.state === 'missing' ? 'Add /code-review from mattpocock/skills and agents review PRs before you do' : '') :
          opts.effort === 'sample' ? 'This effort is followed from its map' : 'Opens once the map\'s way is clear';
        html += '<div class="station' + (p.state === 'missing' ? ' missing' : '') + '"' + (opts.effort === 'madrigal' && s.key === 'wayfinder' ? ' aria-current="page"' : ' aria-disabled="true"') + piece + (why ? ' title="' + why + '"' : '') + '>' + inner + '</div>';
      } else {
        const href = s.key === 'wayfinder' ? s.href + '?effort=' + (opts.effort || 'acx') : s.href;
        html += '<a class="station" href="' + href + '"' + current + piece + '>' + inner + '</a>';
      }
    });
    el.className = 'route';
    el.setAttribute('data-piece', 'route');
    el.setAttribute('aria-label', opts.effort === 'madrigal' ? 'The skill line, and which skills madrigal has installed' : 'Where this effort is on the skill line');
    el.innerHTML = html;
  }

  /* Draw one station's track in, as the course moves past it. */
  function drawTrack(key, delay) {
    const track = document.querySelector('#route [data-piece="station-' + key + '"] .s-track');
    if (!track || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    track.style.animationDelay = (delay || 0) + 'ms';
    track.classList.add('draw');
  }

  /* ─── thread: one ticket's lineage from map to merge ─────────────── */
  function thread(n) {
    const t = ticket(n);
    const building = t.state === 'building' || t.state === 'asking';
    const steps = [
      { skill: '/wayfinder', html: '<a class="nm" href="wayfinder-map.html?effort=acx">ACX compliance before delivery</a>', meta: t.decisions.map((d) => ACX_DECISIONS[d]).join(' · '), s: 'done' },
      { skill: '/to-spec', html: '<a class="nm" href="spec-reader.html#stories">Pre-delivery compliance checks</a>', meta: (t.stories.length > 1 ? 'Stories ' : 'Story ') + t.stories.join(', '), s: 'done' },
      { skill: '/to-tickets', html: '<a class="nm" href="ticket-graph.html#' + n + '">' + esc(t.name) + '</a><span class="id">#' + n + '</span>', meta: t.blockedBy.length ? 'After ' + t.blockedBy.map((b) => TICKETS[b].short).join(', ') : 'No blockers', s: 'done' },
      { skill: '/tdd', html: t.state === 'landed' || t.state === 'review' || building ? '<a class="nm" href="live-build.html?session=' + n + '">wt/' + t.wt + '</a>' : 'No session yet', meta: t.state === 'asking' ? 'Paused · asked you a question' : building ? 'Claude Code · running now' : t.state === 'takeable' ? 'Takeable now' : t.state === 'blocked' ? 'Waiting on blockers' : 'Session finished', s: t.state === 'landed' || t.state === 'review' ? 'done' : building ? t.state : 'pending' },
      { skill: '/code-review', html: t.pr ? '<a class="nm" href="review-desk.html">PR #' + t.pr + '</a>' : 'No PR yet', meta: t.state === 'review' ? 'Standards clean · 1 spec finding' : t.state === 'landed' ? 'Approved' : '', s: t.state === 'landed' ? 'done' : t.state === 'review' ? 'review' : 'pending' },
      { skill: 'merge', html: t.state === 'landed' ? 'Landed' : 'Not landed', meta: t.state === 'landed' ? (t.landedAt || 'just now') : '', s: t.state === 'landed' ? 'done' : 'pending' },
    ];
    return '<ol class="thread">' + steps.map((st, i) => {
      const nx = steps[i + 1];
      const g = st.s === 'done' ? glyph('landed') : st.s === 'pending' ? '<span class="st st-pending" aria-hidden="true"></span>' : glyph(st.s);
      return '<li class="' + (st.s === 'pending' ? 'pending' : '') + (nx && nx.s === 'pending' ? ' next-pending' : '') + '">' +
        '<span class="t-mark">' + g + '</span><div><span class="t-skill">' + st.skill + '</span><div class="t-name">' + st.html + '</div>' +
        (st.meta ? '<div class="t-meta">' + esc(st.meta) + '</div>' : '') + '</div></li>';
    }).join('') + '</ol>';
  }

  function criteriaList(t) {
    return '<ul class="crit">' + t.criteria.map((c) => {
      const box = c.done === true ? '<span class="box on" aria-label="Passing"></span>' : c.done === 'part' ? '<span class="box part" aria-label="Partly covered"></span>' : '<span class="box" aria-label="Not yet"></span>';
      return '<li><span class="c-mark">' + box + '</span><span class="c-text">' + esc(c.text) + (c.test ? '<span class="c-test">' + esc(c.test) + '</span>' : '') + '</span></li>';
    }).join('') + '</ul>';
  }

  /* ─── question card (used on the build view and the desk) ────────── */
  function questionCard(n) {
    const t = ticket(n);
    const q = t.question;
    return '<div class="qcard" data-piece="question-' + n + '">' +
      '<div class="convo"><div class="msg"><span class="who">AI</span><div class="body"><span class="by">Claude Code · wt/' + t.wt + ' · ' + q.asked + '</span>' + esc(q.text) + '</div></div></div>' +
      '<div role="radiogroup" aria-label="Your answer" style="margin: 16px 0 10px 36px;">' +
      q.options.map((o) => '<button type="button" class="choice" role="radio" aria-checked="false" data-value="' + o.value + '"><span class="radio"></span><span><span class="c-title">' + esc(o.title) + '</span><span class="c-sub" style="display:block">' + esc(o.sub) + '</span></span></button>').join('') +
      '<label class="field-label" for="q-note-' + n + '" style="margin-top:12px">Anything the agent should know</label>' +
      '<textarea class="textarea" id="q-note-' + n + '" placeholder="Optional. The agent reads this before it resumes."></textarea>' +
      '<div style="display:flex; gap:8px; align-items:center; margin-top:10px;"><button type="button" class="btn btn-primary q-send" data-piece="send-answer-' + n + '">Send answer and resume</button><span class="meta q-hint">Pick an option or write your own answer.</span></div>' +
      '</div></div>';
  }
  function bindQuestion(root, n) {
    const choices = root.querySelectorAll('.choice');
    const send = root.querySelector('.q-send');
    const note = root.querySelector('textarea');
    const hint = root.querySelector('.q-hint');
    let picked = null;
    choices.forEach((ch) => ch.addEventListener('click', () => {
      picked = ch.dataset.value;
      choices.forEach((o) => o.setAttribute('aria-checked', String(o === ch)));
    }));
    send.addEventListener('click', () => {
      if (send.getAttribute('aria-disabled') === 'true') return;
      const text = note.value.trim();
      if (!picked && !text) { hint.textContent = 'Choose an option, or write an answer first.'; hint.style.color = 'var(--fg)'; return; }
      send.setAttribute('aria-disabled', 'true');
      send.textContent = 'Answer sent';
      hint.textContent = 'Posted to #' + n + '. The session resumes.';
      hint.style.color = 'var(--fg)';
      choices.forEach((o) => o.setAttribute('tabindex', '-1'));
      note.readOnly = true;
    });
  }

  /* ─── fit a fixed-size canvas into its viewport ──────────────────── */
  function fitCanvas(viewport, stage, w, h, minScale) {
    const apply = () => {
      const avail = viewport.clientWidth - 48;
      const s = Math.max(minScale || 0.72, Math.min(1, avail / w));
      stage.style.transform = 'scale(' + s + ')';
      stage.parentElement.style.width = Math.round(w * s) + 'px';
      stage.parentElement.style.height = Math.round(h * s) + 'px';
    };
    apply();
    if ('ResizeObserver' in window) new ResizeObserver(apply).observe(viewport);
    else window.addEventListener('resize', apply);
  }

  function param(name) { return new URLSearchParams(location.search).get(name); }

  window.WS = {
    EFFORTS, ACX_DECISIONS, TICKETS, ORDER, STATES, CASTING_GRILL,
    ticket, tickets, blocks, counts, glyph, needsYou, thread, criteriaList,
    questionCard, bindQuestion, renderTopbar, renderRoute, drawTrack, fitCanvas,
    esc, param,
  };
})();
