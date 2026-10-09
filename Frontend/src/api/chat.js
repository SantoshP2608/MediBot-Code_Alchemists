import { config } from '../config';

export async function sendMessage(payload, signal) {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, config.requestTimeoutMs);
  try {
    const response = await fetch(`${config.apiPrefix}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), signal: controller.signal,
    });
    if (!response.ok) {
      let message = config.network_error;
      try {
        const body = await response.json();
        if (typeof body.detail === 'string') message = body.detail;
      } catch { /* A proxy may return HTML instead of a JSON error. */ }
      throw new Error(message);
    }
    const body = await response.json();
    if (!body.session_id || !['block', 'clarify', 'error', 'response'].includes(body.result?.action)) {
      throw new Error(config.invalid_response);
    }
    return body;
  } catch (error) {
    if (timedOut) throw new Error(config.timeout_error, { cause: error });
    if (signal.aborted) throw error;
    throw new Error(error instanceof TypeError ? config.network_error : error.message, { cause: error });
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}
