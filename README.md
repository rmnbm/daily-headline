# 📰 Daily AI Headline NFT

An autonomous pipeline that fetches the daily **New York Times** headline, generates a conceptual AI artwork using **FLUX.1**, and updates a dynamic NFT on the **Sepolia Ethereum Testnet**.

## 🚀 How it Works
1. **Fetch:** Python script calls the NYT Top Stories API.
2. **Generate:** The headline is sent to the FLUX.1 model on Cloudflare Workers AI to create a high-quality newspaper-style image.
3. **Store:** Image and Metadata JSON are pinned to IPFS via Pinata.
4. **Mint/Update:** The smart contract's `tokenURI` is updated on-chain via Web3.py.
5. **Automate:** GitHub Actions runs this entire flow every day at 08:00 UTC.

## 🛠 Tech Stack
- **Smart Contracts:** Solidity, Foundry, OpenZeppelin
- **Backend:** Python, Web3.py
- **AI/Storage:** Cloudflare Workers AI, Pinata (IPFS)
- **Automation:** GitHub Actions

## 📂 Project Structure
- `/src`: Smart contract source code.
- `/backend`: Python automation script and dependencies.
- `/test`: Foundry smart contract tests.
- `/scripts`: Utility scripts for connection verification.

## 🔗 Contract Information
- **Network:** Sepolia Testnet
- **Contract Address:** `0x80D111626caD7588Fd514324911f08bfa53FE71C`