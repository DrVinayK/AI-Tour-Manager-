# Render Deployment Best Practices

## Free vs. Paid Tiers Comparison

| Feature | Free | Starter | Standard |
|---------|------|---------|----------|
| **Monthly Cost** | $0 | $7/month | $12/month |
| **Sleep Time** | 15 min → cold start | Never sleeps | Never sleeps |
| **CPU** | 0.5 vCPU | 1 vCPU | 2 vCPU |
| **Memory** | 512 MB | 512 MB | 1 GB |
| **Uptime SLA** | No SLA | 99.99% | 99.99% |
| **Auto-scaling** | No | No | Yes |
| **Concurrent Requests** | Limited | Limited | More |
| **Best For** | Dev/Demo | Production | High Traffic |

**Recommendation**: Use **Free tier for testing**, **Starter for production**.

---

## Environment Variables Best Practices

### ✅ DO:
- Store **API keys** only in Render environment variables, never in code
- Use **different secrets** for dev/staging/production
- Rotate API keys periodically
- Keep a `.env.example` file with dummy values for reference

### ❌ DON'T:
- Commit `.env` file to GitHub
- Share API keys in chat or forums
- Reuse the same secret across environments
- Log sensitive information

---

## Performance Optimization Tips

### 1. **Reduce Cold Start Time**
- Use lightweight dependencies
- Lazy load heavy packages
- Set appropriate Python version

### 2. **Database Optimization**
```python
# ❌ Avoid: SQLite (not persistent)
# ✅ Better: PostgreSQL on Render
#   - Go to Render Dashboard → New PostgreSQL
#   - Connect using SQLAlchemy or psycopg2
```

### 3. **Caching**
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_operation(params):
    # Cached results
    pass
```

### 4. **Timeouts**
- Set appropriate timeout in gunicorn:
  ```
  gunicorn --timeout 120 ...
  ```
- Increase if your backend calls take longer

### 5. **Worker Count**
```bash
# For Frontend (Flask/Gunicorn)
gunicorn --workers 2 --worker-class sync app:app

# For heavier workloads:
gunicorn --workers 4 --worker-class sync app:app
```

---

## Monitoring & Debugging

### Check Logs in Real-time
1. Go to Render Dashboard → Select Service
2. Click **Logs** tab
3. Filter by time or search for errors

### Common Log Patterns

**Bad**: Connection timeout to backend
```
ConnectionError: Failed to connect to https://ai-trip-planner-backend.onrender.com
```
**Fix**: Verify backend URL and that both services are running

**Bad**: Module import error
```
ModuleNotFoundError: No module named 'langchain'
```
**Fix**: Add package to `requirements.txt` and redeploy

**Bad**: Environment variable missing
```
KeyError: 'GROQ_API_KEY'
```
**Fix**: Add the variable in Render environment settings and redeploy

### Health Check Endpoint
Add a health check to your backend:

```python
# In Backend_main_new.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/health")
async def health_check():
    return JSONResponse({"status": "healthy"})
```

Then configure in Render (optional):
- **Health Check Path**: `/health`
- **HTTP Port**: `8000`

---

## Database Persistence

### Issue: Plans Lost After Restart
Your current app uses SQLite (`plans.db`), which is **ephemeral** on Render.

### Solution: Use PostgreSQL

1. **Create PostgreSQL on Render**:
   - Dashboard → New PostgreSQL
   - Set name, region, database name
   - Copy the connection string

2. **Update Flask App**:
   ```bash
   pip install SQLAlchemy psycopg2-binary
   ```

3. **Example with SQLAlchemy**:
   ```python
   from flask_sqlalchemy import SQLAlchemy
   import os

   DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///plans.db")
   app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
   db = SQLAlchemy(app)

   class Plan(db.Model):
       id = db.Column(db.String, primary_key=True)
       plan_data = db.Column(db.JSON)
       created_at = db.Column(db.DateTime)
   ```

4. **Set Environment Variable**:
   - Add `DATABASE_URL` from PostgreSQL to both frontend and backend services

---

## Deployment Checklist

- [ ] All dependencies in `requirements.txt`
- [ ] `.env` file NOT committed to git
- [ ] Environment variables configured in Render
- [ ] Start command is correct
- [ ] Python version set to 3.11
- [ ] Region selected (should match for frontend/backend)
- [ ] Logs checked for errors post-deployment
- [ ] Frontend can reach backend (test trip creation)
- [ ] Static files loading correctly

---

## Security Considerations

### 1. **CORS Configuration**
If your backend is at a different origin:

```python
# In Backend_main_new.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai-trip-planner-frontend.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. **Disable Debug Mode in Production**
```python
# app.py
app.run(debug=False)  # Never debug=True in production
```

### 3. **HTTPS Only**
Render automatically provides HTTPS. Always redirect HTTP to HTTPS:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
```

### 4. **Rate Limiting** (Optional)
```bash
pip install Flask-Limiter
```

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(app=app, key_func=get_remote_address)

@app.route("/query", methods=["POST"])
@limiter.limit("10/minute")
def query():
    # Max 10 requests per minute
    pass
```

---

## Cost Optimization

### Free Tier
- **Cost**: $0/month
- **Catch**: Services spin down after 15 min of inactivity
- **Best for**: Development, testing, demos

### Starter Plan
- **Cost**: $7/service/month (e.g., $14 for frontend + backend)
- **Benefit**: Always running, no cold starts
- **Best for**: Production with low-medium traffic

### Estimate Your Bill
- Frontend (Flask): $7/month (Starter)
- Backend (FastAPI): $7/month (Starter)
- PostgreSQL: $7/month (optional)
- **Total**: ~$14-21/month for production setup

---

## Troubleshooting Checklist

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Service won't start | Missing env var or wrong start command | Check logs, verify all vars set |
| "Backend failed..." error | Frontend can't reach backend | Check FASTAPI_BASE_URL, ensure backend is running |
| Slow responses | Cold start or undersized plan | Upgrade to Starter, or accept 30-60s first request |
| 502 Bad Gateway | Backend crashed or timeout too short | Check backend logs, increase timeout to 120+ |
| Static files 404 | `static/` folder not in git | Ensure folder is committed: `git add static/` |
| Database not persisting | Using SQLite | Switch to PostgreSQL |
| High memory usage | Memory leak or large caches | Profile code, add memory limits to requests |

---

## Useful Render CLI Commands (Optional)

If you want to use Render CLI for deployments:

```bash
# Install Render CLI
npm install -g @render-oss/render-cli

# Login
render login

# Deploy from CLI
render deploy --service ai-trip-planner-backend

# Check status
render service:status ai-trip-planner-backend
```

---

## Next Steps After Deployment

1. **Monitor Performance**
   - Check Render dashboard weekly for errors
   - Review logs for API failures

2. **Upgrade Database**
   - Move from SQLite to PostgreSQL for data persistence
   - Add database backups

3. **Custom Domain** (Optional)
   - Add a custom domain (e.g., trip-planner.yoursite.com)
   - Configure DNS records

4. **CI/CD Integration** (Optional)
   - Render auto-deploys on git push (already set up!)
   - No additional configuration needed

5. **Scaling** (Future)
   - Monitor traffic and upgrade plan if needed
   - Consider caching layer (Redis) for high traffic

---

## Resources

- [Render Dashboard](https://dashboard.render.com)
- [Render Documentation](https://render.com/docs)
- [Python Deployment Guide](https://render.com/docs/deploy-python)
- [Environment Variables Guide](https://render.com/docs/environment-variables)
- [Troubleshooting Guide](https://render.com/docs/troubleshooting)

---

**Your app is now production-ready! 🚀**
