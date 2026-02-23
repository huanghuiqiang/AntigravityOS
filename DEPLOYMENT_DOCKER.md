# Antigravity OS - Dockerized Deployment Guide

This guide explains how to deploy and run Antigravity OS using Docker and Docker Compose. This setup containerizes all services, including agents and cron scheduling, for a more consistent and isolated environment.

## Prerequisites

Before you begin, ensure you have the following installed on your system:
*   **Docker Engine**: [Install Docker](https://docs.docker.com/engine/install/)
*   **Docker Compose**: Docker Compose is usually included with Docker Desktop installations. If not, [Install Docker Compose](https://docs.docker.com/compose/install/)

## 1. Configuration

### 1.1. Environment Variables (`.env`)

Antigravity OS uses an `.env` file for configuration, including API keys and paths.
1.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
2.  Edit the newly created `.env` file and fill in your details. At minimum, you will need to provide:
    *   `OPENROUTER_API_KEY`
    *   `TELEGRAM_BOT_TOKEN`
    *   `TELEGRAM_CHAT_ID`
    *   `OBSIDIAN_VAULT_HOST_PATH` (Absolute path to your Obsidian vault on your host machine, e.g., `/Users/youruser/Documents/Obsidian/YourVaultName`)
    *   (可选，若启用飞书桥接) `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_DOC_TOKEN`

### 1.2. Obsidian Vault Path

This is **CRITICAL**. You need to tell Docker Compose where your Obsidian vault is located on your host machine.

1.  Open the `.env` file.
2.  Set the `OBSIDIAN_VAULT_HOST_PATH` variable to the **absolute path** to your Obsidian vault on your host machine.
    *   **Example for macOS/Linux**:
        ```
        OBSIDIAN_VAULT_HOST_PATH=/Users/youruser/Documents/Obsidian/YourVaultName
        ```
    *   **Example for Windows**:
        ```
        OBSIDIAN_VAULT_HOST_PATH=C:\Users\YourUser\Documents\Obsidian\YourVaultName
        ```
    The path `/app/data/obsidian_vault` inside the container should remain unchanged as specified in `docker-compose.yml`, as it's used by the `OBSIDIAN_VAULT` environment variable.

## 2. Build Docker Images

Navigate to the root directory of the Antigravity OS project (where `docker-compose.yml` and `Dockerfile` are located) and build the Docker images:

```bash
docker compose build
```
This command will build the `antigravity-os` base image and the `antigravity-cron` image.

## 3. Running Services

### 3.1. Start the Python Scheduler

The `scheduler` service runs a Python-based scheduler, which will automatically trigger your agents according to their defined schedules.

To start the scheduler in the background:
```bash
docker compose up -d scheduler
```
You can verify it's running:
```bash
docker compose ps scheduler
```

### 3.2. Start Feishu Bridge (Optional)

If you want to expose the local Feishu bridge API in Docker, start the `feishu-bridge` service:

```bash
docker compose up -d feishu-bridge
```

Check the health endpoint:
```bash
curl -sS -X POST http://127.0.0.1:${FEISHU_BRIDGE_PORT:-8001}/health
```

### 3.3. Manual Agent Execution

If you need to run an agent manually (e.g., for testing or `axiom-synthesizer` which is manual), you can use `docker compose run`. This will create a new container, run the command, and then remove the container.

Example for `cognitive-bouncer`:
```bash
docker compose run --rm cognitive-bouncer
```
Example for `axiom-synthesizer`:
```bash
docker compose run --rm axiom-synthesizer
```

## 4. Checking Logs

You can view the real-time logs of the `scheduler` service using:

```bash
docker compose logs -f scheduler
```
Logs for individual agent runs (triggered by the scheduler or manually) will be written to `./data/logs` in your project root on the host machine, thanks to the bind mount. For example, to view logs for `cognitive-bouncer`:
```bash
tail -f ./data/logs/bouncer.log
```
Runtime state files (de-dup cache, cursors, etc.) are persisted in `./data/state`.

## 5. Stopping Services

To stop all running services defined in `docker-compose.yml`:
```bash
docker compose down
```
This will stop and remove the containers and networks created by `docker compose up`. It will **not** remove the `antigravity_logs` volume unless you add the `-v` flag: `docker compose down -v`.

---
