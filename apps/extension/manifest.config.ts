import { defineManifest } from "@crxjs/vite-plugin";

export default defineManifest({
  manifest_version: 3,
  name: "Wealthsimple Prospector",
  version: "0.1.0",
  description: "Qualify prospects, draft outreach, and log activity from LinkedIn profile pages.",
  permissions: ["storage"],
  host_permissions: [
    "https://www.linkedin.com/*",
    "https://api.openai.com/*",
    "https://generativelanguage.googleapis.com/*",
  ],
  background: {
    service_worker: "src/background/index.ts",
    type: "module",
  },
  action: {
    default_title: "Wealthsimple Prospector",
    default_popup: "src/popup/index.html",
  },
  options_page: "src/options/index.html",
  content_scripts: [
    {
      matches: ["https://www.linkedin.com/in/*"],
      js: ["src/content/main.ts"],
      run_at: "document_idle",
    },
  ],
});
