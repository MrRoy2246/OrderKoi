/**
 * Console / network watcher for the page sweep.
 *
 * A page that renders a heading but throws in an effect is broken, and
 * a plain "is the h1 visible" assertion will not notice. This collects
 * what the browser actually complained about — uncaught exceptions,
 * console.error/warn, failed requests and 4xx/5xx responses — and
 * rewrites each one to point at a source file and line.
 *
 * Vite serves the original modules in dev, so a stack frame reads
 * `http://localhost:5173/src/pages/Dashboard.jsx:118:9`. Stripping the
 * origin leaves `src/pages/Dashboard.jsx:118` — which is the line to
 * open. That is the whole point: a red test should name the file.
 */

/** Noise that is never a defect in this app. */
const IGNORED = [
  /Download the React DevTools/i,
  /\[vite\]/i,
  /React Router Future Flag/i,
];

/** Turn a URL into something you can open in an editor. */
export function tidy(url) {
  if (!url) return "";
  return url
    .replace(/^https?:\/\/localhost:\d+\//, "")
    .replace(/^https?:\/\/127\.0\.0\.1:\d+\//, "")
    .split("?")[0];
}

/**
 * The first frame in a stack that points at app source, rather than at
 * node_modules or the Vite client.
 */
export function firstAppFrame(stack) {
  if (!stack) return "";
  for (const line of stack.split("\n")) {
    const match = line.match(/\(?((?:https?:\/\/[^/]+)?\/?(?:src|e2e)\/[^):]+):(\d+):(\d+)\)?/);
    if (match && !line.includes("node_modules")) {
      return `${tidy(match[1])}:${match[2]}:${match[3]}`;
    }
  }
  return "";
}

/**
 * Attach the watcher to a page. Returns the live collections — read
 * them after navigating, they fill in asynchronously.
 */
export function watch(page) {
  const errors = [];
  const warnings = [];
  const failedRequests = [];

  page.on("pageerror", (error) => {
    errors.push({
      message: error.message,
      where: firstAppFrame(error.stack) || "(no app frame — see the stack in the trace)",
    });
  });

  page.on("console", (message) => {
    const text = message.text();
    if (IGNORED.some((pattern) => pattern.test(text))) return;

    // The browser writes a generic "Failed to load resource" line for
    // every non-2xx response. The response listener below already
    // records those with the method and the full URL, which is the part
    // worth reading: keeping both means one broken request is reported
    // twice, and the console copy is the one with nothing to act on.
    if (/^Failed to load resource/.test(text)) return;

    const location = message.location();
    const where = location?.url
      ? `${tidy(location.url)}:${location.lineNumber}:${location.columnNumber}`
      : "";

    if (message.type() === "error") {
      errors.push({ message: text, where });
    } else if (message.type() === "warning") {
      warnings.push({ message: text, where });
    }
  });

  page.on("requestfailed", (request) => {
    const failure = request.failure();
    // Navigation aborts and the HMR socket are the browser doing its
    // job, not the app failing.
    if (!failure || failure.errorText === "net::ERR_ABORTED") return;
    if (request.url().includes("/@vite/")) return;
    failedRequests.push({
      message: `${request.method()} ${tidy(request.url())} — ${failure.errorText}`,
      where: "network",
    });
  });

  page.on("response", (response) => {
    const status = response.status();
    if (status < 400) return;
    const url = response.url();
    if (url.includes("/@vite/") || url.includes("favicon")) return;
    failedRequests.push({
      message: `${status} ${response.request().method()} ${tidy(url)}`,
      where: "network",
    });
  });

  return {
    errors,
    warnings,
    failedRequests,
    /** Everything that should fail the check, as printable lines. */
    format(allowed = []) {
      return [...errors, ...failedRequests]
        .filter((issue) => !allowed.some((pattern) => pattern.test(issue.message)))
        .map((issue) => `  • ${issue.message}${issue.where ? `\n    at ${issue.where}` : ""}`);
    },
    formatWarnings() {
      return warnings.map(
        (issue) => `  • ${issue.message}${issue.where ? `\n    at ${issue.where}` : ""}`,
      );
    },
    reset() {
      errors.length = 0;
      warnings.length = 0;
      failedRequests.length = 0;
    },
  };
}

/** Sign in through the real form, so the redirect logic is covered too. */
export async function signIn(page, email, password) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL(/\/dashboard|\/admin/);
}

/** The signed-in seller's API token, for the calls a test needs to set up. */
export async function apiToken(page) {
  return page.evaluate(() => localStorage.getItem("orderkoi_token"));
}
