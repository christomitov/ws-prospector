import { describe, expect, it } from "vitest";

import { computeScores } from "../lib/scoring";
import { defaultSettings } from "../lib/storage";

describe("computeScores", () => {
  it("gives higher scores for founder profiles with finance keywords", () => {
    const scores = computeScores(
      {
        profileUrl: "https://www.linkedin.com/in/example/",
        name: "Alex Founder",
        headline: "Founder & CEO | Portfolio Investor",
        companyName: "Growth Labs",
        location: "Toronto, Canada",
      },
      defaultSettings,
    );

    expect(scores.icpFit).toBeGreaterThanOrEqual(25);
    expect(scores.capacity).toBeGreaterThanOrEqual(30);
    expect(scores.icpReasons.length).toBeGreaterThan(0);
  });

  it("clamps score floor at zero for negative-only matches", () => {
    const scores = computeScores(
      {
        profileUrl: "https://www.linkedin.com/in/junior-profile/",
        name: "Pat Student",
        headline: "Junior Intern and Student Assistant",
        companyName: "University Project",
        location: "Boston, USA",
      },
      defaultSettings,
    );

    expect(scores.icpFit).toBeGreaterThanOrEqual(0);
    expect(scores.capacity).toBeGreaterThanOrEqual(0);
  });
});
