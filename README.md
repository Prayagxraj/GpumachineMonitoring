# Paperspace Machine Manager

This Streamlit app tracks shared Paperspace machine usage with a PostgreSQL backend so your team can share one live state.

## Files

- `machine.py` — main Streamlit application
- `requirements.txt` — Python dependencies

## Setup

1. Create a PostgreSQL database.
   - Use a managed service (Supabase, Heroku, AWS RDS, Azure Database, GCP Cloud SQL), or a company-hosted Postgres instance.

2. Add database credentials to Streamlit secrets.

Example `secrets.toml`:

```toml
[postgres]
host = "your-db-host"
port = 5432
dbname = "your_db_name"
user = "your_db_user"
password = "your_secret_password"
```

You can copy the example file into place:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
streamlit run machine.py
```

## How it works

- The app creates a `machine_events` table if needed.
- `Check Out` inserts an `In Use` event.
- `Check In` inserts an `Available` event.
- The current status is derived from the most recent event.
- The last 10 usage records are displayed in the app.

## Deployment

### Option 1: Streamlit Cloud

1. Push this repository to GitHub.
2. Create a Streamlit Cloud app from the repository.
3. Add your secrets in the Streamlit Cloud app dashboard under `Secrets`.

Use the same structure as the local `secrets.toml` example:

```toml
[postgres]
host = "your-db-host"
port = 5432
dbname = "your_db_name"
user = "your_db_user"
password = "your_secret_password"
```

### Option 2: Docker

Build the Docker image:

```bash
docker build -t paperspace-machine-manager .
```

Run the container and pass your database credentials as environment variables:

```bash
docker run -p 8501:8501 \
  -e STREAMLIT_SECRETS='{"postgres": {"host": "your-db-host", "port": 5432, "dbname": "your_db_name", "user": "your_db_user", "password": "your_secret_password"}}' \
  paperspace-machine-manager
```

> Note: Docker does not automatically read `secrets.toml`. Use the Streamlit secrets mechanism or mount a secret file if you need persistent secrets.

### Notes

- This is a shared, persistent system suitable for company usage.
- Use a proper PostgreSQL instance for stability and multi-user access.
