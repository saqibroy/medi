import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";
import { spawn } from "node:child_process";

const APP_URL = process.env.APP_URL ?? "http://127.0.0.1:5173";
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/medi_phase3_frontend_qa";
const CHROME = process.env.CHROME_BIN ?? "/usr/bin/google-chrome";
const DEBUG_PORT = Number(process.env.CHROME_DEBUG_PORT ?? 9222);

mkdirSync(SCREENSHOT_DIR, { recursive: true });
rmSync(`${SCREENSHOT_DIR}/chrome-profile`, { recursive: true, force: true });

const chrome = spawn(CHROME, [
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  `--remote-debugging-port=${DEBUG_PORT}`,
  `--user-data-dir=${SCREENSHOT_DIR}/chrome-profile`,
  "about:blank",
], { stdio: "ignore" });

let socket;
let nextId = 1;
const pending = new Map();
const evidence = [];
const pageErrors = [];

function record(check, status, note, screenshot = "") {
  evidence.push({ check, status, note, screenshot });
}

function apiUrl(path) {
  return `${API_URL}${path}`;
}

async function waitForJson(url, attempts = 80) {
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch {
      // Chrome is still starting.
    }
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function cdp(method, params = {}) {
  const id = nextId;
  nextId += 1;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
  });
}

async function evaluate(expression, returnByValue = true) {
  const result = await cdp("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text ?? "Runtime evaluation failed");
  }
  return result.result.value;
}

async function waitFor(expression, attempts = 80) {
  for (let index = 0; index < attempts; index += 1) {
    const value = await evaluate(expression).catch(() => false);
    if (value) return value;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

async function clickAt(x, y) {
  await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await sleep(60);
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}

async function drag(start, end, steps = 8) {
  await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: start.x, y: start.y, button: "none" });
  await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x: start.x, y: start.y, button: "left", clickCount: 1 });
  for (let index = 1; index <= steps; index += 1) {
    const ratio = index / steps;
    await cdp("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: start.x + (end.x - start.x) * ratio,
      y: start.y + (end.y - start.y) * ratio,
      button: "left",
      buttons: 1,
    });
    await sleep(30);
  }
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: end.x, y: end.y, button: "left", clickCount: 1 });
}

async function key(key, modifiers = 0) {
  const specialKeyCodes = { Backspace: 8, Enter: 13, Escape: 27, Delete: 46, ArrowLeft: 37, ArrowRight: 39 };
  const windowsVirtualKeyCode = key.length === 1 ? key.toUpperCase().charCodeAt(0) : specialKeyCodes[key];
  await cdp("Input.dispatchKeyEvent", { type: "keyDown", key, windowsVirtualKeyCode, modifiers });
  await cdp("Input.dispatchKeyEvent", { type: "keyUp", key, windowsVirtualKeyCode, modifiers });
}

async function screenshot(name) {
  const { data } = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const path = `${SCREENSHOT_DIR}/${name}`;
  writeFileSync(path, Buffer.from(data, "base64"));
  return path;
}

async function setViewport(width, height) {
  await cdp("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 700,
  });
}

async function clickButton(label, times = 1) {
  for (let index = 0; index < times; index += 1) {
    await evaluate(`document.querySelector('button[aria-label="${label}"]').click()`);
    await sleep(80);
  }
}

async function login(email) {
  await cdp("Page.navigate", { url: APP_URL });
  await waitFor("document.readyState === 'complete' || document.readyState === 'interactive'");
  await evaluate(`
    (() => {
      window.localStorage.removeItem('medi_token');
      if (!Array.from(document.querySelectorAll('form button')).some((button) => button.textContent.includes('Sign in'))) window.location.reload();
      return true;
    })()
  `);
  await waitFor("Array.from(document.querySelectorAll('form button')).some((button) => button.textContent.includes('Sign in'))");
  await evaluate(`
    (() => {
      const form = Array.from(document.querySelectorAll('form')).find((candidate) =>
        Array.from(candidate.querySelectorAll('button')).some((button) => button.textContent.includes('Sign in'))
      );
      const inputs = Array.from(form.querySelectorAll('input'));
      inputs[0].value = ${JSON.stringify(email)};
      inputs[1].value = 'password';
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
      form.requestSubmit();
      return true;
    })()
  `);
  await waitFor(`
    document.body.innerText.includes('Neuro Oncology Research') &&
    Array.from(document.querySelectorAll('canvas')).some((canvas) => {
      const rect = canvas.getBoundingClientRect();
      return rect.width > 100 && rect.height > 100;
    })
  `, 120);
}

async function chooseTool(label) {
  await evaluate(`
    (() => {
      const button = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.getAttribute('aria-label')?.startsWith(${JSON.stringify(`${label}:`)}));
      if (!button) throw new Error('Missing tool ${label}');
      button.click();
      return true;
    })()
  `);
  await sleep(200);
}

async function chooseLabel(name) {
  await evaluate(`
    (() => {
      const select = Array.from(document.querySelectorAll('select')).find((candidate) =>
        Array.from(candidate.options).some((option) => option.textContent.trim() === ${JSON.stringify(name)})
      );
      if (!select) throw new Error('Missing label select for ${name}');
      const option = Array.from(select.options).find((candidate) => candidate.textContent.trim() === ${JSON.stringify(name)});
      if (!option) throw new Error('Missing label ${name}');
      select.value = option.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()
  `);
  await sleep(200);
}

async function canvasRect() {
  return evaluate(`
    (() => {
      const canvas = Array.from(document.querySelectorAll('canvas'))
        .map((candidate) => ({ candidate, rect: candidate.getBoundingClientRect() }))
        .filter(({ rect }) => rect.width > 100 && rect.height > 100)
        .sort((left, right) => (right.rect.width * right.rect.height) - (left.rect.width * left.rect.height))[0];
      if (!canvas) throw new Error('Missing visible viewer canvas');
      const rect = canvas.rect;
      return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
    })()
  `);
}

async function annotationItems() {
  return evaluate(`
    fetch(${JSON.stringify(apiUrl("/annotations"))}, {
      headers: { Authorization: 'Bearer ' + localStorage.getItem('medi_token') }
    }).then((response) => response.json())
  `);
}

async function run() {
  await waitForJson(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
  const pageTarget = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
  if (!pageTarget) throw new Error("Chrome did not expose a page debugging target");
  socket = new WebSocket(pageTarget.webSocketDebuggerUrl);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      pageErrors.push(message.params.exceptionDetails?.exception?.description ?? message.params.exceptionDetails?.text ?? "Unknown page error");
    }
    if (!message.id) return;
    const deferred = pending.get(message.id);
    if (!deferred) return;
    pending.delete(message.id);
    if (message.error) deferred.reject(new Error(message.error.message));
    else deferred.resolve(message.result);
  });
  await new Promise((resolve) => socket.addEventListener("open", resolve, { once: true }));
  await cdp("Page.enable");
  await cdp("Runtime.enable");

  await setViewport(1440, 900);
  await login("admin@medi.local");
  await chooseLabel("tumour");
  await chooseTool("Box");
  const beforeBoxItems = await annotationItems();
  const beforeBoxIds = new Set(beforeBoxItems.map((item) => item.id));
  let rect = await canvasRect();
  await drag({ x: rect.left + 150, y: rect.top + 150 }, { x: rect.left + 260, y: rect.top + 230 });
  await sleep(700);
  const afterBoxItems = await annotationItems();
  const createdBox = afterBoxItems.find((item) => !beforeBoxIds.has(item.id) && item.annotation_type === "bounding_box");
  await chooseTool("Select");
  if (createdBox) {
    const selector = `[data-annotation-id="${createdBox.id}"]`;
    await waitFor(`document.querySelector(${JSON.stringify(selector)}) !== null`);
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
    await waitFor(`document.querySelector(${JSON.stringify(selector)}).className.includes('border-orange-500')`);
    rect = await canvasRect();
  }
  await drag({ x: rect.left + 205, y: rect.top + 190 }, { x: rect.left + 240, y: rect.top + 220 });
  await sleep(400);
  await drag({ x: rect.left + 295, y: rect.top + 260 }, { x: rect.left + 325, y: rect.top + 285 });
  await sleep(500);
  await key("z", 2);
  await sleep(400);
  await key("y", 2);
  await sleep(500);
  const editedBox = createdBox ? (await annotationItems()).find((item) => item.id === createdBox.id) : null;
  const boxScreenshot = await screenshot("bounding-box-workflow.png");
  await evaluate("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true, cancelable: true }))");
  await sleep(600);
  const boxDeleted = createdBox ? !(await annotationItems()).some((item) => item.id === createdBox.id) : false;
  const boxEdited = Boolean(
    editedBox &&
    editedBox.coordinates.x === 185 &&
    editedBox.coordinates.y === 180 &&
    editedBox.coordinates.width === 140 &&
    editedBox.coordinates.height === 105
  );
  record(
    "Bounding box draw/select/move/resize/delete",
    createdBox && boxEdited && boxDeleted ? "Pass" : "Needs review",
    `Created=${Boolean(createdBox)}, moved/resized/undo-redo geometry verified=${boxEdited} (${JSON.stringify(editedBox?.coordinates ?? null)}), deleted=${boxDeleted}.`,
    boxScreenshot,
  );

  await login("annotator@medi.local");
  await chooseLabel("lesion");
  await chooseTool("Polygon");
  const beforePolygonItems = await annotationItems();
  const beforePolygonIds = new Set(beforePolygonItems.map((item) => item.id));
  rect = await canvasRect();
  await clickAt(rect.left + 310, rect.top + 170);
  await clickAt(rect.left + 390, rect.top + 180);
  await clickAt(rect.left + 420, rect.top + 250);
  await clickAt(rect.left + 330, rect.top + 275);
  await key("Enter");
  await sleep(700);
  const afterPolygonItems = await annotationItems();
  const createdPolygon = afterPolygonItems.find((item) => !beforePolygonIds.has(item.id) && item.annotation_type === "polygon");
  await chooseTool("Select");
  await clickAt(rect.left + 360, rect.top + 220);
  await drag({ x: rect.left + 310, y: rect.top + 170 }, { x: rect.left + 285, y: rect.top + 160 });
  await sleep(600);
  const editedPolygon = createdPolygon ? (await annotationItems()).find((item) => item.id === createdPolygon.id) : null;
  const polygonEdited = Boolean(editedPolygon?.coordinates.points?.[0]?.x === 285 && editedPolygon?.coordinates.points?.[0]?.y === 160);
  const polygonScreenshot = await screenshot("polygon-workflow.png");
  record(
    "Polygon draw and vertex edit",
    createdPolygon && polygonEdited ? "Pass" : "Needs review",
    `Created=${Boolean(createdPolygon)}, saved vertex edit verified=${polygonEdited}.`,
    polygonScreenshot,
  );

  await chooseTool("Polygon");
  const beforeLabelSwitchItems = await annotationItems();
  const beforeLabelSwitchIds = new Set(beforeLabelSwitchItems.map((item) => item.id));
  rect = await canvasRect();
  await clickAt(rect.left + 100, rect.top + 300);
  await clickAt(rect.left + 150, rect.top + 320);
  await chooseLabel("normal");
  await clickAt(rect.left + 170, rect.top + 370);
  await key("Enter");
  await sleep(700);
  const labelSwitchScreenshot = await screenshot("label-switch-draft.png");
  const labelSwitchItems = await annotationItems();
  const savedNormal = labelSwitchItems.find((item) => !beforeLabelSwitchIds.has(item.id) && item.annotation_type === "polygon" && item.label === "normal");
  record(
    "Label switching preserves draft geometry",
    savedNormal ? "Pass" : "Needs review",
    "Started a polygon draft, switched label, completed it, and verified a normal polygon exists through the API.",
    labelSwitchScreenshot,
  );

  await key("v");
  await key("h");
  await key("b");
  await key("p");
  await key("m");
  await key("[");
  await key("]");
  const activeToolLabel = await evaluate(`
    document.querySelector('button[aria-pressed="true"]')?.getAttribute('aria-label') ?? ''
  `);
  const shortcutScreenshot = await screenshot("keyboard-shortcuts.png");
  const inputShortcutSafety = await evaluate(`
    (() => {
      const input = document.querySelector('input');
      if (!input) return false;
      input.focus();
      const before = document.querySelector('button[aria-pressed="true"]')?.getAttribute('aria-label') ?? '';
      const eventsWereNotCancelled = ['b', 'p', 'm'].every((keyValue) =>
        input.dispatchEvent(new KeyboardEvent('keydown', { key: keyValue, bubbles: true, cancelable: true }))
      );
      const after = document.querySelector('button[aria-pressed="true"]')?.getAttribute('aria-label') ?? '';
      input.blur();
      return eventsWereNotCancelled && before === after;
    })()
  `);
  record(
    "Keyboard shortcuts avoid browser conflicts",
    activeToolLabel.startsWith("Mask:") && inputShortcutSafety ? "Pass" : "Needs review",
    `Viewer shortcut sequence ended on Mask; focused-input shortcuts ignored=${inputShortcutSafety}.`,
    shortcutScreenshot,
  );

  await setViewport(1440, 900);
  await clickButton("Reset viewport");
  await clickButton("Zoom out", 2);
  const widthAt50 = (await canvasRect()).width;
  await clickButton("Reset viewport");
  const widthAt100 = (await canvasRect()).width;
  await clickButton("Zoom in", 4);
  const widthAt200 = (await canvasRect()).width;
  await clickButton("Zoom in", 8);
  const widthAt400 = (await canvasRect()).width;
  await chooseTool("Pan");
  const panBefore = await evaluate(`
    (() => {
      const viewport = document.querySelector('[data-viewer-viewport]');
      const rect = viewport.getBoundingClientRect();
      return { scrollLeft: viewport.scrollLeft, scrollTop: viewport.scrollTop, x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    })()
  `);
  await drag(
    { x: panBefore.x + panBefore.width * 0.65, y: panBefore.y + panBefore.height * 0.55 },
    { x: panBefore.x + panBefore.width * 0.35, y: panBefore.y + panBefore.height * 0.35 },
  );
  const panAfter = await evaluate(`
    (() => {
      const viewport = document.querySelector('[data-viewer-viewport]');
      return { scrollLeft: viewport.scrollLeft, scrollTop: viewport.scrollTop };
    })()
  `);
  const zoomScalingVerified = [widthAt50, widthAt100, widthAt200, widthAt400].every((width, index) => Math.abs(width - [256, 512, 1024, 2048][index]) < 1);
  const panVerified = panAfter.scrollLeft !== panBefore.scrollLeft || panAfter.scrollTop !== panBefore.scrollTop;
  await clickButton("Reset viewport");

  const responsiveScreenshots = [];
  for (const [width, height, name] of [
    [1440, 900, "overlay-desktop.png"],
    [1024, 768, "overlay-tablet.png"],
    [390, 844, "overlay-mobile.png"],
  ]) {
    await setViewport(width, height);
    await sleep(600);
    await evaluate(`
      (() => {
        const canvas = Array.from(document.querySelectorAll('canvas')).find((candidate) => {
          const rect = candidate.getBoundingClientRect();
          return rect.width > 100 && rect.height > 100;
        });
        canvas?.scrollIntoView({ block: 'center', inline: 'center' });
        return true;
      })()
    `);
    await sleep(300);
    responsiveScreenshots.push(await screenshot(name));
  }
  const hasHorizontalPageOverflow = await evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth");
  record(
    "Overlay alignment at multiple image sizes",
    pageErrors.length === 0 && !hasHorizontalPageOverflow && zoomScalingVerified && panVerified ? "Visual review" : "Needs review",
    `Canvas widths at 50/100/200/400%=${[widthAt50, widthAt100, widthAt200, widthAt400].join('/')}; pan verified=${panVerified}; page errors=${pageErrors.length}; horizontal page overflow=${hasHorizontalPageOverflow}. Confirm anatomy anchoring visually.`,
    responsiveScreenshots.join(", "),
  );

  const markdownRows = evidence.map((item) => `| ${item.check} | ${item.status} | ${item.note} | ${item.screenshot} |`).join("\n");
  writeFileSync(`${SCREENSHOT_DIR}/phase3_frontend_qa_evidence.md`, `# Phase 3 Frontend QA Evidence\n\n${markdownRows}\n`);
  console.log(JSON.stringify({ screenshotDir: SCREENSHOT_DIR, evidence }, null, 2));
}

run()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    chrome.kill("SIGTERM");
  });
