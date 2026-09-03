# JupyterHub Outpost — minimal setup

A minimal example to get a JupyterHub Outpost running locally with a PostgreSQL database.
This is **not** a production setup: secrets live in plain text in `.env` and all ports are exposed on the host.

## Prerequisites

- Docker with Compose v2 (`docker compose`)
- `python3` with the `cryptography` package
- GNU-compatible tools (`uuidgen`, `sed -i`)

## 1. Prepare `.env`

```sh
cp env.sample .env
```

## 2. Fill in the secrets

```sh
SECRET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
USERNAMES="jupyterhub" # placeholder – adapt to your needs
PASSWORDS=$(uuidgen)
POSTGRESPASSWORDS=$(uuidgen)

sed -i \
  -e "s|^OUTPOST_CRYPT_KEY=.*|OUTPOST_CRYPT_KEY=$SECRET_KEY|" \
  -e "s|^usernames=.*|usernames=$USERNAMES|" \
  -e "s|^passwords=.*|passwords=$PASSWORDS|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRESPASSWORDS|" \
  .env
```

## 3. Start

```sh
docker compose up
```

Add `--profile debug` to also start Adminer (database web UI) on http://localhost:8081.

## 4. Test

Health check:

```sh
curl http://localhost:8099/ping
```

should answer `{"ping": "pong!"}`

Auth check (reads the values from `.env`, so it works in any new shell):

```sh
usernames=$(grep '^usernames=' .env | cut -d= -f2-)
passwords=$(grep '^passwords=' .env | cut -d= -f2-)
AUTH_TOKEN=$(printf '%s:%s' "$usernames" "$passwords" | base64 | tr -d '\n')
curl -H "Authorization: Basic $AUTH_TOKEN" http://localhost:8099/services/
```

should answer `[]` (no running services — not a `403 Not authenticated`).

## 5. Register with the hub

Tell the JupyterHub admin the `usernames` and `passwords` values from your `.env`,
otherwise your Outpost will block all requests.

## Stop

```sh
docker compose down        # stop, keep the database
docker compose down -v     # stop and delete the database data
```

## Notes

- Port `2222` is SSH into the Outpost container; put the keys you get from the central hub admin into `outpost/authorized_keys/authorized_keys`.
- The database persists in the `hub-db_data` Docker volume.
