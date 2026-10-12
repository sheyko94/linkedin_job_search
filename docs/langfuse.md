# Local Langfuse infrastructure

This optional stack runs Langfuse web and worker with PostgreSQL, ClickHouse,
Redis, and MinIO. It follows the [official Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
and currently uses Langfuse v4 images. The Python application uses the Langfuse SDK's
LangChain callback handler to trace the outer graph and nested model and tool calls.

Requires Docker with Compose and Python 3.12+ (already required by the project).
Give Docker enough memory for the six services.

## Start

From the repository root:

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs -f langfuse-web langfuse-worker
```

Set infrastructure variables directly in the repository's root `.env`; the root
`.env.example` lists them. PostgreSQL, ClickHouse, and MinIO use `langfuse` as both
username and password. Redis also uses `langfuse` as its password, configured through `REDIS_AUTH`.

`SALT` and `NEXTAUTH_SECRET` are separate Langfuse secrets. `ENCRYPTION_KEY` must be
64 hexadecimal characters. Keep the existing values in `.env` when retaining data.
Compose refuses to start with missing secrets. Changing credentials or the encryption
key after initialization can prevent access to existing data.

Wait for web startup and migrations to finish, then open <http://localhost:3000>.
Sign up, create an organization, and create a project. There is no default account.
Create project API keys in the UI and set them directly in the root `.env`:

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

Run `uv sync`, then `uv run python main.py`. In your project's Observations view, look for
`linkedin-job-search`; its session ID matches the run's output folder and local logs.
The callback captures graph state, model inputs/outputs, and tool calls, so traces
include profile, criteria, and job data. Pending events are flushed on success and
failure. Existing local logs and token reports continue to be written.

Leave both project keys blank to disable tracing. Setting only one is a configuration
error. If you change `LANGFUSE_PORT`, update `LANGFUSE_BASE_URL` to match.

Only the web UI/API (`3000`) and MinIO storage API (`9090`, used by browser media
uploads/downloads) are published, both on `127.0.0.1`. Databases and the worker
are reachable inside the Compose network. Edit `LANGFUSE_PORT` or `MINIO_PORT`
in the root `.env` if either port is occupied; the corresponding URLs
update automatically. This setup is for local use.

## Operate

Run these commands from the repository root:

```bash
# Stop containers, retaining all data in named Docker volumes.
docker compose down

# Start again with the same credentials and volumes.
docker compose up -d

# Inspect dependency health and startup failures.
docker compose ps
docker compose logs --tail=100
```

`docker compose down -v` deletes the stack's stored data. Use it only for an
intentional reset. Container logs rotate at 10 MB with three files per service;
database and object storage volumes still grow as data accumulates.

Images follow the upstream major/minor tags, and MinIO follows the upstream default
image. For upgrades, back up the data and `.env`, review Langfuse's
[upgrade guidance](https://langfuse.com/self-hosting/upgrade), then run
`docker compose pull` and `docker compose up -d`. This local stack does not provide
automated backups or high availability.
