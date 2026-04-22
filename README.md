# Finance Tracker

A simple Flask-based finance tracker web app with transaction reporting and monthly export support.

## Deployment Setup

This app is ready for hosting on platforms like Render, Railway, or Heroku.

### Included deployment files

- `requirements.txt` — Python dependencies
- `Procfile` — Gunicorn startup command
- `runtime.txt` — Python runtime version
- `.gitignore` — common ignored files
- `render.yaml` — Render service configuration
- `.env.example` — local environment variable example

## Deploy to Render

1. Create a Git repository locally:
   ```powershell
   cd "c:\Users\Termite\OneDrive\Attachments\Finance  App\Finance Tracker"
   git init
   git add .
   git commit -m "Render deployment setup"
   ```

2. Push to GitHub:
   ```powershell
   git branch -M main
   git remote add origin https://github.com/<your-user>/<your-repo>.git
   git push -u origin main
   ```

3. Go to Render and create a new **Web Service**.
   - Connect your GitHub repository.
   - Select the `main` branch.
   - Render should detect Python and use `render.yaml` automatically.

4. Deploy.

### PostgreSQL support

This app defaults to SQLite locally using `sqlite:///finance.db`.
It also supports PostgreSQL in production.

For local development, copy `.env.example` to `.env` and adjust as needed:

```powershell
copy .env.example .env
```

If you want a production-grade database on Render or Railway, set a `DATABASE_URL` environment variable with your PostgreSQL connection string.

Example:

```text
postgresql://user:password@host:port/database
```

Render and Railway will use `DATABASE_URL` automatically.

On Render, your database URL may start with `postgres://`.
The app automatically converts that into a SQLAlchemy-compatible `postgresql://` URL.

## Deploy to Railway

1. Push this project to GitHub.
2. Create a new Railway project and connect the repo.
3. Railway will detect the Python app and install dependencies from `requirements.txt`.
4. Deploy the service.

## Notes

- `data.json` is stored on local disk. On many platforms, filesystem storage is not permanent across restarts, so consider moving to a database later.
- The app listens via Gunicorn in production, as configured by `Procfile`.

## Local Run

```powershell
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in your browser.
