# Strmline

Strmline builds and maintains a structured `.strm` media library from a TorBox account. It provides a local web application for setup, synchronization, searching, metadata maintenance, and optional season completion. The generated library can be scanned by compatible media servers such as Jellyfin and Plex.

## Features

- Synchronizes TorBox media into movie, show, and anime library folders.
- Generates `.strm` files without storing final tokenized TorBox URLs by default.
- Uses TMDB metadata and artwork when configured.
- Detects duplicate media through external identifiers rather than only filenames.
- Supports manual and scheduled account synchronization.
- Offers optional season auto-completion with cached-source preference and rate limiting.
- Stores artwork alongside the library at `artwork/`.
- Provides error-log retention and an in-container password reset command.

## Requirements

- Docker Engine with Docker Compose v2.
- A TorBox account and API key.
- A writable host directory for the generated library.
- A TMDB API key is optional but recommended for metadata, artwork, and reliable media matching.
- An AIOStreams base URL is optional and only needed for season auto-completion.

## Quick Start

1. Clone the repository and enter it.

   ```sh
   git clone https://github.com/<owner>/Strmline.git
   cd Strmline
   ```

2. Create a directory for the generated media library.

   ```sh
   mkdir -p /mnt/strmline-library
   ```

3. Edit `docker-compose.yml` before starting the stack.

   - Replace both `CHANGE_ME` values with long, unique secrets.
   - Change `/mnt/strmline-library` if the library should live elsewhere.
   - Adjust the host port `45733` if it conflicts with another service.

   Generate a secret with:

   ```sh
   openssl rand -hex 32
   ```

4. Pull and start Strmline.

   ```sh
   docker compose pull
   docker compose up -d
   ```

5. Open `http://localhost:45733/setup` and complete the initial setup.

The setup page creates the first user and records the TorBox credentials. Configure a TMDB API key there to enable metadata and posters. The application applies database migrations automatically during startup.

## Docker Compose Configurations

The repository provides a deployment compose file and a source-build development example:

| File | Use case | Application image |
| --- | --- | --- |
| `docker-compose.yml` | Portainer or server deployment | `nepherius/strmline:latest` from Docker Hub |
| `examples/docker-compose.development.yml` | Local source development and testing | Built from the local checkout |

Both examples require the following changes before first use:

- Replace the application secret and PostgreSQL password placeholders.
- Change `/mnt/strmline-library` to the desired host library directory.
- Change `user: "1000:1000"` when the service should write files as a different host user and group.
- Change `45733` when the host port is already in use.

Generate the two secret values with `openssl rand -hex 32` and keep them stable. Changing either value after PostgreSQL has initialized or after provider keys have been saved can make existing data inaccessible.

### Docker Hub and Portainer

The root `docker-compose.yml` is the Docker Hub deployment configuration. For Portainer, create a stack from that file, replace both secret placeholders, adjust the library mount, and deploy it.

It does not contain `build:`, so Portainer pulls `nepherius/strmline:latest` rather than building from a source checkout. To update an existing deployment manually:

```sh
docker compose pull
docker compose up -d
```

### Development

Run the source-build configuration from the repository root:

```sh
docker compose -f examples/docker-compose.development.yml up -d --build
```

The development file has `build.context: ..` because it is stored under `examples/`; this resolves to the repository root and uses the local `Dockerfile`. It uses the same Compose project name as deployment, so stop the deployment stack before starting the development stack.

The development configuration enables debug logging and exposes `/docs`, `/redoc`, and `/openapi.json`. These endpoints are disabled in the Docker Hub deployment configuration. Do not enable debug logging for routine production operation.

For repeatable server releases, replace the `latest` image tag in `docker-compose.yml` with a published version tag before deployment.

## Library Layout

The host library directory is mounted at `/library` inside the application container. Strmline manages the following top-level folders:

```text
library/
├── artwork/
├── movies/
├── shows/
└── anime/
```

Do not manually modify generated `.strm` files while a sync is running. Use the library interface to refresh metadata or remove generated entries.

## Playback Modes

Strmline defaults to resolver playback. Generated `.strm` files point to a Strmline resolver URL, which keeps final tokenized TorBox media URLs out of the files.

Direct playback is available as an explicit setup option. It can be useful for clients that cannot reach the resolver, but it writes the final media URL into the `.strm` file. Treat those files as sensitive.

## Configuration

Most operational settings are available after login in the setup interface. Docker and database settings are configured in `docker-compose.yml` or through `STRMLINE_` environment variables.

| Setting | Purpose |
| --- | --- |
| `STRMLINE_APP_SECRET_KEY` | Required secret used to protect application state. Keep it stable after deployment. |
| `STRMLINE_DATABASE_URL` | Full PostgreSQL connection URL. The compose configuration constructs this from the PostgreSQL settings by default. |
| `STRMLINE_LIBRARY_ROOT` | Container path where the generated library is written. Defaults to `/library`. |
| `STRMLINE_BASE_URL` | Public Strmline URL used when resolver playback is selected. |
| `STRMLINE_SECURE_COOKIES` | Enable for HTTPS deployments. |
| `STRMLINE_DEBUG` | Enables detailed application logging. Avoid using it routinely in production. |

The setup interface also manages TorBox, TMDB, resolver, synchronization, category, and season auto-completion settings.

## Routine Operations

Pull and start the Docker Hub deployment:

```sh
docker compose pull
docker compose up -d
```

Follow application logs:

```sh
docker compose logs -f strmline
```

Stop the stack:

```sh
docker compose down
```

Update a source checkout while retaining the existing database and library:

```sh
git pull
docker compose -f examples/docker-compose.development.yml up -d --build
```

Keep the application secret and PostgreSQL password unchanged when updating an existing installation.

### Reset an Administrator Password

Run the administrative utility from the application container:

```sh
docker compose exec strmline python -m app.admin_cli reset-password
```

It prompts for a new password and prints the username that was reset. The command does not expose existing passwords or secrets.

## Season Auto-Completion

Season auto-completion is disabled by default. When enabled, Strmline checks shows already in the library, identifies released missing episodes, and searches configured AIOStreams sources.

The default behavior selects cached sources only. It can be configured to include uncached sources, but this may create downloads. The scheduler runs an initial check after enabling the setting, then runs at the configured day interval. Use the shows-per-minute setting to limit provider traffic and download activity on large libraries.

## Development

The project has a FastAPI backend in `api/` and a SvelteKit frontend in `web/`.

Install backend dependencies in a virtual environment and run the backend checks:

```sh
cd api
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest tests
.venv/bin/ruff check app tests
.venv/bin/pyright app
```

Install frontend dependencies and run its checks:

```sh
cd web
npm ci
npm run check
npm run lint
npm run test
```

Run the repository file-length check from the repository root:

```sh
python3 scripts/check_file_lengths.py
```
