// Thin client for the Claude Messages API.
//
// Why a raw fetch instead of @anthropic-ai/sdk: this runs inside a Manifest V3
// service worker with no build step. fetch() lets us set the browser-access
// header explicitly and ship the extension as plain files (load unpacked, no
// npm). Everything that talks to the network lives in this one module, so
// swapping in the official SDK or a backend proxy later is a localized change.

const API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';
const MAX_TOKENS = 4096;

/**
 * Send text to Claude and return the parsed structured result.
 * @returns {Promise<object>} parsed JSON matching prompt.js SCHEMA
 */
export async function analyze({ apiKey, model, system, schema, text }) {
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': ANTHROPIC_VERSION,
      // Required for the API to accept calls made directly from a browser/extension.
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model,
      max_tokens: MAX_TOKENS,
      system,
      output_config: { format: { type: 'json_schema', schema } },
      messages: [{ role: 'user', content: text }],
    }),
  });

  if (!res.ok) {
    throw new ApiError(await describeError(res));
  }

  const data = await res.json();

  if (data.stop_reason === 'refusal') {
    throw new ApiError('Модель отклонила запрос (safety). Попробуй другой текст.');
  }

  const textBlock = (data.content || []).find((b) => b.type === 'text');
  if (!textBlock) {
    throw new ApiError('Пустой ответ от модели. Попробуй ещё раз.');
  }

  try {
    return JSON.parse(textBlock.text);
  } catch {
    throw new ApiError('Не удалось разобрать ответ модели.');
  }
}

export class ApiError extends Error {}

async function describeError(res) {
  let detail = '';
  try {
    const body = await res.json();
    detail = body?.error?.message || '';
  } catch {
    /* ignore non-JSON bodies */
  }
  switch (res.status) {
    case 401:
      return 'Неверный API-ключ. Проверь его в настройках.';
    case 403:
      return 'Ключ не имеет доступа к этой модели.';
    case 404:
      return 'Модель не найдена — проверь выбранную модель в настройках.';
    case 429:
      return 'Слишком много запросов (rate limit). Подожди немного.';
    case 529:
      return 'Сервис перегружен. Попробуй чуть позже.';
    default:
      if (res.status >= 500) return `Ошибка сервера (${res.status}). Попробуй позже.`;
      return detail || `Ошибка запроса (${res.status}).`;
  }
}
