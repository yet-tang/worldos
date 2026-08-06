# Docker and GHCR deployment

WorldOS publishes a production image to GitHub Container Registry (GHCR):

```text
ghcr.io/yet-tang/worldos
```

The image contains the WorldOS CLI, Inspector, initialization, one-shot world execution, and online SQLite backup commands. The VPS does not need Python or a source checkout.

## Published tags

- `latest`: current `main` build
- `sha-<short-sha>`: immutable commit build
- `vX.Y.Z`, `X.Y.Z`, `X.Y`: release tag builds

Production deployments should pin an explicit version or digest rather than relying only on `latest`.

## Host preparation

Install Docker Engine and the Docker Compose plugin. Create the deployment directories:

```bash
sudo install -d -m 0750 /opt/worldos/{data,backups,secrets}
sudo chown -R "$USER":"$USER" /opt/worldos
cd /opt/worldos
```

Download `compose.yaml`, `docker/nginx.conf`, and `.env.example` from the matching release or repository revision. Copy `.env.example` to `.env`.

Generate Basic Auth credentials:

```bash
sudo apt-get install -y apache2-utils
htpasswd -c ./secrets/htpasswd worldos
chmod 0600 ./secrets/htpasswd
```

Set `WORLDOS_UID` and `WORLDOS_GID` in `.env` to the owner of the data directories:

```bash
id -u
id -g
```

## Existing SQLite database migration

Stop the legacy process before mounting its database into Docker. Never allow two writers to use the same SQLite database.

Create an online backup while the legacy process is still healthy, then stop it. Copy the validated database to:

```text
/opt/worldos/data/world.db
```

Verify ownership and integrity:

```bash
chown "$(id -u):$(id -g)" ./data/world.db
sqlite3 ./data/world.db 'PRAGMA integrity_check;'
```

The result must be `ok`.

## First deployment

The GHCR package may initially be private. For a private package, log in with a token that has only `read:packages`:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u yet-tang --password-stdin
```

For an existing database:

```bash
docker compose pull
docker compose up -d inspector proxy
docker compose ps
curl --fail http://127.0.0.1:8080/healthz
```

For a new world:

```bash
docker compose --profile admin run --rm init
docker compose up -d inspector proxy
```

The default bind is `127.0.0.1:8080`; expose it through the host's authenticated TLS reverse proxy. Do not publish the Inspector container port directly.

## Run ticks

World execution is an explicit one-shot operation. There is no fabricated shell loop or hidden second writer:

```bash
WORLDOS_RUN_TICKS=100 docker compose --profile admin run --rm run
```

Only run one world-writing command at a time.

## Backup

Create an online SQLite backup through the image:

```bash
docker compose --profile admin run --rm backup
```

The backup is written to `WORLDOS_BACKUP_DIR` and checked with `PRAGMA integrity_check` before success is reported.

## Upgrade

```bash
cd /opt/worldos
docker compose --profile admin run --rm backup
docker compose pull
docker compose up -d inspector proxy
docker compose ps
curl --fail http://127.0.0.1:8080/healthz
```

After upgrade, compare the current tick, event count, timeline, database integrity, and canonical world hash with the pre-upgrade report.

## Rollback

Pin the previous image in `.env`:

```text
WORLDOS_IMAGE=ghcr.io/yet-tang/worldos:sha-<known-good-sha>
```

Then run:

```bash
docker compose pull
docker compose up -d inspector proxy
```

Restore the pre-upgrade database backup only when a data migration or integrity problem requires it.

## Image publication

`.github/workflows/container.yml` builds and smoke-tests the image on pull requests. On `main`, version tags, or manual dispatch, it publishes multi-platform `linux/amd64` and `linux/arm64` images to GHCR and generates a build-provenance attestation.

The repository workflow requires:

```yaml
permissions:
  contents: read
  packages: write
  attestations: write
  id-token: write
```

No VPS deployment credential is stored in GitHub because the VPS pulls the published image itself.
