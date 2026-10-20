/* Frontend logic tests (run with Node.js, no browser required).
 *
 * Uses a minimal DOM shim to exercise the SpaceFractions module without a
 * browser or build tooling.
 *
 * Run with: node tests/test_frontend.js
 */

const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// Minimal DOM shim
// ---------------------------------------------------------------------------
function domShim() {
  const elements = {};
  return {
    getElementById: (id) => {
      if (!elements[id]) {
        elements[id] = {
          id,
          textContent: "",
          innerHTML: "",
          value: "",
          dataset: {},
          className: "",
          children: [],
          classList: {
            _classes: new Set(),
            add: function (c) { this._classes.add(c); },
            remove: function (c) { this._classes.delete(c); },
            contains: function (c) { return this._classes.has(c); },
            toggle: function (c) {
              if (this._classes.has(c)) this._classes.delete(c);
              else this._classes.add(c);
            },
          },
          addEventListener: () => {},
          appendChild: () => {},
        };
      }
      return elements[id];
    },
    querySelectorAll: (sel) =>
      sel === ".screen"
        ? Object.values(elements).filter((e) => e.id.startsWith("screen-"))
        : [],
    querySelector: () => null,
    createElement: () => ({
      textContent: "",
      innerHTML: "",
      dataset: {},
      className: "",
      classList: { add: () => {}, remove: () => {}, contains: () => false },
      addEventListener: () => {},
      appendChild: () => {},
    }),
    addEventListener: () => {},
  };
}

function makeSpaceFractions(fetchImpl) {
  const fakeDoc = domShim();
  global.document = fakeDoc;
  global.window = {};
  global.fetch = fetchImpl || (async () => ({
    ok: true,
    status: 200,
    json: async () => ({}),
  }));

  const src = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");
  const factory = new Function(src + "\n;return SpaceFractions;");
  const SF = factory();
  return { SF, fakeDoc };
}

function assertEq(actual, expected, msg) {
  if (actual !== expected) {
    console.error(`FAIL: ${msg} — expected ${expected}, got ${actual}`);
    process.exit(1);
  }
  console.log(`ok - ${msg}`);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
const { SF, fakeDoc } = makeSpaceFractions();

// Test 1: init shows intro screen by default.
SF.init();
assertEq(
  fakeDoc.getElementById("screen-intro").classList.contains("active"),
  true,
  "init activates the intro screen"
);

// Test 2: showScreen switches between screens.
SF.showScreen("menu");
assertEq(
  fakeDoc.getElementById("screen-menu").classList.contains("active"),
  true,
  "showScreen activates the menu screen"
);
assertEq(
  fakeDoc.getElementById("screen-intro").classList.contains("active"),
  false,
  "showScreen deactivates the intro screen"
);

// Test 3: initial game state is empty.
assertEq(SF._state.gameId, null, "initial gameId is null");
assertEq(SF._state.score, 0, "initial score is 0");
assertEq(SF._state.isAdmin, false, "initial isAdmin is false");

// Test 4: showScreen to each documented view works without throwing.
["game", "score", "help", "admin", "ending"].forEach((name) => {
  SF.showScreen(name);
  assertEq(
    fakeDoc.getElementById("screen-" + name).classList.contains("active"),
    true,
    "showScreen activates " + name + " screen"
  );
});

// ---------------------------------------------------------------------------
// Admin authentication tests (ASR-2)
// ---------------------------------------------------------------------------
function jsonResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

(async () => {
  // Test 5: a successful admin login keeps the token in memory and sends it on later calls.
  const calls = [];
  const fetchOk = async (url, opts) => {
    calls.push({ url, opts });
    if (url === "/api/login") {
      return jsonResponse(200, { token: "tok123", role: "admin", username: "boss" });
    }
    return jsonResponse(200, { questions: [] });
  };
  let { SF, fakeDoc } = makeSpaceFractions(fetchOk);
  fakeDoc.getElementById("admin-username").value = "boss";
  fakeDoc.getElementById("admin-password").value = "s3cret-pass";
  await SF.adminLogin();
  assertEq(SF._state.token, "tok123", "admin login stores the token in memory");
  assertEq(SF._state.isAdmin, true, "admin login sets isAdmin");
  assertEq(fakeDoc.getElementById("admin-password").value, "", "password field is cleared after login");
  assertEq(JSON.parse(calls[0].opts.body).role, undefined, "login request does not send a role");
  assertEq(calls[0].opts.headers["Authorization"], undefined, "login request carries no token");
  const listCall = calls.find((c) => c.url === "/api/questions");
  assertEq(listCall.opts.headers["Authorization"], "Bearer tok123", "later calls send the bearer token");

  // Test 6: logout drops the token, so the next call is anonymous again.
  SF.logout();
  assertEq(SF._state.token, null, "logout clears the token");
  await SF._api("/api/games", { method: "POST" });
  assertEq(calls[calls.length - 1].opts.headers["Authorization"], undefined, "no token after logout");

  // Test 7: wrong password shows an error and never stores a token.
  ({ SF, fakeDoc } = makeSpaceFractions(async () => jsonResponse(401, { detail: "Invalid username or password" })));
  fakeDoc.getElementById("admin-username").value = "boss";
  fakeDoc.getElementById("admin-password").value = "wrong-pass";
  await SF.adminLogin();
  assertEq(SF._state.token, null, "failed login stores no token");
  assertEq(
    fakeDoc.getElementById("admin-status").textContent,
    "Login failed: Invalid username or password",
    "failed login shows the server's message"
  );

  // Test 8: a non-admin account never gets the admin panel or a token.
  ({ SF, fakeDoc } = makeSpaceFractions(async () => jsonResponse(200, { token: "t", role: "player", username: "kid" })));
  fakeDoc.getElementById("admin-username").value = "kid";
  fakeDoc.getElementById("admin-password").value = "rocket-science";
  await SF.adminLogin();
  assertEq(SF._state.token, null, "player login does not keep a token for the admin area");
  assertEq(SF._state.isAdmin, false, "player login does not set isAdmin");

  // Test 8b: FastAPI validation errors (a list) become readable text.
  ({ SF, fakeDoc } = makeSpaceFractions(async () =>
    jsonResponse(422, { detail: [{ msg: "Value error, correct_index must be a valid index into options" }] })));
  let message = "";
  try { await SF._api("/api/questions", { method: "POST" }); } catch (e) { message = e.message; }
  assertEq(message, "correct_index must be a valid index into options", "validation errors are readable");

  // Test 9: empty fields are rejected without calling the server.
  let called = false;
  ({ SF, fakeDoc } = makeSpaceFractions(async () => { called = true; return jsonResponse(200, {}); }));
  await SF.adminLogin();
  assertEq(called, false, "empty credentials make no request");

  console.log("All frontend tests passed.");
  process.exit(0);
})().catch((e) => {
  console.error("FAIL: unexpected error", e);
  process.exit(1);
});
