# NOVA Trader V6.8.1 — Clean Consolidated

This package removes the build-time patch chain. The complete V6.8.1 backend is already consolidated into `app.py`.

## Keep only these backend files

- `app.py`
- `requirements.txt`
- `Dockerfile`
- `README.md`

## Northflank

Build context: `/`
Dockerfile: `/Dockerfile`

After upload, use **Start build / New build**, then deploy the successful build.

Expected `/health` version: `6.8.1`.

## Important environment variables

Keep the existing secrets/settings in Northflank. Do not place secrets in GitHub.

Recommended public-only variable:

`PUMPPORTAL_PUBLIC_WALLET=<public wallet address>`

Live execution remains hard locked in this build.
