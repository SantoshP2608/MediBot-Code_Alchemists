import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import handler from '../api/[...path].js';

const originalFetch = globalThis.fetch;
const originalBackendUrl = process.env.MEDIBOT_BACKEND_URL;
const originalApiToken = process.env.MEDIBOT_API_TOKEN;

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalBackendUrl === undefined) delete process.env.MEDIBOT_BACKEND_URL;
  else process.env.MEDIBOT_BACKEND_URL = originalBackendUrl;
  if (originalApiToken === undefined) delete process.env.MEDIBOT_API_TOKEN;
  else process.env.MEDIBOT_API_TOKEN = originalApiToken;
});

function responseStub() {
  return {
    statusCode: 200,
    headers: {},
    status(code) {
      this.statusCode = code;
      return this;
    },
    setHeader(name, value) {
      this.headers[name.toLowerCase()] = value;
    },
    json(value) {
      this.body = value;
      return this;
    },
    send(value) {
      this.body = value;
      return this;
    },
  };
}

test('proxy sends the server-only token to the Render API', async () => {
  process.env.MEDIBOT_BACKEND_URL = 'https://api.example.onrender.com';
  process.env.MEDIBOT_API_TOKEN = 'server-only-token';
  let upstreamRequest;
  globalThis.fetch = async (url, options) => {
    upstreamRequest = { url: String(url), options };
    return new Response('{"status":"ok"}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };

  const result = responseStub();
  await handler({
    method: 'POST',
    url: '/api/chat',
    body: { message: 'hello', request_id: 'request-id' },
  }, result);

  assert.equal(upstreamRequest.url, 'https://api.example.onrender.com/api/chat');
  assert.equal(upstreamRequest.options.headers.Authorization, 'Bearer server-only-token');
  assert.equal(upstreamRequest.options.body, '{"message":"hello","request_id":"request-id"}');
  assert.equal(result.statusCode, 200);
  assert.equal(result.headers['cache-control'], 'no-store');
});

test('proxy rejects unconfigured deployments and unsupported routes', async () => {
  delete process.env.MEDIBOT_BACKEND_URL;
  delete process.env.MEDIBOT_API_TOKEN;
  const missingConfig = responseStub();
  await handler({ method: 'POST', url: '/api/chat' }, missingConfig);
  assert.equal(missingConfig.statusCode, 500);

  const unsupportedRoute = responseStub();
  await handler({ method: 'POST', url: '/api/admin' }, unsupportedRoute);
  assert.equal(unsupportedRoute.statusCode, 404);

  process.env.MEDIBOT_BACKEND_URL = 'not-an-url';
  process.env.MEDIBOT_API_TOKEN = 'server-only-token';
  const invalidConfig = responseStub();
  await handler({ method: 'POST', url: '/api/chat', body: {} }, invalidConfig);
  assert.equal(invalidConfig.statusCode, 500);
});
