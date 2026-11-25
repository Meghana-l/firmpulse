# Deploy

1. Push this folder to GitHub, then import it in Vercel (leave build settings alone).
2. Vercel -> Settings -> Environment Variables:
   - `FRED_API_KEY` (free, https://fred.stlouisfed.org/docs/api/api_key.html) makes the data LIVE
   - `SEC_USER_AGENT` = `Your Name your@email.com` (the SEC asks for a contact; it is sent only from the server to the SEC and visitors never see it)
   - optional: `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY` (set a spend limit if you add this one)
3. Redeploy. The badge top-right shows LIVE or SAMPLE.

Local: `python dev_server.py` then open http://localhost:3000. Tests: `python -m pytest tests -q`.
