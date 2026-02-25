#!/usr/bin/env node
import CDP from "chrome-remote-interface";

const host = process.env.CHROME_DEBUG_HOST || "127.0.0.1";
const port = Number(process.env.CHROME_DEBUG_PORT || "9222");
const filter = process.env.DEBUG_TARGET_FILTER || "linkedin.com";
const onlyWsp = process.env.WSP_ONLY !== "0";

const toJson = (value) => {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const stringifyArg = (arg) => {
  if (typeof arg.value !== "undefined") {
    if (typeof arg.value === "string") {
      return arg.value;
    }
    return toJson(arg.value);
  }
  if (typeof arg.unserializableValue === "string") {
    return arg.unserializableValue;
  }
  if (arg.preview?.properties && Array.isArray(arg.preview.properties)) {
    const preview = Object.fromEntries(
      arg.preview.properties.map((entry) => [entry.name, entry.value ?? entry.type ?? ""]),
    );
    return toJson(preview);
  }
  if (typeof arg.description === "string") {
    return arg.description;
  }
  return "";
};

const now = () => new Date().toISOString();

const main = async () => {
  const targets = await CDP.List({ host, port });
  const target = targets.find(
    (entry) => entry.type === "page" && typeof entry.url === "string" && entry.url.includes(filter),
  );

  if (!target) {
    console.error(
      `[debug-tail] no page target matched filter "${filter}" on ${host}:${port}. Open the LinkedIn tab first.`,
    );
    process.exitCode = 1;
    return;
  }

  const client = await CDP({ host, port, target });
  const { Runtime, Log } = client;

  await Promise.all([Runtime.enable(), Log.enable()]);

  console.log(`[debug-tail] attached to ${target.title || target.url}`);
  console.log(`[debug-tail] streaming console logs (onlyWsp=${onlyWsp})... Ctrl+C to stop.`);

  Runtime.consoleAPICalled((entry) => {
    const text = entry.args
      .map((arg) => stringifyArg(arg))
      .join(" ")
      .trim();
    if (!text) {
      return;
    }
    if (onlyWsp && !text.includes("[WSP]")) {
      return;
    }
    console.log(`${now()} [console:${entry.type}] ${text}`);
  });

  Log.entryAdded(({ entry }) => {
    const text = `${entry.source ?? "log"}: ${entry.text ?? ""}`.trim();
    if (onlyWsp && !text.includes("[WSP]")) {
      return;
    }
    console.log(`${now()} [log:${entry.level}] ${text}`);
  });

  const shutdown = async () => {
    try {
      await client.close();
    } finally {
      process.exit(0);
    }
  };

  process.on("SIGINT", () => {
    void shutdown();
  });
  process.on("SIGTERM", () => {
    void shutdown();
  });
};

main().catch((error) => {
  console.error("[debug-tail] failed:", error);
  process.exit(1);
});
