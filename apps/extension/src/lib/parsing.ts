import type { ProspectSnapshot } from "./types";

const textFromSelectors = (selectors: string[]): string => {
  for (const selector of selectors) {
    const value = document.querySelector(selector)?.textContent?.trim();
    if (value) {
      return value;
    }
  }
  return "";
};

const textFromMeta = (name: string, attr: "name" | "property" = "name"): string =>
  document.querySelector<HTMLMetaElement>(`meta[${attr}="${name}"]`)?.content?.trim() ?? "";

const squeezeWhitespace = (value: string): string => value.replace(/\s+/g, " ").trim();

const linesFromTextBlock = (value: string): string[] =>
  value
    .split(/\n+/)
    .map((line) => squeezeWhitespace(line))
    .filter(Boolean);

const blockText = (element: Element): string => {
  if ("innerText" in element) {
    const inner = (element as HTMLElement).innerText;
    if (typeof inner === "string" && inner.length > 0) {
      return inner;
    }
  }
  return element.textContent ?? "";
};

const topCardLines = (): string[] => {
  const container = document.querySelector(
    "main section[componentkey*='topcard' i], main section, .pv-top-card, .pv-text-details__left-panel",
  );
  if (!container) {
    return [];
  }
  return linesFromTextBlock(blockText(container));
};

const sectionLines = (
  matcher: (section: Element, lines: string[], heading: string, componentKey: string) => boolean,
): string[] => {
  const sections = Array.from(document.querySelectorAll("main section"));
  for (const section of sections) {
    const lines = linesFromTextBlock(blockText(section));
    if (lines.length === 0) {
      continue;
    }
    const heading = squeezeWhitespace(section.querySelector("h2")?.textContent ?? "");
    const componentKey = section.getAttribute("componentkey") ?? "";
    if (matcher(section, lines, heading, componentKey)) {
      return lines;
    }
  }
  return [];
};

const linesForSection = (heading: RegExp, componentKey: RegExp): string[] =>
  sectionLines((_section, lines, detectedHeading, detectedComponentKey) => {
    const firstLine = lines[0] ?? "";
    return (
      heading.test(detectedHeading) ||
      heading.test(firstLine) ||
      componentKey.test(detectedComponentKey)
    );
  });

const isSectionUiLine = (line: string): boolean => {
  const lower = line.toLowerCase();
  return (
    lower === "show all" ||
    lower === "show all activity" ||
    lower === "show all posts" ||
    lower === "see all" ||
    lower === "posts" ||
    lower === "comments" ||
    lower === "videos" ||
    lower === "images" ||
    lower === "book an appointment" ||
    lower === "message" ||
    lower === "connect" ||
    lower === "follow" ||
    lower === "repost" ||
    lower === "send" ||
    lower === "like" ||
    lower === "comment"
  );
};

const isNoiseLine = (line: string): boolean => {
  const lower = line.toLowerCase();
  return (
    lower === "contact info" ||
    lower === "message" ||
    lower === "follow" ||
    lower === "connect" ||
    lower === "see more" ||
    lower === "… more" ||
    lower === "more" ||
    lower === "posts" ||
    lower === "comments" ||
    lower === "activity" ||
    lower === "about" ||
    lower === "sales insights" ||
    lower === "key signals" ||
    lower === "retry sales navigator" ||
    lower === "book an appointment" ||
    /connections?/.test(lower) ||
    /mutual/.test(lower) ||
    /followers?/.test(lower)
  );
};

const looksLikeLocation = (line: string): boolean => {
  if (!line || isNoiseLine(line)) {
    return false;
  }
  if (/^\W+$/.test(line)) {
    return false;
  }
  if (line.includes("|")) {
    return false;
  }
  if (line.length > 90) {
    return false;
  }
  const lower = line.toLowerCase();
  if (/^\d+(st|nd|rd|th)$/i.test(lower.replace("·", "").trim())) {
    return false;
  }
  if (line.includes(",")) {
    return true;
  }
  return /\b(area|region|canada|usa|united states|uk|india|australia|remote)\b/i.test(line);
};

const nameFromTopCard = (lines: string[]): string => {
  for (const line of lines.slice(0, 3)) {
    if (!line || isNoiseLine(line)) {
      continue;
    }
    if (line.includes("|")) {
      continue;
    }
    if (looksLikeLocation(line)) {
      continue;
    }
    if (/\d/.test(line)) {
      continue;
    }
    const words = line.split(/\s+/).filter(Boolean);
    if (words.length >= 2 && words.length <= 8) {
      return line;
    }
  }
  return "";
};

const headlineFromTopCard = (lines: string[], name: string): string => {
  const loweredName = name.toLowerCase();
  for (const [index, line] of lines.entries()) {
    if (!line || isNoiseLine(line)) {
      continue;
    }
    if (index === 0) {
      continue;
    }
    const lower = line.toLowerCase();
    if (lower === loweredName) {
      continue;
    }
    if (/^(he|she|they)\s*\/\s*(him|her|them)$/i.test(line)) {
      continue;
    }
    if (/^·?\s*\d+(st|nd|rd|th)$/i.test(line)) {
      continue;
    }
    if (looksLikeLocation(line)) {
      continue;
    }
    if (/university|college|school/i.test(line)) {
      continue;
    }
    return line;
  }
  return "";
};

const organizationFromTopCard = (lines: string[]): string => {
  const contactIndex = lines.findIndex((line) => /^contact info$/i.test(line));
  if (contactIndex >= 0) {
    for (let i = contactIndex + 1; i < Math.min(lines.length, contactIndex + 6); i += 1) {
      const candidate = lines[i];
      if (!candidate || isNoiseLine(candidate) || looksLikeLocation(candidate)) {
        continue;
      }
      if (/^·/.test(candidate)) {
        continue;
      }
      return candidate;
    }
  }
  return "";
};

const locationFromTopCard = (lines: string[]): string => {
  const contactIndex = lines.findIndex((line) => /^contact info$/i.test(line));
  if (contactIndex > 0) {
    for (let i = contactIndex - 1; i >= Math.max(0, contactIndex - 4); i -= 1) {
      const candidate = lines[i];
      if (candidate && looksLikeLocation(candidate)) {
        return candidate;
      }
    }
  }

  for (const line of lines) {
    if (looksLikeLocation(line)) {
      return line;
    }
  }

  return "";
};

const aboutFromSectionText = (): string => {
  const lines = linesForSection(/^about$/i, /about/i);
  if (lines.length === 0) {
    return "";
  }

  return lines
    .slice(1)
    .filter((line) => !/^…\s*more$/i.test(line) && !/^see more$/i.test(line))
    .join(" ");
};

const looksLikeTimelineLine = (line: string): boolean =>
  /(\bpresent\b|\b\d{4}\b|\b\d+\s*(yr|yrs|year|years|mo|mos|month|months)\b|[–-])/.test(
    line.toLowerCase(),
  );

const experienceHighlightsFromSection = (): string => {
  const lines = linesForSection(/^experience$/i, /experiencetoplevelsection/i);
  if (lines.length === 0) {
    return "";
  }

  const highlights = lines
    .slice(1)
    .map((line) => squeezeWhitespace(line))
    .filter(
      (line) =>
        Boolean(line) &&
        !isNoiseLine(line) &&
        !isSectionUiLine(line) &&
        !looksLikeTimelineLine(line) &&
        !/^\W+$/.test(line) &&
        !/\+\d+\s+skills?/i.test(line),
    );

  return highlights.slice(0, 4).join(" | ");
};

const activityPostHighlight = (): string => {
  const lines = linesForSection(/^activity$/i, /activity/i);
  if (lines.length === 0) {
    return "";
  }

  const body = lines
    .slice(1)
    .map((line) => squeezeWhitespace(line))
    .filter(
      (line) =>
        Boolean(line) &&
        !isNoiseLine(line) &&
        !isSectionUiLine(line) &&
        !/^•/.test(line) &&
        !/^\d{1,2}(st|nd|rd|th)$/i.test(line.replace(/^·\s*/, "")) &&
        !/^\d[\d,]*\s+followers?$/i.test(line) &&
        !/^\d+\s*(m|h|d|w|mo|yr|yrs)\s*•?$/i.test(line) &&
        !/^\d+\s*·\s*\d+\s+comments?$/i.test(line.toLowerCase()),
    );

  const looksLikeNameLine = (line: string): boolean => {
    const cleaned = line.replace(/[•·]/g, "").trim();
    const parts = cleaned.split(/\s+/).filter(Boolean);
    if (parts.length < 2 || parts.length > 6) {
      return false;
    }
    return parts.every((part) => /^[A-Z][\w.'-]*$/i.test(part));
  };

  const best = body.find((line) => line.length >= 45 && !looksLikeNameLine(line));
  return best ?? body.find((line) => line.length >= 30) ?? "";
};

const activitySignalFromSalesInsights = (): string => {
  const lines = linesForSection(/^sales insights$/i, /sales/i);
  return (
    lines.find((line) =>
      /\b(posted in the past|hiring|new position|funding|announced|shared)\b/i.test(
        line.toLowerCase(),
      ),
    ) ?? ""
  );
};

const recentActivityFromSections = (): string => {
  const activitySignal = activitySignalFromSalesInsights();
  const activitySnippet = activityPostHighlight();
  return [activitySignal, activitySnippet].filter(Boolean).join(" | ");
};

export const normalizeProfileUrl = (url: string): string => {
  try {
    const parsed = new URL(url);
    const cleanedPath = parsed.pathname.replace(/\/+$/, "");
    return `${parsed.origin}${cleanedPath}`;
  } catch {
    return url;
  }
};

export const isLinkedInProfilePage = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    return (
      parsed.hostname === "www.linkedin.com" &&
      parsed.pathname.startsWith("/in/") &&
      parsed.pathname.length > "/in/".length
    );
  } catch {
    return false;
  }
};

const inferCompanyFromHeadline = (headline: string): string => {
  const match = headline.match(/\bat\s+(.+)$/i);
  return match?.[1]?.trim() ?? "";
};

const parseJsonLdPerson = (): {
  name?: string;
  headline?: string;
  companyName?: string;
  location?: string;
  about?: string;
} => {
  const scripts = Array.from(
    document.querySelectorAll<HTMLScriptElement>('script[type="application/ld+json"]'),
  );

  for (const script of scripts) {
    const raw = script.textContent?.trim();
    if (!raw) {
      continue;
    }

    try {
      const parsed = JSON.parse(raw) as unknown;
      const items = Array.isArray(parsed)
        ? parsed
        : typeof parsed === "object" && parsed && "@graph" in parsed
          ? ((parsed as { "@graph"?: unknown[] })["@graph"] ?? [])
          : [parsed];

      for (const item of items) {
        if (!item || typeof item !== "object") {
          continue;
        }

        const entity = item as Record<string, unknown>;
        const typeValue = entity["@type"];
        const types = Array.isArray(typeValue) ? typeValue : [typeValue];
        const isPerson = types.some(
          (entry) => typeof entry === "string" && entry.toLowerCase() === "person",
        );
        if (!isPerson) {
          continue;
        }

        const worksFor = entity.worksFor;
        const worksForName =
          worksFor && typeof worksFor === "object" && "name" in worksFor
            ? String((worksFor as { name?: unknown }).name ?? "")
            : "";

        const address = entity.address;
        const locality =
          address && typeof address === "object" && "addressLocality" in address
            ? String((address as { addressLocality?: unknown }).addressLocality ?? "")
            : "";

        return {
          name: squeezeWhitespace(String(entity.name ?? "")),
          headline: squeezeWhitespace(String(entity.jobTitle ?? entity.headline ?? "")),
          companyName: squeezeWhitespace(worksForName),
          location: squeezeWhitespace(locality),
          about: squeezeWhitespace(String(entity.description ?? "")),
        };
      }
    } catch {
      // Best-effort parsing only.
    }
  }

  return {};
};

const nameFromOgTitle = (): string => {
  const ogTitle = textFromMeta("og:title", "property");
  if (!ogTitle) {
    return "";
  }

  const [candidate] = ogTitle.split("|").map((part) => part.trim());
  return candidate ?? "";
};

const inferNameFromSlug = (profileUrl: string): string => {
  try {
    const pathname = new URL(profileUrl).pathname;
    const match = pathname.match(/^\/in\/([^/]+)/i);
    const slug = match?.[1];
    if (!slug) {
      return "";
    }

    const withoutHash = slug.replace(/-\w*\d[\w-]*$/, "");
    return withoutHash
      .split("-")
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  } catch {
    return "";
  }
};

export const parseLinkedInProfile = (url: string): ProspectSnapshot => {
  const profileUrl = normalizeProfileUrl(url);
  const jsonLd = parseJsonLdPerson();
  const topLines = topCardLines();

  const name = textFromSelectors([
    "main section[componentkey*='topcard' i] h2",
    "h1.text-heading-xlarge",
    "h1.inline.t-24.v-align-middle.break-words",
    ".pv-text-details__left-panel h1",
    "main h1",
  ]);
  const topCardName = nameFromTopCard(topLines);

  const headline = textFromSelectors([
    ".pv-text-details__left-panel .text-body-medium.break-words",
    ".pv-text-details__left-panel .text-body-medium",
    ".ph5 .text-body-medium.break-words",
    ".text-body-medium.break-words",
    "main .text-body-medium",
  ]);
  const topCardHeadline = headlineFromTopCard(topLines, name || topCardName || jsonLd.name || "");

  const companyName =
    textFromSelectors([
      'main a[href*="/company/"] span[aria-hidden="true"]',
      'main a[href*="/company/"]',
      'a[data-field="experience_company_logo"] span[aria-hidden="true"]',
      '.pv-text-details__right-panel .display-flex span[aria-hidden="true"]',
    ]) ||
    organizationFromTopCard(topLines) ||
    inferCompanyFromHeadline(headline || topCardHeadline);

  const location = textFromSelectors([
    ".text-body-small.inline.t-black--light.break-words",
    ".pv-text-details__left-panel .text-body-small",
    ".pv-text-details__left-panel .text-body-small.inline",
  ]);
  const topCardLocation = locationFromTopCard(topLines);

  const about = textFromSelectors([
    "#about ~ * .display-flex .visually-hidden",
    "#about ~ div .full-width",
    'section.artdeco-card #about ~ div span[aria-hidden="true"]',
    "section.artdeco-card p",
  ]);
  const aboutSectionText = aboutFromSectionText();
  const experienceHighlights = experienceHighlightsFromSection();
  const recentActivity = recentActivityFromSections();

  return {
    profileUrl,
    name: squeezeWhitespace(
      name || topCardName || jsonLd.name || nameFromOgTitle() || inferNameFromSlug(profileUrl),
    ),
    headline: squeezeWhitespace(headline || topCardHeadline || jsonLd.headline || ""),
    companyName: squeezeWhitespace(
      companyName || jsonLd.companyName || inferCompanyFromHeadline(headline || topCardHeadline),
    ),
    location: squeezeWhitespace(location || topCardLocation || jsonLd.location || ""),
    about: squeezeWhitespace(about || aboutSectionText || jsonLd.about || ""),
    experienceHighlights: squeezeWhitespace(experienceHighlights),
    recentActivity: squeezeWhitespace(recentActivity),
  };
};
