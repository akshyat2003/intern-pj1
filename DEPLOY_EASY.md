# Easy Deployment Guide

This project has two deploys:

- Backend: Render
- Frontend: Vercel

You only need to copy secrets into dashboards. The backend settings are already saved in `render.yaml`.

## 1. Push To GitHub

Open PowerShell in the project folder:

```powershell
cd C:\Users\ADMIN\Desktop\intern-pj1
git add .
git commit -m "Add deployment setup"
git branch -M main
git push -u origin main
```

If `git push` says there is no remote, create a new GitHub repository first, then run:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/intern-pj1.git
git push -u origin main
```

## 2. Create Free Postgres Database

Use Neon or Supabase.

Copy the database connection string. It looks like:

```text
postgresql://username:password@host/dbname?sslmode=require
```

You will paste this as `DATABASE_URL` in Render.

## 3. Deploy Backend On Render

1. Go to Render.
2. Click New.
3. Choose Blueprint.
4. Select this GitHub repository.
5. Render should read `render.yaml`.
6. Fill the secret values Render asks for:

```text
GROQ_API_KEY = your real Groq API key
DATABASE_URL = your Neon/Supabase Postgres URL
ALLOWED_ORIGINS = http://localhost:3000
SMTP_HOST = your email SMTP host
SMTP_USERNAME = your email username
SMTP_PASSWORD = your email app password
SMTP_FROM_EMAIL = the email address OTPs come from
```

Deploy it.

If you do not add SMTP settings, signup still works locally because the API returns a dev OTP. For real deployment, add SMTP so users receive OTP by email.

After deploy, open:

```text
https://YOUR-BACKEND.onrender.com/health
```

Expected:

```json
{"status":"ok","chunks":0,"storage":"postgres"}
```

Also try:

```text
https://YOUR-BACKEND.onrender.com/docs
```

## 4. Deploy Frontend On Vercel

1. Go to Vercel.
2. Add New Project.
3. Import this GitHub repository.
4. Set Root Directory to:

```text
frontend
```

5. Add this environment variable:

```text
NEXT_PUBLIC_API_BASE_URL = https://YOUR-BACKEND.onrender.com
```

6. Deploy.

After deploy, Vercel gives you a frontend URL:

```text
https://YOUR-FRONTEND.vercel.app
```

## 5. Final Render Update

Go back to Render environment variables.

Change:

```text
ALLOWED_ORIGINS = https://YOUR-FRONTEND.vercel.app
```

Redeploy the backend.

## 6. Test

Open your Vercel frontend:

```text
https://YOUR-FRONTEND.vercel.app
```

Then:

1. Upload a document.
2. Ask a question.
3. Refresh the page.
4. Ask again.

The uploaded document chunks should stay saved because production uses Postgres.
