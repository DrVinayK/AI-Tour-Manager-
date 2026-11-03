# Render Deployment Checklist

## Pre-Deployment Setup

- [ ] **Create a Render Account** at https://render.com
- [ ] **Push code to GitHub** (Render deploys from git repositories)
  ```bash
  git add .
  git commit -m "Prepare for Render deployment"
  git push origin main
  ```

## Backend Deployment

- [ ] **Verify Backend Entry Point**
  - Confirm `Backend_main_new.py` exports a FastAPI `app` object
  - Quick test: Run `uvicorn Backend_main_new:app --reload` locally

- [ ] **Go to Render Dashboard** → https://dashboard.render.com
  
- [ ] **Create Web Service (Backend)**
  1. Click **New +** → **Web Service**
  2. Select **Deploy an existing Git repository**
  3. Authorize GitHub and select your repository
  4. Configure:
     - **Name**: `ai-trip-planner-backend`
     - **Region**: Select closest to your users
     - **Branch**: `main`
     - **Build Command**: `pip install --no-cache-dir -r requirements.txt`
     - **Start Command**: `uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT`
  5. Select **Plan**: Free tier or Starter (if you need more power)
  6. Click **Advanced** and set Python version to 3.11
  7. Add Environment Variables (click **Add Environment Variable**):
     - `GROQ_API_KEY`: Your API key
     - `GOOGLE_API_KEY`: Your API key
     - `GPLACES_API_KEY`: Your API key
     - `FOURSQUARE_API_KEY`: Your API key
     - `TAVILY_API_KEY`: Your API key
     - `OPENWEATHERMAP_API_KEY`: Your API key
     - `EXCHANGE_RATE_API_KEY`: Your API key
  8. Click **Create Web Service**

- [ ] **Wait for Deployment** (3-5 minutes)
  - Check Logs tab for any errors
  - Once deployed, note your backend URL (e.g., `https://ai-trip-planner-backend.onrender.com`)

- [ ] **Test Backend**
  - Visit: `https://your-backend-url.onrender.com/docs` (FastAPI OpenAPI docs)
  - Or call an endpoint to verify it's running

## Frontend Deployment

- [ ] **Update `.env` File**
  ```env
  FASTAPI_BASE_URL=https://ai-trip-planner-backend.onrender.com
  FLASK_SECRET_KEY=<your-secret-key>
  FLASK_DEBUG=false
  RESET_PLANS_ON_START=true
  GROQ_API_KEY=your_key
  GOOGLE_API_KEY=your_key
  GPLACES_API_KEY=your_key
  FOURSQUARE_API_KEY=your_key
  TAVILY_API_KEY=your_key
  OPENWEATHERMAP_API_KEY=your_key
  EXCHANGE_RATE_API_KEY=your_key
  ```

- [ ] **Verify Frontend Dependencies**
  - Confirm `gunicorn>=21.0.0` is in `requirements.txt`
  - If not present, add: `echo "gunicorn>=21.0.0" >> requirements.txt`

- [ ] **Create Web Service (Frontend)**
  1. Go to Render Dashboard → **New +** → **Web Service**
  2. Select your repository again
  3. Configure:
     - **Name**: `ai-trip-planner-frontend`
     - **Region**: Same as backend (important!)
     - **Branch**: `main`
     - **Build Command**: `pip install --no-cache-dir -r requirements.txt`
     - **Start Command**: `gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app`
  4. Set Python version to 3.11
  5. Add Environment Variables (same as `.env`):
     - `FASTAPI_BASE_URL`: Your backend URL
     - All API keys
  6. Click **Create Web Service**

- [ ] **Wait for Frontend Deployment** (3-5 minutes)
  - Check Logs for any errors
  - Note your frontend URL (e.g., `https://ai-trip-planner-frontend.onrender.com`)

## Post-Deployment Testing

- [ ] **Test Backend Health**
  ```bash
  curl https://your-backend-url.onrender.com/health
  ```

- [ ] **Visit Frontend**
  - Open: `https://your-frontend-url.onrender.com`
  - Test creating a trip plan
  - Verify that it connects to the backend successfully

- [ ] **Check Logs**
  - Backend Logs: Look for any errors related to missing API keys
  - Frontend Logs: Ensure FASTAPI_BASE_URL is correctly set

## Troubleshooting

### Backend won't start
- [ ] Check logs for error messages
- [ ] Verify `Backend_main_new.py` has a FastAPI `app` object
- [ ] Ensure all API keys are set as environment variables

### Frontend shows "Backend failed..."
- [ ] Verify `FASTAPI_BASE_URL` is correctly set in frontend environment variables
- [ ] Check that backend service is running (visit `/docs` endpoint)
- [ ] Ensure CORS is configured in backend to allow requests from frontend

### "Module not found" errors
- [ ] Verify all packages are in `requirements.txt`
- [ ] Check Python version compatibility (3.11 recommended)

### Slow performance
- [ ] Free tier services may cold-start (takes 30-60 seconds)
- [ ] Consider upgrading to Starter or Standard plan for production

### Static files returning 404
- [ ] Ensure `static/` folder is committed to git
- [ ] Check that Flask is configured to serve static files correctly

## Notes

- **Cold Starts**: Free tier services spin down after 15 minutes of inactivity. First request takes 30-60s.
- **Database**: SQLite (`plans.db`) is not persistent. For production, consider PostgreSQL.
- **Secrets**: Never commit API keys to git. Use Render's environment variable system.
- **Logs**: Check **Logs** tab in Render dashboard for debugging.

---

## Quick Links

- [Render Dashboard](https://dashboard.render.com)
- [Render Docs](https://render.com/docs)
- [Your Services](https://dashboard.render.com/services)

---

**Once everything is verified, your AI Trip Planner is live! 🚀**
