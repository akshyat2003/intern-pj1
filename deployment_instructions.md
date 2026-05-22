# Deployment Guide: Vercel & Render

This guide walks you through deploying your full-stack RAG Chatbot:
1. **Backend (FastAPI)**: Deployed to **Render** and connected to your **Neon DB (Postgres)**.
2. **Frontend (Next.js)**: Deployed to **Vercel** and configured to communicate with the Render backend.

---

## Step 1: Push Your Code to GitHub

Both Vercel and Render deploy directly from a GitHub repository. If you haven't pushed your code to GitHub yet, run these commands in your project root:

```bash
git init
git add .
git commit -m "Prepare for deployment"
# Create a new repository on github.com, then run:
git remote add origin https://github.com/your-username/your-repo-name.git
git branch -M main
git push -u origin main
```

---

## Step 2: Deploy Backend to Render

1. Go to **[Render.com](https://render.com/)** and log in.
2. Click **New** (top right) and select **Web Service**.
3. Connect your GitHub repository.
4. Configure the Web Service settings:
   - **Name**: `rag-chatbot-backend`
   - **Region**: Choose the region closest to your users.
   - **Branch**: `main`
   - **Root Directory**: `backend` *(This is important because requirements.txt and app/ are inside the backend/ folder)*
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`

5. Under the **Environment Variables** section, click **Add Environment Variable** to add the following variables:

   | Key | Value | Description |
   |---|---|---|
   | `DATABASE_URL` | `postgresql://...` | Your **Neon DB connection string** |
   | `AI_PROVIDER` | `groq` *(or `nvidia`)* | AI Provider to use |
   | `GROQ_API_KEY` | `gsk_...` | Your Groq API key (if using Groq) |
   | `NVIDIA_API_KEY` | `nvapi-...` | Your Nvidia API key (if using Nvidia) |
   | `AUTH_SECRET` | *(Create a random secure string)* | A secure random string (e.g., run `openssl rand -hex 32` or just type a long random password) to sign authentication tokens |
   | `SMTP_HOST` | *(Your SMTP host)* | SMTP host for emails (e.g. `smtp.gmail.com` or `smtp.sendgrid.net`) |
   | `SMTP_PORT` | `587` | Standard SMTP TLS port |
   | `SMTP_USERNAME` | *(Your SMTP username)* | Username / email address used to log in to SMTP |
   | `SMTP_PASSWORD` | *(Your SMTP password)* | Password or App Password for your SMTP service |
   | `SMTP_FROM_EMAIL` | *(Your SMTP email)* | The email address shown in the "From" field |
   | `ALLOWED_ORIGINS` | `http://localhost:3000` | We will add your Vercel URL here in **Step 4** |

6. Click **Deploy Web Service** at the bottom of the page.
7. Wait a few minutes for the build to finish. Once successful, copy your backend URL from the top of the Render dashboard (it looks like `https://rag-chatbot-backend.onrender.com`).

---

## Step 3: Deploy Frontend to Vercel

1. Go to **[Vercel.com](https://vercel.com/)** and log in.
2. Click **Add New** -> **Project**.
3. Import your GitHub repository.
4. Configure the Vercel project settings:
   - **Framework Preset**: `Next.js` (automatically detected)
   - **Root Directory**: Click **Edit** and select the `frontend` folder *(Very important since the Next.js code resides there)*
   - **Build and Output Settings**: Leave at their defaults.

5. Open the **Environment Variables** section and add:

   | Key | Value | Description |
   |---|---|---|
   | `API_PROXY_TARGET` | `https://your-backend.onrender.com` | The backend URL you copied from Render (e.g. `https://rag-chatbot-backend.onrender.com`) |
   | `INTERNAL_API_BASE_URL` | `https://your-backend.onrender.com` | The same backend URL, used during server-side pre-rendering check |

6. Click **Deploy**.
7. Once deployed, Vercel will provide your live URL (e.g., `https://rag-chatbot-frontend.vercel.app`). Copy this URL.

---

## Step 4: Configure CORS on the Backend

Since the frontend runs on Vercel and the backend runs on Render, the backend must accept requests originating from your Vercel site:

1. Go back to your **Render Dashboard** and open your backend Web Service.
2. Go to the **Environment** tab.
3. Edit the `ALLOWED_ORIGINS` variable. Update it to include your Vercel URL separated by a comma (do not add trailing slashes):
   `http://localhost:3000,https://your-frontend-app.vercel.app`
4. Click **Save Changes**.
5. Render will automatically redeploy the service with the new settings.

---

## Step 5: Test and Verify

1. Open your Vercel frontend URL in your browser.
2. In the top right corner, check if the status pill shows "**0 chunks indexed**" (or another number) instead of "Backend unavailable". This confirms the frontend is successfully talking to the backend.
3. Try creating a new account (Sign Up). The backend will send a verification code to the email address using your SMTP credentials.
4. Check your email, enter the OTP to verify, and sign in.
5. Upload a document (e.g., PDF or text) to index it, and try asking a question to ensure that the Neon DB reads/writes and AI providers are operating as expected!
