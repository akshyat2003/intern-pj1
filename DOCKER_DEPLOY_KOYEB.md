# Docker + Koyeb Deployment

This deployment runs the frontend and backend in one Docker container.

Public website:

```text
https://YOUR-APP.koyeb.app
```

Inside the container:

```text
Next.js frontend: port 3000
FastAPI backend: port 8000
Browser API calls: /api/*
```

## Local Docker Test

Create a local env file:

```powershell
copy backend\.env.example .env.docker
```

Edit `.env.docker` and set:

```env
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_key
DATABASE_URL=
SQLITE_PATH=data/documents.db
AUTH_SECRET=local-dev-secret-change-me
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ALLOWED_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1)(:\d+)?
```

Build:

```powershell
docker build -t intern-pj1 .
```

Run:

```powershell
docker run --rm -p 3000:3000 --env-file .env.docker intern-pj1
```

Open:

```text
http://localhost:3000
```

Stop Docker:

```powershell
Ctrl + C
```

## Production

Use:

- Koyeb for the Docker app
- Neon or Supabase for Postgres
- Gmail SMTP app password for OTP email

Set these environment variables in Koyeb:

```env
PORT=3000
BACKEND_PORT=8000
NEXT_PUBLIC_API_BASE_URL=/api
API_PROXY_TARGET=http://127.0.0.1:8000
INTERNAL_API_BASE_URL=http://127.0.0.1:8000
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1
DATABASE_URL=your_neon_or_supabase_postgres_url
AUTH_SECRET=make_this_long_and_random
AUTH_TOKEN_MINUTES=10080
OTP_EXPIRY_MINUTES=10
ALLOWED_ORIGINS=https://YOUR-APP.koyeb.app
ALLOWED_ORIGIN_REGEX=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM_EMAIL=your_gmail@gmail.com
```

