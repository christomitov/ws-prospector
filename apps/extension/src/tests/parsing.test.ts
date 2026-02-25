// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import { parseLinkedInProfile } from "../lib/parsing";

describe("parseLinkedInProfile", () => {
  beforeEach(() => {
    document.head.innerHTML = "";
    document.body.innerHTML = "";
  });

  it("extracts core fields from visible profile DOM", () => {
    document.body.innerHTML = `
      <main>
        <h1 class="text-heading-xlarge">Jamie Duncan</h1>
        <div class="pv-text-details__left-panel">
          <div class="text-body-medium break-words">Founder at Atlas Growth</div>
          <div class="text-body-small inline t-black--light break-words">Toronto, Canada</div>
        </div>
      </main>
    `;

    const snapshot = parseLinkedInProfile("https://www.linkedin.com/in/jamie-duncan-3ab4b431/");

    expect(snapshot.name).toBe("Jamie Duncan");
    expect(snapshot.headline).toContain("Founder");
    expect(snapshot.companyName).toContain("Atlas Growth");
    expect(snapshot.location).toBe("Toronto, Canada");
  });

  it("falls back to JSON-LD and og:title when selectors are missing", () => {
    document.head.innerHTML =
      '<meta property="og:title" content="Alex Rivers | LinkedIn" />' +
      '<script type="application/ld+json">{"@type":"Person","jobTitle":"Managing Partner","worksFor":{"name":"Northline Capital"},"address":{"addressLocality":"New York"}}</script>';

    const snapshot = parseLinkedInProfile("https://www.linkedin.com/in/alex-rivers-1829/");

    expect(snapshot.name).toBe("Alex Rivers");
    expect(snapshot.headline).toBe("Managing Partner");
    expect(snapshot.companyName).toBe("Northline Capital");
    expect(snapshot.location).toBe("New York");
  });

  it("falls back to profile slug for name when needed", () => {
    const snapshot = parseLinkedInProfile("https://www.linkedin.com/in/sam-porter-97a11b2/");

    expect(snapshot.name).toBe("Sam Porter");
  });

  it("parses top-card text lines when LinkedIn classes are obfuscated", () => {
    document.body.innerHTML = `
      <main>
        <section componentkey="com.linkedin.sdui.profile.card.ref123Topcard">
          <h2>Rob Gill</h2>
          <div>
            Rob Gill
            He/Him
            · 1st
            Full-Stack Senior Software Developer | Certified AWS Cloud Practitioner
            Kitchener, Ontario, Canada
            ·
            Contact info
            eDynamic Learning
            McMaster University
            361 connections
          </div>
        </section>
      </main>
    `;

    const snapshot = parseLinkedInProfile("https://www.linkedin.com/in/rob-gill/");

    expect(snapshot.name).toBe("Rob Gill");
    expect(snapshot.headline).toContain("Full-Stack Senior Software Developer");
    expect(snapshot.companyName).toBe("eDynamic Learning");
    expect(snapshot.location).toBe("Kitchener, Ontario, Canada");
  });

  it("extracts about, experience highlights, and recent activity from section text", () => {
    document.body.innerHTML = `
      <main>
        <section componentkey="com.linkedin.sdui.profile.card.ref123About">
          <h2>About</h2>
          <div>
            I specialize in FP&A and financial modeling.
            Data analytics and SaaS operations are my focus.
          </div>
        </section>
        <section componentkey="com.linkedin.sdui.profile.card.ref123Activity">
          <h2>Activity</h2>
          <div>
            2h •
            Proud to share we launched a new planning workflow this month.
          </div>
        </section>
        <section componentkey="com.linkedin.sdui.profile.card.ref123ExperienceTopLevelSection">
          <h2>Experience</h2>
          <div>
            Founder & CEO
            Monte Carlos Consulting Inc.
            Oct 2023 - Present · 2 yrs 5 mos
            Advisor
            Digits
          </div>
        </section>
      </main>
    `;

    const snapshot = parseLinkedInProfile("https://www.linkedin.com/in/charliexwliu/");

    expect(snapshot.about).toContain("FP&A");
    expect(snapshot.experienceHighlights).toContain("Founder & CEO");
    expect(snapshot.recentActivity).toContain("Proud to share");
  });
});
