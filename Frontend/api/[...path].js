import { Buffer } from 'node:buffer';
import process from 'node:process';

const routes = new Map([
  ['/chat', 'POST'],
  ['/select', 'POST'],
  ['/health', 'GET'],
]);

export default async function handler(request, response) {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  const route = pathname.startsWith('/api/') ? pathname.slice('/api'.length) : '';
  const allowedMethod = routes.get(route);

  if (!allowedMethod) {
    return response.status(404).json({ detail: 'Not found.' });
  }
  if (request.method !== allowedMethod) {
    response.setHeader('Allow', allowedMethod);
    return response.status(405).json({ detail: 'Method not allowed.' });
  }

  const backendUrl = process.env.MEDIBOT_BACKEND_URL;
  const apiToken = process.env.MEDIBOT_API_TOKEN;
  if (!backendUrl || !apiToken) {
    return response.status(500).json({ detail: 'The API proxy is not configured.' });
  }

  let backend;
  try {
    backend = new URL(backendUrl);
  } catch {
    return response.status(500).json({ detail: 'MEDIBOT_BACKEND_URL must be an HTTPS origin.' });
  }
  if (
    backend.protocol !== 'https:' ||
    backend.pathname !== '/' ||
    backend.username ||
    backend.password ||
    backend.search ||
    backend.hash
  ) {
    return response.status(500).json({ detail: 'MEDIBOT_BACKEND_URL must be an HTTPS origin.' });
  }

  let upstream;
  try {
    upstream = await fetch(new URL(`/api${route}`, backend.origin), {
      method: allowedMethod,
      headers: {
        Authorization: `Bearer ${apiToken}`,
        ...(allowedMethod === 'POST' ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(allowedMethod === 'POST' ? { body: JSON.stringify(request.body) } : {}),
    });
  } catch (error) {
    console.error('MediBot backend request failed:', error);
    return response.status(502).json({ detail: 'The backend could not be reached.' });
  }

  response.status(upstream.status);
  response.setHeader('Cache-Control', 'no-store');
  const contentType = upstream.headers.get('content-type');
  if (contentType) response.setHeader('Content-Type', contentType);
  return response.send(Buffer.from(await upstream.arrayBuffer()));
}
