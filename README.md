# Oral Exam: General Chemistry - Cloud Version

**Shareable AI-powered chemistry oral exam evaluator. Deploy online and share with your colleagues.**

## Features
- 🎤 Audio recording with cloud-based **AssemblyAI** transcription
- 🤖 Dynamic 6-turn oral dialogue powered by **OpenAI gpt-4o-mini** (examiner) + **o3-mini** (final grading)
- 📊 Holistic scoring with trajectory tracking (improving / consistent strong / consistent weak / declining / mixed)
- 🌐 Hosted on Streamlit Cloud for easy sharing
- 📋 Results logged to Google Sheets for instructor review

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

## Cost Estimate (per completed exam)

Each exam consists of up to **6 student turns**, generating up to **7 OpenAI API calls** total (1 question generation + 5 examiner follow-ups + 1 final grading).

| Service | Usage per exam | Estimated cost |
|---------|---------------|----------------|
| **OpenAI gpt-4o-mini** | Opening question + up to 5 examiner follow-ups | ~$0.001–0.003 |
| **OpenAI o3-mini** | 1 final holistic grading call (full transcript) | ~$0.01–0.02 |
| **AssemblyAI** | Up to 6 audio responses (~4–5 min total audio) | ~$0.02–0.03 |
| **Total** | | **~$0.03–0.05 per exam** |

Free tiers:
- **AssemblyAI:** 100 hours/month free — covers ~1,200 exams/month
- **OpenAI:** No persistent free tier; pre-purchase credits at [platform.openai.com](https://platform.openai.com)

## Differences from Local Version
- **This version:** Cloud-hosted, shareable, uses cloud APIs
- **Local version:** Runs on your machine, free, no API keys, see `AITaskForceApp-Local/`

---

Built with ❤️ for chemistry education
