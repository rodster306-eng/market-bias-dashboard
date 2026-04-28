# Supabase Setup

## 1. Create the Supabase project

1. Create a new project in Supabase.
2. In `Authentication > Providers`, keep `Email` enabled.
3. In `Authentication > Sign In / Providers`, choose whether email confirmation is required.

## 2. Create the dashboard table

1. Open the SQL editor in Supabase.
2. Run the contents of [supabase_schema.sql](/C:/Users/rodst/Desktop/market_bias_dashboard/supabase_schema.sql:1).

This creates a `user_dashboards` table with row-level security so each user can only access their own saved dashboard data.

## 3. Add Streamlit secrets

Add these secrets in Streamlit Community Cloud:

```toml
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_ANON_KEY = "your-anon-key"
```

For local development, you can place the same values in `.streamlit/secrets.toml`.

## 4. Deploy

1. Push this repo to GitHub.
2. Deploy [app.py](/C:/Users/rodst/Desktop/market_bias_dashboard/app.py:1) on Streamlit Community Cloud.
3. Paste the secrets above into the app's secret settings.

## Notes

- Registration and sign-in are email/password based through Supabase Auth.
- Saved analyst and news profiles are now stored per user in Supabase instead of local JSON files.
- The current auth session is stored in Streamlit session state, so a hard browser refresh may require the user to sign in again. If you want, the next step can be persistent auth cookies.
