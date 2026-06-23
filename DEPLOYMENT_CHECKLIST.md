# Deployment Checklist

## Files Created/Updated ✅

- [x] `requirements.txt` - Backend Python dependencies
- [x] `render.yaml` - Render deployment config
- [x] `Procfile` - Uvicorn startup configuration
- [x] `.env.production` - Production environment variables (backend)
- [x] `frontend/.env.production` - Production environment variables (frontend)
- [x] `frontend/vercel.json` - Vercel build config
- [x] `.gitignore` - Git ignore rules
- [x] `DEPLOYMENT.md` - Full deployment guide
- [x] Frontend build tested ✅ (no errors)

## Pre-Deployment Steps (Before pushing to GitHub)

- [ ] Update `render.yaml` CORS_ALLOW_ORIGINS with your Vercel domain
- [ ] Update `frontend/.env.production`:
  - [ ] `VITE_API_BASE_URL` → Your Render backend URL
- [ ] Create GitHub repository
- [ ] Initialize git and push code

## Backend Deployment (Render)

- [ ] Create account at render.com
- [ ] Connect GitHub repository
- [ ] Create Web Service with these settings:
  - [ ] Build: `pip install -r requirements.txt && alembic upgrade head`
  - [ ] Start: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] Add environment variables (DATABASE_URL, APP_ENV, LLM_PROVIDER, etc.)
- [ ] Deploy and monitor logs
- [ ] Test health endpoint: `curl https://your-api.onrender.com/health`
- [ ] Copy backend URL for frontend config

## Frontend Deployment (Vercel)

- [ ] Create account at vercel.com
- [ ] Import GitHub repository
- [ ] Verify build command: `npm run build`
- [ ] Verify output directory: `dist`
- [ ] Add environment variables (VITE_API_BASE_URL, VITE_API_BACKEND)
- [ ] Deploy and monitor
- [ ] Copy frontend URL

## Integration & Testing

- [ ] Create first workspace user via frontend register flow
- [ ] Update Render CORS_ALLOW_ORIGINS with Vercel domain
- [ ] Re-deploy backend (redeploy from Render dashboard)
- [ ] Test frontend loads at Vercel URL
- [ ] Test authoring a simulation
- [ ] Test creating and running a participant session
- [ ] Verify allocations submit without errors
- [ ] Check debrief generates correctly

## Post-Deployment

- [ ] Monitor logs for errors
- [ ] Set up Slack/email alerts for deployment failures
- [ ] Document custom domain setup if needed
- [ ] Plan CI/CD pipeline for auto-deployments
