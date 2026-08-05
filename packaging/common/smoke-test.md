# Packaging smoke test

Run every packaged artifact on a clean machine or VM for that platform.

1. Start the packaged LLM Vampire app.
2. Confirm it binds the configured gateway port, defaulting to `7777`.
3. Open `http://127.0.0.1:7777/` and confirm the bundled dashboard loads.
4. Request `GET /vampire/v1/status` and confirm a `vampire.status` response.
5. Stop the app and confirm the process exits cleanly.
