from flask import Flask, render_template, request, jsonify, session
from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod
import json, os, uuid, hashlib
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.secret_key = "marbet-secret-key-change-in-prod-2025"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE   = DATA_DIR / "users.json"
MARKETS_FILE = DATA_DIR / "markets.json"
BETS_FILE    = DATA_DIR / "bets.json"
HOUSE_FILE   = DATA_DIR / "house.json"

def load_json(p):
    return json.loads(p.read_text()) if p.exists() else {}

def save_json(p, d):
    p.write_text(json.dumps(d, indent=2))

users   = load_json(USERS_FILE)
markets = load_json(MARKETS_FILE)
bets    = load_json(BETS_FILE)

STARTING_BALANCE = 1_000_000_000  # 1000 ALGO in microALGO

# ── ALGORAND CLIENT ───────────────────────────────────────────────────────────
ALGOD_ENDPOINTS = [
    ("https://testnet-api.algonode.cloud", ""),
    ("https://testnet.algonode.cloud",     ""),
]
algod_client    = None
active_endpoint = "offline"

for addr, token in ALGOD_ENDPOINTS:
    try:
        c = algod.AlgodClient(token, addr, headers={"User-Agent": "MARBET/2.0"})
        c.status()
        algod_client    = c
        active_endpoint = addr
        break
    except Exception:
        continue

def get_params():
    if algod_client:
        try:
            return algod_client.suggested_params()
        except Exception:
            pass
    return None

def try_real_payment(sender_pk, sender_addr, receiver_addr, amount, note=""):
    try:
        params = get_params()
        if not params:
            raise Exception("offline")
        txn    = transaction.PaymentTxn(sender_addr, params, receiver_addr,
                                        amount, note=note.encode())
        signed = txn.sign(sender_pk)
        tx_id  = algod_client.send_transaction(signed)
        return tx_id, True
    except Exception:
        return f"SIM-{uuid.uuid4().hex[:20].upper()}", False

# ── HOUSE WALLET ──────────────────────────────────────────────────────────────
def get_or_create_house():
    house = load_json(HOUSE_FILE)
    if not house:
        pk, addr = account.generate_account()
        mn = mnemonic.from_private_key(pk)
        house = {"address": addr, "mnemonic": mn, "private_key": pk,
                 "simulated_balance": 10_000_000_000}
        save_json(HOUSE_FILE, house)
        print(f"\n[MARBET] House wallet created: {addr}")
    return house

HOUSE = get_or_create_house()

# ── BALANCE HELPERS ───────────────────────────────────────────────────────────
def user_balance(u):
    return u.get("simulated_balance", STARTING_BALANCE)

def debit(username, amount):
    u   = users[username]
    bal = user_balance(u)
    if bal < amount:
        raise ValueError(f"Insufficient balance. You have {bal/1e6:.4f} ALGO.")
    u["simulated_balance"] = bal - amount
    save_json(USERS_FILE, users)

def credit(username, amount):
    u = users[username]
    u["simulated_balance"] = user_balance(u) + amount
    save_json(USERS_FILE, users)

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/market")
def market_page():
    if "username" not in session:
        return render_template("index.html")
    return render_template("market.html", username=session["username"])

@app.route("/user")
def user_page():
    return render_template("user.html")

@app.route("/api/status")
def status():
    online = False
    if algod_client:
        try:
            algod_client.status(); online = True
        except Exception:
            pass
    return jsonify({"online": online, "endpoint": active_endpoint, "house": HOUSE["address"]})

@app.route("/api/register", methods=["POST"])
def register():
    data     = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username:
        return jsonify({"success": False, "message": "Username required."})
    if username in users:
        return jsonify({"success": False, "message": "Username taken — try logging in."})
    pk, addr = account.generate_account()
    mn       = mnemonic.from_private_key(pk)
    pw_hash  = hashlib.sha256(password.encode()).hexdigest() if password else ""
    users[username] = {
        "address": addr, "mnemonic": mn, "private_key": pk,
        "pw_hash": pw_hash, "simulated_balance": STARTING_BALANCE,
        "created_at": datetime.now().isoformat(),
    }
    save_json(USERS_FILE, users)
    session["username"] = username
    return jsonify({"success": True,
                    "message": f"Welcome, {username}! 1,000 ALGO added to your wallet.",
                    "address": addr, "mnemonic": mn, "redirect": "/market"})

@app.route("/api/login", methods=["POST"])
def login():
    data     = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    mn_input = data.get("mnemonic", "").strip()
    if username not in users:
        return jsonify({"success": False, "message": "User not found — please register."})
    u = users[username]
    authed = False
    if mn_input:
        try:
            rpk   = mnemonic.to_private_key(mn_input)
            raddr = account.address_from_private_key(rpk)
            if raddr != u["address"]:
                return jsonify({"success": False, "message": "Mnemonic doesn't match this account."})
            u["private_key"] = rpk
            save_json(USERS_FILE, users)
            authed = True
        except Exception:
            return jsonify({"success": False, "message": "Invalid mnemonic phrase."})
    elif password:
        ph     = hashlib.sha256(password.encode()).hexdigest()
        authed = (u.get("pw_hash") == ph) or (not u.get("pw_hash"))
    else:
        authed = not u.get("pw_hash")
    if not authed:
        return jsonify({"success": False, "message": "Incorrect password."})
    session["username"] = username
    return jsonify({"success": True, "message": f"Welcome back, {username}!", "redirect": "/market"})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/wallet")
def wallet_info():
    if "username" not in session:
        return jsonify({"success": False})
    u = users.get(session["username"])
    if not u:
        return jsonify({"success": False})
    bal = user_balance(u)
    return jsonify({
        "success": True, "username": session["username"],
        "address": u["address"], "balance": bal,
        "balance_algo": round(bal / 1_000_000, 4),
        "house_address": HOUSE["address"],
        "house_balance": round(HOUSE.get("simulated_balance", 0) / 1_000_000, 4),
        "simulated": True,
    })

@app.route("/api/markets")
def get_markets():
    active = {k: v for k, v in markets.items() if not v.get("deleted")}
    for mid, m in active.items():
        totals = {o: 0 for o in m["options"]}
        for b in bets.values():
            if b["market_id"] == mid and not b.get("refunded"):
                totals[b["option"]] = totals.get(b["option"], 0) + b["amount_microalgo"]
        m["bet_totals"] = totals
        m["total_pool"]  = sum(totals.values())
    return jsonify({"markets": active})

@app.route("/api/markets/create", methods=["POST"])
def create_market():
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated."})
    data     = request.json
    question = data.get("question", "").strip()
    options  = [o.strip() for o in data.get("options", []) if o.strip()]
    if not question or len(options) < 2:
        return jsonify({"success": False, "message": "Need a question and at least 2 options."})
    mid        = str(uuid.uuid4())[:8].upper()
    tx_id, real = try_real_payment(HOUSE["private_key"], HOUSE["address"],
                                   HOUSE["address"], 0, f"MARBET:CREATE:{mid}")
    markets[mid] = {
        "id": mid, "creator": session["username"], "question": question,
        "options": options, "resolved": False, "winner": None, "deleted": False,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tx_id": tx_id, "real_tx": real,
    }
    save_json(MARKETS_FILE, markets)
    return jsonify({"success": True, "message": f"Market #{mid} deployed!",
                    "market_id": mid, "tx_id": tx_id, "real_tx": real})

@app.route("/api/markets/<mid>/bet", methods=["POST"])
def place_bet(mid):
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated."})
    if mid not in markets:
        return jsonify({"success": False, "message": "Market not found."})
    m = markets[mid]
    if m["resolved"] or m.get("deleted"):
        return jsonify({"success": False, "message": "Market is closed."})
    data   = request.json
    option = data.get("option", "").strip()
    try:
        amount_algo = float(data.get("amount_algo", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid amount."})
    if option not in m["options"]:
        return jsonify({"success": False, "message": "Invalid option."})
    if amount_algo < 0.01:
        return jsonify({"success": False, "message": "Minimum bet is 0.01 ALGO."})
    amount_micro = int(amount_algo * 1_000_000)
    try:
        debit(session["username"], amount_micro)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)})
    u = users[session["username"]]
    tx_id, real = try_real_payment(u["private_key"], u["address"],
                                   HOUSE["address"], amount_micro,
                                   f"MARBET:BET:{mid}:{option}")
    HOUSE["simulated_balance"] = HOUSE.get("simulated_balance", 0) + amount_micro
    save_json(HOUSE_FILE, HOUSE)
    bet_id = str(uuid.uuid4())[:12]
    bets[bet_id] = {
        "id": bet_id, "user": session["username"], "market_id": mid,
        "option": option, "amount_microalgo": amount_micro,
        "tx_id": tx_id, "real_tx": real,
        "placed_at": datetime.now().isoformat(),
        "refunded": False, "payout_tx": None,
    }
    save_json(BETS_FILE, bets)
    new_bal = user_balance(users[session["username"]])
    return jsonify({"success": True,
                    "message": f"Bet placed! {amount_algo} ALGO on '{option}'",
                    "tx_id": tx_id, "real_tx": real, "bet_id": bet_id,
                    "new_balance_algo": round(new_bal / 1_000_000, 4)})

@app.route("/api/markets/<mid>/resolve", methods=["POST"])
def resolve_market(mid):
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated."})
    if mid not in markets:
        return jsonify({"success": False, "message": "Market not found."})
    m = markets[mid]
    if m["creator"] != session["username"]:
        return jsonify({"success": False, "message": "Only the creator can resolve."})
    if m["resolved"]:
        return jsonify({"success": False, "message": "Already resolved."})
    winner = request.json.get("winner", "").strip()
    if winner not in m["options"]:
        return jsonify({"success": False, "message": "Invalid winner option."})
    m["resolved"] = True
    m["winner"]   = winner
    winning_bets = [b for b in bets.values()
                    if b["market_id"] == mid and b["option"] == winner and not b.get("refunded")]
    all_bets     = [b for b in bets.values()
                    if b["market_id"] == mid and not b.get("refunded")]
    total_pool   = sum(b["amount_microalgo"] for b in all_bets)
    winning_pool = sum(b["amount_microalgo"] for b in winning_bets)
    payout_results = []
    for b in winning_bets:
        if winning_pool == 0:
            break
        payout = int((b["amount_microalgo"] / winning_pool) * total_pool * 0.97)
        if payout < 1000:
            continue
        u_addr = users[b["user"]]["address"]
        p_tx, real = try_real_payment(HOUSE["private_key"], HOUSE["address"],
                                      u_addr, payout, f"MARBET:PAYOUT:{mid}:{b['id']}")
        credit(b["user"], payout)
        HOUSE["simulated_balance"] = max(0, HOUSE.get("simulated_balance", 0) - payout)
        b["payout_tx"] = p_tx
        payout_results.append({"user": b["user"], "algo": round(payout/1e6, 4),
                                "tx_id": p_tx, "real_tx": real})
    save_json(HOUSE_FILE, HOUSE)
    save_json(MARKETS_FILE, markets)
    save_json(BETS_FILE, bets)
    return jsonify({"success": True,
                    "message": f"Resolved! Winner: '{winner}'. {len(payout_results)} payout(s) sent.",
                    "payouts": payout_results, "pool_algo": round(total_pool/1e6, 4)})

@app.route("/api/markets/<mid>/delete", methods=["DELETE"])
def delete_market(mid):
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated."})
    if mid not in markets:
        return jsonify({"success": False, "message": "Market not found."})
    m = markets[mid]
    if m["creator"] != session["username"]:
        return jsonify({"success": False, "message": "Only the creator can delete."})
    if m["resolved"]:
        return jsonify({"success": False, "message": "Cannot delete a resolved market."})
    refunds = []
    for b in bets.values():
        if b["market_id"] == mid and not b.get("refunded"):
            r_tx, real = try_real_payment(HOUSE["private_key"], HOUSE["address"],
                                          users[b["user"]]["address"],
                                          b["amount_microalgo"],
                                          f"MARBET:REFUND:{mid}:{b['id']}")
            credit(b["user"], b["amount_microalgo"])
            HOUSE["simulated_balance"] = max(0, HOUSE.get("simulated_balance", 0) - b["amount_microalgo"])
            b["refunded"] = True; b["refund_tx"] = r_tx
            refunds.append({"user": b["user"], "algo": round(b["amount_microalgo"]/1e6, 4), "tx_id": r_tx})
    m["deleted"] = True
    save_json(HOUSE_FILE, HOUSE)
    save_json(MARKETS_FILE, markets)
    save_json(BETS_FILE, bets)
    return jsonify({"success": True,
                    "message": f"Market #{mid} deleted. {len(refunds)} bet(s) refunded.",
                    "refunds": refunds})

@app.route("/api/my-bets")
def my_bets():
    if "username" not in session:
        return jsonify({"success": False})
    my = [b for b in bets.values() if b["user"] == session["username"]]
    for b in my:
        mkt = markets.get(b["market_id"], {})
        b["market_question"] = mkt.get("question", "Unknown")
        b["market_winner"]   = mkt.get("winner")
        b["market_resolved"] = mkt.get("resolved", False)
    return jsonify({"success": True,
                    "bets": sorted(my, key=lambda x: x["placed_at"], reverse=True)})

@app.route("/api/faucet", methods=["POST"])
def faucet():
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated."})
    u = users.get(session["username"])
    if not u:
        return jsonify({"success": False, "message": "User not found."})
    FAUCET_AMOUNT = 100_000_000  # 100 ALGO
    DAILY_LIMIT   = 2
    claims = u.get("faucet_claims", 0)
    if claims >= DAILY_LIMIT:
        return jsonify({"success": False, "message": f"Faucet limit reached ({DAILY_LIMIT} claims max)."})
    credit(session["username"], FAUCET_AMOUNT)
    u["faucet_claims"] = claims + 1
    save_json(USERS_FILE, users)
    tx_id = f"FAUCET-{uuid.uuid4().hex[:16].upper()}"
    new_bal = user_balance(users[session["username"]])
    return jsonify({
        "success": True,
        "message": f"100 ALGO added! ({DAILY_LIMIT - u['faucet_claims']} claim(s) remaining)",
        "tx_id": tx_id,
        "new_balance_algo": round(new_bal / 1_000_000, 4),
    })

@app.route("/api/transactions")
def transactions():
    if "username" not in session:
        return jsonify({"success": False})
    u    = users.get(session["username"])
    name = session["username"]
    txs  = []
    for b in bets.values():
        if b["user"] == name:
            txs.append({
                "type":    "BET",
                "label":   f"Bet on '{b['option']}' — #{b['market_id']}",
                "amount":  -b["amount_microalgo"],
                "tx_id":   b["tx_id"],
                "real_tx": b.get("real_tx", False),
                "time":    b["placed_at"],
            })
        if b.get("payout_tx") and b["user"] == name:
            txs.append({
                "type":    "PAYOUT",
                "label":   f"Payout — #{b['market_id']} won '{b['option']}'",
                "amount":  int(b["amount_microalgo"] * 0.97),
                "tx_id":   b["payout_tx"],
                "real_tx": b.get("real_tx", False),
                "time":    b["placed_at"],
            })
        if b.get("refund_tx") and b["user"] == name:
            txs.append({
                "type":    "REFUND",
                "label":   f"Refund — market #{b['market_id']} deleted",
                "amount":  b["amount_microalgo"],
                "tx_id":   b["refund_tx"],
                "real_tx": b.get("real_tx", False),
                "time":    b["placed_at"],
            })
    txs.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"success": True, "transactions": txs,
                    "address": u["address"],
                    "balance_algo": round(user_balance(u) / 1_000_000, 4)})

@app.route("/api/house-ledger")
def house_ledger():
    all_bets  = [b for b in bets.values() if not b.get("refunded")]
    total_in  = sum(b["amount_microalgo"] for b in all_bets)
    total_out = sum(b["amount_microalgo"] for b in bets.values()
                    if b.get("payout_tx") or b.get("refund_tx"))
    entries = []
    for b in sorted(bets.values(), key=lambda x: x["placed_at"], reverse=True):
        mkt = markets.get(b["market_id"], {})
        entries.append({
            "user":     b["user"],
            "type":     "REFUND" if b.get("refunded") else "BET",
            "market":   b["market_id"],
            "question": mkt.get("question",""),
            "option":   b["option"],
            "algo":     round(b["amount_microalgo"]/1e6, 4),
            "tx_id":    b["tx_id"],
            "real_tx":  b.get("real_tx", False),
            "time":     b["placed_at"][:16],
        })
    return jsonify({
        "success": True,
        "house_address": HOUSE["address"],
        "house_balance": round(HOUSE.get("simulated_balance",0)/1e6, 4),
        "total_in_algo":  round(total_in/1e6, 4),
        "total_out_algo": round(total_out/1e6, 4),
        "entries": entries,
        "market_count": len([m for m in markets.values() if not m.get("deleted")]),
        "user_count":   len(users),
    })

# ── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  MARBET — Prediction Markets on Algorand")
    print(f"{'='*60}")
    print(f"  House wallet : {HOUSE['address']}")
    print(f"  Algorand node: {active_endpoint}")
    print(f"  Starting bal : 1,000 ALGO per user (simulated)")
    print(f"{'='*60}\n")
    app.run(debug=True, host="0.0.0.0", port=5000)