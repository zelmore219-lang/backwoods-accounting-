const { app, BrowserWindow, ipcMain, dialog, shell } = require("electron");
require('./connected-profile.cjs').prepareProfile({app,dialog}, require('./business-accounting-config.json'));
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const isDev = !app.isPackaged;
const appName = "Backwoods Brew";
const updateConfigName = "update-config.json";
const builtInUpdateFeedUrl = "https://github.com/zelmore219-lang/backwoods-brew-releases/releases/latest/download/";

let updateStatus = {
  phase: "idle",
  message: "Updater idle.",
  currentVersion: app.getVersion(),
  feedUrl: "",
  feedUrlConfigured: false,
  enabled: false,
  autoDownload: false,
  updateAvailable: false,
  updateDownloaded: false,
  latestVersion: "",
  percent: 0,
  lastCheckedAt: "",
  error: ""
};
let updater = null;
let updaterFeedUrl = "";
let downloadedInstallerPath = "";

function logCrash(message, extra = {}) {
  try {
    const dir = path.join(app.getPath("userData"), "logs");
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(
      path.join(dir, "electron.log"),
      JSON.stringify({ at: new Date().toISOString(), message, ...extra }) + "\n"
    );
  } catch {}
}

function normalizeUpdateFeedUrl(value) {
  let feedUrl = String(value || "").trim().replace(/\\/g, "/");
  if (!feedUrl) return "";
  feedUrl = feedUrl.replace(/\/+$/, "");
  feedUrl = feedUrl.replace(/\/latest(?:-[\d.]+)?\.ya?ml$/i, "");
  feedUrl = feedUrl.replace(/\/[^/]+\.exe(?:\.blockmap)?$/i, "");
  feedUrl = feedUrl.replace(/\/releases\/download$/i, "/releases/latest/download");
  feedUrl = feedUrl.replace(/\/releases\/download\/v[^/]+$/i, "/releases/latest/download");
  return feedUrl.replace(/\/+$/, "");
}

function sanitizeUpdateConfig(config = {}) {
  const envFeedUrl = normalizeUpdateFeedUrl(process.env.BACKWOODS_UPDATE_FEED_URL || "");
  const savedFeedUrl = normalizeUpdateFeedUrl(config.feedUrl || "");
  const feedUrl = envFeedUrl || savedFeedUrl || normalizeUpdateFeedUrl(builtInUpdateFeedUrl);
  const hasSavedFeedUrl = savedFeedUrl !== "";
  return {
    enabled: !!envFeedUrl || (hasSavedFeedUrl ? config.enabled !== false : true),
    feedUrl,
    channel: String(config.channel || "latest").trim() || "latest",
    autoDownload: config.autoDownload === true,
    allowPrerelease: config.allowPrerelease === true
  };
}

function updateConfigPath() {
  return path.join(app.getPath("userData"), updateConfigName);
}

function readUpdateConfig() {
  try {
    const parsed = JSON.parse(fs.readFileSync(updateConfigPath(), "utf8"));
    return sanitizeUpdateConfig(parsed);
  } catch {
    return sanitizeUpdateConfig({});
  }
}

function writeUpdateConfig(config) {
  const next = sanitizeUpdateConfig(config);
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(updateConfigPath(), JSON.stringify(next, null, 2));
  return next;
}

function publicUpdateStatus(patch = {}) {
  const config = readUpdateConfig();
  updateStatus = {
    ...updateStatus,
    currentVersion: app.getVersion(),
    feedUrl: config.feedUrl,
    feedUrlConfigured: !!config.feedUrl,
    enabled: !!config.enabled,
    autoDownload: !!config.autoDownload,
    ...patch
  };
  return updateStatus;
}

function broadcastUpdateStatus(patch = {}) {
  const status = publicUpdateStatus(patch);
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send("update-status", status);
  }
  return status;
}

function validateFeedUrl(feedUrl) {
  if (!feedUrl) return true;
  try {
    const parsed = new URL(feedUrl);
    return ["http:", "https:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}

const weatherUserAgent = "BackwoodsBrew/8.1.48 (local-weather; contact: owner@backwoodsbrew.local)";

function validCoordinate(latitude, longitude) {
  const lat = Number(latitude);
  const lon = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

async function fetchWeatherJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        "User-Agent": weatherUserAgent,
        "Accept": "application/geo+json, application/json"
      }
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`Weather service returned ${response.status}: ${text.slice(0, 160)}`);
    }
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

function nwsCondition(shortForecast = "") {
  const text = String(shortForecast || "").toLowerCase();
  if (text.includes("thunder") || text.includes("storm") || text.includes("severe")) return "Storm";
  if (text.includes("snow") || text.includes("ice") || text.includes("sleet") || text.includes("freezing")) return "Snow / Ice";
  if (text.includes("rain") || text.includes("showers") || text.includes("drizzle")) return "Rain";
  if (text.includes("cloud") || text.includes("overcast") || text.includes("fog")) return "Cloudy";
  return "Sunny";
}

function nwsWindMph(windSpeed = "") {
  const speeds = String(windSpeed || "").match(/\d+/g) || [];
  if (!speeds.length) return 0;
  return Math.max(...speeds.map(Number).filter(Number.isFinite));
}

async function fetchLocalWeather(payload = {}) {
  const latitude = Number(payload.latitude);
  const longitude = Number(payload.longitude);
  if (!validCoordinate(latitude, longitude)) {
    return { ok: false, error: "Store latitude and longitude are required for local weather." };
  }
  if (typeof fetch !== "function") {
    return { ok: false, error: "Weather fetch is not available in this desktop runtime." };
  }

  try {
    const lat = latitude.toFixed(4);
    const lon = longitude.toFixed(4);
    const point = await fetchWeatherJson(`https://api.weather.gov/points/${lat},${lon}`);
    const hourlyUrl = point?.properties?.forecastHourly;
    const forecastUrl = point?.properties?.forecast;
    if (!hourlyUrl && !forecastUrl) throw new Error("Weather point lookup did not return a forecast URL.");

    const [hourlyResult, forecastResult, alertsResult] = await Promise.allSettled([
      hourlyUrl ? fetchWeatherJson(hourlyUrl) : Promise.resolve(null),
      forecastUrl ? fetchWeatherJson(forecastUrl) : Promise.resolve(null),
      fetchWeatherJson(`https://api.weather.gov/alerts/active?point=${lat},${lon}`)
    ]);

    const hourly = hourlyResult.status === "fulfilled" ? hourlyResult.value : null;
    const forecast = forecastResult.status === "fulfilled" ? forecastResult.value : null;
    const alerts = alertsResult.status === "fulfilled" ? (alertsResult.value?.features || []) : [];
    const period = hourly?.properties?.periods?.[0] || forecast?.properties?.periods?.[0] || {};
    const dailyPeriods = (forecast?.properties?.periods || []).slice(0, 4).map(period => ({
      name: period.name || "",
      shortForecast: period.shortForecast || "",
      temperature: period.temperature ?? "",
      temperatureUnit: period.temperatureUnit || "F",
      windSpeed: period.windSpeed || "",
      rainChance: period.probabilityOfPrecipitation?.value ?? 0
    }));
    const alertRows = alerts.slice(0, 5).map(feature => ({
      event: feature?.properties?.event || "",
      headline: feature?.properties?.headline || "",
      severity: feature?.properties?.severity || "",
      expires: feature?.properties?.expires || ""
    }));

    return {
      ok: true,
      weather: {
        source: "National Weather Service",
        latitude,
        longitude,
        storeName: payload.storeName || "",
        location: payload.location || point?.properties?.relativeLocation?.properties?.city || "",
        condition: nwsCondition(period.shortForecast),
        shortForecast: period.shortForecast || "Forecast unavailable",
        tempF: Number(period.temperature ?? 0),
        rainChance: Number(period.probabilityOfPrecipitation?.value ?? 0),
        windMph: nwsWindMph(period.windSpeed),
        windText: period.windSpeed || "",
        alertCount: alerts.length,
        alerts: alertRows,
        forecastPeriods: dailyPeriods,
        fetchedAt: new Date().toISOString()
      }
    };
  } catch (error) {
    logCrash("weather-fetch-error", { error: error?.message || String(error), latitude, longitude });
    return { ok: false, error: error?.message || "Local weather lookup failed." };
  }
}
function getConfiguredUpdater() {
  return { ok: false, phase: "manual", error: "Install updates using the Backwoods download links. Automatic updates are disabled for this connected build." };
}

function updaterPendingDirs() {
  const dirs = [];
  const localAppData = process.env.LOCALAPPDATA || "";
  const names = ["backwoods-brew-pc-updater", "backwoods-brew-updater", `${app.getName()}-updater`];
  if (localAppData) {
    for (const name of names) dirs.push(path.join(localAppData, name, "pending"));
  }
  return [...new Set(dirs)];
}

function findDownloadedInstaller(version = "") {
  const wanted = String(version || updateStatus.latestVersion || "").trim();
  const candidates = [];
  for (const dir of updaterPendingDirs()) {
    try {
      for (const name of fs.readdirSync(dir)) {
        if (!/\.exe$/i.test(name)) continue;
        const fullPath = path.join(dir, name);
        const stat = fs.statSync(fullPath);
        if (!stat.isFile()) continue;
        candidates.push({ path: fullPath, name, mtime: stat.mtimeMs, versionMatch: wanted && name.includes(wanted) });
      }
    } catch {}
  }
  candidates.sort((a, b) => Number(b.versionMatch) - Number(a.versionMatch) || b.mtime - a.mtime);
  return candidates[0]?.path || "";
}

function launchDownloadedInstaller(installerPath) {
  if (!installerPath || !fs.existsSync(installerPath)) return { ok: false, error: "Downloaded installer was not found." };
  try {
    const child = spawn(installerPath, [], { detached: true, stdio: "ignore" });
    child.unref();
    setTimeout(() => app.quit(), 250);
    return { ok: true, installerPath };
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }
}
async function checkForAppUpdates() {
  const setup = getConfiguredUpdater();
  if (!setup.ok) {
    return broadcastUpdateStatus({
      phase: setup.phase || "not-configured",
      message: setup.error,
      error: setup.error,
      lastCheckedAt: new Date().toISOString()
    });
  }
  broadcastUpdateStatus({ phase: "checking", message: "Checking for updates...", error: "" });
  try {
    await setup.updater.checkForUpdates();
    return publicUpdateStatus();
  } catch (error) {
    return broadcastUpdateStatus({
      phase: "error",
      message: "Update check failed.",
      error: error?.message || String(error)
    });
  }
}

async function downloadAppUpdate() {
  const setup = getConfiguredUpdater();
  if (!setup.ok) {
    return broadcastUpdateStatus({ phase: setup.phase || "not-configured", message: setup.error, error: setup.error });
  }
  broadcastUpdateStatus({ phase: "downloading", message: "Downloading update...", error: "" });
  try {
    await setup.updater.downloadUpdate();
    return publicUpdateStatus();
  } catch (error) {
    return broadcastUpdateStatus({
      phase: "error",
      message: "Update download failed.",
      error: error?.message || String(error)
    });
  }
}

function installDownloadedUpdate() {
  const setup = getConfiguredUpdater();
  if (!setup.ok) {
    return broadcastUpdateStatus({ phase: setup.phase || "not-configured", message: setup.error, error: setup.error });
  }
  if (!updateStatus.updateDownloaded) {
    return broadcastUpdateStatus({
      phase: "download-required",
      message: "Download an update before installing it.",
      error: "No downloaded update is ready."
    });
  }
  broadcastUpdateStatus({ phase: "installing", message: "Installing update and restarting..." });
  try {
    setup.updater.quitAndInstall(false, true);
    return publicUpdateStatus();
  } catch (error) {
    logCrash("updater-install-fallback", { error: error?.message || String(error) });
    const installerPath = downloadedInstallerPath || updateStatus.downloadedFile || findDownloadedInstaller(updateStatus.latestVersion);
    const launched = launchDownloadedInstaller(installerPath);
    if (launched.ok) {
      return broadcastUpdateStatus({
        phase: "installing",
        message: "Opening downloaded installer...",
        downloadedFile: launched.installerPath,
        error: ""
      });
    }
    return broadcastUpdateStatus({
      phase: "error",
      message: "Update install failed.",
      error: launched.error || error?.message || String(error)
    });
  }
}
function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    title: appName,
    backgroundColor: "#0c0a09",
    show: false,
    autoHideMenuBar: true,
    icon: path.join(__dirname, "..", "assets", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false
    }
  });

  win.once("ready-to-show", () => {
    win.show();
    if (isDev) win.webContents.openDevTools({ mode: "detach" });
  });

  win.webContents.on("render-process-gone", (_event, details) => {
    logCrash("render-process-gone", details);
    dialog.showErrorBox("Backwoods Brew", "The app renderer crashed. Restarting is recommended.");
  });

  win.webContents.on("did-fail-load", (_event, code, desc, url) => {
    logCrash("did-fail-load", { code, desc, url });
  });

  if (isDev) {
    win.loadFile(path.join(__dirname, "..", "www", "index.html"));
  } else {
    win.loadFile(path.join(__dirname, "..", "www", "index.html"));
  }

  return win;
}

app.setName(appName);

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.whenReady().then(() => {
    const win = createWindow();
    publicUpdateStatus({ message: app.isPackaged ? "Updater ready." : "Updater disabled in dev mode." });

    if (false && app.isPackaged && readUpdateConfig().enabled && readUpdateConfig().feedUrl) {
      setTimeout(() => {
        checkForAppUpdates().catch(error => logCrash("startup-update-check-failed", { error: error?.message || String(error) }));
      }, 8000);
    }

    app.on("second-instance", () => {
      if (win.isMinimized()) win.restore();
      win.focus();
    });

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

process.on("uncaughtException", (error) => {
  logCrash("uncaughtException", { error: error?.stack || String(error) });
});

process.on("unhandledRejection", (reason) => {
  logCrash("unhandledRejection", { reason: String(reason) });
});

ipcMain.handle("app-info", () => ({
  name: appName,
  version: app.getVersion(),
  packaged: app.isPackaged,
  userData: app.getPath("userData"),
  updateConfigPath: updateConfigPath()
}));

ipcMain.handle("update-status", () => ({ phase: "manual", enabled: false, currentVersion: app.getVersion(), message: "Use the new Windows installer for updates.", updateAvailable: false, updateDownloaded: false }));

ipcMain.handle("update-configure", (_event, config) => {
  const next = sanitizeUpdateConfig(config);
  if (next.feedUrl && !validateFeedUrl(next.feedUrl)) {
    return broadcastUpdateStatus({
      phase: "config-error",
      message: "Update feed URL must start with https:// or http://.",
      error: "Invalid update feed URL."
    });
  }
  const saved = writeUpdateConfig(next);
  updater = null;
  updaterFeedUrl = "";
  return broadcastUpdateStatus({
      phase: saved.enabled && saved.feedUrl ? "configured" : "not-configured",
    message: saved.enabled && saved.feedUrl ? "Auto-update feed configured." : "Needs hosted update feed URL before update checks can run.",
    error: ""
  });
});

ipcMain.handle("update-check", () => checkForAppUpdates());

ipcMain.handle("update-download", () => downloadAppUpdate());

ipcMain.handle("update-install", () => installDownloadedUpdate());
ipcMain.handle("local-weather-fetch", (_event, payload) => fetchLocalWeather(payload));

ipcMain.handle("open-user-data", async () => {
  await shell.openPath(app.getPath("userData"));
  return true;
});

ipcMain.handle("print-receipt", async (_event, payload) => {
  const win = BrowserWindow.getFocusedWindow();
  if (!win) return { ok: false, error: "No focused window" };

  const printWin = new BrowserWindow({
    show: false,
    width: 380,
    height: 700,
    webPreferences: { contextIsolation: true }
  });

  const text = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  const html = `<html><body><pre style="font-family:monospace;font-size:12px;white-space:pre-wrap;">${String(text).replace(/[&<>]/g, s => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;" }[s]))}</pre></body></html>`;

  await printWin.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));

  return new Promise((resolve) => {
    printWin.webContents.print({ silent: false, printBackground: true }, (success, errorType) => {
      printWin.close();
      resolve({ ok: success, error: errorType || "" });
    });
  });
});

require('./desktop-feed.cjs');
