import { MODELS, LANGUAGES, TONES, getSettings, setSettings } from '../lib/storage.js';

const els = {
  form: document.getElementById('form'),
  apiKey: document.getElementById('apiKey'),
  toggleKey: document.getElementById('toggle-key'),
  model: document.getElementById('model'),
  nativeLanguage: document.getElementById('nativeLanguage'),
  targetLanguage: document.getElementById('targetLanguage'),
  tone: document.getElementById('tone'),
  test: document.getElementById('test'),
  save: document.getElementById('save'),
  status: document.getElementById('status'),
};

init();

async function init() {
  fillOptions(els.model, MODELS.map((m) => [m.id, m.label]));
  fillOptions(els.nativeLanguage, LANGUAGES.map((l) => [l, l]));
  fillOptions(els.targetLanguage, LANGUAGES.map((l) => [l, l]));
  fillOptions(els.tone, TONES.map((t) => [t.id, t.label]));

  const s = await getSettings();
  els.apiKey.value = s.apiKey;
  els.model.value = s.model;
  els.nativeLanguage.value = s.nativeLanguage;
  els.targetLanguage.value = s.targetLanguage;
  els.tone.value = s.tone;

  els.form.addEventListener('submit', onSave);
  els.toggleKey.addEventListener('click', toggleKey);
  els.test.addEventListener('click', onTest);
}

function currentValues() {
  return {
    apiKey: els.apiKey.value.trim(),
    model: els.model.value,
    nativeLanguage: els.nativeLanguage.value,
    targetLanguage: els.targetLanguage.value,
    tone: els.tone.value,
  };
}

async function onSave(e) {
  e.preventDefault();
  await setSettings(currentValues());
  showStatus('Настройки сохранены.', 'ok');
}

async function onTest() {
  const values = currentValues();
  if (!values.apiKey) {
    showStatus('Сначала введи API-ключ.', 'error');
    return;
  }
  await setSettings(values);
  els.test.disabled = true;
  showStatus('Проверяю ключ…');

  const res = await chrome.runtime.sendMessage({
    type: 'analyze',
    text: 'This are a test sentence.',
  });

  els.test.disabled = false;
  if (res?.ok) {
    showStatus('Ключ работает — расширение готово.', 'ok');
  } else {
    showStatus(res?.error === 'NO_KEY' ? 'Ключ не задан.' : (res?.error || 'Не удалось проверить ключ.'), 'error');
  }
}

function toggleKey() {
  const showing = els.apiKey.type === 'text';
  els.apiKey.type = showing ? 'password' : 'text';
  els.toggleKey.textContent = showing ? 'Показать' : 'Скрыть';
}

function fillOptions(select, pairs) {
  for (const [value, label] of pairs) {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    select.appendChild(opt);
  }
}

function showStatus(text, kind) {
  els.status.textContent = text;
  els.status.className = 'status' + (kind ? ' ' + kind : '');
  els.status.hidden = false;
}
