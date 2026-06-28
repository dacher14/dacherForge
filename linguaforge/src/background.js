// Service worker: the only place that holds the API key and talks to Claude.
// The popup sends it text; it replies with the structured result.

import { getSettings } from './lib/storage.js';
import { buildSystem, SCHEMA } from './lib/prompt.js';
import { analyze, ApiError } from './lib/anthropic.js';

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'analyze') {
    handleAnalyze(msg).then(sendResponse);
    return true; // keep the message channel open for the async reply
  }
  return false;
});

async function handleAnalyze({ text, targetOverride }) {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    return { ok: false, error: 'Пустой текст — нечего проверять.' };
  }

  const settings = await getSettings();
  if (!settings.apiKey) {
    return { ok: false, error: 'NO_KEY' };
  }

  const targetLanguage = targetOverride || settings.targetLanguage;
  const system = buildSystem({
    nativeLanguage: settings.nativeLanguage,
    targetLanguage,
    tone: settings.tone,
  });

  try {
    const data = await analyze({
      apiKey: settings.apiKey,
      model: settings.model,
      system,
      schema: SCHEMA,
      text: trimmed,
    });
    return { ok: true, data, targetLanguage };
  } catch (err) {
    const error = err instanceof ApiError ? err.message : 'Сеть недоступна или произошла неизвестная ошибка.';
    return { ok: false, error };
  }
}
