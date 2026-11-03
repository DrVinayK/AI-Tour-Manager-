# Environment Variables Template for Render Deployment

This file shows you what environment variables you need to set up in Render.
Copy the variable names and paste them into Render's environment variable setup.

## Do NOT use this file as an actual .env file for your code!
## Only use this as a REFERENCE for setting up variables in Render.

---

## BACKEND SERVICE Environment Variables

Add these to your backend service in Render:

```
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GPLACES_API_KEY=your_google_places_api_key_here
FOURSQUARE_API_KEY=your_foursquare_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key_here
EXCHANGE_RATE_API_KEY=your_exchangerate_api_key_here
```

---

## FRONTEND SERVICE Environment Variables

Add these to your frontend service in Render:

```
FASTAPI_BASE_URL=https://ai-trip-planner-backend.onrender.com
FLASK_SECRET_KEY=your_generated_secret_key_here
FLASK_DEBUG=false
RESET_PLANS_ON_START=true
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GPLACES_API_KEY=your_google_places_api_key_here
FOURSQUARE_API_KEY=your_foursquare_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key_here
EXCHANGE_RATE_API_KEY=your_exchangerate_api_key_here
```

---

## Where to Get Each Key

### GROQ_API_KEY
- Website: https://console.groq.com/keys
- Steps:
  1. Go to Groq Console
  2. Click "API Keys"
  3. Copy your API key
  4. Paste into GROQ_API_KEY field

### GOOGLE_API_KEY & GPLACES_API_KEY
- Website: https://console.cloud.google.com
- Steps:
  1. Create a new project or select existing
  2. Enable "Maps API"
  3. Enable "Places API"
  4. Create an API Key
  5. Copy and use for GOOGLE_API_KEY
  6. Copy again and use for GPLACES_API_KEY
  (You can reuse the same key for both)

### FOURSQUARE_API_KEY
- Website: https://developer.foursquare.com/
- Steps:
  1. Sign up or log in
  2. Create an application
  3. Copy your API key
  4. Paste into FOURSQUARE_API_KEY field

### TAVILY_API_KEY
- Website: https://tavily.com/
- Steps:
  1. Sign up or log in
  2. Go to API settings
  3. Copy your API key
  4. Paste into TAVILY_API_KEY field

### OPENWEATHERMAP_API_KEY
- Website: https://openweathermap.org/api
- Steps:
  1. Sign up or log in
  2. Go to API keys section
  3. Copy your API key
  4. Paste into OPENWEATHERMAP_API_KEY field

### EXCHANGE_RATE_API_KEY
- Website: https://exchangerate-api.com/
- Steps:
  1. Sign up or log in
  2. Go to your dashboard
  3. Copy your API key
  4. Paste into EXCHANGE_RATE_API_KEY field

### FLASK_SECRET_KEY
- Generate with Python:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- Run this command
- Copy the output
- Paste into FLASK_SECRET_KEY field

### FASTAPI_BASE_URL
- This is your backend URL from Render
- Format: `https://ai-trip-planner-backend.onrender.com`
- Replace with your actual backend service name

---

## How to Add Variables in Render

1. Go to Render Dashboard: https://dashboard.render.com
2. Select your service (backend or frontend)
3. Go to "Environment" tab
4. Click "Add Environment Variable"
5. Fill in:
   - Key: (variable name, e.g., GROQ_API_KEY)
   - Value: (your actual API key)
6. Click "Save"
7. Repeat for all variables

---

## Checklist Before Deployment

### Backend Service
- [ ] GROQ_API_KEY set
- [ ] GOOGLE_API_KEY set
- [ ] GPLACES_API_KEY set
- [ ] FOURSQUARE_API_KEY set
- [ ] TAVILY_API_KEY set
- [ ] OPENWEATHERMAP_API_KEY set
- [ ] EXCHANGE_RATE_API_KEY set

### Frontend Service
- [ ] FASTAPI_BASE_URL set (to your backend URL)
- [ ] FLASK_SECRET_KEY set (generated value)
- [ ] FLASK_DEBUG = false
- [ ] RESET_PLANS_ON_START = true
- [ ] GROQ_API_KEY set (same as backend)
- [ ] GOOGLE_API_KEY set (same as backend)
- [ ] GPLACES_API_KEY set (same as backend)
- [ ] FOURSQUARE_API_KEY set (same as backend)
- [ ] TAVILY_API_KEY set (same as backend)
- [ ] OPENWEATHERMAP_API_KEY set (same as backend)
- [ ] EXCHANGE_RATE_API_KEY set (same as backend)

---

## Important Notes

- **Never share your API keys** - Keep them secret!
- **Different keys for dev/prod** - Use different keys if you have dev and production
- **Rotate keys periodically** - Update your API keys every 3-6 months
- **Store securely** - Only use Render's environment variable system, never hardcode
- **FASTAPI_BASE_URL** - Make sure there's no trailing slash
- **No quotes needed** - Don't add quotes around values in Render

---

## Troubleshooting

### "ModuleNotFoundError: No module named..."
- Check: All packages in requirements.txt
- Fix: Add missing package and redeploy

### "KeyError: 'GROQ_API_KEY'"
- Check: Variable is set in Render environment
- Fix: Add the missing variable and redeploy

### Backend won't start
- Check: All API keys are set
- Check: Python version is 3.11
- Check: Build command is correct

### Frontend can't reach backend
- Check: FASTAPI_BASE_URL is exactly correct
- Check: No trailing slash
- Check: Backend service is running

---

For more help, see:
- GUIDES/RENDER_CHECKLIST.md
- GUIDES/COPY_PASTE_COMMANDS.md
- GUIDES/RENDER_BEST_PRACTICES.md
