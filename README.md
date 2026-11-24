# 📰 Daily AI Headline NFT

[![CI](https://github.com/rmnbm/daily-headline/actions/workflows/ci.yml/badge.svg)](https://github.com/rmnbm/daily-headline/actions/workflows/ci.yml)

An autonomous pipeline that fetches the daily **New York Times** headline, generates a conceptual AI artwork using **FLUX.1**, and updates a dynamic NFT on the **Sepolia Ethereum Testnet**.

## 🚀 How it Works
1. **Fetch:** the backend calls the NYT Top Stories API.
2. **Generate:** the headline is sent to the FLUX.1 model on Cloudflare Workers AI to create a newspaper-style image.
3. **Store:** the image and the metadata JSON are pinned to IPFS via Pinata.
4. **Update:** the smart contract's `tokenURI` is updated on-chain via Web3.py.
5. **Automate:** GitHub Actions runs this whole flow every day at 08:00 UTC.

Steps 1–2 produce a *draft* and steps 3–5 *publish* it. The daily job chains both;
the review API lets a human check the image before anything goes on-chain.

## 🛠 Tech Stack
- **Smart Contracts:** Solidity, Foundry, OpenZeppelin
- **Backend:** Python 3.12, FastAPI, SQLite, Web3.py
- **AI/Storage:** Cloudflare Workers AI, Pinata (IPFS)
- **Automation:** GitHub Actions

## 📂 Project Structure
```
backend/
  app/
    config.py      settings from environment variables / .env
    pipeline.py    prepare (headline + image) and publish (IPFS + contract)
    services/      one client per external service: NYT, Cloudflare AI, Pinata, Web3
    db.py          SQLite history of runs and their steps
    api.py         review API (FastAPI)
    cli.py         `run` (daily job) and `serve` (API)
  tests/           pytest suite, no network access
  scripts/         manual connection check
contracts/
  src/             DailyHeadline.sol (ERC-721)
  test/            Foundry tests
  script/          deployment script
.github/workflows/
  ci.yml           tests and lint on every push / PR
  daily.yml        daily publication at 08:00 UTC
```

## ⚙️ Configuration
Create `backend/.env` (never committed):

| Variable | Used by | Description |
| --- | --- | --- |
| `NYT_API_KEY` | pipeline | NYT Top Stories API key |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | pipeline | Cloudflare Workers AI |
| `PINATA_JWT` | pipeline | Pinata JWT |
| `RPC_URL` | pipeline | Sepolia RPC endpoint |
| `PRIVATE_KEY` | pipeline | wallet that owns the contract |
| `CONTRACT_ADDRESS` | pipeline | deployed `DailyHeadline` address |
| `API_KEY` | API | secret expected in the `X-API-Key` header |
| `DATABASE_PATH` | API | SQLite file (default `data/daily_headline.db`) |
| `LOG_LEVEL` | both | default `INFO` |

The daily workflow reads the pipeline variables from the repository's GitHub Actions secrets.

## 💻 Running Locally
```bash
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

python -m app.cli run        # full pipeline, publishes on-chain
python -m app.cli serve      # review API on http://127.0.0.1:8000 (docs at /docs)

python -m pytest             # tests + coverage
ruff check . && ruff format --check .
```

### Review API
All endpoints except `/health` require `X-API-Key: $API_KEY`.

| Method | Path | Effect |
| --- | --- | --- |
| `GET` | `/health` | liveness check |
| `POST` | `/runs` | fetch the headline and generate the image → `draft` (body optional: `{"date": "YYYY-MM-DD"}`) |
| `GET` | `/runs`, `/runs/{id}` | history, with the status of each step |
| `GET` | `/runs/{id}/image` | the generated PNG |
| `POST` | `/runs/{id}/publish` | pin to IPFS and update the contract (`draft` → `published`) |
| `POST` | `/runs/{id}/reject` | discard a draft (`draft` → `rejected`) |

A draft can be published only once; any other transition answers `409`.

### Contracts
```bash
cd contracts
forge install --no-git foundry-rs/forge-std@v1.15.0 OpenZeppelin/openzeppelin-contracts@v5.5.0  # first time
forge test
```

## 🔗 Contract Information
- **Network:** Sepolia Testnet
- **Contract Address:** `0x80D111626caD7588Fd514324911f08bfa53FE71C`
