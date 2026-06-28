import { LANGUAGES, getSettings, setSettings } from '../lib/storage.js';

const els = {
  target: document.getElementById('target'),
  input: document.getElementById('input'),
  check: document.getElementById('check'),
  paste: document.getElementById('paste-selection'),
  copy: document.getElementById('copy'),
  options: document.getElementById('open-options'),
  status: document.getElementById('status'),
  result: document.getElementById('result'),
  summary: document.getElementById('summary'),
  corrected: document.getElementById('corrected'),
  translationBlock: document.getElementById('translation-block'),
  translation: document.getElementById('translation'),
  issuesBlock: document.getElementById('issues-block'),
  issues: document.getElementById('issues'),
};

const CATEGORY_LABELS = {
  grammar: 'Грамматика',
  spelling: 'Орфография',
  word_choice: 'Выбор слова',
  punctuation: 'Пунктуация',
  style: 'Стиль',
  naturalness: 'Естественность',
};

init();

async function init() {
  const settings = await getSettings();

  for (const lang of LANGUAGES) {
    const opt = document.createElement('option');
    opt.value = lang;
    opt.textContent = lang;
    els.target.appendChild(opt);
  }
  els.target.value = settings.targetLanguage;

  const { lastInput = '' } = await chrome.storage.local.get('lastInput');
  els.input.value = lastInput;

  if (!settings.apiKey) {
    showStatus('Сначала добавь API-ключ Anthropic в ', { withOptionsLink: true });
  }

  els.check.addEventListener('click', runCheck);
  els.paste.addEventListener('click', pasteSelection);
  els.copy.addEventListener('click', copyCorrected);
  els.options.addEventListener('click', () => chrome.runtime.openOptionsPage());
  els.target.addEventListener('change', () => setSettings({ targetLanguage: els.target.value }));
  els.input.addEventListener('input', debounce(() => {
    chrome.storage.local.set({ lastInput: els.input.value });
  }, 400));
  els.input.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runCheck();
  });
}

async function runCheck() {
  const text = els.input.value.trim();
  if (!text) {
    showStatus('Пустой текст — нечего проверять.');
    return;
  }
  hide(els.result);
  setBusy(true);
  showStatus('Проверяю…');

  const res = await chrome.runtime.sendMessage({
    type: 'analyze',
    text,
    targetOverride: els.target.value,
  });

  setBusy(false);

  if (!res?.ok) {
    if (res?.error === 'NO_KEY') {
      showStatus('Сначала добавь API-ключ Anthropic в ', { withOptionsLink: true, error: true });
    } else {
      showStatus(res?.error || 'Не удалось проверить текст.', { error: true });
    }
    return;
  }

  hide(els.status);
  render(res.data);
}

function render(data) {
  els.summary.textContent = data.summary || '';
  els.corrected.textContent = data.corrected_text || '';

  if (data.translation && data.translation.trim()) {
    els.translation.textContent = data.translation;
    show(els.translationBlock);
  } else {
    hide(els.translationBlock);
  }

  els.issues.replaceChildren();
  const issues = Array.isArray(data.issues) ? data.issues : [];
  if (issues.length === 0) {
    const li = document.createElement('li');
    li.className = 'clean';
    li.textContent = '✓ Ошибок не найдено — текст звучит естественно.';
    els.issues.appendChild(li);
  } else {
    for (const issue of issues) els.issues.appendChild(renderIssue(issue));
  }
  show(els.issuesBlock);
  show(els.result);
}

function renderIssue(issue) {
  const li = document.createElement('li');
  li.className = 'issue';

  const change = document.createElement('div');
  change.className = 'change';
  const original = document.createElement('span');
  original.className = 'original';
  original.textContent = issue.original || '';
  const arrow = document.createTextNode(' → ');
  const suggestion = document.createElement('span');
  suggestion.className = 'suggestion';
  suggestion.textContent = issue.suggestion || '';
  change.append(original, arrow, suggestion);

  const explanation = document.createElement('div');
  explanation.className = 'explanation';
  explanation.textContent = issue.explanation || '';

  li.append(change, explanation);

  if (issue.category) {
    const cat = document.createElement('span');
    cat.className = 'cat';
    cat.textContent = CATEGORY_LABELS[issue.category] || issue.category;
    li.appendChild(cat);
  }
  return li;
}

async function pasteSelection() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error();
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    const selection = (result || '').trim();
    if (!selection) {
      showStatus('На странице ничего не выделено.');
      return;
    }
    els.input.value = selection;
    chrome.storage.local.set({ lastInput: selection });
    hide(els.status);
  } catch {
    showStatus('Не удалось прочитать выделение на этой странице.');
  }
}

async function copyCorrected() {
  const text = els.corrected.textContent;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    els.copy.textContent = 'Скопировано';
    setTimeout(() => (els.copy.textContent = 'Копировать'), 1200);
  } catch {
    /* clipboard may be unavailable; ignore */
  }
}

function showStatus(text, { withOptionsLink = false, error = false } = {}) {
  els.status.replaceChildren();
  els.status.classList.toggle('error', error);
  els.status.appendChild(document.createTextNode(text));
  if (withOptionsLink) {
    const link = document.createElement('span');
    link.className = 'link';
    link.textContent = 'настройках';
    link.addEventListener('click', () => chrome.runtime.openOptionsPage());
    els.status.appendChild(link);
    els.status.appendChild(document.createTextNode('.'));
  }
  show(els.status);
}

function setBusy(busy) {
  els.check.disabled = busy;
  els.paste.disabled = busy;
  els.check.textContent = busy ? '…' : 'Проверить';
}

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
