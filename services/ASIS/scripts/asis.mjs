#!/usr/bin/env node
/**
 * One-command A.S.I.S. launcher: `npm run ASIS`.
 *
 *  1. Ensures `.venv` exists — via `py setup_venv.py` first (uv-based,
 *     WDAC-safe classic layout), falling back to plain `py -3.12 -m venv`
 *     + pip when uv is unavailable. Reinstalls light deps only when the
 *     venv python or the `asis.cli.main` import is broken. Voice extras
 *     (heavy torch stack) are never auto-installed; a hint is printed
 *     when `voice` mode is requested without them.
 *  2. Ensures Ollama is up: connects when already running (never owned),
 *     otherwise starts a detached `ollama serve` it owns, polling
 *     `/api/tags` up to 60s. Then verifies `qwen3:14b` is pulled — fails
 *     fast with the exact `ollama pull` command, never silently pulls GBs.
 *  3. Launches `.venv\Scripts\python.exe -m asis <args>` with inherited
 *     stdio (REPL + voice need a TTY), forwarding the exit code. No args
 *     → interactive REPL via the existing `entry()` default.
 *  4. On exit, stops ONLY a launcher-owned server. A pre-existing server
 *     is left alone.
 *
 * Modes: `voice` starts voice mode; `--check` runs a fast boot probe
 * (`asis --identify`); `--test` runs pytest. Anything after `--`
 * (`npm run ASIS -- --message "hi"`) is forwarded to `python -m asis`.
 *
 * Stdlib only (child_process, fs, http, os, path, url).
 */

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { request as httpRequest } from "node:http";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import os from "node:os";

const ROOT = resolve(join(dirname(fileURLToPath(import.meta.url)), ".."));
const IS_WINDOWS = os.platform() === "win32";
const VENV_PYTHON = IS_WINDOWS
  ? join(ROOT, ".venv", "Scripts", "python.exe")
  : join(ROOT, ".venv", "bin", "python");
// Launcher used to create the venv: `py` on Windows, `python3` on POSIX.
const PYTHON_LAUNCHER = IS_WINDOWS ? "py" : "python3";
// Overridable for testing (e.g. ASIS_OLLAMA_PORT=1 forces the down-path).
const OLLAMA_HOST = process.env.ASIS_OLLAMA_HOST ?? "127.0.0.1";
const OLLAMA_PORT = Number(process.env.ASIS_OLLAMA_PORT ?? 11434);
// Parse ASIS_AI_ENDPOINT if set (format: http://host:port/path)
let ENDPOINT_URL = null;
let ENDPOINT_HOST = OLLAMA_HOST;
let ENDPOINT_PORT = OLLAMA_PORT;
let ENDPOINT_PROTOCOL = "http:";
let ENDPOINT_PATH = "";
const AI_ENDPOINT = process.env.ASIS_AI_ENDPOINT;
if (AI_ENDPOINT) {
  try {
    const url = new URL(AI_ENDPOINT);
    ENDPOINT_URL = url;
    ENDPOINT_HOST = url.hostname;
    ENDPOINT_PORT = Number(url.port) || (url.protocol === "https:" ? 443 : 80);
    ENDPOINT_PROTOCOL = url.protocol;
    ENDPOINT_PATH = url.pathname || "";
  } catch {
    // Ignore parse errors, fall back to defaults
  }
}
// Bind address for a launcher-started `ollama serve` (OLLAMA_HOST format).
// Override for sandbox tests, e.g. ASIS_OLLAMA_SERVE_BIND=127.0.0.1:11435,
// so the live :11434 server is never disturbed.
const SERVE_BIND = process.env.ASIS_OLLAMA_SERVE_BIND ?? "127.0.0.1:11434";
const MODEL = process.env.ASIS_AI_MODEL ?? "qwen3:14b";
// Slow machines need longer for first boot (cold GPU discovery under RAM
// pressure); override with ASIS_OLLAMA_SERVE_TIMEOUT_S.
const SERVE_READY_TIMEOUT_MS =
  Number(process.env.ASIS_OLLAMA_SERVE_TIMEOUT_S ?? 120) * 1000;

function fail(message, code = 2) {
  console.error(`asis: ERROR: ${message}`);
  process.exit(code);
}

/** Run a command with inherited stdio; return its exit code. */
function runForeground(cmd, args) {
  const result = spawnSync(cmd, args, { stdio: "inherit", cwd: ROOT });
  if (result.error) {
    fail(`could not run '${cmd}': ${result.error.message}`);
  }
  return result.status ?? 1;
}

/** Run a command quietly; return { status, error }. */
function runQuiet(cmd, args) {
  const result = spawnSync(cmd, args, {
    stdio: "pipe",
    encoding: "utf8",
    cwd: ROOT,
  });
  return { status: result.status ?? 1, error: result.error ?? null };
}

function commandExists(cmd) {
  const probe = IS_WINDOWS
    ? runQuiet("where", [cmd])
    : runQuiet("sh", ["-c", `command -v ${cmd}`]);
  return probe.status === 0;
}

function ensureVenv() {
  if (existsSync(VENV_PYTHON)) {
    const probe = runQuiet(VENV_PYTHON, ["-c", "import asis.cli.main; import textual"]);
    if (probe.status === 0) return; // healthy venv, nothing to do
    console.error(
      "asis: venv python or 'asis' import is broken; reinstalling light deps..."
    );
    const code = runForeground(VENV_PYTHON, [
      "-m",
      "pip",
      "install",
      "-r",
      "requirements.txt",
      "-r",
      "requirements/development.txt",
      "-r",
      "requirements/tui.txt",
    ]);
    if (code !== 0) {
      fail("pip install failed; run setup_venv.py manually and retry.");
    }
    return;
  }
  if (commandExists("uv")) {
    console.error("asis: creating .venv via setup_venv.py (uv) ...");
    const code = runForeground(PYTHON_LAUNCHER, ["setup_venv.py"]);
    if (code === 0 && existsSync(VENV_PYTHON)) return;
    console.error("asis: setup_venv.py failed; falling back to plain venv ...");
  } else {
    console.error("asis: 'uv' not found; falling back to plain venv ...");
  }
  let created = false;
  const fallbacks = IS_WINDOWS
    ? [
        ["py", "-3.12"],
        ["py", "-3"],
      ]
    : [[PYTHON_LAUNCHER]];
  for (const launcher of fallbacks) {
    const result = runQuiet(launcher[0], [
      ...launcher.slice(1),
      "-m",
      "venv",
      ".venv",
    ]);
    if (result.status === 0 && existsSync(VENV_PYTHON)) {
      created = true;
      break;
    }
  }
  if (!created) {
    fail(
      IS_WINDOWS
        ? "could not create .venv. Install uv (https://docs.astral.sh/uv/) or Python 3.12+ with the 'py' launcher and retry."
        : "could not create .venv. Install uv (https://docs.astral.sh/uv/) or have Python 3.12+ available as 'python3' and retry."
    );
  }
  runForeground(VENV_PYTHON, ["-m", "pip", "install", "--upgrade", "pip"]);
  const deps = runForeground(VENV_PYTHON, [
    "-m",
    "pip",
    "install",
    "-r",
    "requirements.txt",
    "-r",
    "requirements/development.txt",
    "-r",
    "requirements/tui.txt",
  ]);
  if (deps !== 0) fail("pip install failed.");
}

function voiceDepsPresent() {
  const probe = runQuiet(VENV_PYTHON, ["-c", "import sounddevice"]);
  return probe.status === 0;
}

function fetchJson(path) {
  return new Promise((resolvePromise, rejectPromise) => {
    const requestOptions = {
      host: ENDPOINT_HOST,
      port: ENDPOINT_PORT,
      path: ENDPOINT_PATH + path,
      method: "GET",
      timeout: 5000,
    };
    const requestModule = ENDPOINT_PROTOCOL === "https:" ? "https" : "http";
    const { request } = require(requestModule);
    const req = request(requestOptions, (response) => {
      let body = "";
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => {
        try {
          resolvePromise(JSON.parse(body));
        } catch (error) {
          rejectPromise(error);
        }
      });
    });
    req.on("timeout", () => {
      req.destroy(new Error("timed out"));
    });
    req.on("error", rejectPromise);
    req.end();
  });
}

async function ollamaUp() {
  try {
    await fetchJson("/api/tags");
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

/**
 * Ensure an Ollama server is reachable. Returns `{ owned, servePid }`:
 * `owned` is true only when this launcher started `ollama serve` itself.
 */
async function ensureOllama() {
  if (await ollamaUp()) {
    return { owned: false, servePid: null };
  }
  // Refuse automatic local startup for remote endpoints
  if (ENDPOINT_URL && ENDPOINT_URL.hostname !== "127.0.0.1" && ENDPOINT_URL.hostname !== "localhost") {
    fail(
      `Ollama is not reachable at ${AI_ENDPOINT} and automatic local startup is disabled for remote endpoints. ` +
      `Start Ollama manually or configure a local endpoint.`
    );
  }
  console.error("asis: Ollama is down; starting 'ollama serve' ...");
  const server = spawn("ollama", ["serve"], {
    detached: true,
    stdio: "ignore",
    cwd: ROOT,
    env: { ...process.env, OLLAMA_HOST: SERVE_BIND },
  });
  let spawnError = null;
  server.on("error", (error) => {
    spawnError = error;
  });
  // Give spawn a tick to report ENOENT (missing binary) before polling.
  await sleep(500);
  if (spawnError) {
    fail(
      `could not spawn 'ollama' (${spawnError.message}). Install Ollama (https://ollama.com) and ensure it is on PATH, or start it with 'ollama serve' and retry.`
    );
  }
  if (server.exitCode !== null) {
    fail(
      `'ollama serve' exited immediately (code ${server.exitCode}). Start it manually with 'ollama serve' to see why, then retry.`
    );
  }
  server.unref();
  const deadline = Date.now() + SERVE_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await sleep(1000);
    if (await ollamaUp()) {
      console.error("asis: Ollama server is up (launcher-owned).");
      return { owned: true, servePid: server.pid };
    }
  }
  stopServeProcess(server.pid);
  fail(
    `'ollama serve' did not become ready within ${
      SERVE_READY_TIMEOUT_MS / 1000
    }s. Start it manually with 'ollama serve' to see why, then retry.`
  );
}

/** Best-effort kill of a serve PID we started. Never throws. */
function stopServeProcess(pid) {
  try {
    if (pid == null) return;
    if (IS_WINDOWS) {
      spawnSync("taskkill", ["/PID", String(pid), "/F"], { stdio: "ignore" });
    } else {
      process.kill(pid, "SIGTERM");
    }
  } catch {
    // best-effort only
  }
}

/** Best-effort unload of the active model. Never throws. */
function unloadModel(model) {
  try {
    // Scope the CLI to the launcher-owned server so a pre-existing
    // :11434 server is never touched.
    spawnSync("ollama", ["stop", model], {
      stdio: "ignore",
      timeout: 60000,
      env: { ...process.env, OLLAMA_HOST: SERVE_BIND },
    });
  } catch {
    // best-effort only
  }
}

function normalizeModelTag(tag) {
  // Normalize model tag for comparison: strip digest suffix if present
  // e.g., "qwen3:14b@sha256:abc" -> "qwen3:14b"
  return tag.split("@")[0];
}

async function checkModel(model = MODEL) {
  const tags = await fetchJson("/api/tags");
  const names = new Set((tags.models ?? []).map((model) => normalizeModelTag(model.name)));
  const normalizedModel = normalizeModelTag(model);
  const present = names.has(normalizedModel);
  if (!present) {
    fail(
      `model '${model}' is not pulled. Run 'ollama pull ${model}', then retry.`
    );
  }
}

async function probeInference() {
  // Minimal inference probe: POST /api/chat with a single "hello" message
  // Use higher num_predict to allow thinking models to generate visible content
  // Also disable thinking for the probe to get a faster response
  return new Promise((resolvePromise, rejectPromise) => {
    const payload = JSON.stringify({
      model: MODEL,
      messages: [{ role: "user", content: "hello" }],
      stream: false,
      think: false,
      options: { num_predict: 64 },
    });
    const requestOptions = {
      host: ENDPOINT_HOST,
      port: ENDPOINT_PORT,
      path: ENDPOINT_PATH + "/api/chat",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(payload),
      },
      timeout: 30000,
    };
    const requestModule = ENDPOINT_PROTOCOL === "https:" ? "https" : "http";
    const { request } = require(requestModule);
    const req = request(requestOptions, (response) => {
      let body = "";
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => {
        try {
          const data = JSON.parse(body);
          // Check both content and thinking fields (for thinking models)
          const content = data?.message?.content ?? "";
          const thinking = data?.message?.thinking ?? "";
          const visible = content.trim() || thinking.trim();
          if (visible) {
            resolvePromise(true);
          } else {
            rejectPromise(new Error("Empty response from model"));
          }
        } catch (error) {
          rejectPromise(error);
        }
      });
    });
    req.on("timeout", () => {
      req.destroy(new Error("inference probe timed out"));
    });
    req.on("error", rejectPromise);
    req.write(payload);
    req.end();
  });
}

async function main() {
  const rawArgs = process.argv.slice(2);
  process.chdir(ROOT);
  ensureVenv();

  if (rawArgs.includes("--test")) {
    process.exit(runForeground(VENV_PYTHON, ["-m", "pytest", "-q"]));
  }

  const isMockMode = rawArgs.includes("--mock");

  // Remove --mock from args passed to Python (Python uses --provider mock)
  const filteredArgs = rawArgs.filter(arg => arg !== "--mock");

  // Extract provider/model/inference overrides for forwarding
  const providerArg = rawArgs.includes("--provider") ? rawArgs[rawArgs.indexOf("--provider") + 1] : null;
  const modelArg = rawArgs.includes("--model") ? rawArgs[rawArgs.indexOf("--model") + 1] : null;
  const aiTempArg = rawArgs.includes("--ai-temperature") ? rawArgs[rawArgs.indexOf("--ai-temperature") + 1] : null;
  const aiThinkArg = rawArgs.includes("--ai-think") ? rawArgs[rawArgs.indexOf("--ai-think") + 1] : null;
  const aiNumPredictArg = rawArgs.includes("--ai-num-predict") ? rawArgs[rawArgs.indexOf("--ai-num-predict") + 1] : null;
  const aiKeepAliveArg = rawArgs.includes("--ai-keep-alive") ? rawArgs[rawArgs.indexOf("--ai-keep-alive") + 1] : null;

  if (rawArgs[0] === "voice" && !voiceDepsPresent()) {
    console.error(
      "asis: voice extras are not installed; voice mode will use mock engines."
    );
    console.error(
      "asis: for real audio run: uv pip install -r requirements/voice.txt"
    );
  }

  if (rawArgs.includes("--check")) {
    if (isMockMode) {
      process.exit(runForeground(VENV_PYTHON, ["-m", "asis", "--identify", "--provider", "mock"]));
    }
    const { owned, servePid } = await ensureOllama();
    
    // Register cleanup handlers early (before any risky operations)
    const shutdownOwned = () => {
      if (owned) {
        unloadModel(MODEL);
        stopServeProcess(servePid);
      }
    };
    process.on("SIGINT", () => { shutdownOwned(); process.exit(130); });
    process.on("SIGTERM", () => { shutdownOwned(); process.exit(143); });

    await checkModel(modelArg);
    try {
      await probeInference();
      console.error("asis: Inference probe successful.");
    } catch (error) {
      if (owned) {
        unloadModel(MODEL);
        stopServeProcess(servePid);
      }
      fail(`Inference probe failed: ${error.message}`);
    }
    if (owned) {
      unloadModel(MODEL);
      stopServeProcess(servePid);
    }
    process.exit(0);
  }

  let owned = false;
  let servePid = null;
  if (!isMockMode) {
    const result = await ensureOllama();
    owned = result.owned;
    servePid = result.servePid;
    
    // Register cleanup handlers immediately after acquiring owned resources
    const shutdownOwned = () => {
      if (owned) {
        unloadModel(MODEL);
        stopServeProcess(servePid);
      }
    };
    process.on("SIGINT", () => { shutdownOwned(); process.exit(130); });
    process.on("SIGTERM", () => { shutdownOwned(); process.exit(143); });

    await checkModel(modelArg);
  }

  const shutdownOwned = () => {
    if (owned) {
      unloadModel(MODEL);
      stopServeProcess(servePid);
    }
  };

  const pythonArgs = ["-m", "asis", ...filteredArgs];
  if (isMockMode) {
    pythonArgs.push("--provider", "mock");
  }
  // Forward provider/model/inference overrides explicitly
  if (providerArg) {
    pythonArgs.push("--provider", providerArg);
  }
  if (modelArg) {
    pythonArgs.push("--model", modelArg);
  }
  if (aiTempArg) {
    pythonArgs.push("--ai-temperature", aiTempArg);
  }
  if (aiThinkArg) {
    pythonArgs.push("--ai-think", aiThinkArg);
  }
  if (aiNumPredictArg) {
    pythonArgs.push("--ai-num-predict", aiNumPredictArg);
  }
  if (aiKeepAliveArg) {
    pythonArgs.push("--ai-keep-alive", aiKeepAliveArg);
  }
  const child = spawn(VENV_PYTHON, pythonArgs, {
    stdio: "inherit",
  });
  child.on("error", (error) => {
    shutdownOwned();
    fail(`could not launch asis: ${error.message}`);
  });
  child.on("exit", (code, signal) => {
    shutdownOwned();
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });
}

await main();
