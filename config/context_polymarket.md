# Polymarket API Documentation

Polymarket is the world's largest prediction market platform enabling users to trade on future event outcomes through tokenized shares. The platform combines accurate, unbiased probability assessments with decentralized trading infrastructure running on Polygon. Shares representing event outcomes trade between $0-$1 USDC, with winning outcomes paying $1 per share upon market resolution. Unlike traditional sportsbooks, Polymarket operates peer-to-peer through a Central Limit Order Book (CLOB), allowing users to buy and sell positions before events conclude.

This documentation covers the complete Polymarket API ecosystem including the Gamma Markets API for market data, CLOB API for order placement and management, Data API for user positions and trades, and WebSocket connections for real-time updates. Developers can integrate these APIs to build trading interfaces, automated trading systems, analytics platforms, or research tools. The platform supports multiple authentication methods including EOA wallets, email-based Magic Link accounts, and browser wallets like MetaMask.

## List Markets

Retrieve available prediction markets with filtering, pagination, and sorting options.

```bash
# Get first 10 active markets sorted by volume
curl "https://gamma-api.polymarket.com/markets?limit=10&active=true&order=volumeNum&ascending=false"

# Filter markets by tag and date range
curl "https://gamma-api.polymarket.com/markets?tag_id=5&start_date_min=2025-01-01T00:00:00Z&end_date_max=2025-12-31T23:59:59Z"

# Get markets by specific condition IDs
curl "https://gamma-api.polymarket.com/markets?condition_ids=0xdd22472e552920b8438158ea7238bfadfa4f736aa4cee91a6b86c39ead110917"

# Response includes market details with pricing and volume
# {
#   "id": "12345",
#   "question": "Will Bitcoin reach $100k in 2025?",
#   "slug": "bitcoin-100k-2025",
#   "conditionId": "0xdd224...",
#   "clobTokenIds": "123456,789012",
#   "outcomes": "[\"Yes\",\"No\"]",
#   "outcomePrices": "[\"0.65\",\"0.35\"]",
#   "volume": "1250000",
#   "liquidity": "450000",
#   "endDate": "2025-12-31T23:59:59Z",
#   "active": true,
#   "closed": false,
#   "enableOrderBook": true,
#   "orderPriceMinTickSize": 0.01,
#   "orderMinSize": 1
# }
```

## Get User Positions

Retrieve current open positions for a specified user address with P&L calculations.

```python
import requests

# Get all positions for a user sorted by token count
user_address = "0x56687bf447db6ffa42ffe2204a05edaa20f55839"
response = requests.get(
    "https://data-api.polymarket.com/positions",
    params={
        "user": user_address,
        "sortBy": "TOKENS",
        "sortDirection": "DESC",
        "limit": 100,
        "sizeThreshold": 1  # Filter out positions smaller than 1 token
    }
)

positions = response.json()
# [
#   {
#     "proxyWallet": "0x566...",
#     "asset": "123456789",
#     "conditionId": "0xdd224...",
#     "size": 150.5,
#     "avgPrice": 0.45,
#     "initialValue": 67.73,
#     "currentValue": 97.83,
#     "curPrice": 0.65,
#     "cashPnl": 30.10,
#     "percentPnl": 44.43,
#     "realizedPnl": 5.50,
#     "title": "Bitcoin to reach $100k",
#     "outcome": "Yes",
#     "redeemable": false,
#     "mergeable": false,
#     "negativeRisk": false
#   }
# ]

# Filter positions by specific market
market_positions = requests.get(
    "https://data-api.polymarket.com/positions",
    params={
        "user": user_address,
        "market": ["0xdd22472e552920b8438158ea7238bfadfa4f736aa4cee91a6b86c39ead110917"]
    }
).json()
```

## Get User Trades

Query trade history for users or markets with filtering and pagination.

```javascript
// Get recent trades for a specific user
const axios = require('axios');

async function getUserTrades(userAddress) {
  const response = await axios.get('https://data-api.polymarket.com/trades', {
    params: {
      user: userAddress,
      limit: 50,
      offset: 0,
      takerOnly: true,  // Only show trades where user was taker
      side: 'BUY'  // Filter by BUY or SELL
    }
  });

  return response.data;
  // [
  //   {
  //     "proxyWallet": "0x56687...",
  //     "side": "BUY",
  //     "asset": "123456789",
  //     "conditionId": "0xdd224...",
  //     "size": 25.5,
  //     "price": 0.48,
  //     "timestamp": 1704067200,
  //     "title": "Bitcoin to reach $100k",
  //     "outcome": "Yes",
  //     "transactionHash": "0xabc123..."
  //   }
  // ]
}

// Get all trades for a specific market
async function getMarketTrades(conditionId) {
  const response = await axios.get('https://data-api.polymarket.com/trades', {
    params: {
      market: [conditionId],
      filterType: 'CASH',
      filterAmount: 100,  // Minimum $100 trades
      limit: 100
    }
  });

  return response.data;
}
```

## Place First Order (Python)

Initialize CLOB client and place a limit order using the Python SDK.

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# Configuration
host = "https://clob.polymarket.com"
private_key = "YOUR_PRIVATE_KEY"  # From Magic Link or wallet
chain_id = 137  # Polygon mainnet
proxy_address = "YOUR_PROXY_ADDRESS"  # From Polymarket profile

# Initialize client for Email/Magic login
client = ClobClient(
    host,
    key=private_key,
    chain_id=chain_id,
    signature_type=1,  # 1=Magic, 2=Browser Wallet, 0=EOA
    funder=proxy_address
)

# Create API credentials (do once, then reuse)
client.set_api_creds(client.create_or_derive_api_creds())

# Place limit order to buy 100 YES shares at $0.55
token_id = "123456789012345678901234567890"  # From markets API
order_args = OrderArgs(
    price=0.55,
    size=100.0,
    side=BUY,
    token_id=token_id
)

signed_order = client.create_order(order_args)
response = client.post_order(signed_order, OrderType.GTC)

# Response contains order ID and status
# {
#   "orderID": "0xabc123...",
#   "success": true,
#   "status": "LIVE"
# }

# Cancel order
client.cancel(order_id="0xabc123...")

# Get open orders
open_orders = client.get_orders()
```

## Place First Order (TypeScript)

Initialize CLOB client and place orders using the TypeScript SDK.

```typescript
import { ClobClient, OrderType, Side } from "@polymarket/clob-client";
import { Wallet } from "@ethersproject/wallet";

const host = 'https://clob.polymarket.com';
const privateKey = 'YOUR_PRIVATE_KEY';
const funder = 'YOUR_PROXY_ADDRESS';
const signer = new Wallet(privateKey);

// Create or derive API credentials
async function initializeClient() {
  const creds = await new ClobClient(host, 137, signer).createOrDeriveApiKey();

  // Initialize with signature type: 0=EOA, 1=Magic, 2=Browser Wallet
  const clobClient = new ClobClient(
    host,
    137,
    signer,
    creds,
    1,  // signatureType
    funder
  );

  return clobClient;
}

// Place order
async function placeOrder() {
  const client = await initializeClient();

  const response = await client.createAndPostOrder(
    {
      tokenID: "123456789012345678901234567890",
      price: 0.55,
      side: Side.BUY,
      size: 100,
      feeRateBps: 0
    },
    {
      tickSize: "0.01",  // From market metadata
      negRisk: false     // From market metadata
    },
    OrderType.GTC
  );

  console.log(response);
  // { orderID: "0xabc...", success: true, status: "LIVE" }
}

// Cancel order
async function cancelOrder(orderId: string) {
  const client = await initializeClient();
  await client.cancelOrder({ orderID: orderId });
}

placeOrder().catch(console.error);
```

## Get Order Book

Retrieve current bids and asks for a specific token.

```bash
# Get order book for token
curl "https://clob.polymarket.com/book?token_id=123456789012345678901234567890"

# Response structure
# {
#   "market": "0x1b6f76e5b8587ee896c35847e12d11e75290a8c3934c5952e8a9d6e4c6f03cfa",
#   "asset_id": "123456789012345678901234567890",
#   "timestamp": "2025-10-08T12:00:00Z",
#   "hash": "0xabc123def456...",
#   "bids": [
#     { "price": "0.5500", "size": "250.5" },
#     { "price": "0.5400", "size": "180.0" },
#     { "price": "0.5300", "size": "420.2" }
#   ],
#   "asks": [
#     { "price": "0.5600", "size": "150.3" },
#     { "price": "0.5700", "size": "300.0" },
#     { "price": "0.5800", "size": "275.8" }
#   ],
#   "min_order_size": "1.0",
#   "tick_size": "0.01",
#   "neg_risk": false
# }

# Calculate spread
# best_bid = 0.55, best_ask = 0.56
# spread = 0.56 - 0.55 = 0.01 (1 cent or ~1.8%)
```

## Get Midpoint Price

Retrieve the current midpoint price between best bid and ask.

```python
import requests

def get_midpoint_price(token_id):
    response = requests.get(
        "https://clob.polymarket.com/midpoint",
        params={"token_id": token_id}
    )

    if response.status_code == 200:
        data = response.json()
        return float(data["mid"])
    elif response.status_code == 404:
        print("No order book exists for this token")
        return None
    else:
        print(f"Error: {response.json()['error']}")
        return None

# Get midpoint for token
token_id = "123456789012345678901234567890"
midpoint = get_midpoint_price(token_id)
print(f"Midpoint price: ${midpoint:.4f}")
# Midpoint price: $0.5550

# Use for market orders or analytics
if midpoint:
    slippage_tolerance = 0.02  # 2%
    max_buy_price = midpoint * (1 + slippage_tolerance)
    min_sell_price = midpoint * (1 - slippage_tolerance)
```

## WebSocket Market Data

Subscribe to real-time order book updates for markets.

```python
from websocket import WebSocketApp
import json
import threading
import time

class MarketWebSocket:
    def __init__(self, asset_ids, api_key, api_secret, api_passphrase):
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.asset_ids = asset_ids
        self.auth = {
            "apiKey": api_key,
            "secret": api_secret,
            "passphrase": api_passphrase
        }

        self.ws = WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

    def on_open(self, ws):
        # Subscribe to market updates
        subscribe_msg = {
            "assets_ids": self.asset_ids,
            "type": "market"
        }
        ws.send(json.dumps(subscribe_msg))

        # Start ping thread to keep connection alive
        threading.Thread(target=self.ping_loop, args=(ws,), daemon=True).start()

    def on_message(self, ws, message):
        if message == "PONG":
            return

        data = json.loads(message)
        # Handle order book updates
        # {
        #   "asset_id": "123456...",
        #   "hash": "0xabc...",
        #   "timestamp": "2025-10-08T12:00:00Z",
        #   "bids": [{"price": "0.55", "size": "100"}],
        #   "asks": [{"price": "0.56", "size": "150"}]
        # }
        print(f"Market update: {data}")

    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"Connection closed: {close_msg}")

    def ping_loop(self, ws):
        while True:
            ws.send("PING")
            time.sleep(10)

    def run(self):
        self.ws.run_forever()

# Usage
asset_ids = [
    "109681959945973300464568698402968596289258214226684818748321941747028805721376"
]

# Get API credentials from CLOB client
# See "Place First Order" examples for credential generation
ws = MarketWebSocket(
    asset_ids=asset_ids,
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    api_passphrase="YOUR_PASSPHRASE"
)

ws.run()
```

## WebSocket User Updates

Subscribe to real-time updates for user orders and fills.

```python
class UserWebSocket:
    def __init__(self, condition_ids, api_key, api_secret, api_passphrase):
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.condition_ids = condition_ids
        self.auth = {
            "apiKey": api_key,
            "secret": api_secret,
            "passphrase": api_passphrase
        }

        self.ws = WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

    def on_open(self, ws):
        subscribe_msg = {
            "markets": self.condition_ids,
            "type": "user",
            "auth": self.auth
        }
        ws.send(json.dumps(subscribe_msg))
        threading.Thread(target=self.ping_loop, args=(ws,), daemon=True).start()

    def on_message(self, ws, message):
        if message == "PONG":
            return

        data = json.loads(message)
        # Handle order status updates and fills
        # {
        #   "event_type": "fill",
        #   "order_id": "0xabc...",
        #   "asset_id": "123456...",
        #   "price": "0.55",
        #   "size": "25.5",
        #   "side": "BUY",
        #   "timestamp": 1704067200
        # }
        print(f"User update: {data}")

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"Closed: {close_msg}")

    def ping_loop(self, ws):
        while True:
            ws.send("PING")
            time.sleep(10)

    def run(self):
        self.ws.run_forever()

# Subscribe to user updates for specific markets
condition_ids = ["0xdd22472e552920b8438158ea7238bfadfa4f736aa4cee91a6b86c39ead110917"]

user_ws = UserWebSocket(
    condition_ids=condition_ids,
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    api_passphrase="YOUR_PASSPHRASE"
)

user_ws.run()
```

## Derive API Keys

Generate authentication credentials for WebSocket and authenticated API endpoints.

```python
from py_clob_client.client import ClobClient

# Initialize client (see "Place First Order" for full setup)
client = ClobClient(
    "https://clob.polymarket.com",
    key="YOUR_PRIVATE_KEY",
    chain_id=137,
    signature_type=1,
    funder="YOUR_PROXY_ADDRESS"
)

# Derive API credentials
api_creds = client.derive_api_key()
# {
#   "apiKey": "abc123...",
#   "secret": "def456...",
#   "passphrase": "ghi789..."
# }

# Use these credentials for WebSocket connections and authenticated endpoints
print(f"API Key: {api_creds.api_key}")
print(f"Secret: {api_creds.api_secret}")
print(f"Passphrase: {api_creds.api_passphrase}")

# Store credentials securely - reuse them instead of generating new ones
```

```typescript
import { ClobClient } from "@polymarket/clob-client";
import { Wallet } from "@ethersproject/wallet";

async function deriveApiKeys() {
  const host = 'https://clob.polymarket.com';
  const signer = new Wallet("YOUR_PRIVATE_KEY");

  const clobClient = new ClobClient(host, 137, signer);
  const apiKey = await clobClient.deriveApiKey();

  console.log(apiKey);
  // {
  //   apiKey: "abc123...",
  //   secret: "def456...",
  //   passphrase: "ghi789..."
  // }

  return apiKey;
}

deriveApiKeys().catch(console.error);
```

## Understanding Negative Risk Markets

Handle special market types where only one outcome can win.

```python
import requests

# Check if market is negative risk
def check_negative_risk(slug):
    response = requests.get(
        f"https://gamma-api.polymarket.com/markets",
        params={"slug": slug}
    )

    market = response.json()[0]
    events = market.get("events", [])

    if events and len(events) > 0:
        event = events[0]
        neg_risk = event.get("negRisk", False)
        enable_neg_risk = event.get("enableNegRisk", False)

        print(f"Negative Risk: {neg_risk}")
        print(f"Enable Negative Risk: {enable_neg_risk}")

        # For negative risk markets, use negRisk=True in order args
        return neg_risk or enable_neg_risk

    return False

# Place order on negative risk market
from py_clob_client.clob_types import OrderArgs

is_neg_risk = check_negative_risk("presidential-election-2024")

order_args = OrderArgs(
    price=0.65,
    size=100.0,
    side=BUY,
    token_id="123456789",
    negrisk=is_neg_risk  # Important: set this flag!
)

# Note: Negative risk allows converting NO shares in one outcome
# to YES shares in all other outcomes for capital efficiency
```

## Complete Trading Bot Example

Full example integrating market data, order placement, and position tracking.

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
import requests
import time

class TradingBot:
    def __init__(self, private_key, proxy_address, signature_type=1):
        self.client = ClobClient(
            "https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=signature_type,
            funder=proxy_address
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())
        self.proxy_address = proxy_address

    def get_market_info(self, slug):
        """Fetch market metadata"""
        response = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"slug": slug}
        )
        return response.json()[0] if response.json() else None

    def get_current_price(self, token_id):
        """Get midpoint price for token"""
        response = requests.get(
            "https://clob.polymarket.com/midpoint",
            params={"token_id": token_id}
        )
        return float(response.json()["mid"]) if response.status_code == 200 else None

    def get_positions(self):
        """Get current open positions"""
        response = requests.get(
            "https://data-api.polymarket.com/positions",
            params={
                "user": self.proxy_address,
                "sortBy": "TOKENS",
                "sortDirection": "DESC"
            }
        )
        return response.json()

    def place_order(self, token_id, price, size, side, neg_risk=False):
        """Place limit order"""
        order_args = OrderArgs(
            price=price,
            size=size,
            side=side,
            token_id=token_id,
            negrisk=neg_risk
        )

        signed_order = self.client.create_order(order_args)
        response = self.client.post_order(signed_order, OrderType.GTC)
        return response

    def run_strategy(self, slug, target_price, size):
        """Simple buy-low strategy"""
        market = self.get_market_info(slug)
        if not market:
            print("Market not found")
            return

        token_ids = market["clobTokenIds"].split(",")
        yes_token = token_ids[0]

        print(f"Monitoring {market['question']}")

        while True:
            current_price = self.get_current_price(yes_token)

            if current_price and current_price <= target_price:
                print(f"Price {current_price} <= target {target_price}, placing order")

                response = self.place_order(
                    token_id=yes_token,
                    price=target_price,
                    size=size,
                    side=BUY,
                    neg_risk=market.get("negRisk", False)
                )

                print(f"Order placed: {response}")
                break

            print(f"Current price: {current_price}, waiting...")
            time.sleep(30)

# Usage
bot = TradingBot(
    private_key="YOUR_PRIVATE_KEY",
    proxy_address="YOUR_PROXY_ADDRESS"
)

# Run strategy: buy when price drops to 0.50
bot.run_strategy(
    slug="bitcoin-100k-2025",
    target_price=0.50,
    size=100
)

# Check positions
positions = bot.get_positions()
for pos in positions:
    print(f"{pos['title']}: {pos['size']} @ {pos['avgPrice']} (P&L: {pos['cashPnl']})")
```

## Summary

The Polymarket API provides comprehensive access to prediction market trading through three primary interfaces: the Gamma Markets API for discovering and filtering markets, the CLOB API for placing and managing orders, and the Data API for tracking positions and trades. WebSocket connections enable real-time order book updates and user notifications. All market prices represent probabilities between 0 and 1, with winning outcome shares redeemable for $1 USDC upon resolution. The platform supports standard limit orders, market orders, and advanced features like negative risk markets for capital efficiency.

Integration patterns typically involve fetching market metadata from Gamma, monitoring prices via the CLOB midpoint endpoint or WebSocket, placing orders through the CLOB client libraries, and tracking positions via the Data API. The Python and TypeScript SDKs abstract signature complexity and handle order construction automatically. Authentication uses EIP-712 signatures with three signature types supporting EOA wallets, Magic Link email accounts, and browser wallets. Rate limits and order size constraints apply based on available balances, with continuous monitoring of allowances and on-chain state to ensure order validity.
