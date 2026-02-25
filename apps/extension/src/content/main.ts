import "./sidebar.css";

import { debugLog, installDebugApi } from "../lib/debug";
import { isLinkedInProfilePage, normalizeProfileUrl, parseLinkedInProfile } from "../lib/parsing";
import { deriveProfileSignals } from "../lib/scoring";
import {
  addActivityEvent,
  getProspectRecord,
  getSettings,
  getSidebarCollapsed,
  saveProspectRecord,
  saveSettings,
  saveSidebarCollapsed,
} from "../lib/storage";
import type {
  GeneratedMessages,
  LlmProvider,
  ProspectRecord,
  ProspectSnapshot,
  ScoreBreakdown,
  UserSettings,
} from "../lib/types";

const ROOT_ID = "dc-root";
const LAUNCHER_ID = "dc-profile-launcher";

let latestProfileUrl = "";
let regenerateSeed = 1;
let latestAiSignals: string[] = [];
let latestAiScores: ScoreBreakdown | null = null;
let derivedSnapshotFields: {
  about?: string;
  experienceHighlights?: string;
  recentActivity?: string;
} = {};

interface UiRefs {
  root: HTMLDivElement;
  launcher: HTMLButtonElement;
  settingsCog: HTMLButtonElement;
  toggle: HTMLButtonElement;
  save: HTMLButtonElement;
  refreshParse: HTMLButtonElement;
  aiEnrich: HTMLButtonElement;
  parseStatus: HTMLElement;
  aiSignals: HTMLUListElement;
  aiIcpScore: HTMLElement;
  aiCapacityScore: HTMLElement;
  aiIcpReasons: HTMLUListElement;
  aiCapacityReasons: HTMLUListElement;
  generate: HTMLButtonElement;
  regenerate: HTMLButtonElement;
  editPrompt: HTMLButtonElement;
  name: HTMLInputElement;
  headline: HTMLInputElement;
  company: HTMLInputElement;
  location: HTMLInputElement;
  profileUrl: HTMLInputElement;
  promptModal: HTMLDivElement;
  promptEditor: HTMLTextAreaElement;
  promptSave: HTMLButtonElement;
  promptCancel: HTMLButtonElement;
  aiModal: HTMLDivElement;
  aiProvider: HTMLSelectElement;
  aiModel: HTMLInputElement;
  aiKey: HTMLInputElement;
  aiSave: HTMLButtonElement;
  aiCancel: HTMLButtonElement;
  messageOutput: HTMLTextAreaElement;
  copyOutput: HTMLButtonElement;
}

interface LlmEnrichmentResponse {
  ok: boolean;
  enrichment?: {
    headline: string;
    companyName: string;
    location: string;
    aboutSummary: string;
    highLevelSignals: string[];
    scores: ScoreBreakdown;
  };
  error?: string;
}

interface LlmGenerateResponse {
  ok: boolean;
  draft?: {
    message: string;
    personalizationHook: string;
    signalsUsed: string[];
  };
  error?: string;
}

const byId = <T extends HTMLElement>(root: ParentNode, id: string): T => {
  const el = root.querySelector<T>(`#${id}`);
  if (!el) {
    throw new Error(`Missing element #${id}`);
  }
  return el;
};

const wait = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });

const syncDerivedFields = (snapshot: ProspectSnapshot): void => {
  derivedSnapshotFields = {
    ...(snapshot.about ? { about: snapshot.about } : {}),
    ...(snapshot.experienceHighlights
      ? { experienceHighlights: snapshot.experienceHighlights }
      : {}),
    ...(snapshot.recentActivity ? { recentActivity: snapshot.recentActivity } : {}),
  };
};

const readSnapshot = (ui: UiRefs): ProspectSnapshot => ({
  profileUrl: normalizeProfileUrl(ui.profileUrl.value.trim()),
  name: ui.name.value.trim(),
  headline: ui.headline.value.trim(),
  companyName: ui.company.value.trim(),
  location: ui.location.value.trim(),
  ...derivedSnapshotFields,
});

const mergeSnapshot = (base: ProspectSnapshot, candidate: ProspectSnapshot): ProspectSnapshot => {
  const about = candidate.about || base.about;
  const experienceHighlights = candidate.experienceHighlights || base.experienceHighlights;
  const recentActivity = candidate.recentActivity || base.recentActivity;

  return {
    profileUrl: candidate.profileUrl || base.profileUrl,
    name: candidate.name || base.name,
    headline: candidate.headline || base.headline,
    companyName: candidate.companyName || base.companyName,
    location: candidate.location || base.location,
    ...(typeof about === "string" ? { about } : {}),
    ...(typeof experienceHighlights === "string" ? { experienceHighlights } : {}),
    ...(typeof recentActivity === "string" ? { recentActivity } : {}),
  };
};

const parseCoverageText = (snapshot: ProspectSnapshot): string => {
  const fields = [snapshot.name, snapshot.headline, snapshot.companyName, snapshot.location].filter(
    Boolean,
  );
  return `Auto parsed ${fields.length}/4 basics`;
};

const badgeClass = (label: "Low" | "Medium" | "High"): string => label.toLowerCase();

const renderList = (target: HTMLUListElement, values: string[], emptyText: string): void => {
  target.innerHTML = "";
  for (const value of values) {
    const li = document.createElement("li");
    li.textContent = value;
    target.append(li);
  }
  if (values.length === 0) {
    const li = document.createElement("li");
    li.textContent = emptyText;
    target.append(li);
  }
};

const renderEnrichmentPanel = (
  ui: UiRefs,
  signals: string[],
  scores: ScoreBreakdown | null,
): void => {
  renderList(ui.aiSignals, signals, "No AI signals yet.");

  const scoreSet = scores ?? emptyAiScores();
  ui.aiIcpScore.innerHTML = `${scoreSet.icpFit} <span class="dc-badge ${badgeClass(scoreSet.icpLabel)}">${scoreSet.icpLabel}</span>`;
  ui.aiCapacityScore.innerHTML = `${scoreSet.capacity} <span class="dc-badge ${badgeClass(scoreSet.capacityLabel)}">${scoreSet.capacityLabel}</span>`;
  renderList(ui.aiIcpReasons, scoreSet.icpReasons, "No ICP reasons yet.");
  renderList(ui.aiCapacityReasons, scoreSet.capacityReasons, "No capacity reasons yet.");
};

const parseSnapshotWithRetries = async (url: string): Promise<ProspectSnapshot> => {
  let best = parseLinkedInProfile(url);
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (best.name && best.headline && best.companyName && best.location) {
      return best;
    }
    await wait(350);
    const next = parseLinkedInProfile(url);
    best = mergeSnapshot(best, next);
  }
  return best;
};

const setMessageFields = (ui: UiRefs, messages: GeneratedMessages): void => {
  ui.messageOutput.value = messages.dm1;
};

const copyText = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

const populateSnapshotInputs = (ui: UiRefs, snapshot: ProspectSnapshot): void => {
  ui.profileUrl.value = snapshot.profileUrl;
  ui.name.value = snapshot.name;
  ui.headline.value = snapshot.headline;
  ui.company.value = snapshot.companyName;
  ui.location.value = snapshot.location;
};

const dedupe = (values: string[]): string[] => Array.from(new Set(values.filter(Boolean)));

const buildRecordSignals = (snapshot: ProspectSnapshot): string[] =>
  dedupe([...deriveProfileSignals(snapshot), ...latestAiSignals]);

const emptyAiScores = (): ScoreBreakdown => ({
  icpFit: 0,
  icpLabel: "Low",
  icpReasons: [],
  capacity: 0,
  capacityLabel: "Low",
  capacityReasons: [],
});

const providerLabel = (provider: LlmProvider): string =>
  provider === "gemini" ? "Gemini" : "ChatGPT";

const getProviderKey = (settings: UserSettings, provider = settings.llmProvider): string =>
  provider === "gemini" ? settings.geminiApiKey.trim() : settings.openAiApiKey.trim();

const sendMessageWithTimeout = <TResponse>(
  message: unknown,
  timeoutMs = 15000,
): Promise<TResponse> =>
  new Promise((resolve) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      resolve({ ok: false, error: "Background request timed out." } as TResponse);
    }, timeoutMs);

    try {
      chrome.runtime.sendMessage(message, (response: unknown) => {
        if (settled) {
          return;
        }
        settled = true;
        window.clearTimeout(timer);
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message } as TResponse);
          return;
        }
        resolve(response as TResponse);
      });
    } catch (error) {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      resolve({
        ok: false,
        error: error instanceof Error ? error.message : "Unknown sendMessage error",
      } as TResponse);
    }
  });

const enrichWithAi = async (ui: UiRefs, settings: UserSettings): Promise<UserSettings> => {
  if (!getProviderKey(settings)) {
    ui.parseStatus.textContent = `${parseCoverageText(readSnapshot(ui))} · Set ${providerLabel(settings.llmProvider)} key`;
    return settings;
  }

  const snapshot = readSnapshot(ui);
  const response = await sendMessageWithTimeout<LlmEnrichmentResponse>({
    type: "LLM_ENRICH_PROFILE",
    snapshot,
  });

  if (!response?.ok || !response.enrichment) {
    ui.parseStatus.textContent = `${parseCoverageText(snapshot)} · AI error`;
    debugLog("ai", "enrich:error", { response });
    return settings;
  }

  const enrichmentCandidate: ProspectSnapshot = {
    ...snapshot,
    headline: response.enrichment.headline || snapshot.headline,
    companyName: response.enrichment.companyName || snapshot.companyName,
    location: response.enrichment.location || snapshot.location,
    ...(response.enrichment.aboutSummary || snapshot.about
      ? { about: response.enrichment.aboutSummary || snapshot.about || "" }
      : {}),
  };
  const merged: ProspectSnapshot = mergeSnapshot(snapshot, enrichmentCandidate);

  latestAiSignals = response.enrichment.highLevelSignals ?? [];
  latestAiScores = response.enrichment.scores ?? emptyAiScores();
  syncDerivedFields(merged);
  populateSnapshotInputs(ui, merged);
  renderEnrichmentPanel(ui, latestAiSignals, latestAiScores);
  ui.parseStatus.textContent = `${parseCoverageText(merged)} · AI enriched`;

  debugLog("ai", "enrich:success", {
    coverage: ui.parseStatus.textContent,
    aiSignals: latestAiSignals,
    merged,
  });

  return settings;
};

const attachCopyHandler = (
  button: HTMLButtonElement,
  getText: () => string,
  profileUrl: string,
): void => {
  button.addEventListener("click", async () => {
    const ok = await copyText(getText());
    if (!ok) {
      return;
    }
    await addActivityEvent(profileUrl, "COPIED");
  });
};

const openPromptModal = (ui: UiRefs): void => {
  ui.promptModal.classList.remove("hidden");
  ui.promptEditor.focus();
  ui.promptEditor.select();
};

const closePromptModal = (ui: UiRefs): void => {
  ui.promptModal.classList.add("hidden");
};

const openAiModal = (ui: UiRefs): void => {
  ui.aiModal.classList.remove("hidden");
};

const closeAiModal = (ui: UiRefs): void => {
  ui.aiModal.classList.add("hidden");
};

const defaultModelForProvider = (provider: LlmProvider): string =>
  provider === "gemini" ? "gemini-2.5-flash" : "gpt-4.1-mini";

const hydrateAiSettingsForm = (ui: UiRefs, settings: UserSettings): void => {
  const provider = settings.llmProvider;
  ui.aiProvider.value = provider;
  ui.aiModel.value = settings.llmModel || defaultModelForProvider(provider);
  ui.aiKey.value = getProviderKey(settings, provider);
  ui.aiKey.placeholder = provider === "gemini" ? "AIza..." : "sk-...";
};

const setCollapsedState = (ui: UiRefs, collapsed: boolean): void => {
  ui.root.classList.toggle("dc-collapsed", collapsed);
  ui.toggle.textContent = collapsed ? "Expand" : "Collapse";
  ui.launcher.textContent = "Open Prospector";
  if (collapsed) {
    ui.launcher.style.display = "inline-flex";
    return;
  }
  ui.launcher.style.display = "none";
};

const buildUi = async (): Promise<UiRefs> => {
  document.getElementById(LAUNCHER_ID)?.remove();
  document.getElementById(ROOT_ID)?.remove();

  const root = document.createElement("div");
  root.id = ROOT_ID;
  root.innerHTML = `
    <div class="dc-header">
      <div class="dc-title">Wealthsimple Prospector</div>
      <div class="dc-header-actions">
        <button id="dc-settings-cog" class="dc-icon-button" title="AI settings" aria-label="AI settings">&#9881;</button>
        <button id="dc-toggle">Collapse</button>
      </div>
    </div>
    <div class="dc-body">
      <section class="dc-section">
        <h3>Prospect Snapshot</h3>
        <div id="dc-parse-status" class="dc-meta"></div>
        <label class="dc-field"><span>Name</span><input id="dc-name" class="dc-input" /></label>
        <label class="dc-field"><span>Headline / Title</span><input id="dc-headline" class="dc-input" /></label>
        <label class="dc-field"><span>Company</span><input id="dc-company" class="dc-input" /></label>
        <label class="dc-field"><span>Location</span><input id="dc-location" class="dc-input" /></label>
        <label class="dc-field"><span>Profile URL</span><input id="dc-profile-url" class="dc-input" /></label>
        <div class="dc-actions">
          <button id="dc-save" class="dc-button">Save</button>
          <button id="dc-refresh-parse" class="dc-button secondary">Refresh</button>
          <button id="dc-ai-enrich" class="dc-button secondary">AI Enrich</button>
        </div>
      </section>

      <section class="dc-section">
        <h3>AI Enrichment</h3>
        <div class="dc-field"><span>ICP Fit</span><div id="dc-ai-icp-score"></div></div>
        <ul id="dc-ai-icp-reasons" class="dc-reasons"></ul>
        <div class="dc-field"><span>Capacity</span><div id="dc-ai-capacity-score"></div></div>
        <ul id="dc-ai-capacity-reasons" class="dc-reasons"></ul>
        <div class="dc-field"><span>Signals</span></div>
        <ul id="dc-ai-signals" class="dc-reasons"></ul>
      </section>

      <section class="dc-section">
        <h3>Message Generator</h3>
        <div class="dc-meta">Generate one copy-ready draft from profile + AI context.</div>
        <div class="dc-actions">
          <button id="dc-generate" class="dc-button">Generate</button>
          <button id="dc-regenerate" class="dc-button secondary">Regenerate</button>
          <button id="dc-edit-prompt" class="dc-button secondary">Edit Prompt</button>
        </div>
        <label class="dc-field"><span>Generated message (<=600)</span><textarea id="dc-output" class="dc-textarea"></textarea></label>
        <div class="dc-actions"><button id="dc-copy-output" class="dc-button secondary">Copy Message</button></div>
      </section>
    </div>
    <div id="dc-prompt-modal" class="dc-modal hidden">
      <div class="dc-modal-card">
        <h3>Edit Generation Prompt</h3>
        <label class="dc-field">
          <span>Prompt used for Generate/Regenerate</span>
          <textarea id="dc-prompt-editor" class="dc-textarea"></textarea>
        </label>
        <div class="dc-actions">
          <button id="dc-prompt-save" class="dc-button">Save Prompt</button>
          <button id="dc-prompt-cancel" class="dc-button secondary">Cancel</button>
        </div>
      </div>
    </div>
    <div id="dc-ai-modal" class="dc-modal hidden">
      <div class="dc-modal-card">
        <h3>AI Settings</h3>
        <label class="dc-field">
          <span>Provider</span>
          <select id="dc-ai-provider" class="dc-select">
            <option value="openai">ChatGPT (OpenAI)</option>
            <option value="gemini">Gemini (Google)</option>
          </select>
        </label>
        <label class="dc-field">
          <span>Model</span>
          <input id="dc-ai-model" class="dc-input" />
        </label>
        <label class="dc-field">
          <span>API key</span>
          <input id="dc-ai-key" class="dc-input" type="password" />
        </label>
        <div class="dc-actions">
          <button id="dc-ai-save" class="dc-button">Save AI Settings</button>
          <button id="dc-ai-cancel" class="dc-button secondary">Cancel</button>
        </div>
      </div>
    </div>
  `;

  const launcher = document.createElement("button");
  launcher.id = LAUNCHER_ID;
  launcher.className = "dc-profile-launcher";
  launcher.textContent = "Open Prospector";

  document.body.append(root);
  document.body.append(launcher);

  const collapsed = await getSidebarCollapsed();
  root.classList.toggle("dc-collapsed", collapsed);
  launcher.textContent = "Open Prospector";
  if (collapsed) {
    launcher.style.display = "inline-flex";
  } else {
    launcher.style.display = "none";
  }

  const toggle = byId<HTMLButtonElement>(root, "dc-toggle");

  return {
    root,
    launcher,
    settingsCog: byId(root, "dc-settings-cog"),
    toggle,
    save: byId(root, "dc-save"),
    refreshParse: byId(root, "dc-refresh-parse"),
    aiEnrich: byId(root, "dc-ai-enrich"),
    parseStatus: byId(root, "dc-parse-status"),
    aiSignals: byId(root, "dc-ai-signals"),
    aiIcpScore: byId(root, "dc-ai-icp-score"),
    aiCapacityScore: byId(root, "dc-ai-capacity-score"),
    aiIcpReasons: byId(root, "dc-ai-icp-reasons"),
    aiCapacityReasons: byId(root, "dc-ai-capacity-reasons"),
    generate: byId(root, "dc-generate"),
    regenerate: byId(root, "dc-regenerate"),
    editPrompt: byId(root, "dc-edit-prompt"),
    name: byId(root, "dc-name"),
    headline: byId(root, "dc-headline"),
    company: byId(root, "dc-company"),
    location: byId(root, "dc-location"),
    profileUrl: byId(root, "dc-profile-url"),
    promptModal: byId(root, "dc-prompt-modal"),
    promptEditor: byId(root, "dc-prompt-editor"),
    promptSave: byId(root, "dc-prompt-save"),
    promptCancel: byId(root, "dc-prompt-cancel"),
    aiModal: byId(root, "dc-ai-modal"),
    aiProvider: byId(root, "dc-ai-provider"),
    aiModel: byId(root, "dc-ai-model"),
    aiKey: byId(root, "dc-ai-key"),
    aiSave: byId(root, "dc-ai-save"),
    aiCancel: byId(root, "dc-ai-cancel"),
    messageOutput: byId(root, "dc-output"),
    copyOutput: byId(root, "dc-copy-output"),
  };
};

const hydrateAndBind = async (): Promise<void> => {
  if (!isLinkedInProfilePage(window.location.href)) {
    document.getElementById(LAUNCHER_ID)?.remove();
    document.getElementById(ROOT_ID)?.remove();
    return;
  }

  debugLog("content", "hydrate:start", { url: window.location.href });

  const ui = await buildUi();
  let settings = await getSettings();
  ui.promptEditor.value = settings.outreachPrompt;
  hydrateAiSettingsForm(ui, settings);

  const parsed = await parseSnapshotWithRetries(window.location.href);
  const profileUrl = normalizeProfileUrl(parsed.profileUrl);
  const existing = await getProspectRecord(profileUrl);

  latestAiSignals = existing?.signals ?? [];
  latestAiScores = existing?.scores ?? null;
  const snapshot: ProspectSnapshot = {
    profileUrl,
    name: existing?.name || parsed.name,
    headline: existing?.headline || parsed.headline,
    companyName: existing?.companyName || parsed.companyName,
    location: existing?.location || parsed.location,
    ...(existing?.about || parsed.about ? { about: existing?.about || parsed.about } : {}),
    ...(existing?.experienceHighlights || parsed.experienceHighlights
      ? { experienceHighlights: existing?.experienceHighlights || parsed.experienceHighlights }
      : {}),
    ...(existing?.recentActivity || parsed.recentActivity
      ? { recentActivity: existing?.recentActivity || parsed.recentActivity }
      : {}),
  };

  syncDerivedFields(snapshot);
  populateSnapshotInputs(ui, snapshot);
  renderEnrichmentPanel(ui, latestAiSignals, latestAiScores);
  ui.parseStatus.textContent = parseCoverageText(snapshot);
  if (!getProviderKey(settings)) {
    ui.parseStatus.textContent = `${ui.parseStatus.textContent} · Set ${providerLabel(settings.llmProvider)} key`;
  }

  debugLog("parser", "snapshot:parsed", {
    coverage: ui.parseStatus.textContent,
    snapshot,
  });

  installDebugApi(() => ({
    currentUrl: window.location.href,
    parseStatus: ui.parseStatus.textContent,
    snapshot: readSnapshot(ui),
    aiSignals: latestAiSignals,
    aiScores: latestAiScores,
    outreachPrompt: settings.outreachPrompt,
    llmProvider: settings.llmProvider,
    llmModel: settings.llmModel,
  }));

  if (existing?.generatedMessages) {
    setMessageFields(ui, existing.generatedMessages);
  }

  ui.toggle.addEventListener("click", async () => {
    const collapsed = !ui.root.classList.contains("dc-collapsed");
    setCollapsedState(ui, collapsed);
    await saveSidebarCollapsed(collapsed);
  });

  ui.launcher.addEventListener("click", async () => {
    const collapsed = ui.root.classList.contains("dc-collapsed");
    const next = !collapsed;
    setCollapsedState(ui, next);
    await saveSidebarCollapsed(next);
  });

  ui.refreshParse.addEventListener("click", async () => {
    const refreshed = await parseSnapshotWithRetries(window.location.href);
    const merged = mergeSnapshot(readSnapshot(ui), refreshed);
    syncDerivedFields(merged);
    populateSnapshotInputs(ui, merged);
    renderEnrichmentPanel(ui, latestAiSignals, latestAiScores);
    ui.parseStatus.textContent = parseCoverageText(merged);

    debugLog("parser", "snapshot:refresh", {
      coverage: ui.parseStatus.textContent,
      merged,
    });
  });

  ui.aiEnrich.addEventListener("click", async () => {
    const originalText = ui.aiEnrich.textContent;
    ui.aiEnrich.disabled = true;
    ui.aiEnrich.textContent = "Enriching...";

    try {
      settings = await enrichWithAi(ui, settings);
    } finally {
      ui.aiEnrich.disabled = false;
      ui.aiEnrich.textContent = originalText;
    }
  });

  ui.settingsCog.addEventListener("click", () => {
    hydrateAiSettingsForm(ui, settings);
    openAiModal(ui);
  });

  ui.aiProvider.addEventListener("change", () => {
    const selected = (ui.aiProvider.value === "gemini" ? "gemini" : "openai") as LlmProvider;
    const defaultModel = defaultModelForProvider(selected);
    ui.aiKey.value = getProviderKey(settings, selected);
    ui.aiModel.value = defaultModel;
    ui.aiModel.placeholder = defaultModel;
    ui.aiKey.placeholder = selected === "gemini" ? "AIza..." : "sk-...";
  });

  ui.aiSave.addEventListener("click", async () => {
    const provider = (ui.aiProvider.value === "gemini" ? "gemini" : "openai") as LlmProvider;
    const model = ui.aiModel.value.trim() || defaultModelForProvider(provider);
    const key = ui.aiKey.value.trim();

    settings = {
      ...settings,
      llmEnabled: true,
      llmProvider: provider,
      llmModel: model,
      openAiApiKey: provider === "openai" ? key : settings.openAiApiKey,
      geminiApiKey: provider === "gemini" ? key : settings.geminiApiKey,
    };
    await saveSettings(settings);
    closeAiModal(ui);
    ui.parseStatus.textContent = `${parseCoverageText(readSnapshot(ui))} · AI settings saved (${providerLabel(provider)})`;
    debugLog("ai", "settings:updated", {
      provider,
      model,
      hasKey: Boolean(key),
    });
  });

  ui.aiCancel.addEventListener("click", () => {
    closeAiModal(ui);
  });

  ui.aiModal.addEventListener("click", (event) => {
    if (event.target === ui.aiModal) {
      closeAiModal(ui);
    }
  });

  ui.editPrompt.addEventListener("click", () => {
    ui.promptEditor.value = settings.outreachPrompt;
    openPromptModal(ui);
  });

  ui.promptSave.addEventListener("click", async () => {
    const nextPrompt = ui.promptEditor.value.trim();
    if (!nextPrompt) {
      ui.parseStatus.textContent = `${ui.parseStatus.textContent || ""} · Prompt cannot be empty`;
      return;
    }
    settings = {
      ...settings,
      outreachPrompt: nextPrompt,
    };
    await saveSettings(settings);
    closePromptModal(ui);
    debugLog("generator", "prompt:updated", {
      chars: nextPrompt.length,
    });
  });

  ui.promptCancel.addEventListener("click", () => {
    closePromptModal(ui);
  });

  ui.promptModal.addEventListener("click", (event) => {
    if (event.target === ui.promptModal) {
      closePromptModal(ui);
    }
  });

  ui.save.addEventListener("click", async () => {
    const activeSnapshot = readSnapshot(ui);
    const signals = buildRecordSignals(activeSnapshot);
    const scores = latestAiScores ?? emptyAiScores();

    const previousRecord = await getProspectRecord(activeSnapshot.profileUrl);
    const record: ProspectRecord = {
      ...activeSnapshot,
      scores,
      signals,
      tags: previousRecord?.tags ?? existing?.tags ?? [],
      status: previousRecord?.status ?? existing?.status ?? "New",
      notes: previousRecord?.notes ?? existing?.notes ?? "",
      updatedAt: new Date().toISOString(),
      ...(previousRecord?.generatedMessages
        ? { generatedMessages: previousRecord.generatedMessages }
        : existing?.generatedMessages
          ? { generatedMessages: existing.generatedMessages }
          : {}),
    };

    await saveProspectRecord(record);
    await addActivityEvent(activeSnapshot.profileUrl, "SAVED");
  });

  const generate = async (seed: number): Promise<void> => {
    if (!getProviderKey(settings)) {
      ui.parseStatus.textContent = `${parseCoverageText(readSnapshot(ui))} · Set ${providerLabel(settings.llmProvider)} key`;
      return;
    }

    const activeSnapshot = readSnapshot(ui);
    const signals = buildRecordSignals(activeSnapshot);
    const aiScores = latestAiScores ?? emptyAiScores();

    const promptInstruction = settings.outreachPrompt.trim();

    const response = await sendMessageWithTimeout<LlmGenerateResponse>(
      {
        type: "LLM_GENERATE_OUTREACH",
        snapshot: activeSnapshot,
        aiSignals: signals,
        aiScores,
        promptInstruction,
        variantSeed: seed,
      },
      25000,
    );

    if (!response?.ok || !response.draft?.message?.trim()) {
      ui.parseStatus.textContent = `${parseCoverageText(activeSnapshot)} · Message generation error`;
      debugLog("generator", "messages:error", {
        response,
        profileUrl: activeSnapshot.profileUrl,
      });
      return;
    }

    const trimmedMessage = response.draft.message.trim().slice(0, 600);
    const messages: GeneratedMessages = {
      connectionNote: trimmedMessage,
      dm1: trimmedMessage,
      followUp1: "",
      followUp2: "",
      personalizationHook: response.draft.personalizationHook || "",
    };

    setMessageFields(ui, messages);
    ui.parseStatus.textContent = `${parseCoverageText(activeSnapshot)} · Message generated`;

    const previousRecord = await getProspectRecord(activeSnapshot.profileUrl);
    const updated: ProspectRecord = {
      ...activeSnapshot,
      scores: aiScores,
      signals,
      tags: previousRecord?.tags ?? existing?.tags ?? [],
      status: previousRecord?.status ?? existing?.status ?? "New",
      notes: previousRecord?.notes ?? existing?.notes ?? "",
      generatedMessages: messages,
      updatedAt: new Date().toISOString(),
    };

    await saveProspectRecord(updated);
    await addActivityEvent(activeSnapshot.profileUrl, "GENERATED", {
      promptMode: "single-modal",
    });
    debugLog("generator", "messages:generated", {
      promptMode: "single-modal",
      promptChars: promptInstruction.length,
      profileUrl: activeSnapshot.profileUrl,
      aiSignalCount: signals.length,
      signalsUsedByModel: response.draft.signalsUsed,
      personalizationHook: response.draft.personalizationHook,
    });
  };

  ui.generate.addEventListener("click", async () => {
    const generateLabel = ui.generate.textContent;
    const regenerateLabel = ui.regenerate.textContent;
    ui.generate.disabled = true;
    ui.regenerate.disabled = true;
    ui.generate.textContent = "Generating...";

    try {
      await generate(regenerateSeed);
    } finally {
      ui.generate.disabled = false;
      ui.regenerate.disabled = false;
      ui.generate.textContent = generateLabel;
      ui.regenerate.textContent = regenerateLabel;
    }
  });

  ui.regenerate.addEventListener("click", async () => {
    const generateLabel = ui.generate.textContent;
    const regenerateLabel = ui.regenerate.textContent;
    ui.generate.disabled = true;
    ui.regenerate.disabled = true;
    ui.regenerate.textContent = "Regenerating...";
    regenerateSeed += 1;

    try {
      await generate(regenerateSeed);
    } finally {
      ui.generate.disabled = false;
      ui.regenerate.disabled = false;
      ui.generate.textContent = generateLabel;
      ui.regenerate.textContent = regenerateLabel;
    }
  });

  attachCopyHandler(ui.copyOutput, () => ui.messageOutput.value, profileUrl);
};

const watchProfileNavigation = (): void => {
  const readCurrent = (): string => normalizeProfileUrl(window.location.href);
  latestProfileUrl = readCurrent();

  window.setInterval(() => {
    const current = readCurrent();
    if (current === latestProfileUrl) {
      return;
    }
    latestProfileUrl = current;
    void hydrateAndBind();
  }, 1000);
};

void hydrateAndBind();
watchProfileNavigation();
