// Builds the system prompt and the structured-output JSON schema we send to Claude.
// Keeping this isolated makes the "brain" of the product easy to iterate on.

const TONE_GUIDANCE = {
  neutral: 'a clear, neutral register suitable for most situations',
  formal: 'a formal, polite register (e.g. business email, official request)',
  friendly: 'a warm, casual register (e.g. message to a friend)',
};

export function buildSystem({ nativeLanguage, targetLanguage, tone }) {
  const toneText = TONE_GUIDANCE[tone] || TONE_GUIDANCE.neutral;
  return [
    `You are LinguaForge, a writing assistant for someone whose native language is ${nativeLanguage} and who wants to write correctly in ${targetLanguage}.`,
    '',
    'You receive a piece of text the user wrote. Do the following:',
    `1. Detect what language the text is actually written in.`,
    `2. If it is already in ${targetLanguage}: find every real mistake (grammar, spelling, word choice, punctuation) and anything that sounds unnatural to a native speaker. Produce a corrected, natural version in ${targetLanguage}.`,
    `3. If it is written in ${nativeLanguage} (or another language): translate it into natural ${targetLanguage}. Put the translation in "translation" and also use it as "corrected_text".`,
    `4. Aim the corrected text at ${toneText}.`,
    '',
    'Rules:',
    `- Write every explanation and the summary IN ${nativeLanguage}, so the user understands them. Keep each explanation short and concrete — say WHY, like a good tutor ("here you need an article because…"), not just "this is wrong".`,
    '- Do not invent mistakes. If the text is already correct and natural, return an empty issues array and set corrected_text to the original (cleaned up only if genuinely needed).',
    '- Preserve the user\'s meaning, formatting and intent. Do not add new ideas.',
    '- Only flag substantive issues; ignore subjective stylistic preferences unless they genuinely hurt clarity or naturalness.',
    '- "translation" must be a non-empty string ONLY when you actually translated from another language; otherwise it must be an empty string.',
  ].join('\n');
}

// JSON Schema for structured outputs. Every field is required and
// additionalProperties is false everywhere — required by the structured-output API.
export const SCHEMA = {
  type: 'object',
  properties: {
    detected_language: {
      type: 'string',
      description: 'The language the input text is written in, as an English name (e.g. "English", "Russian").',
    },
    matches_target: {
      type: 'boolean',
      description: 'True if the text was already written in the target language.',
    },
    corrected_text: {
      type: 'string',
      description: 'The full text, corrected and natural, in the target language.',
    },
    issues: {
      type: 'array',
      description: 'One entry per real mistake or unnatural phrasing. Empty if the text is already correct.',
      items: {
        type: 'object',
        properties: {
          original: { type: 'string', description: 'The exact fragment from the user text that is wrong or awkward.' },
          suggestion: { type: 'string', description: 'The corrected fragment.' },
          explanation: { type: 'string', description: "Short explanation in the user's native language of why." },
          category: {
            type: 'string',
            enum: ['grammar', 'spelling', 'word_choice', 'punctuation', 'style', 'naturalness'],
          },
        },
        required: ['original', 'suggestion', 'explanation', 'category'],
        additionalProperties: false,
      },
    },
    translation: {
      type: 'string',
      description: 'Translation into the target language if the input was in another language; otherwise an empty string.',
    },
    summary: {
      type: 'string',
      description: "One short sentence in the user's native language summarising the result.",
    },
  },
  required: ['detected_language', 'matches_target', 'corrected_text', 'issues', 'translation', 'summary'],
  additionalProperties: false,
};
