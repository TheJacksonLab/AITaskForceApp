# ChemViva

**AI-powered oral chemistry exam platform for the University of Illinois. Deploy online and share with your colleagues.**

## Features
- ✍️ Typed-only oral-exam dialogue (a deliberate CHEM 202 course policy)
- 🤖 Dynamic 6-turn oral dialogue powered by **OpenAI gpt-5.1** (examiner + final grading)
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
```

Get an API key:
- **OpenAI:** [platform.openai.com](https://platform.openai.com)

### 3. Run Locally
```bash
streamlit run app.py
```

## Grading Regression Check

After exporting the results sheet as CSV, replay a reproducible sample through
the current production rubric:

```bash
python scripts/regrade_transcripts.py path/to/export.csv --sample-size 12
```

The check reports the old and new score-versus-student-word-count correlation,
prints the new trajectory distribution, and fails if every sampled transcript
receives the same trajectory label. It uses the `OPENAI_API_KEY` environment
variable and makes one grading call per sampled transcript.

Two optional policies live in `config.json`: `score_abandoned_sessions` controls
whether zero-answer sessions write a numeric score to the sheet, and
`verify_grader_feedback` enables a second chemistry-accuracy review of grader
feedback for the instructor queue. Both default to `false`.

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
   ```
3. Save and refresh

Your app is now live! Share the URL with colleagues. 🎉

## Cost Estimate (per completed exam)

Each exam consists of up to **6 student turns**. The opening question is served from a static bank (no LLM call) and the closing turn is generated locally, so the examiner makes up to **5 follow-up calls**, plus a final grading call and two lightweight post-exam calls (per-turn annotation + study advice).

| Service | Usage per exam | Estimated cost |
|---------|---------------|----------------|
| **OpenAI gpt-5.1** | Up to 5 adaptive examiner follow-ups + 1 final grading call | ~$0.03 |
| **OpenAI gpt-4o-mini** | Per-turn annotation + study-advice generation | ~$0.001–0.003 |
| **Total** | | **~$0.03 per exam** |

> Cost figures are approximate (measured token counts × list prices at time of writing). Verify current model pricing at [platform.openai.com](https://platform.openai.com).

OpenAI has no persistent free tier; pre-purchase credits at [platform.openai.com](https://platform.openai.com).

## Differences from Local Version
- **This version:** Cloud-hosted, shareable, uses cloud APIs
- **Local version:** Runs on your machine, free, no API keys, see `AITaskForceApp-Local/`

---

Built with ❤️ for chemistry education
