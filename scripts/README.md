# Scripts

Run from **repo root**.

## Build wheel (with latest console)

```bash
bash scripts/wheel_build.sh
```

- Builds the console frontend (`console/`), copies `console/dist` to `src/qwenpaw/console/dist`, then builds the wheel. Output: `dist/*.whl`.

## Build website

```bash
bash scripts/website_build.sh
```

- Installs dependencies (pnpm or npm) and runs the Vite build. Output: `website/dist/`.

## Build Docker image

```bash
bash scripts/docker_build.sh [IMAGE_TAG] [EXTRA_ARGS...]
```

- Default tag: `qwenpaw:latest`. Uses `deploy/Dockerfile` (multi-stage: builds console then Python app).
- Example: `bash scripts/docker_build.sh myreg/qwenpaw:v1 --no-cache`.

## Run Test

```bash
# Run all tests
python scripts/run_tests.py

# Run all unit tests
python scripts/run_tests.py -u

# Run unit tests for a specific module
python scripts/run_tests.py -u providers

# Run integration tests
python scripts/run_tests.py -i

# Run all tests and generate a coverage report
python scripts/run_tests.py -a -c

# Run tests in parallel (requires pytest-xdist)
python scripts/run_tests.py -p

# Show help
python scripts/run_tests.py -h
```

## Reset showcase demo state

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\reset-showcase-demo-state.ps1
```

- Stops processes listening on the default showcase ports `18088`, `8091`, and `8092`.
- Also stops the default `qwenpaw app` web port `8088`.
- Recreates clean working, secret, and backup directories using the same default resolution as QwenPaw itself: `QWENPAW_WORKING_DIR` or `COPAW_WORKING_DIR`, else `~/.copaw`, else `~/.qwenpaw`.
- Clears the default Security Center store file and optionally the directory from `QWENPAW_SECURITY_CENTER_DATA_DIR`.
- Prints the environment variables you should export before restarting the demo services.