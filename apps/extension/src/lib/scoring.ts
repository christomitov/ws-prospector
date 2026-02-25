import type { ProspectSnapshot, RuleDefinition, ScoreBreakdown, UserSettings } from "./types";

const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

const labelFromScore = (score: number): "Low" | "Medium" | "High" => {
  if (score >= 70) {
    return "High";
  }
  if (score >= 40) {
    return "Medium";
  }
  return "Low";
};

const runRules = (
  profile: ProspectSnapshot,
  rules: RuleDefinition[],
): { score: number; reasons: string[] } => {
  let score = 0;
  const reasons: string[] = [];

  for (const rule of rules) {
    const sourceValue = (profile[rule.source] ?? "").toLowerCase();
    const matchedKeyword = rule.keywords.find((keyword) =>
      sourceValue.includes(keyword.toLowerCase()),
    );
    if (!matchedKeyword) {
      continue;
    }

    score += rule.weight;
    reasons.push(`${rule.label} (${rule.weight > 0 ? "+" : ""}${rule.weight})`);
  }

  return {
    score: clamp(score, 0, 100),
    reasons,
  };
};

const truncateSignal = (value: string, maxLength = 140): string =>
  value.length <= maxLength ? value : `${value.slice(0, maxLength - 1).trimEnd()}…`;

export const deriveProfileSignals = (profile: ProspectSnapshot): string[] => {
  const signals: string[] = [];
  const about = (profile.about ?? "").toLowerCase();

  if (about.includes("fp&a") || about.includes("financial planning")) {
    signals.push("About: FP&A/finance specialization detected");
  }
  if (
    about.includes("data analytics") ||
    about.includes("financial modeling") ||
    about.includes("spreadsheet")
  ) {
    signals.push("About: analytics/modeling focus detected");
  }
  if (about.includes("saas") || about.includes("e-commerce")) {
    signals.push("About: SaaS or e-commerce domain detected");
  }

  if (profile.experienceHighlights) {
    signals.push(`Experience: ${truncateSignal(profile.experienceHighlights, 120)}`);
  }
  if (profile.recentActivity) {
    signals.push(`Recent activity: ${truncateSignal(profile.recentActivity, 120)}`);
  }

  return signals;
};

export const computeScores = (
  profile: ProspectSnapshot,
  settings: UserSettings,
): ScoreBreakdown => {
  const icpResult = runRules(profile, settings.icpRules);
  const capacityResult = runRules(profile, settings.capacityRules);

  return {
    icpFit: icpResult.score,
    icpLabel: labelFromScore(icpResult.score),
    icpReasons: icpResult.reasons,
    capacity: capacityResult.score,
    capacityLabel: labelFromScore(capacityResult.score),
    capacityReasons: capacityResult.reasons,
  };
};
