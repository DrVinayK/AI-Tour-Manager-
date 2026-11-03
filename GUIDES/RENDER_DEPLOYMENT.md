# Deploying AI Trip Planner to Render

This guide walks you through deploying both the **Flask frontend** and **FastAPI backend** to Render.

## Prerequisites

1. **Render Account**: Sign up at [render.com](https://render.com)
2. **GitHub Repository**: Push your code to GitHub (Render deploys from git)
3. **Environment Variables**: Have your API keys ready (GROQ, Google, etc.)

---

## Part 1: Deploy the FastAPI Backend

### Step 1: Create a `render.yaml` for the Backend

In your project root, create a file named `render.yaml` with the following content:

```yaml
services:
  - type: web
    name: ai-trip-planner-backend
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11
      - key: GROQ_API_KEY
        sync: false
      - key: GOOGLE_API_KEY
        sync: false
      - key: GPLACES_API_KEY
        sync: false
      - key: FOURSQUARE_API_KEY
        sync: false
      - key: TAVILY_API_KEY
        sync: false
      - key: OPENWEATHERMAP_API_KEY
        sync: false
      - key: EXCHANGE_RATE_API_KEY
        sync: false
```

**Note**: The `Backend_main_new.py` file should export an `app` object. If it doesn't, you'll need to adjust the `startCommand` accordingly.

### Step 2: Push to GitHub

```bash
git add render.yaml requirements.txt Backend_main_new.py
git commit -m "Add Render deployment configuration"
git push
```

### Step 3: Create Backend Service on Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Select **Deploy an existing Git repository**
4. Connect your GitHub account and select your repository
5. Fill in the details:
   - **Name**: `ai-trip-planner-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn Backend_main_new:app --host 0.0.0.0 --port $PORT`
6. Scroll down to **Environment** section
7. Add all API keys:
   - `GROQ_API_KEY`
   - `GOOGLE_API_KEY`
   - `GPLACES_API_KEY`
   - `FOURSQUARE_API_KEY`
   - `TAVILY_API_KEY`
   - `OPENWEATHERMAP_API_KEY`
   - `EXCHANGE_RATE_API_KEY`
8. Click **Create Web Service**

Wait for deployment to complete. Your backend URL will be something like:
```
https://ai-trip-planner-backend.onrender.com
```

**Save this URL** — you'll need it for the frontend!

---

## Part 2: Deploy the Flask Frontend

### Step 1: Update Your `.env` File

Update your `.env` with the backend URL from Part 1:

```env
FASTAPI_BASE_URL=https://ai-trip-planner-backend.onrender.com
FLASK_SECRET_KEY=<your-secret-key>
FLASK_DEBUG=false
RESET_PLANS_ON_START=true
GROQ_API_KEY=your_groq_key
GOOGLE_API_KEY=your_google_key
GPLACES_API_KEY=your_gplaces_key
FOURSQUARE_API_KEY=your_foursquare_key
TAVILY_API_KEY=your_tavily_key
OPENWEATHERMAP_API_KEY=your_weather_key
EXCHANGE_RATE_API_KEY=your_exchange_rate_key
```

### Step 2: Create a Production Startup Script

Create a file named `start.sh`:

```bash
#!/bin/bash
pip install -r requirements.txt
gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app
```

### Step 3: Update `requirements.txt`

Add `gunicorn` to your requirements (for production WSGI server):

```bash
echo "gunicorn>=21.0.0" >> requirements.txt
```

Your `requirements.txt` should now include:
```
Flask>=2.3.0
gunicorn>=21.0.0
requests>=2.31.0
... (rest of your dependencies)
```

### Step 4: Update `app.py`

Make sure the Flask app runs properly in production:

```python
if __name__ == "__main__":
    # Don't use debug=True in production
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
```

### Step 5: Create Frontend Service on Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Select **Deploy an existing Git repository**
4. Select your repository again
5. Fill in the details:
   - **Name**: `ai-trip-planner-frontend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --workers 2 --worker-class sync --timeout 120 --bind 0.0.0.0:$PORT app:app`
6. **Environment Variables**:
   - Add all variables from your `.env` file
   - Especially `FASTAPI_BASE_URL` with your backend URL
7. Click **Create Web Service**

Wait for deployment. Your frontend URL will be something like:
```
https://ai-trip-planner-frontend.onrender.com
```

---

## Step 3: Verify Deployment

### Check Backend Health

Visit your backend health check endpoint:
```
https://ai-trip-planner-backend.onrender.com/docs
```

(This assumes your FastAPI app has the auto-generated OpenAPI docs)

### Test Frontend

Visit your frontend:
```
https://ai-trip-planner-frontend.onrender.com
```

Try creating a trip plan to verify the frontend-backend connection works.

---

## Important Notes

### 1. **Cold Starts on Free Tier**
Render's free tier spins down services after 15 minutes of inactivity. The first request after a spin-down takes 30-60 seconds. Consider upgrading to a paid tier for production.

### 2. **Database Persistence**
Your current app uses SQLite (`plans.db`). On Render, this is **not persistent** between deployments. For production:
- Switch to PostgreSQL (Render offers a free PostgreSQL database)
- Or use an external database service

### 3. **Static Files**
Ensure your `static/` folder is in your repository so Render can serve CSS, JS, and other assets.

### 4. **Secrets Management**
Never commit `.env` to GitHub! Add sensitive API keys only via the Render dashboard environment variables.

### 5. **Logging**
Render aggregates logs from your services. Check them in:
- **Logs** tab → Service logs for debugging

---

## Optional: Database Persistence

If you need persistent storage, add a PostgreSQL database:

1. In Render Dashboard, click **New +** → **PostgreSQL**
2. Set a name and region
3. Copy the database connection string
4. In your Flask app, add SQLAlchemy:
   ```bash
   echo "SQLAlchemy>=2.0" >> requirements.txt
   ```
5. Update your app to use PostgreSQL instead of SQLite

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Backend failed..." | Check that backend URL is correct in frontend `.env` |
| 404 errors on static files | Ensure `static/` folder is committed to git |
| Service won't start | Check logs in Render dashboard; common issue is missing environment variables |
| Slow response times | Free tier cold starts can be slow; upgrade to paid tier if needed |
| Database not persisting | SQLite doesn't persist on Render; switch to PostgreSQL |

---

## Summary of Deployment Steps

1. ✅ Create `render.yaml` for backend
2. ✅ Push code to GitHub
3. ✅ Deploy backend as Web Service
4. ✅ Update frontend `.env` with backend URL
5. ✅ Add gunicorn to requirements.txt
6. ✅ Deploy frontend as Web Service
7. ✅ Verify both services are running
8. ✅ Test the full application

Your AI Trip Planner is now live! 🚀
