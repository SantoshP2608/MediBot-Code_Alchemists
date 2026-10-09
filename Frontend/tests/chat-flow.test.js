import assert from 'node:assert/strict';
import { after, afterEach, before, beforeEach, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';

let dom, server, createRoot, ChatPage, config, root, container;
const originalFetch = globalThis.fetch;

before(async () => {
  dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:5173' });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  dom.window.HTMLElement.prototype.scrollIntoView = () => {};
  ({ createRoot } = await import('react-dom/client'));
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  ({ default: ChatPage } = await server.ssrLoadModule('/src/ChatPage.jsx'));
  ({ config } = await server.ssrLoadModule('/src/config.js'));
});

beforeEach(async () => {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(React.createElement(ChatPage)));
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  globalThis.fetch = originalFetch;
});

after(async () => {
  await server?.close();
  dom?.window.close();
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  delete globalThis.window;
  delete globalThis.document;
});

const textarea = () => container.querySelector('textarea');
const sendButton = () => container.querySelector('button[type="submit"]');
const response = (payload, result) => ({ ok: true, json: async () => ({ session_id: payload.session_id, result }) });
const answer = (text) => ({ action: 'response', results: [{ intent: 'general_health', status: 'ok', data: text }] });

async function acceptDisclaimer() {
  await act(async () => container.querySelector('input[type="checkbox"]').click());
}

async function type(text) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set.call(textarea(), text);
    textarea().dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
}

async function clickSend(text) {
  await type(text);
  await act(async () => sendButton().click());
}

test('Send calls the API and displays its answer; loading prevents duplicate submissions', async () => {
  const calls = [];
  let complete;
  globalThis.fetch = (url, options) => {
    calls.push({ url, payload: JSON.parse(options.body) });
    return new Promise((resolve) => { complete = resolve; });
  };
  assert.equal(textarea().disabled, true);
  assert.equal(textarea().maxLength, config.maxMessageLength);
  assert.ok(container.textContent.includes(config.welcome));
  assert.doesNotMatch(container.textContent, /Frontend preview|sample comparison/i);
  await acceptDisclaimer();
  await clickSend('Tell me about sleep');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${config.apiPrefix}/chat`);
  assert.equal(calls[0].payload.message, 'Tell me about sleep');
  assert.match(calls[0].payload.session_id, /^[0-9a-f-]{36}$/);
  assert.match(calls[0].payload.request_id, /^[0-9a-f-]{36}$/);
  assert.equal(container.querySelectorAll('.message-row.user').length, 1);
  assert.equal(textarea().value, '');
  assert.equal(textarea().disabled, true);
  assert.ok(container.querySelector('[role="status"]'));
  await act(async () => textarea().form.requestSubmit());
  assert.equal(calls.length, 1);
  await act(async () => complete(response(calls[0].payload, answer('A real backend answer'))));
  assert.ok(container.textContent.includes('A real backend answer'));
  assert.equal(textarea().disabled, false);
  assert.equal(container.querySelector('[role="status"]'), null);
});

test('Enter sends clarification replies in the same session; Shift+Enter does not submit', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push(payload);
    return response(payload, calls.length === 1
      ? { action: 'clarify', message: 'Which medicine?', candidates: ['Example Tablet'] }
      : { action: 'response', disclaimer: 'Please consult a doctor.', results: [
        { intent: 'side_effects', status: 'ok', data: [{ medicine: 'Example Tablet', side_effects: ['Example effect'] }] },
      ] });
  };
  await acceptDisclaimer();
  await clickSend('Side effects?');
  assert.ok(container.textContent.includes('Which medicine?'));
  assert.ok(container.textContent.includes('Example Tablet'));
  await type('Example Tablet');
  await act(async () => textarea().dispatchEvent(new dom.window.KeyboardEvent('keydown', {
    key: 'Enter', shiftKey: true, bubbles: true, cancelable: true,
  })));
  assert.equal(calls.length, 1);
  await act(async () => textarea().dispatchEvent(new dom.window.KeyboardEvent('keydown', {
    key: 'Enter', bubbles: true, cancelable: true,
  })));
  assert.equal(calls.length, 2);
  assert.equal(calls[1].message, 'Example Tablet');
  assert.equal(calls[1].session_id, calls[0].session_id);
  assert.notEqual(calls[1].request_id, calls[0].request_id);
  assert.ok(container.textContent.includes('Example effect'));
  assert.equal(container.querySelector('.response-disclaimer').textContent, 'Please consult a doctor.');
});

test('Retry reuses request IDs, renders the recovered response, and does not duplicate user messages', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push(payload);
    if (calls.length === 1) throw new TypeError('Failed to fetch');
    return response(payload, answer('Recovered answer'));
  };
  await acceptDisclaimer();
  await clickSend('Tell me about hydration');
  assert.ok(container.textContent.includes(config.network_error));
  const retry = container.querySelector('.retry-button');
  assert.ok(retry);
  await act(async () => retry.click());
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(container.querySelectorAll('.message-row.user').length, 1);
  assert.ok(container.textContent.includes('Recovered answer'));
  assert.equal(container.querySelector('.retry-button'), null);
  assert.ok(!container.textContent.includes(config.network_error));
});

test('blocked messages render, Schedule X stays silent, and comparisons use the response renderer', async () => {
  const results = [
    { action: 'block', reason: 'availability', message: 'Availability is not supported.' },
    { action: 'block', reason: 'schedule_x', message: null },
    { action: 'response', results: [{ intent: 'price_comparison', status: 'ok', data: [{
      original: { medicine: 'Example Tablet', regulatory: 'OTC', composition: [], prices: { quotes: [] } },
      alternatives: [],
    }] }] },
  ];
  globalThis.fetch = async (url, options) => response(JSON.parse(options.body), results.shift());
  await acceptDisclaimer();
  await clickSend('Is Example available?');
  assert.ok(container.textContent.includes('Availability is not supported.'));
  const assistantCount = container.querySelectorAll('.message-row.assistant').length;
  await clickSend('Restricted medicine');
  assert.equal(container.querySelectorAll('.message-row.assistant').length, assistantCount);
  assert.equal(container.querySelector('[role="status"]'), null);
  await clickSend('Compare Example prices');
  assert.ok(container.querySelector('.medicine-sandbox'));
  assert.ok(container.textContent.includes(config.no_quotes));
});

test('New chat starts a fresh session and ignores an older in-flight response', async () => {
  const calls = [];
  let completeOld;
  globalThis.fetch = async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push(payload);
    if (calls.length === 1) return new Promise((resolve) => { completeOld = resolve; });
    return response(payload, answer('New conversation answer'));
  };
  await acceptDisclaimer();
  await clickSend('Old question');
  await act(async () => container.querySelector('.new-chat-button').click());
  assert.equal(container.querySelectorAll('.message-row.user').length, 0);
  assert.equal(textarea().disabled, false);
  await clickSend('New question');
  assert.notEqual(calls[1].session_id, calls[0].session_id);
  await act(async () => completeOld(response(calls[0], answer('Late old answer'))));
  assert.ok(container.textContent.includes('New conversation answer'));
  assert.ok(!container.textContent.includes('Late old answer'));
  assert.equal(container.querySelectorAll('.message-row.user').length, 1);
});
