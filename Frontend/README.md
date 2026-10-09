# MediBot frontend

React + Vite chat connected to the Python backend. Start the backend with
`python -m backend.api` from the repository root, then run `npm.cmd ci` and
`npm.cmd run dev` here. Open http://localhost:5173.

No sign-in UI or account is required. The chat renders safety messages,
clarification questions, medicine uses and side effects, general health answers,
and original/substitute pharmacy quotes. Schedule H/G disclaimers remain visible;
Schedule X produces no assistant reply. Maximum savings and sample comparisons
have been removed. Missing prices display as unavailable.

`vite.config.js` reads the public settings from `../constants.txt` and forwards
`/api` to the backend. For production, configure the host to proxy `/api` to Python.
Sessions are anonymous and held by the backend. New chat starts a fresh session.

Checks: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`.
See the root README for Ollama setup, API behavior, and deployment limitations.
