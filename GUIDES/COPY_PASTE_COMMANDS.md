# Copy-Paste Commands for Render Deployment

Use these exact commands to deploy your app. Copy and paste them directly.

---

## 1️⃣ PREPARE YOUR LOCAL REPOSITORY

### Change to your project directory
```bash
cd "E:\Acclivis\VS Code\AI_Trip_Planner_Multiagent\AI_Trip_Planner_Portable"
```

### Initialize Git (if not already done)
```bash
git init
git add .
git commit -m "Initial commit - ready for Render deployment"
```

### Add remote and push to GitHub
```bash
git remote add origin https://github.com/YOUR_USERNAME/ai-trip-planner.git
git branch -M main
git push -u origin main
```

> **Replace `YOUR_USERNAME`** with your actual GitHub username and make sure the repo exists at that URL first!

---

## 2️⃣ CREATE YOUR API KEYS (Do this BEFORE deployment)

### GROQ API Key
```
Go to: https://console.groq.com/keys
Copy your API key
```

### Google API Keys (for Maps & Places)
```
Go to: https://console.cloud.google.com/
Create a new project
Enable: Maps API + Places API
Create an API Key
```

### Other API Keys
```
Foursquare:     https://developer.foursquare.com/
Tavily:         https://tavily.com/
Weather:        https://openweathermap.org/api
Exchange Rate:  https://exchangerate-api.com/
```

---

## 3️⃣ DEPLOY BACKEND ON RENDER

### Step-by-step:

1. **Open**: https://dashboard.render.com/new/web-service
2. **Click**: "Deploy an existing Git repository"
3. **Authorize GitHub** and select your repository
4. **Fill in**:
   - Name: `ai-trip-planner-backend`
   - Environment: `Python 3`
   - Build Command:
     ```
     pip install --no-cache-dir -r requirements.txt
     ```
   - Start Command:
     ```
     uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT
     ```

5. **Click Advanced** and set Python Version to `3.11`

6. **Add Environment Variables** (click "Add Environment Variable" for each):
   ```
   GROQ_API_KEY = <paste your key>
   GOOGLE_API_KEY = <paste your key>
   GPLACES_API_KEY = <paste your key>
   FOURSQUARE_API_KEY = <paste your key>
   TAVILY_API_KEY = <paste your key>
   OPENWEATHERMAP_API_KEY = <paste your key>
   EXCHANGE_RATE_API_KEY = <paste your key>
   ```

7. **Select Plan**: Free (or Starter for production)

8. **Click**: "Create Web Service"

⏳ **Wait 3-5 minutes** while it deploys. Watch the logs.

✅ **When done**: Copy your backend URL (e.g., `https://ai-trip-planner-backend.onrender.com`)

### Test Backend:
```
Visit: https://ai-trip-planner-backend.onrender.com/docs
Should see: FastAPI Swagger UI
```

---

## 4️⃣ DEPLOY FRONTEND ON RENDER

### Step-by-step:

1. **Open**: https://dashboard.render.com/new/web-service
2. **Click**: "Deploy an existing Git repository"
3. **Select your repository again** (same as backend)
4. **Fill in**:
   - Name: `ai-trip-planner-frontend`
   - Environment: `Python 3`
   - Build Command:
     ```
     pip install --no-cache-dir -r requirements.txt
     ```
   - Start Command:
     ```
     gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app
     ```

5. **Click Advanced** and set Python Version to `3.11`

6. **Add Environment Variables**:
   ```
   FASTAPI_BASE_URL = https://ai-trip-planner-backend.onrender.com
   FLASK_SECRET_KEY = <generate: python -c "import secrets; print(secrets.token_hex(32))">
   FLASK_DEBUG = false
   RESET_PLANS_ON_START = true
   GROQ_API_KEY = <same as backend>
   GOOGLE_API_KEY = <same as backend>
   GPLACES_API_KEY = <same as backend>
   FOURSQUARE_API_KEY = <same as backend>
   TAVILY_API_KEY = <same as backend>
   OPENWEATHERMAP_API_KEY = <same as backend>
   EXCHANGE_RATE_API_KEY = <same as backend>
   ```

7. **Select Plan**: Free or Starter

8. **Click**: "Create Web Service"

⏳ **Wait 3-5 minutes** while it deploys.

✅ **When done**: Copy your frontend URL (e.g., `https://ai-trip-planner-frontend.onrender.com`)

### Test Frontend:
```
Visit: https://ai-trip-planner-frontend.onrender.com
Create a trip plan to verify everything works
```

---

## 5️⃣ GENERATE FLASK SECRET KEY (if needed)

Run this in your terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and paste it as `FLASK_SECRET_KEY` in Render.

---

## 6️⃣ COMMON ISSUES & FIXES

### Issue: "ModuleNotFoundError: No module named 'gunicorn'"
**Fix**: 
```bash
echo "gunicorn>=21.0.0" >> requirements.txt
git add requirements.txt
git commit -m "Add gunicorn"
git push
# Then redeploy in Render
```

### Issue: Backend won't start
**Fix**: Check Render logs (Logs tab) and verify:
- All environment variables are set
- `Backend_main_new.py` has `app = FastAPI()`
- Python version is 3.11

### Issue: Frontend can't reach backend
**Fix**: Verify `FASTAPI_BASE_URL` is exactly:
```
https://ai-trip-planner-backend.onrender.com
```
(No trailing slash!)

### Issue: "Backend failed..." message in UI
**Fix**:
1. Check that backend service is running
2. Wait 30-60 seconds (cold start)
3. Reload the page
4. Check both services' logs in Render dashboard

### Issue: Database/plans not persisting
**Fix**: SQLite doesn't persist on Render. For production:
1. Create PostgreSQL: https://dashboard.render.com/new/postgresql
2. Add `DATABASE_URL` environment variable to both services
3. Update your Flask app to use SQLAlchemy with PostgreSQL

---

## 7️⃣ AFTER DEPLOYMENT

### Share Your App
```
Frontend URL: https://ai-trip-planner-frontend.onrender.com
Backend URL: https://ai-trip-planner-backend.onrender.com
```

### Monitor Performance
- Check Render Dashboard → Logs regularly
- Look for errors or slow requests

### Next Steps (Optional)
- [ ] Add custom domain
- [ ] Set up PostgreSQL database
- [ ] Upgrade to Starter plan for production
- [ ] Add monitoring/alerts

---

## 8️⃣ USEFUL CURL COMMANDS FOR TESTING

### Test Backend Health
```bash
curl https://ai-trip-planner-backend.onrender.com/health
```

### Test Backend Docs
```bash
curl https://ai-trip-planner-backend.onrender.com/docs
```

### Test Frontend (in browser)
```
https://ai-trip-planner-frontend.onrender.com
```

---

## 9️⃣ DEPLOYMENT CHECKLIST

Before you start:
- [ ] Create Render account: https://render.com
- [ ] Have all API keys ready
- [ ] Code pushed to GitHub
- [ ] `requirements.txt` includes gunicorn

During deployment:
- [ ] Backend URL copied
- [ ] Frontend `FASTAPI_BASE_URL` set correctly
- [ ] All environment variables added to both services

After deployment:
- [ ] Backend health check passes
- [ ] Frontend loads without errors
- [ ] Can create a trip plan successfully

---

## 🔟 FILE MODIFICATIONS MADE

I've already created/modified these files for you:

✅ **requirements.txt** - Added `gunicorn>=21.0.0` and `python-multipart>=0.0.6`
✅ **render.yaml** - Created for automated deployment
✅ **Dockerfile** - Created (optional alternative deployment)
✅ **start.sh** - Created startup script

No other files were modified. Safe to deploy!

---

## 💡 PRO TIPS

1. **Free Tier Testing**: Use free tier first to test. If it works, upgrade to Starter.

2. **Faster Deploys**: Push code changes to GitHub → Render auto-deploys. No manual upload needed!

3. **Debug Mode**: Never use `debug=True` in Flask for production. Already disabled in your .env!

4. **Cold Starts**: Free tier services sleep after 15 minutes. First request takes 30-60 seconds. Normal!

5. **Logs**: Always check Render Logs tab when something goes wrong. Very helpful!

---

## 📞 NEED HELP?

- **Render Docs**: https://render.com/docs
- **Render Dashboard**: https://dashboard.render.com
- **GitHub Repo Settings**: To connect/disconnect from Render
- **Check our guides**: 
  - QUICK_START_RENDER.md
  - RENDER_DEPLOYMENT.md
  - RENDER_BEST_PRACTICES.md

---

**You've got this! Your app will be live in 15-20 minutes. 🚀**
