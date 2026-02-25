export type LlmProvider = "openai" | "gemini";

export type ActivityEventType =
  | "SAVED"
  | "GENERATED"
  | "COPIED"
  | "LOGGED_TOUCH"
  | "STAGE_MOVED"
  | "NOTE_ADDED";

export interface Offer {
  id: string;
  name: string;
  description: string;
  targetPersonaTags: string[];
}

export interface PromptTemplate {
  id: string;
  name: string;
  instruction: string;
}

export interface RuleDefinition {
  id: string;
  label: string;
  category:
    | "Seniority"
    | "CompanySize"
    | "Industry"
    | "Keywords"
    | "FundingTrigger"
    | "RoleMatch"
    | "Geography";
  weight: number;
  source:
    | "name"
    | "headline"
    | "companyName"
    | "location"
    | "about"
    | "experienceHighlights"
    | "recentActivity";
  keywords: string[];
}

export interface PrivacyFlags {
  includeAbout: boolean;
  includeExperienceHighlights: boolean;
  includeCrmNotes: boolean;
}

export interface UserSettings {
  offers: Offer[];
  personas: string[];
  ctaDefaults: string;
  outreachPrompt: string;
  promptTemplates: PromptTemplate[];
  defaultPromptTemplateId: string;
  icpRules: RuleDefinition[];
  capacityRules: RuleDefinition[];
  privacyFlags: PrivacyFlags;
  llmEnabled: boolean;
  llmProvider: LlmProvider;
  llmModel: string;
  openAiApiKey: string;
  geminiApiKey: string;
}

export interface ProspectSnapshot {
  profileUrl: string;
  linkedinId?: string;
  name: string;
  headline: string;
  companyName: string;
  companyUrl?: string;
  location: string;
  about?: string;
  experienceHighlights?: string;
  recentActivity?: string;
}

export interface ScoreBreakdown {
  icpFit: number;
  icpLabel: "Low" | "Medium" | "High";
  icpReasons: string[];
  capacity: number;
  capacityLabel: "Low" | "Medium" | "High";
  capacityReasons: string[];
}

export interface GeneratedMessages {
  connectionNote: string;
  dm1: string;
  followUp1: string;
  followUp2: string;
  personalizationHook: string;
}

export interface ProspectRecord extends ProspectSnapshot {
  signals: string[];
  scores: ScoreBreakdown;
  tags: string[];
  status: "New" | "Contacted" | "Connected" | "Replied" | "Qualified" | "Disqualified";
  notes: string;
  generatedMessages?: GeneratedMessages;
  updatedAt: string;
}

export interface ActivityEvent {
  profileUrl: string;
  type: ActivityEventType;
  timestamp: string;
  payload?: Record<string, string>;
}

export interface DebugEntry {
  timestamp: string;
  scope: string;
  event: string;
  details?: unknown;
}
