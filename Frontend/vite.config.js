import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { readFileSync } from 'node:fs'

const constants = JSON.parse(readFileSync(new URL('../constants.txt', import.meta.url), 'utf8'))
const api = constants.api
const proxy = { [api.prefix]: { target: `http://${api.host}:${api.port}` } }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: { __MEDIBOT_CONFIG__: JSON.stringify({ ...constants.frontend,
    apiPrefix: api.prefix, maxMessageLength: api.max_message_length,
    requestTimeoutMs: api.request_timeout_ms, currency: constants.pricing.currency }) },
  server: { port: api.frontend_port, strictPort: true, proxy },
  preview: { proxy },
})
