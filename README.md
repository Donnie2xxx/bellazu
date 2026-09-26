# BellaZu

A simple, phone-friendly English/Español helper for first-time home buyers in North Jersey.

* **Check a home:** type an address and get one clear verdict (Good deal / Maybe / Skip), the price,
  your monthly cost, cash to close, the rent it could earn, and whether Airbnb is allowed.
  Everything else is under "See details", plus a downloadable full report.
* **Find rentals in a town:** Airbnb rules for renters first, then the top rentals by estimated
  profit as furnished 30+ day rentals (the legal option in towns that ban Airbnb).

## Run on Streamlit Community Cloud
1. Push this folder as the root of a GitHub repo.
2. On share.streamlit.io: New app, pick the repo, branch `main`, main file **`app.py`**.
   Advanced settings: Python 3.12 or 3.13.
3. App settings > Secrets (see `secrets.toml.example`):
   `APP_PASSCODE` (required), `RENTCAST_API_KEY` (optional), `RENTCAST_MONTHLY_CAP`, `RENTCAST_USED_OFFSET` (optional).

Run locally: `pip install -r requirements.txt`, then `APP_PASSCODE=... streamlit run app.py`
(or put the values in `.streamlit/secrets.toml`, which git ignores).

Data: Inside Airbnb (CC BY 4.0), HUD Small Area FMR, Census Reporter (ACS), FRED (Freddie Mac PMMS),
OpenStreetMap Nominatim, Craigslist, Rent.com, Redfin, RentCast (optional).
Estimates only, not financial, legal or lending advice.
