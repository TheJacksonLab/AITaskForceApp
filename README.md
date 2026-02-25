# Oral Exam: General Chemistry - Cloud Version

**Shareable AI-powered chemistry oral exam evaluator. Deploy online and share with your colleagues.**

## Features
- 🎤 Audio recording with cloud-based **AssemblyAI** transcription
- 🤖 AI evaluation powered by **OpenAI o3-mini** (fast, affordable)
- 📊 Real-time feedback and conceptual accuracy scoring
- 🌐 Hosted on Streamlit Cloud for easy sharing

## Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up API Keys
Create a `.env` file (copy from `.env.template`):
```bash
cp .env.template .env
```

Then add your API keys:
```
OPENAI_API_KEY=sk-...your-key...
ASSEMBLYAI_API_KEY=aai_...your-key...
```

Get free API keys:
- **OpenAI:** [platform.openai.com](https://platform.openai.com)
- **AssemblyAI:** [assemblyai.com](https://assemblyai.com)

### 3. Run Locally
```bash
streamlit run app.py
```

## Deploy to Streamlit Cloud

### 1. Push to GitHub
```bash
git add .
git commit -m "Your message"
git push origin main
```

### 2. Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select your repository: `TheJacksonLab/AITaskForceApp`
4. Click **Deploy**

### 3. Add Secrets
Once deployed:
1. Click **⋯ (menu)** → **Settings** → **Secrets**
2. Add your API keys:
   ```
   OPENAI_API_KEY=sk-...
   ASSEMBLYAI_API_KEY=aai_...
   ```
3. Save and refresh

Your app is now live! Share the URL with colleagues. 🎉

## Cost Estimate
- **AssemblyAI:** ~$0.00-0.10 per minute of audio (free tier: 600 min/month)
- **OpenAI o3-mini:** Very cheap (~$0.001-0.05 per request)

## Differences from Local Version
- **This version:** Cloud-hosted, shareable, uses cloud APIs
- **Local version:** Runs on your machine, free, no API keys, see `AITaskForceApp-Local/`

---

Built with ❤️ for chemistry education
