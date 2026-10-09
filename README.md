# MediBot backend

Requires Python 3.11 or newer. Run these commands from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For the interactive tester, install Ollama, start its local server, and pull the model:

```powershell
ollama pull qwen2.5:3b
.\.venv\Scripts\python.exe -m backend.safety_cli
```

The default server is `http://localhost:11434`. Override `OLLAMA_HOST` and
`OLLAMA_MODEL` through environment variables if needed. The extractor demo is
available with `python -m backend.extractor` or the compatibility entry point
`python extractor.py`.

## Request handling

- Prescribing, diagnosis, and interaction intents return a blocking frontend
  message immediately, including mixed requests. Clarification does not affect
  their routing.
- Other requests with `needs_clarification=true` return the extractor's question.
  A non-empty question is required. When clarification is unnecessary the
  question must be null. These consistency checks are skipped for blocked intents.
- All declared non-blocked intents, including `other`, are supported for
  downstream handling. After clarification and medicine checks, they continue
  to classification. Their specific handlers will be decided later.
- Supported requests without a medicine or with a blank medicine name ask for
  the missing name.
- `continue_to_classification` means the next medicine database check is needed;
  it does not verify a medicine or authorize dispensing. That database step is
  not implemented here.

`backend/models.py` owns the schema and intent policies, `backend/extractor.py`
calls Ollama, and `backend/safety/safety_guard.py` routes the validated extraction.
The CLI returns an error result if extraction or validation fails and logs the
exception locally for diagnosis.

The repository currently provides an interactive tester in `backend/safety_cli.py`;
it does not contain an automated test suite.
