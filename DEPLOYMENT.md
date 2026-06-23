# Deployment Guide

This document provides step-by-step instructions for deploying the Allocation Room platform to Render (backend) and Vercel (frontend).

## Prerequisites

- GitHub account (push your code there)
- Render account (render.com)
- Vercel account (vercel.com)
- PostgreSQL database URL (already created on Render)

---

## Phase 1: Prepare for Deployment

### 1.1 Initialize Git and Push to GitHub

```bash
cd /Users/ashunegi/Desktop/Konverz/AI\ Simulation\ Maker/allocation-room

# Initialize git
git init
git add .
git commit -m "Initial commit: Allocation Room platform"

# Create a new GitHub repo and push
# 1. Go to github.com/new
# 2. Create repo "allocation-room"
# 3. Copy the commands GitHub shows and run them:
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/allocation-room.git
git push -u origin main
```

### 1.2 Update Configuration

Replace placeholders in these files with your actual URLs:

- **render.yaml**: Update `CORS_ALLOW_ORIGINS` with your Vercel domain (will be `your-project.vercel.app`)
- **frontend/.env.production**: Update `VITE_API_BASE_URL` after backend deployment

---

## Phase 2: Deploy Backend to Render

### 2.1 Connect Your GitHub Repository

1. Go to **render.com** and sign in
2. Click **"New +"** → **"Web Service"**
3. Select **"Deploy existing GitHub repo"**
4. Find and select **"allocation-room"** repo
5. Fill in these settings:
   - **Name**: `allocation-room-api`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt && alembic upgrade head`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 2.2 Add Environment Variables in Render

In the Render dashboard, click **"Environment"** and add:

```
DATABASE_URL=postgresql+asyncpg://allocation_room_db_user:YOUR_PASSWORD@dpg-xxxxx-a/allocation_room_db
APP_ENV=production
LLM_PROVIDER=openai
CORS_ALLOW_ORIGINS=https://your-vercel-domain.vercel.app,http://localhost:3000
MAX_CONCURRENCY=12
MAX_REVISIONS=2
RATE_LIMIT_PER_MINUTE=120
```

### 2.3 Deploy

Click **"Create Web Service"**. Render will:
1. Clone your repo
2. Install dependencies from `requirements.txt`
3. Run database migrations with `alembic upgrade head`
4. Start the backend server

Monitor the logs. Once deployment succeeds, you'll get a URL like:
```
https://allocation-room-api.onrender.com
```

### 2.4 Test Backend

```bash
curl https://allocation-room-api.onrender.com/health
# Should return: {"status": "ok", "provider": "openai"}
```

---

## Phase 3: Deploy Frontend to Vercel

### 3.1 Connect to Vercel

1. Go to **vercel.com** and sign in
2. Click **"Add New..."** → **"Project"**
3. Import your GitHub repo `allocation-room`
4. Select **"root"** as the root directory (or navigate to `frontend/` if Vercel doesn't detect it automatically)

### 3.2 Configure Build Settings

Vercel should auto-detect these from `package.json`:
- **Build Command**: `npm run build`
- **Output Directory**: `dist`

If not, set them manually.

### 3.3 Add Environment Variables

In the Vercel dashboard, go to **"Settings"** → **"Environment Variables"** and add:

```
VITE_API_BASE_URL=https://allocation-room-api.onrender.com
VITE_API_BACKEND=https://allocation-room-api.onrender.com
```

### 3.4 Deploy

Click **"Deploy"**. Vercel will build and deploy your frontend. You'll get a URL like:
```
https://allocation-room.vercel.app
```

---

## Phase 4: Integration & Testing

### 4.1 Create First Workspace User

The auth flow creates a tenant automatically on registration:

1. Open your Vercel frontend URL
2. Click **Create workspace**
3. Register with email/password
4. Use that same account to author simulations

### 4.2 Update CORS in Backend

In Render dashboard, update `CORS_ALLOW_ORIGINS` to include your Vercel domain:
```
https://your-vercel-domain.vercel.app,http://localhost:3000
```

### 4.3 Test End-to-End

1. Go to `https://your-vercel-domain.vercel.app`
2. Author a new simulation
3. Create and generate
4. Run a participant session
5. Submit allocations
6. View the debrief

All requests should succeed without CORS errors.

---

## Troubleshooting

### Backend Won't Start

Check Render logs:
- Database connection error → verify `DATABASE_URL` is correct
- Import error → check `requirements.txt` includes all dependencies
- Migration failed → check database is accessible

### Frontend Shows Errors

Check browser console:
- CORS error → backend's `CORS_ALLOW_ORIGINS` doesn't include your Vercel domain
- API 404 → `VITE_API_BASE_URL` points to wrong backend URL
- 401/403 → sign in again, or verify frontend points to the correct backend

### Migrations Didn't Run

In Render, click **"Shell"** and run:
```bash
alembic upgrade head
```

---

## Environment Variables Reference

### Backend (.env.production or Render dashboard)

| Variable | Example | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Postgres connection string |
| `APP_ENV` | `production` | Enable rate limiting & worker |
| `LLM_PROVIDER` | `openai` or `mock` | Which LLM backend to use |
| `CORS_ALLOW_ORIGINS` | `https://domain.vercel.app,http://localhost:3000` | Allowed browser origins |
| `MAX_CONCURRENCY` | `12` | LLM call parallelism |

### Frontend (Vercel environment variables)

| Variable | Example | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `https://api.onrender.com` | Frontend's API endpoint |
| `VITE_API_BACKEND` | `https://api.onrender.com` | Dev proxy target |

---

## Next Steps

- Monitor production logs regularly
- Set up error tracking (e.g., Sentry)
- Configure email notifications for deployment failures
- Implement CI/CD for automatic deployments on git push
