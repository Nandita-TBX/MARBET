# MARBET - Decentralised Prediction Markets on Algorand

MARBET is a web-based prediction market platform built on the Algorand blockchain.
Users can create markets, place bets, and receive proportional payouts — all backed
by real Algorand keypairs and cryptographic transaction signatures.

## Features
- Register with an auto-generated Algorand wallet (25-word mnemonic)
- 1,000 ALGO simulated starting balance + faucet (2 × 100 ALGO claims)
- Create prediction markets with custom questions and options
- Place bets with live pool share preview
- Automatic proportional payouts on resolution (97% to winners, 3% house fee)
- Full transaction history and house ledger
- Real on-chain transactions when Algorand testnet is reachable; falls back to
  simulation mode with cryptographically generated TX IDs
- No external links - all TX confirmation shown inline

## Stack
- Backend: Python / Flask
- Blockchain: Algorand (algosdk) - Testnet
- Frontend: Vanilla HTML/CSS/JS (Space Mono + Syne fonts)
- Storage: JSON flat files (users, markets, bets, house wallet)

## Setup

### Prerequisites
    pip install flask py-algorand-sdk

### Run
    python app.py

App runs at http://localhost:5000

## File Structure
    project/
    ├── app.py
    ├── templates/
    │   ├── index.html       # Login / Register / Recover
    │   ├── market.html      # Main SPA — Markets, Wallet, Ledger, Transactions
    │   └── user.html        # Account page
    ├── static/
        ├── main.js          # Shared API helper, toast, logout
        ├── style.css        # Global dark theme
        └── logo.svg         # MARBET logo

## How It Works
1. Register → Algorand keypair generated server-side, mnemonic shown once
2. Browse markets → see live pool distributions per option
3. Place a bet → funds debited from your wallet, sent to house escrow
4. Creator resolves market → winners paid proportionally from pool
5. Every action produces a Transaction ID (real or simulated)

## Notes
- This is a testnet/demo application. No real ALGO is used.
- Mnemonic phrases are stored server-side for demo purposes only.
  In production, private keys should never leave the client.
