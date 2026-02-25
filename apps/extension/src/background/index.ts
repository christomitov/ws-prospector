import { getSettings } from "../lib/storage";
import type {
  DebugEntry,
  LlmProvider,
  ProspectSnapshot,
  ScoreBreakdown,
  UserSettings,
} from "../lib/types";

const DEBUG_LOG_LIMIT = 400;
const debugLogBuffer: DebugEntry[] = [];
const OPENAI_DEFAULT_MODEL = "gpt-4.1-mini";
const GEMINI_DEFAULT_MODEL = "gemini-2.5-flash";

const pushDebugLog = (entry: DebugEntry): void => {
  debugLogBuffer.unshift(entry);
  if (debugLogBuffer.length > DEBUG_LOG_LIMIT) {
    debugLogBuffer.length = DEBUG_LOG_LIMIT;
  }
};

chrome.runtime.onInstalled.addListener(() => {
  console.info("[Wealthsimple Prospector] extension installed.");
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "PING") {
    sendResponse({ ok: true, source: "background" });
    return false;
  }

  if (message?.type === "DEBUG_EVENT" && message.entry) {
    pushDebugLog(message.entry as DebugEntry);
    return false;
  }

  if (message?.type === "DEBUG_GET_LOGS") {
    sendResponse({ ok: true, logs: debugLogBuffer });
    return false;
  }

  if (message?.type === "DEBUG_CLEAR_LOGS") {
    debugLogBuffer.length = 0;
    sendResponse({ ok: true });
  }

  if (message?.type === "LLM_ENRICH_PROFILE" && message.snapshot) {
    void (async () => {
      try {
        const settings = await getSettings();
        if (!settings.llmEnabled) {
          sendResponse({ ok: false, error: "AI enrichment is disabled in settings." });
          return;
        }
        if (!getActiveApiKey(settings)) {
          sendResponse({
            ok: false,
            error: `Missing ${providerLabel(settings.llmProvider)} API key.`,
          });
          return;
        }

        const snapshot = message.snapshot as ProspectSnapshot;
        const text = await callProvider(
          settings,
          buildEnrichmentPayload(settings.llmModel, snapshot),
        );
        const parsed = parseEnrichmentText(text);
        sendResponse({ ok: true, enrichment: parsed });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Unknown enrichment error",
        });
      }
    })();

    return true;
  }

  if (message?.type === "LLM_GENERATE_OUTREACH" && message.snapshot) {
    void (async () => {
      try {
        const settings = await getSettings();
        if (!settings.llmEnabled) {
          sendResponse({ ok: false, error: "AI generation is disabled in settings." });
          return;
        }
        if (!getActiveApiKey(settings)) {
          sendResponse({
            ok: false,
            error: `Missing ${providerLabel(settings.llmProvider)} API key.`,
          });
          return;
        }

        const snapshot = message.snapshot as ProspectSnapshot;
        const promptInstruction =
          typeof message.promptInstruction === "string" ? message.promptInstruction : "";
        const aiSignals = Array.isArray(message.aiSignals)
          ? message.aiSignals
              .filter((entry: unknown): entry is string => typeof entry === "string")
              .map((entry: string) => entry.trim())
              .filter(Boolean)
              .slice(0, 12)
          : [];
        const aiScores = toScoreBreakdown(message.aiScores);
        const variantSeed = Number.isInteger(message.variantSeed) ? Number(message.variantSeed) : 0;

        const text = await callProvider(
          settings,
          buildOutreachPayload(settings.llmModel, {
            snapshot,
            promptInstruction,
            aiSignals,
            aiScores,
            variantSeed,
          }),
        );
        const parsed = parseGeneratedDraftText(text);
        sendResponse({ ok: true, draft: parsed });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Unknown generation error",
        });
      }
    })();

    return true;
  }

  return false;
});

interface LlmPromptPayload {
  model: string;
  system: string;
  user: string;
  temperature: number;
  maxOutputTokens: number;
}

const providerLabel = (provider: LlmProvider): string =>
  provider === "gemini" ? "Gemini" : "OpenAI";

const getActiveApiKey = (settings: UserSettings): string =>
  settings.llmProvider === "gemini" ? settings.geminiApiKey.trim() : settings.openAiApiKey.trim();

const resolveModel = (settings: UserSettings, requested: string): string => {
  if (requested.trim()) {
    return requested.trim();
  }
  return settings.llmProvider === "gemini" ? GEMINI_DEFAULT_MODEL : OPENAI_DEFAULT_MODEL;
};

const buildEnrichmentPayload = (model: string, snapshot: ProspectSnapshot): LlmPromptPayload => ({
  model: model || OPENAI_DEFAULT_MODEL,
  temperature: 0.2,
  maxOutputTokens: 500,
  system:
    "You extract structured sales-enrichment data from LinkedIn profile text. Return strict JSON only.",
  user: [
    "Extract best-effort fields from this profile snapshot.",
    'Return JSON with keys: "headline", "companyName", "location", "aboutSummary", "highLevelSignals", "scores".',
    '"highLevelSignals" must be an array of 3 to 6 concise strings (<=110 chars each).',
    '"scores" must be: { "icpFit": number(0-100), "icpLabel": "Low|Medium|High", "icpReasons": string[], "capacity": number(0-100), "capacityLabel": "Low|Medium|High", "capacityReasons": string[] }.',
    "Use the provided profile evidence to classify; do not assume missing facts.",
    "If unknown, use empty string or empty array. Do not include markdown.",
    "",
    `Name: ${snapshot.name || ""}`,
    `Profile URL: ${snapshot.profileUrl || ""}`,
    `Headline: ${snapshot.headline || ""}`,
    `Company: ${snapshot.companyName || ""}`,
    `Location: ${snapshot.location || ""}`,
    `About: ${snapshot.about || ""}`,
    `Experience highlights: ${snapshot.experienceHighlights || ""}`,
    `Recent activity: ${snapshot.recentActivity || ""}`,
  ].join("\n"),
});

interface OutreachPayloadContext {
  snapshot: ProspectSnapshot;
  promptInstruction: string;
  aiSignals: string[];
  aiScores: ScoreBreakdown;
  variantSeed: number;
}

const defaultOutreachFramework = [
  "My LinkedIn Outreach Drafting Prompt (Framework)",
  "Exact message structure (in order):",
  '1) Always open with "hey (name)" where hey is lowercase.',
  "2) Personalized opener tied to their profile.",
  "3) Pain-point paragraph about fragmented personal finances (max 2 sentences).",
  "4) Wealthsimple Private Wealth positioning with investable asset range ($500K-$50M+).",
  '5) Include this exact line: "And frankly a more modern approach to wealth management than legacy banks."',
  '6) Include this exact CTA: "Happy to do a 15-minute call next week to see if our exclusive team can add value and bring clarity to your current setup."',
  '7) Close with: "Cheers".',
  "Tone: non-spammy, curious, concise but not abrupt, subtly exclusive, no hard pitch.",
].join("\n");

const buildOutreachPayload = (model: string, context: OutreachPayloadContext): LlmPromptPayload => {
  const framework = context.promptInstruction.trim() || defaultOutreachFramework;
  const scoreContext = [
    `ICP Fit: ${context.aiScores.icpFit} (${context.aiScores.icpLabel})`,
    `ICP reasons: ${context.aiScores.icpReasons.join(" | ") || "none"}`,
    `Capacity: ${context.aiScores.capacity} (${context.aiScores.capacityLabel})`,
    `Capacity reasons: ${context.aiScores.capacityReasons.join(" | ") || "none"}`,
  ].join("\n");

  return {
    model: model || OPENAI_DEFAULT_MODEL,
    temperature: 0.35,
    maxOutputTokens: 650,
    system:
      "You write one LinkedIn outreach draft for Wealthsimple Private Wealth. Return strict JSON only with no markdown.",
    user: [
      "Write exactly one outreach message.",
      'Output JSON schema: { "message": string, "personalizationHook": string, "signalsUsed": string[] }',
      "message must be <= 600 characters.",
      "If the framework requires exact lines, preserve them verbatim.",
      "Use only evidence from the supplied profile context.",
      "",
      "Framework and extra instructions:",
      framework,
      "",
      "Profile context:",
      `Name: ${context.snapshot.name || ""}`,
      `Profile URL: ${context.snapshot.profileUrl || ""}`,
      `Headline: ${context.snapshot.headline || ""}`,
      `Company: ${context.snapshot.companyName || ""}`,
      `Location: ${context.snapshot.location || ""}`,
      `About: ${context.snapshot.about || ""}`,
      `Experience highlights: ${context.snapshot.experienceHighlights || ""}`,
      `Recent activity: ${context.snapshot.recentActivity || ""}`,
      "",
      "AI signal context:",
      `Signals: ${context.aiSignals.join(" | ") || "none"}`,
      scoreContext,
      `Variant seed: ${context.variantSeed}`,
    ].join("\n"),
  };
};

const callProvider = async (settings: UserSettings, payload: LlmPromptPayload): Promise<string> => {
  const provider = settings.llmProvider;
  const model = resolveModel(settings, payload.model);
  const apiKey = getActiveApiKey(settings);
  if (!apiKey) {
    throw new Error(`Missing ${providerLabel(provider)} API key.`);
  }

  if (provider === "gemini") {
    return callGemini(apiKey, { ...payload, model });
  }
  return callOpenAi(apiKey, { ...payload, model });
};

const callOpenAi = async (apiKey: string, payload: LlmPromptPayload): Promise<string> => {
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey.trim()}`,
    },
    body: JSON.stringify({
      model: payload.model || OPENAI_DEFAULT_MODEL,
      temperature: payload.temperature,
      max_output_tokens: payload.maxOutputTokens,
      input: [
        {
          role: "system",
          content: payload.system,
        },
        {
          role: "user",
          content: payload.user,
        },
      ],
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenAI request failed (${response.status}): ${body.slice(0, 240)}`);
  }

  const result = (await response.json()) as {
    output_text?: string;
    output?: Array<{ content?: Array<{ text?: string }> }>;
  };
  return readOpenAiOutputText(result);
};

const callGemini = async (apiKey: string, payload: LlmPromptPayload): Promise<string> => {
  const model = payload.model || GEMINI_DEFAULT_MODEL;
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey.trim())}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      system_instruction: {
        parts: [{ text: payload.system }],
      },
      contents: [
        {
          role: "user",
          parts: [{ text: payload.user }],
        },
      ],
      generationConfig: {
        temperature: payload.temperature,
        maxOutputTokens: payload.maxOutputTokens,
        responseMimeType: "application/json",
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Gemini request failed (${response.status}): ${body.slice(0, 240)}`);
  }

  const result = (await response.json()) as {
    candidates?: Array<{
      content?: {
        parts?: Array<{ text?: string }>;
      };
    }>;
  };
  return readGeminiOutputText(result);
};

const readOpenAiOutputText = (response: {
  output_text?: string;
  output?: Array<{ content?: Array<{ text?: string }> }>;
}): string => {
  if (typeof response.output_text === "string" && response.output_text.trim()) {
    return response.output_text.trim();
  }

  for (const item of response.output ?? []) {
    for (const part of item.content ?? []) {
      if (typeof part.text === "string" && part.text.trim()) {
        return part.text.trim();
      }
    }
  }

  return "";
};

const readGeminiOutputText = (response: {
  candidates?: Array<{
    content?: {
      parts?: Array<{ text?: string }>;
    };
  }>;
}): string => {
  for (const candidate of response.candidates ?? []) {
    for (const part of candidate.content?.parts ?? []) {
      if (typeof part.text === "string" && part.text.trim()) {
        return part.text.trim();
      }
    }
  }
  return "";
};

const parseEnrichmentText = (
  text: string,
): {
  headline: string;
  companyName: string;
  location: string;
  aboutSummary: string;
  highLevelSignals: string[];
  scores: {
    icpFit: number;
    icpLabel: "Low" | "Medium" | "High";
    icpReasons: string[];
    capacity: number;
    capacityLabel: "Low" | "Medium" | "High";
    capacityReasons: string[];
  };
} => {
  const emptyScores = {
    icpFit: 0,
    icpLabel: "Low" as const,
    icpReasons: [],
    capacity: 0,
    capacityLabel: "Low" as const,
    capacityReasons: [],
  };

  if (!text) {
    return {
      headline: "",
      companyName: "",
      location: "",
      aboutSummary: "",
      highLevelSignals: [],
      scores: emptyScores,
    };
  }

  try {
    const normalized = text.replace(/^```json\s*|\s*```$/g, "");
    const parsed = JSON.parse(normalized) as {
      headline?: unknown;
      companyName?: unknown;
      location?: unknown;
      aboutSummary?: unknown;
      highLevelSignals?: unknown;
      scores?: unknown;
    };

    const rawScores =
      parsed.scores && typeof parsed.scores === "object"
        ? (parsed.scores as {
            icpFit?: unknown;
            icpLabel?: unknown;
            icpReasons?: unknown;
            capacity?: unknown;
            capacityLabel?: unknown;
            capacityReasons?: unknown;
          })
        : undefined;

    const toLabel = (value: unknown): "Low" | "Medium" | "High" =>
      value === "High" || value === "Medium" || value === "Low" ? value : "Low";

    const parsedScores = {
      icpFit:
        typeof rawScores?.icpFit === "number"
          ? Math.max(0, Math.min(100, Math.round(rawScores.icpFit)))
          : 0,
      icpLabel: toLabel(rawScores?.icpLabel),
      icpReasons: Array.isArray(rawScores?.icpReasons)
        ? rawScores.icpReasons
            .filter((entry): entry is string => typeof entry === "string")
            .map((entry) => entry.trim())
            .filter(Boolean)
            .slice(0, 6)
        : [],
      capacity:
        typeof rawScores?.capacity === "number"
          ? Math.max(0, Math.min(100, Math.round(rawScores.capacity)))
          : 0,
      capacityLabel: toLabel(rawScores?.capacityLabel),
      capacityReasons: Array.isArray(rawScores?.capacityReasons)
        ? rawScores.capacityReasons
            .filter((entry): entry is string => typeof entry === "string")
            .map((entry) => entry.trim())
            .filter(Boolean)
            .slice(0, 6)
        : [],
    };

    return {
      headline: typeof parsed.headline === "string" ? parsed.headline.trim() : "",
      companyName: typeof parsed.companyName === "string" ? parsed.companyName.trim() : "",
      location: typeof parsed.location === "string" ? parsed.location.trim() : "",
      aboutSummary: typeof parsed.aboutSummary === "string" ? parsed.aboutSummary.trim() : "",
      highLevelSignals: Array.isArray(parsed.highLevelSignals)
        ? parsed.highLevelSignals
            .filter((entry): entry is string => typeof entry === "string")
            .map((entry) => entry.trim())
            .filter(Boolean)
            .slice(0, 6)
        : [],
      scores: parsedScores,
    };
  } catch {
    return {
      headline: "",
      companyName: "",
      location: "",
      aboutSummary: "",
      highLevelSignals: [],
      scores: emptyScores,
    };
  }
};

const toScoreBreakdown = (value: unknown): ScoreBreakdown => {
  const toLabel = (input: unknown): "Low" | "Medium" | "High" =>
    input === "Low" || input === "Medium" || input === "High" ? input : "Low";
  const source = (value && typeof value === "object" ? value : {}) as {
    icpFit?: unknown;
    icpLabel?: unknown;
    icpReasons?: unknown;
    capacity?: unknown;
    capacityLabel?: unknown;
    capacityReasons?: unknown;
  };

  return {
    icpFit:
      typeof source.icpFit === "number" ? Math.max(0, Math.min(100, Math.round(source.icpFit))) : 0,
    icpLabel: toLabel(source.icpLabel),
    icpReasons: Array.isArray(source.icpReasons)
      ? source.icpReasons
          .filter((entry): entry is string => typeof entry === "string")
          .map((entry) => entry.trim())
          .filter(Boolean)
          .slice(0, 8)
      : [],
    capacity:
      typeof source.capacity === "number"
        ? Math.max(0, Math.min(100, Math.round(source.capacity)))
        : 0,
    capacityLabel: toLabel(source.capacityLabel),
    capacityReasons: Array.isArray(source.capacityReasons)
      ? source.capacityReasons
          .filter((entry): entry is string => typeof entry === "string")
          .map((entry) => entry.trim())
          .filter(Boolean)
          .slice(0, 8)
      : [],
  };
};

const parseGeneratedDraftText = (
  text: string,
): {
  message: string;
  personalizationHook: string;
  signalsUsed: string[];
} => {
  if (!text) {
    return {
      message: "",
      personalizationHook: "",
      signalsUsed: [],
    };
  }

  try {
    const normalized = text.replace(/^```json\s*|\s*```$/g, "");
    const parsed = JSON.parse(normalized) as {
      message?: unknown;
      personalizationHook?: unknown;
      signalsUsed?: unknown;
    };

    return {
      message: typeof parsed.message === "string" ? parsed.message.trim().slice(0, 600) : "",
      personalizationHook:
        typeof parsed.personalizationHook === "string" ? parsed.personalizationHook.trim() : "",
      signalsUsed: Array.isArray(parsed.signalsUsed)
        ? parsed.signalsUsed
            .filter((entry): entry is string => typeof entry === "string")
            .map((entry) => entry.trim())
            .filter(Boolean)
            .slice(0, 8)
        : [],
    };
  } catch {
    return {
      message: text.trim().slice(0, 600),
      personalizationHook: "",
      signalsUsed: [],
    };
  }
};
