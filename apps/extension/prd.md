Product Spec: LinkedIn Deal Copilot (Chrome Extension)

1. Summary

A Chrome extension that adds a sidebar on LinkedIn profile pages. It helps a user (your fiancée) qualify prospects, generate personalized outreach messages, and sync/update CRM pipeline context, while keeping all “actions” manual (copy/paste + click send) to reduce enforcement risk.

2. Goals

Reduce manual work: eliminate repetitive copying of profile info and writing first drafts.

Improve targeting: provide an ICP Fit score + Capacity band score with transparent reasons.

Prevent duplicates: detect if the person/company already exists in CRM and show stage/last touch.

Improve conversion: generate message variants based on persona + offer + signals and support follow-ups.

Workflow-friendly: one-click “Save lead”, “Log touch”, “Move stage” inside sidebar.

3. Non-goals (explicitly out of scope)

Auto-clicking LinkedIn UI for Connect/Message/Follow/Next profile

Bulk scraping LinkedIn search results

“Net worth estimation” as a numeric claim (replace with capacity bands + evidence)

Bypassing LinkedIn paywalls / gated data / hidden endpoints

4. Target Users & Primary Use Cases

Primary user: individual prospector / agency / SDR doing LinkedIn outreach.

Use case A — Before connecting

On profile page: evaluate fit → generate a connection note (≤300 chars) → copy → send manually → log action.

Use case B — After connecting

On profile page: generate DM #1 + follow-up sequence → copy → send manually → log action → update pipeline stage.

Use case C — CRM hygiene

On profile page: “Already exists?” → show stage, owner, last activity → avoid duplicating leads.

5. UX Overview
   5.1 Sidebar placement

Inject a fixed sidebar on the right side of LinkedIn profile pages.

Collapsible; remembers open/closed state per user.

5.2 Sidebar sections (top → bottom)

Prospect Snapshot

Name

Headline / Title

Company

Location (if visible)

Profile URL (read-only)

Buttons: Save / Update, Copy Profile URL

Scores

ICP Fit: 0–100 with label (Low/Med/High)

Capacity: 0–100 with label (Low/Med/High)

Decision Authority: 0–100 (optional)

“Why?” collapsible list showing the triggered signals

CRM Panel

Status: Not found / Found

If found: Record link, Stage, Owner, Last activity date, Next task

Buttons:

Create Lead

Attach to existing

Move stage (dropdown)

Log touch (connection sent / message sent / replied / meeting booked)

Add note

Message Generator

Context controls:

Persona dropdown (e.g., Founder, Exec, HR, Sales leader, etc.)

Offer selection (stored in settings)

Tone (Friendly / Direct / Professional)

Objective (Connect / DM #1 / Follow-up / Breakup)

Output tabs:

Connection Note (≤300 chars)

DM #1 (≤600 chars)

Follow-up #1

Follow-up #2

Buttons:

Generate

Regenerate variant

Copy

Save to CRM notes (saves the generated copy)

Activity Log

Local timeline + CRM sync status

Events: Saved, Connection note generated, Copied, Logged touch, Stage moved, etc.

6. Data Model
   6.1 Local storage (Chrome storage)

Store per-user settings and per-prospect records.

UserSettings

offers[]: { id, name, description, targetPersonaTags[], constraints }

toneDefault

ctaDefaults

icpRules (editable JSON; see scoring)

capacityRules (editable JSON)

crmProvider (hubspot/pipedrive/salesforce/notion/sheets/custom)

crmAuth (token or OAuth state)

aiProvider (OpenAI) + API key (if user supplies)

privacyFlags (see Privacy)

ProspectRecord

profileUrl (primary key)

linkedinId (optional if derivable)

name

headline

companyName

companyUrl (if visible)

location

signals (array of detected signals)

scores: { icpFit, capacity, authority }

tags[]

status: New / Contacted / Connected / Replied / Qualified / Disqualified

notes (free text)

generatedMessages: { connectionNote, dm1, fu1, fu2, timestamp }

crm: { provider, recordId, recordUrl, stage, owner, lastActivityAt }

ActivityEvent

profileUrl

type (SAVED, GENERATED, COPIED, LOGGED_TOUCH, STAGE_MOVED, NOTE_ADDED)

timestamp

payload (small)

6.2 CRM mapping (generic)

CRMLeadPayload

firstName/lastName (best effort split)

title

company

linkedinUrl

source = “LinkedIn”

lifecycleStage / pipelineStage

notes (append)

tags

lastTouchAt

7. LinkedIn Page Parsing (DOM extraction)

Rule: only parse what’s visible on the current page.

Required fields

Profile URL (window.location.href normalized)

Name

Headline

Current company (from headline/experience summary)

Location (if visible)

Optional fields if visible

About snippet

Experience highlights (first 1–2 entries)

“Open to” indicators if visible

Recent post snippet if user is on activity section

Implementation detail

Use resilient selectors with fallback strategies; LinkedIn DOM shifts.

If extraction fails: show “Couldn’t parse X, click to manually enter”.

8. Scoring & Heuristics
   8.1 Design principles

Explainable: every score must have “why”.

Editable: rules live in Settings for future tuning.

Conservative: avoid claims like “net worth”.

8.2 Signals

Define a Signal object:

id, label, category (Seniority / CompanySize / Industry / Keywords / FundingTrigger / RoleMatch)

weight (positive or negative)

evidence (string excerpt, e.g., “Title contains ‘Founder’”)

8.3 ICP Fit score (0–100)

Weighted sum of signals, clamped 0–100.

Example baseline rules:

+25 if title contains Founder/Owner/Partner/Principal/Managing Partner

+20 if title contains VP/CXO/Head of

+10 if industry keyword match (configurable)

+10 if geography match (configurable)

+15 if company size in target band (if available)

-15 if student/intern/junior keywords

-10 if irrelevant industry keyword match

8.4 Capacity band score (0–100)

Goal: approximate “capacity to buy” and “affluence signals” without claiming net worth.

Example rules:

+25 Founder/Owner/Partner

+20 C-level/VP at mid-large org

+10 Finance/PE/RE/Wealth/Asset Management keywords

+10 “Managing” / “Portfolio” / “Investor” indicators

-10 early-career indicators unless at known high-income firms (optional list)

Output labels

0–39 Low

40–69 Medium

70–100 High

8.5 Decision authority score (optional)

Title seniority and role keywords affecting buying influence.

9. AI Message Generation
   9.1 Inputs to the model

Construct a structured payload:

Prospect snapshot (name, title, company, location)

Visible “about” / highlights (if available)

Detected signals + score reasons

Selected Persona + Offer + Tone + Objective

CRM context (stage, last touch, previous notes)

Constraints:

Connection note max chars: 300

DM max chars: 600 (configurable)

“No spammy phrases” list (configurable)

Required CTA style (question vs soft CTA)

9.2 Outputs

Return JSON:

connection_note

dm1

follow_up_1

follow_up_2

personalization_hook (1 line)

subject_line (optional)

compliance_disclaimer (optional; usually omitted)

9.3 Prompting requirements

Always generate 2 variants per message type when “Regenerate” is clicked.

Avoid mentioning “I saw your profile” (configurable).

Use 1 personalization hook max unless user requests more.

9.4 “Voice training”

In settings, store:

“Example messages I like” (3–10 samples)

“Do not say” phrases list

Tone selection

Model should emulate style based on these.

10. CRM Integration
    10.1 Required behaviors

Lookup on profile load (debounced):

First by LinkedIn URL (best)

Else by (name + company)

Show found record summary + stage + last activity

Allow:

Create lead

Update stage

Append note (generated message or user note)

Log activity (“Sent connection”, “Sent DM”, “Replied”, etc.)

10.2 Provider strategy

Implement a provider interface:

ICrmProvider

searchByLinkedInUrl(url)

searchByNameCompany(name, company)

createLead(payload)

updateLead(recordId, payload)

logActivity(recordId, activity)

moveStage(recordId, stageId)

getStages()

Start with one provider (recommended: HubSpot or Pipedrive) and keep others stubbed.

10.3 Pipeline correlation (bonus)

If CRM supports it:

Fetch recent closed-won deals (or user-provided export)

Build a simple “lookalike” scorer:

Compare persona/title keywords + industry + company size

Output: “Similar wins: 3” and show top 3 brief anonymized reasons

This can be v2.

11. Enrichment (optional / v2)

If you want “pull from various sources”:

Company domain inference (if available) OR manual input

Public firmographics: headcount band, funding, news triggers

Only do enrichment on explicit user action: Enrich company

Store enrichment results with source and timestamp; show them in “Signals”.

12. Privacy, Safety, and Compliance
    12.1 Safety constraints (must)

No automated sending

No looping across profiles

No scraping of search result pages at scale

Manual-trigger only for enrichment calls

Display a small “usage safety” note in settings

12.2 Data handling

Default local storage only.

If CRM enabled: only send required fields (name/title/company/linkedin url/notes).

If AI enabled: send only the visible data the user opted into (privacy toggles):

Toggle: include About section yes/no

Toggle: include experience highlights yes/no

Toggle: include CRM notes yes/no

12.3 Transparency

“Why this score?” always visible

“What data is being sent?” indicator next to Generate + CRM actions

13. Technical Architecture
    13.1 Extension components

Manifest v3

Content script: DOM parsing + sidebar injection + UI events

Background service worker: API calls (AI + CRM) + auth + caching

Options/Settings page: offers, tone, rules editor, CRM auth, privacy toggles

Storage layer: wrapper for chrome.storage.local + caching

13.2 State management

Current profile context (in content script)

Persisted prospect record (storage)

API results cached keyed by profileUrl + timestamp

13.3 Error handling

LinkedIn DOM changed → show fallback “manual entry”

CRM auth expired → show reconnect CTA

AI errors → show retry + partial generation

Rate limit on enrichment → backoff + message

14. Acceptance Criteria (MVP)

On any LinkedIn profile page:

Sidebar loads within 500ms after DOM ready (without blocking).

Extracts at least: name, headline, company (or shows manual input).

Save prospect creates/updates local record.

Scoring computes ICP Fit + Capacity + explanations.

Generate creates connection note + DM + follow-ups respecting character limits.

Copy buttons work and log an event.

CRM integration:

Lookup works

Create lead works

Append note works

Move stage works

No automated sending/clicking on LinkedIn UI.

15. Milestones
    Milestone 1 — MVP (core)

Sidebar injection + DOM parsing

Local storage records

Rules-based scoring + “why”

Message generator (AI) with settings

CSV export (backup if CRM not done yet)

Milestone 2 — CRM v1

CRM provider (HubSpot or Pipedrive)

Lookup, create, update, log activity, stages

Milestone 3 — Enrichment + pipeline correlation

Company enrichment on demand

Lookalike scoring using CRM closed-won patterns

16. Implementation Notes for Codex (guidance)

Keep LinkedIn parsing modular and tolerant to UI changes.

Use feature flags for enrichment + pipeline correlation.

Make all network calls from background service worker (not content script) to avoid CORS issues.

Store minimal PII; provide “Delete local data for this prospect” button.

Add “Diagnostics” view in settings: last parsed fields + last API calls + errors.

17. Open Questions (you can decide defaults now)

To finalize implementation, choose defaults:

CRM: which one first (HubSpot or Pipedrive)?

AI provider/key handling: user supplies their own key vs your backend proxy?

Offers/personas list: start with 5–10 common ones or custom-only?

Do you want “Connected” detection? (LinkedIn doesn’t reliably expose this; you can let user set status manually.)
