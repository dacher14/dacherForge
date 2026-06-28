// Central place for user settings. Everything is stored in chrome.storage.local
// (the API key never leaves the user's machine except in calls to api.anthropic.com).

export const DEFAULTS = {
  apiKey: '',
  model: 'claude-opus-4-8',
  // Languages are stored as plain English names — that's what we hand to the model.
  nativeLanguage: 'Russian',
  targetLanguage: 'English',
  // Register the corrected text should aim for.
  tone: 'neutral', // 'neutral' | 'formal' | 'friendly'
};

export const MODELS = [
  { id: 'claude-opus-4-8', label: 'Claude Opus 4.8 — самый умный (по умолчанию)' },
  { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 — баланс скорости и качества' },
  { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5 — самый быстрый и дешёвый' },
];

export const LANGUAGES = [
  'English', 'Russian', 'Ukrainian', 'Spanish', 'German', 'French',
  'Italian', 'Portuguese', 'Polish', 'Dutch', 'Turkish', 'Arabic',
  'Chinese', 'Japanese', 'Korean',
];

export const TONES = [
  { id: 'neutral', label: 'Нейтральный' },
  { id: 'formal', label: 'Формальный' },
  { id: 'friendly', label: 'Дружеский' },
];

export async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

export async function setSettings(patch) {
  await chrome.storage.local.set(patch);
}
