# Bamidele Salam Support Frame Generator

A Flask web app that lets supporters upload their photo and name to create a personalised campaign poster.

## Features
- Auto background removal (rembg / U2Net AI)
- 5 colour design variants
- Instant JPEG download

## Deploy on Render
1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — just click **Deploy**

## Local Development
```bash
pip install -r requirements.txt
python app.py
```
Open http://localhost:5050
