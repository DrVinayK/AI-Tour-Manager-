# Render Deployment Checklist

## Pre-Deployment (Do This First!)

- [ ] Create Render account at https://render.com
- [ ] Push your code to GitHub
- [ ] Gather all API keys:
  - [ ] GROQ_API_KEY from https://console.groq.com/keys
  - [ ] GOOGLE_API_KEY from https://console.cloud.google.com
  - [ ] GPLACES_API_KEY from https://console.cloud.google.com
  - [ ] FOURSQUARE_API_KEY from https://developer.foursquare.com/
  - [ ] TAVILY_API_KEY from https://tavily.com/
  - [ ] OPENWEATHERMAP_API_KEY from https://openweathermap.org/api
  - [ ] EXCHANGE_RATE_API_KEY from https://exchangerate-api.com/

## Backend Deployment

### Setup
- [ ] Go to: https://dashboard.render.com/new/web-service
- [ ] Authorize GitHub connection
- [ ] Select your repository

### Configuration
- [ ] Name: `ai-trip-planner-backend`
- [ ] Environment: `Python 3`
- [ ] Build Command: `pip install --no-cache-dir -r requirements.txt`
- [ ] Start Command: `uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT`

### Advanced Settings
- [ ] Click: Advanced
- [ ] Python Version: `3.11`
- [ ] Region: Select your preferred region

### Environment Variables (Add each one)
- [ ] GROQ_API_KEY = (your key)
- [ ] GOOGLE_API_KEY = (your key)
- [ ] GPLACES_API_KEY = (your key)
- [ ] FOURSQUARE_API_KEY = (your key)
- [ ] TAVILY_API_KEY = (your key)
- [ ] OPENWEATHERMAP_API_KEY = (your key)
- [ ] EXCHANGE_RATE_API_KEY = (your key)

### Deployment
- [ ] Select Plan: Free or Starter
- [ ] Click: Create Web Service
- [ ] Wait: 3-5 minutes for deployment
- [ ] Check: Logs for any errors
- [ ] Copy: Backend URL (e.g., https://ai-trip-planner-backend.onrender.com)
- [ ] Note: Paste this URL somewhere safe - you'll need it!

### Test Backend
- [ ] Visit: https://your-backend-url.onrender.com/docs
- [ ] Verify: FastAPI Swagger UI is visible
- [ ] Status: Backend is running ✅

## Frontend Deployment

### Setup
- [ ] Go to: https://dashboard.render.com/new/web-service
- [ ] Select: Your repository again (same repo)

### Configuration
- [ ] Name: `ai-trip-planner-frontend`
- [ ] Environment: `Python 3`
- [ ] Build Command: `pip install --no-cache-dir -r requirements.txt`
- [ ] Start Command: `gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app`

### Advanced Settings
- [ ] Click: Advanced
- [ ] Python Version: `3.11`
- [ ] Region: Same as backend (important!)

### Environment Variables (Add each one)
- [ ] FASTAPI_BASE_URL = https://ai-trip-planner-backend.onrender.com
- [ ] FLASK_SECRET_KEY = (generate: python -c "import secrets; print(secrets.token_hex(32))")
- [ ] FLASK_DEBUG = false
- [ ] RESET_PLANS_ON_START = true
- [ ] GROQ_API_KEY = (same as backend)
- [ ] GOOGLE_API_KEY = (same as backend)
- [ ] GPLACES_API_KEY = (same as backend)
- [ ] FOURSQUARE_API_KEY = (same as backend)
- [ ] TAVILY_API_KEY = (same as backend)
- [ ] OPENWEATHERMAP_API_KEY = (same as backend)
- [ ] EXCHANGE_RATE_API_KEY = (same as backend)

### Deployment
- [ ] Select Plan: Free or Starter
- [ ] Click: Create Web Service
- [ ] Wait: 3-5 minutes for deployment
- [ ] Check: Logs for any errors
- [ ] Copy: Frontend URL (e.g., https://ai-trip-planner-frontend.onrender.com)

### Test Frontend
- [ ] Visit: https://your-frontend-url.onrender.com
- [ ] Verify: Homepage loads without errors
- [ ] Status: Frontend is running ✅

## Post-Deployment Testing

### Backend Verification
- [ ] Visit: https://your-backend-url.onrender.com/docs
- [ ] See: FastAPI Swagger UI
- [ ] Result: ✅ Backend working

### Frontend Verification
- [ ] Visit: https://your-frontend-url.onrender.com
- [ ] See: Trip planner homepage
- [ ] Result: ✅ Frontend working

### End-to-End Testing
- [ ] Fill in: Departure city (e.g., "New York")
- [ ] Fill in: Destination city (e.g., "Paris")
- [ ] Select: Travel dates
- [ ] Click: Generate Plan
- [ ] Verify: Itinerary appears without errors
- [ ] Result: ✅ Full functionality working

## Success Criteria

- [ ] Backend deployed and responding
- [ ] Frontend deployed and responding
- [ ] Frontend can communicate with backend
- [ ] Can create trip plans end-to-end
- [ ] No errors in either service logs
- [ ] Static files (CSS/JS) load correctly

## If Something Goes Wrong

- [ ] Check: Render Dashboard → Logs tab
- [ ] Check: Environment variables are all set
- [ ] Check: Backend URL in frontend is correct
- [ ] Wait: 30-60 seconds for cold start
- [ ] Retry: Reload the page
- [ ] Reference: GUIDES/RENDER_CHECKLIST.md → Troubleshooting

## After Successful Deployment

- [ ] Share: Frontend URL with friends/family
- [ ] Monitor: Check Render logs occasionally
- [ ] Celebrate: Your app is live! 🎉

## Optional Next Steps

- [ ] Upgrade from Free to Starter plan (for production)
- [ ] Add PostgreSQL database for data persistence
- [ ] Set up custom domain
- [ ] Configure monitoring/alerts
- [ ] Optimize performance (read RENDER_BEST_PRACTICES.md)

---

**Timeline**: 30-40 minutes
**Difficulty**: Easy 🟢
**Cost**: $0 (free tier) or $14/month (Starter)
**Result**: Your app is LIVE! 🚀
