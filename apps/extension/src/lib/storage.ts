import type { ActivityEvent, ActivityEventType, ProspectRecord, UserSettings } from "./types";

const SETTINGS_KEY = "deal_copilot:settings";
const UI_COLLAPSED_KEY = "deal_copilot:ui_collapsed";
const keyForProspect = (profileUrl: string) =>
  `deal_copilot:prospect:${encodeURIComponent(profileUrl)}`;
const keyForActivity = (profileUrl: string) =>
  `deal_copilot:activity:${encodeURIComponent(profileUrl)}`;

export const defaultSettings: UserSettings = {
  offers: [
    {
      id: "offer-1",
      name: "Outbound Optimization Sprint",
      description: "2-week sprint to improve reply rates and meeting conversion.",
      targetPersonaTags: ["Founder", "Sales Leader", "RevOps"],
    },
    {
      id: "offer-2",
      name: "LinkedIn Outreach System",
      description: "Build a repeatable outbound workflow with quality controls.",
      targetPersonaTags: ["Founder", "Agency Owner"],
    },
  ],
  personas: ["Founder", "Exec", "HR", "Sales Leader", "Marketing Leader"],
  ctaDefaults: "Soft question CTA",
  outreachPrompt:
    'Framework: start with "hey (name)" lowercase, then personalized opener from profile, then max-2-sentence pain point on fragmented personal finances, then Wealthsimple Private Wealth positioning for $500K-$50M+ investable assets; include exact line "And frankly a more modern approach to wealth management than legacy banks."; include exact CTA "Happy to do a 15-minute call next week to see if our exclusive team can add value and bring clarity to your current setup."; close with "Cheers". Tone: non-spammy, curious, concise, subtly exclusive, use relevant commonalities/humor when appropriate, unique opener that drives reply.',
  promptTemplates: [
    {
      id: "prompt-1",
      name: "Wealthsimple framework",
      instruction:
        'Framework: start with "hey (name)" lowercase, then personalized opener from profile, then max-2-sentence pain point on fragmented personal finances, then Wealthsimple Private Wealth positioning for $500K-$50M+ investable assets; include exact line "And frankly a more modern approach to wealth management than legacy banks."; include exact CTA "Happy to do a 15-minute call next week to see if our exclusive team can add value and bring clarity to your current setup."; close with "Cheers". Tone: non-spammy, curious, concise, subtly exclusive, use relevant commonalities/humor when appropriate, unique opener that drives reply.',
    },
    {
      id: "prompt-2",
      name: "Value-first message",
      instruction:
        "Lead with one practical improvement idea tied to their role, then invite a short discussion.",
    },
  ],
  defaultPromptTemplateId: "prompt-1",
  icpRules: [
    {
      id: "icp-founder",
      label: "Founder / owner seniority",
      category: "Seniority",
      weight: 25,
      source: "headline",
      keywords: ["founder", "owner", "partner", "principal", "managing partner"],
    },
    {
      id: "icp-vp-cxo",
      label: "VP/CXO/Head role",
      category: "Seniority",
      weight: 20,
      source: "headline",
      keywords: ["vp", "chief", "cxo", "head of"],
    },
    {
      id: "icp-industry",
      label: "Target industry keyword match",
      category: "Industry",
      weight: 10,
      source: "headline",
      keywords: ["software", "saas", "services", "consulting"],
    },
    {
      id: "icp-finance-domain-about",
      label: "Finance/FP&A expertise in About",
      category: "Industry",
      weight: 12,
      source: "about",
      keywords: ["fp&a", "financial planning", "corporate performance", "cpm", "epm"],
    },
    {
      id: "icp-junior-negative",
      label: "Early-career title mismatch",
      category: "Seniority",
      weight: -15,
      source: "headline",
      keywords: ["student", "intern", "junior"],
    },
  ],
  capacityRules: [
    {
      id: "cap-founder",
      label: "Founder/Owner signal",
      category: "RoleMatch",
      weight: 25,
      source: "headline",
      keywords: ["founder", "owner", "partner"],
    },
    {
      id: "cap-c-level",
      label: "C-level / VP signal",
      category: "RoleMatch",
      weight: 20,
      source: "headline",
      keywords: ["chief", "vp", "vice president", "head of"],
    },
    {
      id: "cap-finance-keywords",
      label: "Finance or investment indicators",
      category: "Industry",
      weight: 10,
      source: "headline",
      keywords: ["investor", "portfolio", "private equity", "wealth"],
    },
    {
      id: "cap-experience-advisory",
      label: "Leadership/advisory in experience",
      category: "RoleMatch",
      weight: 12,
      source: "experienceHighlights",
      keywords: ["founder", "chief", "advisor", "fractional", "consulting", "lead"],
    },
    {
      id: "cap-recent-activity-momentum",
      label: "Recent activity momentum",
      category: "FundingTrigger",
      weight: 8,
      source: "recentActivity",
      keywords: ["posted in the past", "announc", "proud to", "launch", "partner"],
    },
    {
      id: "cap-early-career-negative",
      label: "Early-career indicator",
      category: "RoleMatch",
      weight: -10,
      source: "headline",
      keywords: ["student", "intern", "assistant"],
    },
  ],
  privacyFlags: {
    includeAbout: true,
    includeExperienceHighlights: true,
    includeCrmNotes: false,
  },
  llmEnabled: true,
  llmProvider: "openai",
  llmModel: "gpt-4.1-mini",
  openAiApiKey: "",
  geminiApiKey: "",
};

const storageGet = async <T>(key: string): Promise<T | undefined> => {
  const data = (await chrome.storage.local.get(key)) as Record<string, T | undefined>;
  return data[key];
};

const storageSet = async (payload: Record<string, unknown>): Promise<void> => {
  await chrome.storage.local.set(payload);
};

export const getSettings = async (): Promise<UserSettings> => {
  const settings = await storageGet<UserSettings>(SETTINGS_KEY);
  if (!settings) {
    return defaultSettings;
  }

  const legacySettings = settings as UserSettings & { llmApiKey?: string };
  const migratedOpenAiApiKey =
    settings.openAiApiKey || legacySettings.llmApiKey || defaultSettings.openAiApiKey;

  return {
    ...defaultSettings,
    ...settings,
    llmProvider: settings.llmProvider || defaultSettings.llmProvider,
    openAiApiKey: migratedOpenAiApiKey,
    geminiApiKey: settings.geminiApiKey || defaultSettings.geminiApiKey,
    promptTemplates:
      settings.promptTemplates && settings.promptTemplates.length > 0
        ? settings.promptTemplates
        : defaultSettings.promptTemplates,
    defaultPromptTemplateId:
      settings.defaultPromptTemplateId || defaultSettings.defaultPromptTemplateId,
    privacyFlags: {
      ...defaultSettings.privacyFlags,
      ...settings.privacyFlags,
    },
  };
};

export const saveSettings = async (settings: UserSettings): Promise<void> => {
  await storageSet({ [SETTINGS_KEY]: settings });
};

export const getProspectRecord = async (profileUrl: string): Promise<ProspectRecord | undefined> =>
  storageGet<ProspectRecord>(keyForProspect(profileUrl));

export const saveProspectRecord = async (record: ProspectRecord): Promise<void> => {
  await storageSet({ [keyForProspect(record.profileUrl)]: record });
};

export const getActivityEvents = async (profileUrl: string): Promise<ActivityEvent[]> =>
  (await storageGet<ActivityEvent[]>(keyForActivity(profileUrl))) ?? [];

export const addActivityEvent = async (
  profileUrl: string,
  type: ActivityEventType,
  payload?: Record<string, string>,
): Promise<void> => {
  const list = await getActivityEvents(profileUrl);
  const event: ActivityEvent = {
    profileUrl,
    type,
    timestamp: new Date().toISOString(),
    ...(payload ? { payload } : {}),
  };
  const next = [event, ...list].slice(0, 100);
  await storageSet({ [keyForActivity(profileUrl)]: next });
};

export const getSidebarCollapsed = async (): Promise<boolean> => {
  const stored = await storageGet<boolean>(UI_COLLAPSED_KEY);
  return stored ?? false;
};

export const saveSidebarCollapsed = async (collapsed: boolean): Promise<void> => {
  await storageSet({ [UI_COLLAPSED_KEY]: collapsed });
};
