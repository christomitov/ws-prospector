import { useEffect, useMemo, useState } from "react";

import { defaultSettings, getSettings, saveSettings } from "../lib/storage";
import type { LlmProvider, PromptTemplate, RuleDefinition, UserSettings } from "../lib/types";

const parsePromptTemplates = (value: string): PromptTemplate[] =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx) => {
      const [rawName = "", rawInstruction = ""] = line.split("|").map((item) => item.trim());
      return {
        id: `prompt-${idx + 1}`,
        name: rawName || `Prompt ${idx + 1}`,
        instruction:
          rawInstruction ||
          "Write concise, specific outreach grounded in visible profile signals with one soft CTA.",
      };
    });

const formatPromptTemplates = (settings: UserSettings): string =>
  settings.promptTemplates
    .map((template) => `${template.name} | ${template.instruction}`)
    .join("\n");

const parseRules = (jsonText: string): RuleDefinition[] => {
  const parsed = JSON.parse(jsonText) as RuleDefinition[];
  return parsed;
};

export const App = () => {
  const [settings, setSettings] = useState<UserSettings>(defaultSettings);
  const [promptTemplatesText, setPromptTemplatesText] = useState(
    formatPromptTemplates(defaultSettings),
  );
  const [defaultPromptTemplateId, setDefaultPromptTemplateId] = useState(
    defaultSettings.defaultPromptTemplateId,
  );
  const [outreachPromptText, setOutreachPromptText] = useState(defaultSettings.outreachPrompt);
  const [icpRulesText, setIcpRulesText] = useState(
    JSON.stringify(defaultSettings.icpRules, null, 2),
  );
  const [capacityRulesText, setCapacityRulesText] = useState(
    JSON.stringify(defaultSettings.capacityRules, null, 2),
  );
  const [status, setStatus] = useState("");

  useEffect(() => {
    void (async () => {
      const loaded = await getSettings();
      setSettings(loaded);
      setOutreachPromptText(loaded.outreachPrompt);
      setPromptTemplatesText(formatPromptTemplates(loaded));
      setDefaultPromptTemplateId(loaded.defaultPromptTemplateId);
      setIcpRulesText(JSON.stringify(loaded.icpRules, null, 2));
      setCapacityRulesText(JSON.stringify(loaded.capacityRules, null, 2));
    })();
  }, []);

  const parsedTemplates = useMemo(
    () => parsePromptTemplates(promptTemplatesText),
    [promptTemplatesText],
  );

  const canSave = useMemo(() => parsedTemplates.length > 0, [parsedTemplates]);

  const onSave = async () => {
    try {
      const templates = parsePromptTemplates(promptTemplatesText);
      const defaultTemplate =
        templates.find((template) => template.id === defaultPromptTemplateId) ?? templates[0];

      const next: UserSettings = {
        ...settings,
        outreachPrompt: outreachPromptText.trim() || defaultSettings.outreachPrompt,
        promptTemplates: templates,
        defaultPromptTemplateId: defaultTemplate?.id ?? templates[0]?.id ?? "prompt-1",
        icpRules: parseRules(icpRulesText),
        capacityRules: parseRules(capacityRulesText),
      };

      await saveSettings(next);
      setSettings(next);
      setDefaultPromptTemplateId(next.defaultPromptTemplateId);
      setStatus("Saved successfully.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setStatus(`Save failed: ${message}`);
    }
  };

  const onReset = async () => {
    await saveSettings(defaultSettings);
    setSettings(defaultSettings);
    setOutreachPromptText(defaultSettings.outreachPrompt);
    setPromptTemplatesText(formatPromptTemplates(defaultSettings));
    setDefaultPromptTemplateId(defaultSettings.defaultPromptTemplateId);
    setIcpRulesText(JSON.stringify(defaultSettings.icpRules, null, 2));
    setCapacityRulesText(JSON.stringify(defaultSettings.capacityRules, null, 2));
    setStatus("Reset to defaults.");
  };

  return (
    <main className="options-shell">
      <header>
        <h1>Wealthsimple Prospector Settings</h1>
        <p>Keep this simple: prompt templates, score rules, and privacy toggles.</p>
      </header>

      <section className="card">
        <h2>Sidebar Outreach Prompt</h2>
        <label>
          Default prompt text for sidebar generation
          <textarea
            value={outreachPromptText}
            onChange={(event) => setOutreachPromptText(event.target.value)}
            rows={8}
          />
        </label>
      </section>

      <section className="card">
        <h2>Prompt Templates</h2>
        <label>
          Templates (one per line: Name | Prompt instruction)
          <textarea
            value={promptTemplatesText}
            onChange={(event) => setPromptTemplatesText(event.target.value)}
            rows={7}
          />
        </label>
        <label>
          Default template
          <select
            value={defaultPromptTemplateId}
            onChange={(event) => setDefaultPromptTemplateId(event.target.value)}
          >
            {parsedTemplates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="card">
        <h2>Scoring Rules JSON</h2>
        <label>
          ICP rules
          <textarea
            value={icpRulesText}
            onChange={(event) => setIcpRulesText(event.target.value)}
            rows={10}
          />
        </label>
        <label>
          Capacity rules
          <textarea
            value={capacityRulesText}
            onChange={(event) => setCapacityRulesText(event.target.value)}
            rows={10}
          />
        </label>
      </section>

      <section className="card">
        <h2>Privacy Toggles</h2>
        <label>
          <input
            type="checkbox"
            checked={settings.privacyFlags.includeAbout}
            onChange={(event) =>
              setSettings({
                ...settings,
                privacyFlags: {
                  ...settings.privacyFlags,
                  includeAbout: event.target.checked,
                },
              })
            }
          />
          Include About section in generation context
        </label>
        <label>
          <input
            type="checkbox"
            checked={settings.privacyFlags.includeExperienceHighlights}
            onChange={(event) =>
              setSettings({
                ...settings,
                privacyFlags: {
                  ...settings.privacyFlags,
                  includeExperienceHighlights: event.target.checked,
                },
              })
            }
          />
          Include experience highlights in generation context
        </label>
        <label>
          <input
            type="checkbox"
            checked={settings.privacyFlags.includeCrmNotes}
            onChange={(event) =>
              setSettings({
                ...settings,
                privacyFlags: {
                  ...settings.privacyFlags,
                  includeCrmNotes: event.target.checked,
                },
              })
            }
          />
          Include CRM notes (currently unused in Milestone 1)
        </label>
      </section>

      <section className="card">
        <h2>AI Enrichment</h2>
        <label>
          <input
            type="checkbox"
            checked={settings.llmEnabled}
            onChange={(event) => setSettings({ ...settings, llmEnabled: event.target.checked })}
          />
          Enable AI profile enrichment
        </label>
        <label>
          Provider
          <select
            value={settings.llmProvider}
            onChange={(event) =>
              setSettings({
                ...settings,
                llmProvider: event.target.value as LlmProvider,
                llmModel: event.target.value === "gemini" ? "gemini-2.5-flash" : "gpt-4.1-mini",
              })
            }
          >
            <option value="openai">ChatGPT (OpenAI)</option>
            <option value="gemini">Gemini (Google)</option>
          </select>
        </label>
        <label>
          Model
          <input
            type="text"
            value={settings.llmModel}
            onChange={(event) => setSettings({ ...settings, llmModel: event.target.value })}
            placeholder={settings.llmProvider === "gemini" ? "gemini-2.5-flash" : "gpt-4.1-mini"}
          />
        </label>
        <label>
          OpenAI API key (stored locally in extension storage)
          <input
            type="password"
            value={settings.openAiApiKey}
            onChange={(event) => setSettings({ ...settings, openAiApiKey: event.target.value })}
            placeholder="sk-..."
          />
        </label>
        <label>
          Gemini API key (stored locally in extension storage)
          <input
            type="password"
            value={settings.geminiApiKey}
            onChange={(event) => setSettings({ ...settings, geminiApiKey: event.target.value })}
            placeholder="AIza..."
          />
        </label>
      </section>

      <footer className="footer-actions">
        <button type="button" disabled={!canSave} onClick={() => void onSave()}>
          Save Settings
        </button>
        <button type="button" className="secondary" onClick={() => void onReset()}>
          Reset Defaults
        </button>
        <span>{status}</span>
      </footer>
    </main>
  );
};
