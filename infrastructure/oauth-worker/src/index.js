const encoder = new TextEncoder();
const STATE_COOKIE = "tellius_archive_oauth_state";
const STATE_TTL_SECONDS = 300;

function base64Url(bytes) {
  let binary = "";
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeBase64Url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  return Uint8Array.from(atob(padded), character => character.charCodeAt(0));
}

async function hmac(secret, value) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}

async function createState(env, origin) {
  const nonce = new Uint8Array(24);
  crypto.getRandomValues(nonce);
  const payload = base64Url(encoder.encode(JSON.stringify({
    origin,
    nonce: base64Url(nonce),
    expires: Math.floor(Date.now() / 1000) + STATE_TTL_SECONDS,
  })));
  return `${payload}.${base64Url(await hmac(env.OAUTH_STATE_SECRET, payload))}`;
}

async function verifyState(env, state, expectedOrigin) {
  const [payload, signature, extra] = (state || "").split(".");
  if (!payload || !signature || extra) return false;
  const expected = await hmac(env.OAUTH_STATE_SECRET, payload);
  const actual = decodeBase64Url(signature);
  if (actual.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < actual.length; index += 1) difference |= actual[index] ^ expected[index];
  if (difference !== 0) return false;
  let contents;
  try { contents = JSON.parse(new TextDecoder().decode(decodeBase64Url(payload))); }
  catch { return false; }
  return contents.origin === expectedOrigin && Number(contents.expires) >= Math.floor(Date.now() / 1000);
}

function cookieValue(request, name) {
  const header = request.headers.get("Cookie") || "";
  const match = header.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function callbackUrl(url) {
  return `${url.origin}/callback?provider=github`;
}

function safeOrigin(env, requested) {
  const allowed = new URL(env.ALLOWED_ORIGIN).origin;
  if (!requested) return allowed;
  try { return new URL(requested).origin === allowed ? allowed : null; }
  catch { return null; }
}

async function authorize(request, env, url) {
  if (url.searchParams.get("provider") !== "github") return new Response("Invalid provider", { status: 400 });
  const origin = safeOrigin(env, url.searchParams.get("site_id") ? `https://${url.searchParams.get("site_id")}` : env.ALLOWED_ORIGIN);
  if (!origin) return new Response("Invalid site origin", { status: 400 });
  const state = await createState(env, origin);
  const target = new URL("https://github.com/login/oauth/authorize");
  target.searchParams.set("client_id", env.GITHUB_OAUTH_ID);
  target.searchParams.set("redirect_uri", callbackUrl(url));
  target.searchParams.set("scope", env.GITHUB_SCOPE || "public_repo,user");
  target.searchParams.set("state", state);
  return new Response(null, {
    status: 302,
    headers: {
      Location: target.toString(),
      "Cache-Control": "no-store",
      "Set-Cookie": `${STATE_COOKIE}=${encodeURIComponent(state)}; Max-Age=${STATE_TTL_SECONDS}; Path=/callback; Secure; HttpOnly; SameSite=Lax`,
    },
  });
}

function callbackPage(origin, status, payload) {
  const nonceBytes = new Uint8Array(16);
  crypto.getRandomValues(nonceBytes);
  const nonce = base64Url(nonceBytes);
  const message = `authorization:github:${status}:${JSON.stringify(payload)}`;
  const script = `
    const expectedOrigin = ${JSON.stringify(origin)};
    const finish = () => window.opener.postMessage(${JSON.stringify(message)}, expectedOrigin);
    window.addEventListener("message", (event) => {
      if (event.origin === expectedOrigin) finish();
    }, { once: true });
    window.opener.postMessage("authorizing:github", expectedOrigin);
  `;
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>Authorizing Tellius Archive</title></head><body><p>Finishing GitHub authorization…</p><script nonce="${nonce}">${script}</script></body></html>`, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'none'; img-src 'none'; base-uri 'none'; frame-ancestors 'none'`,
      "Referrer-Policy": "no-referrer",
      "Set-Cookie": `${STATE_COOKIE}=; Max-Age=0; Path=/callback; Secure; HttpOnly; SameSite=Lax`,
    },
  });
}

async function callback(request, env, url) {
  if (url.searchParams.get("provider") !== "github") return new Response("Invalid provider", { status: 400 });
  const state = url.searchParams.get("state") || "";
  const cookieState = cookieValue(request, STATE_COOKIE);
  const origin = new URL(env.ALLOWED_ORIGIN).origin;
  if (state !== cookieState || !(await verifyState(env, state, origin))) {
    return new Response("Invalid or expired OAuth state", { status: 400, headers: { "Cache-Control": "no-store" } });
  }
  const code = url.searchParams.get("code");
  if (!code) return callbackPage(origin, "error", { message: "GitHub did not return an authorization code." });
  const response = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", "User-Agent": "Tellius-Archive-OAuth" },
    body: JSON.stringify({
      client_id: env.GITHUB_OAUTH_ID,
      client_secret: env.GITHUB_OAUTH_SECRET,
      code,
      redirect_uri: callbackUrl(url),
    }),
  });
  const result = await response.json();
  if (!response.ok || !result.access_token) return callbackPage(origin, "error", { message: "GitHub token exchange failed." });
  return callbackPage(origin, "success", { token: result.access_token });
}

export default {
  async fetch(request, env) {
    if (!env.GITHUB_OAUTH_ID || !env.GITHUB_OAUTH_SECRET || !env.OAUTH_STATE_SECRET || !env.ALLOWED_ORIGIN) {
      return new Response("OAuth worker is not configured", { status: 503 });
    }
    const url = new URL(request.url);
    if (request.method !== "GET") return new Response("Method not allowed", { status: 405, headers: { Allow: "GET" } });
    if (url.pathname === "/auth") return authorize(request, env, url);
    if (url.pathname === "/callback") return callback(request, env, url);
    if (url.pathname === "/healthz") return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
    return new Response("Tellius Archive OAuth proxy", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  },
};
