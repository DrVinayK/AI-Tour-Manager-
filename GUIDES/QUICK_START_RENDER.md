# Quick Start: Deploy to Render in 5 Steps

## Step 1: Prepare Your GitHub Repository

```bash
# Make sure you're in your project directory
cd "E:\Acclivis\VS Code\AI_Trip_Planner_Multiagent\AI_Trip_Planner_Portable"

# Initialize git if not already done
git init
git add .
git commit -m "Initial commit - ready for Render deployment"

# Push to GitHub (replace 'origin' and 'main' if your remote/branch is different)
git push -u origin main
```

**Note**: If you don't have a GitHub repo yet:
1. Go to https://github.com/new
2. Create a new repository (e.g., `ai-trip-planner`)
3. Follow the instructions to push your local code

---

## Step 2: Deploy the FastAPI Backend

1. **Go to**: https://dashboard.render.com/new/web-service
2. **Authorize GitHub** if prompted
3. **Select your repository**: `ai-trip-planner` (or your repo name)
4. **Fill in these fields**:
   - **Name**: `ai-trip-planner-backend`
   - **Environment**: Python 3
   - **Build Command**: `pip install --no-cache-dir -r requirements.txt`
   - **Start Command**: `uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT`
5. **Click Advanced** → Set **Python Version** to `3.11`
6. **Add Environment Variables** (click "Add Environment Variable" for each):
   ```
   GROQ_API_KEY = (your key from https://console.groq.com)
   GOOGLE_API_KEY = (your key from Google Cloud)
   GPLACES_API_KEY = (your key from Google Cloud)
   FOURSQUARE_API_KEY = (your key)
   TAVILY_API_KEY = (your key)
   OPENWEATHERMAP_API_KEY = (your key)
   EXCHANGE_RATE_API_KEY = (your key)
   ```
7. **Select Plan**: Free (or Starter for better performance)
8. **Click**: "Create Web Service"

⏳ **Wait 3-5 minutes** for deployment. You'll see the logs update.

**When complete**, note your backend URL:
```
https://ai-trip-planner-backend.onrender.com
```

---

## Step 3: Test the Backend

Once the backend is running:

1. Visit: `https://ai-trip-planner-backend.onrender.com/docs`
   - You should see the FastAPI Swagger UI
2. If you get an error or blank page, check the **Logs** tab in Render to see what went wrong

---

## Step 4: Deploy the Flask Frontend

1. **Go to**: https://dashboard.render.com/new/web-service
2. **Select your repository again** (same as Step 2)
3. **Fill in these fields**:
   - **Name**: `ai-trip-planner-frontend`
   - **Environment**: Python 3
   - **Build Command**: `pip install --no-cache-dir -r requirements.txt`
   - **Start Command**: `gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app`
4. **Click Advanced** → Set **Python Version** to `3.11`
5. **Add Environment Variables**:
   ```
   FASTAPI_BASE_URL = https://ai-trip-planner-backend.onrender.com
   FLASK_SECRET_KEY = (run: python -c "import secrets; print(secrets.token_hex(32))")
   FLASK_DEBUG = false
   RESET_PLANS_ON_START = true
   
   (+ all API keys from Step 2)
   GROQ_API_KEY = (your key)
   GOOGLE_API_KEY = (your key)
   GPLACES_API_KEY = (your key)
   FOURSQUARE_API_KEY = (your key)
   TAVILY_API_KEY = (your key)
   OPENWEATHERMAP_API_KEY = (your key)
   EXCHANGE_RATE_API_KEY = (your key)
   ```
6. **Select Plan**: Free or Starter
7. **Click**: "Create Web Service"

⏳ **Wait 3-5 minutes** for deployment.

---

## Step 5: Test Your Application

Once the frontend is deployed:

1. **Visit your frontend**: `https://ai-trip-planner-frontend.onrender.com`
2. **Try creating a trip plan**:
   - Enter a departure city
   - Enter a destination city
   - Select dates
   - Click "Generate Plan"
3. **If it works**: ✅ Congratulations! Your app is live!
4. **If it shows "Backend failed..."**:
   - Check that your `FASTAPI_BASE_URL` is correct in the frontend environment variables
   - Wait a bit and retry (backend might be cold-starting)
   - Check both services' logs in Render dashboard

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend deployment fails | Check logs → likely missing API keys or wrong Python version |
| Frontend won't connect to backend | Verify `FASTAPI_BASE_URL` is exactly correct (copy from Render URL bar) |
| "Cannot import Backend_main_new" | Make sure `Backend_main_new.py` exists and has `app = FastAPI()` |
| Slow first page load | Free tier cold-starts take 30-60 seconds; upgrade to Starter plan for faster response |
| 404 on static files (CSS/JS not loading) | Ensure `static/` folder is committed to GitHub |

---

## Important Configuration Files

These files have been created for you:

- **`render.yaml`** - Render deployment configuration
- **`Dockerfile`** - Docker configuration (optional)
- **`start.sh`** - Startup script (optional)
- **`requirements.txt`** - Updated with gunicorn and python-multipart

---

## Your Deployed URLs

Once both services are running:

- **Frontend**: `https://ai-trip-planner-frontend.onrender.com`
- **Backend**: `https://ai-trip-planner-backend.onrender.com`

Share these URLs with others to let them use your app! 🎉

---

## Next Steps (Optional)

- **Custom Domain**: Add a custom domain in Render settings
- **Database**: Add PostgreSQL for data persistence
- **Monitoring**: Set up alerts for service failures
- **Upgrade Plan**: Move to Standard plan for higher uptime SLA

---

**Need help?** Check the detailed guides:
- [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) - Full deployment guide
- [RENDER_CHECKLIST.md](./RENDER_CHECKLIST.md) - Detailed checklist
- [Render Docs](https://render.com/docs) - Official documentation
