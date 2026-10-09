import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server, ResponseMessage, LandingPage, sendMessage, config;
const originalFetch = globalThis.fetch;

before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  ({ default: ResponseMessage } = await server.ssrLoadModule('/src/components/ResponseMessage.jsx'));
  ({ default: LandingPage } = await server.ssrLoadModule('/src/LandingPage.jsx'));
  ({ sendMessage } = await server.ssrLoadModule('/src/api/chat.js'));
  ({ config } = await server.ssrLoadModule('/src/config.js'));
});
after(async () => { globalThis.fetch = originalFetch; await server?.close(); });

const render = (result) => renderToStaticMarkup(React.createElement(ResponseMessage, { result }));

test('landing has a start button and no sign-in or login', () => {
  const html = renderToStaticMarkup(React.createElement(LandingPage));
  assert.match(html, /Get Started/);
  assert.doesNotMatch(html, /sign.?in|log.?in/i);
});

test('clarification, blocked responses and errors show messages and H/G disclaimers', () => {
  for (const action of ['clarify', 'block', 'error']) {
    const html = render({ action, message: 'Please specify the medicine.', disclaimer: 'Please consult a doctor.' });
    assert.match(html, /Please specify the medicine/);
    assert.match(html, /Please consult a doctor/);
  }
  assert.equal(render({ action: 'block', reason: 'schedule_x', message: null }), '');
});

test('uses, side effects and general health render independently without raw HTML injection', () => {
  const html = render({ action: 'response', results: [
    { intent: 'side_effects', status: 'ok', data: [{ medicine: 'Example', side_effects: ['Effect'] }] },
    { intent: 'uses_of_medicine', status: 'ok', data: [{ medicine: 'Example', uses: [] }] },
    { intent: 'general_health', status: 'ok', data: '<script>alert(1)</script>' },
  ] });
  assert.match(html, /Side effects/);
  assert.match(html, /Effect/);
  assert.match(html, /Uses/);
  assert.ok(html.includes(config.no_data));
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test('actual comparison schema renders once for combined intents with missing prices and no max savings', () => {
  const example = JSON.parse(readFileSync(new URL('../../examples/price_response.json', import.meta.url), 'utf8'));
  const html = render(example);
  assert.match(html, /Augmentin/);
  assert.match(html, /Moxikind/);
  assert.match(html, /ACTIVE COMPOSITION/);
  assert.ok(html.includes(config.price_unavailable));
  assert.equal((html.match(/aria-label="Medicine comparison"/g) || []).length, 1);
  assert.doesNotMatch(html, /MAX POTENTIAL|maxSavings|NaN|undefined/);
  assert.match(html, /View pharmacy/);
});

test('empty quotes and alternatives do not invent prices', () => {
  const html = render({ action: 'response', results: [{ intent: 'price_comparison', status: 'ok', data: [{
    original: { medicine: 'Example', composition: [], prices: { quotes: [] } }, alternatives: [],
  }] }] });
  assert.ok(html.includes(config.no_quotes));
  assert.ok(html.includes(config.no_alternatives));
  assert.doesNotMatch(html, /NaN|undefined/);
});

test('chat client sends only the message and request/session IDs and accepts a backend response', async () => {
  const payload = { message: 'Hello', session_id: 'session', request_id: 'request' };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, `${config.apiPrefix}/chat`);
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), payload);
    return { ok: true, json: async () => ({ session_id: 'session', result: { action: 'clarify' } }) };
  };
  const result = await sendMessage(payload, new AbortController().signal);
  assert.equal(result.result.action, 'clarify');
});

test('HTTP failures and malformed responses are errors, never successful answers', async () => {
  globalThis.fetch = async () => ({ ok: false });
  await assert.rejects(sendMessage({}, new AbortController().signal), { message: config.network_error });
  globalThis.fetch = async () => ({ ok: false, json: async () => ({ detail: 'MediBot is busy.' }) });
  await assert.rejects(sendMessage({}, new AbortController().signal), { message: 'MediBot is busy.' });
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ result: { action: 'continue' } }) });
  await assert.rejects(sendMessage({}, new AbortController().signal), { message: config.invalid_response });
});

test('new-chat cancellation and timeout abort in-flight fetch', async () => {
  globalThis.fetch = async (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  });
  const controller = new AbortController();
  const pending = sendMessage({}, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  const timeout = config.requestTimeoutMs;
  config.requestTimeoutMs = 5;
  try {
    await assert.rejects(sendMessage({}, new AbortController().signal), { message: config.timeout_error });
  } finally { config.requestTimeoutMs = timeout; }
});
