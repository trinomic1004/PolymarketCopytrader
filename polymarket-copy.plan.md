<!-- 9d11e06e-0523-47f4-a3cc-8689674c06f8 a03d5437-70e6-46ad-b08a-63c06e21328a -->
# Polymarket Multi-Trader Copytrading CLI

## Architecture Overview

The system will support **multiple trader wallets simultaneously** with **portfolio-proportional allocation**. Each trader gets a dedicated capital allocation, and trades are mirrored based on what percentage of their portfolio they're risking.

**Core Components:**

1. **Configuration Manager** - Multi-trader settings, per-trader capital allocation
2. **Portfolio Tracker** - Monitors each trader's total portfolio value in real-time
3. **Trade Monitor** - Watches all configured traders simultaneously  
4. **Risk Manager** - Validates trades with global + per-trader limits
5. **Trade Executor** - Executes proportionally-sized orders
6. **CLI Interface** - Start/stop/status commands with per-trader reporting

## Implementation Details

### 1. Project Structure & Dependencies

```
polymarket-copytrade/
├── config/
│   └── settings.yaml         # Multi-trader configuration
├── src/
│   ├── __init__.py
│   ├── cli.py               # CLI entry point
│   ├── config_manager.py    # Load/validate multi-trader config
│   ├── portfolio_tracker.py # Track trader portfolio values
│   ├── monitor.py           # Multi-trader monitoring
│   ├── risk_manager.py      # Global + per-trader risk validation
│   ├── executor.py          # Proportional trade execution
│   └── utils.py             # Logging, helpers
├── requirements.txt
├── .env.example
└── README.md
```

**Dependencies:**

- `py-clob-client` - Official Polymarket Python SDK
- `gql` + `aiohttp` - GraphQL queries to Polymarket Subgraph
- `click` - CLI framework
- `pyyaml` - Config file handling
- `python-dotenv` - Environment variables
- `asyncio` - Async multi-trader monitoring

### 2. Multi-Trader Configuration (`config_manager.py`)

```yaml
your_account:
  api_key: "env:POLYMARKET_API_KEY"
  api_secret: "env:POLYMARKET_API_SECRET"
  api_passphrase: "env:POLYMARKET_API_PASSPHRASE"
  total_capital: 5000.0         # Your total available capital

traders:
  - name: "Whale Trader"
    wallet_address: "0xabc123..."
    allocated_capital: 2000.0    # Allocate $2000 to copy this trader
    enabled: true
    
  - name: "Sharp Bettor"  
    wallet_address: "0xdef456..."
    allocated_capital: 1500.0    # Allocate $1500 to this one
    enabled: true
    
  - name: "Experimental"
    wallet_address: "0x789xyz..."
    allocated_capital: 500.0
    enabled: false               # Disabled but kept in config

risk_management:
  global:
    max_total_exposure: 5000.0   # Max across ALL traders combined
    max_single_bet: 500.0        # Absolute max for any single trade
    reserve_capital: 1000.0      # Keep this much unallocated
    
  per_trader:
    min_portfolio_value: 100.0   # Don't copy if trader portfolio < $100
    max_position_pct: 0.5        # Max 50% of allocated capital per trade
    use_portfolio_proportion: true  # Scale by trader's portfolio %
    
  market_filters:
    whitelist_categories: []     # Empty = allow all
    blacklist_categories: []     
    min_liquidity: 500.0
    
monitoring:
  poll_interval: 5               # Check for new trades every 5s
  portfolio_sync_interval: 60    # Update portfolio values every 60s

logging:
  level: "INFO"
  file: "copytrade.log"
  trades_file: "trades.csv"      # Audit trail
```

**Key Validation:**

- Sum of allocated_capital ≤ total_capital
- Each trader has valid wallet address
- Risk limits are reasonable

### 3. Portfolio Tracking with Cash Reserve Monitoring (`portfolio_tracker.py`)

**Purpose:** Track each trader's total portfolio value AND deployment rate using Polymarket Data API.

```python
import aiohttp
import asyncio

class PortfolioTracker:
    def __init__(self):
        self.portfolios = {}  # {wallet_address: portfolio_value}
        self.deployed_capital = {}  # {wallet_address: deployed_amount}
        self.deployment_rates = {}  # {wallet_address: deployment_percentage}
        self.data_api_url = "https://data-api.polymarket.com"
    
    async def sync_portfolio(self, wallet_address):
        """Query Polymarket Data API for trader's positions and calculate deployment"""
        positions = await self._fetch_positions(wallet_address)
        
        if not positions:
            return {
                'total_portfolio': 0,
                'deployed': 0,
                'cash_reserve': 0,
                'deployment_rate': 0
            }
        
        # Calculate deployed capital from current position values
        deployed = sum(float(pos['currentValue']) for pos in positions)
        
        # Calculate total portfolio (deployed + estimated reserves)
        # Use deployed capital + total P&L as proxy for portfolio size
        total_pnl = sum(float(pos['cashPnl']) for pos in positions)
        initial_investment = sum(float(pos['initialValue']) for pos in positions)
        
        # Estimate total portfolio: current deployed + any realized gains
        total_value = deployed if deployed > 0 else initial_investment
        
        # Calculate deployment rate
        deployment_rate = min(deployed / total_value, 1.0) if total_value > 0 else 0
        
        # Store values
        self.portfolios[wallet_address] = total_value
        self.deployed_capital[wallet_address] = deployed
        self.deployment_rates[wallet_address] = deployment_rate
        
        return {
            'total_portfolio': total_value,
            'deployed': deployed,
            'cash_reserve': total_value - deployed,
            'deployment_rate': deployment_rate,
            'position_count': len(positions)
        }
    
    async def _fetch_positions(self, wallet_address):
        """Fetch all open positions from Polymarket Data API"""
        async with aiohttp.ClientSession() as session:
            params = {
                'user': wallet_address,
                'sortBy': 'TOKENS',
                'sortDirection': 'DESC',
                'sizeThreshold': 0.1  # Filter out dust positions
            }
            
            async with session.get(f"{self.data_api_url}/positions", params=params) as response:
                if response.status == 200:
                    positions = await response.json()
                    # Data structure:
                    # {
                    #   "proxyWallet": "0x566...",
                    #   "asset": "123456789",
                    #   "conditionId": "0xdd224...",
                    #   "size": 150.5,
                    #   "avgPrice": 0.45,
                    #   "initialValue": 67.73,
                    #   "currentValue": 97.83,
                    #   "curPrice": 0.65,
                    #   "cashPnl": 30.10,
                    #   "percentPnl": 44.43,
                    #   "title": "Bitcoin to reach $100k",
                    #   "outcome": "Yes"
                    # }
                    return positions
                return []
    
    def get_position_percentage(self, wallet_address, trade_size):
        """Calculate what % of portfolio this trade represents"""
        portfolio_value = self.portfolios.get(wallet_address, 0)
        if portfolio_value == 0:
            return 0
        return trade_size / portfolio_value
    
    def get_deployment_rate(self, wallet_address):
        """Get trader's current deployment rate (% of capital in positions)"""
        return self.deployment_rates.get(wallet_address, 1.0)  # Default 100%
    
    def calculate_effective_allocation(self, wallet_address, allocated_capital):
        """Calculate how much of allocated capital should be available for trading"""
        deployment_rate = self.get_deployment_rate(wallet_address)
        
        # If trader is 70% deployed, you should only use 70% of allocated capital
        effective_allocation = allocated_capital * deployment_rate
        
        return effective_allocation, deployment_rate
```

**Data Source:** Polymarket Data API (`https://data-api.polymarket.com/positions`)

**Response Fields Used:**
- `currentValue` - Current USD value of position
- `initialValue` - Initial USD investment
- `cashPnl` - Realized/unrealized profit/loss
- `size` - Number of shares held
- `asset` - Token ID

**Cash Reserve Logic:**
- **Example 1:** Trader has $10k total, $7k in positions → 70% deployed → You use 70% of your allocation
- **Example 2:** Trader has $5k total, $5k in positions → 100% deployed → You use 100% of your allocation
- **Example 3:** Trader has $20k total, $8k in positions → 40% deployed → You use only 40% of your allocation (staying cautious like them)

### 4. Multi-Trader Monitoring with Exit/Sell Tracking (`monitor.py`)

**Monitor all traders in parallel:**

```python
class MultiTraderMonitor:
    def __init__(self, traders_config):
        self.traders = traders_config
        self.last_check = {}  # {wallet: timestamp}
    
    async def monitor_all_traders(self):
        """Concurrently monitor all enabled traders"""
        tasks = []
        for trader in self.traders:
            if trader['enabled']:
                task = self.monitor_trader(trader)
                tasks.append(task)
        
        # Run all monitors concurrently
        results = await asyncio.gather(*tasks)
        return results
    
    async def monitor_trader(self, trader):
        """Get new trades for a specific trader"""
        wallet = trader['wallet_address']
        
        # GraphQL query to Polymarket Subgraph
        query = """
        query GetTrades($wallet: String!, $since: Int!) {
          orders(
            where: {maker: $wallet, timestamp_gte: $since}
            orderBy: timestamp
            orderDirection: desc
          ) {
            id
            market
            tokenID
            side
            size
            price
            timestamp
          }
        }
        """
        
        new_trades = await self._execute_query(query, {
            'wallet': wallet.lower(),
            'since': self.last_check.get(wallet, 0)
        })
        
        self.last_check[wallet] = int(time.time())
        
        # Attach trader info to each trade
        for trade in new_trades:
            trade['trader_name'] = trader['name']
            trade['trader_wallet'] = wallet
            trade['allocated_capital'] = trader['allocated_capital']
        
        return new_trades
```

**Key Features:**

- Async concurrent monitoring (all traders at once)
- Per-trader timestamp tracking
- Attach allocation context to each trade

### 5. Risk Management with Multi-Trader Support (`risk_manager.py`)

```python
class RiskManager:
    def __init__(self, config, portfolio_tracker):
        self.config = config
        self.portfolio_tracker = portfolio_tracker
        self.current_exposure = {}  # {trader_wallet: exposure}
        self.global_exposure = 0
    
    def calculate_mirror_size(self, trade):
        """Calculate proportional trade size based on trader's portfolio"""
        trader_wallet = trade['trader_wallet']
        allocated_capital = trade['allocated_capital']
        
        # Get trader's portfolio value
        trader_portfolio = self.portfolio_tracker.portfolios.get(trader_wallet, 0)
        
        if trader_portfolio == 0:
            return 0, "Trader portfolio value unknown"
        
        # Calculate position percentage
        position_pct = trade['size'] / trader_portfolio
        
        # Calculate your mirror size
        mirror_size = allocated_capital * position_pct
        
        return mirror_size, f"{position_pct*100:.1f}% of portfolio"
    
    def validate_trade(self, trade, mirror_size):
        """Validate against all risk parameters"""
        trader_wallet = trade['trader_wallet']
        
        # Check 1: Absolute max single bet
        if mirror_size > self.config['global']['max_single_bet']:
            return False, f"Exceeds max single bet: ${mirror_size:.2f}"
        
        # Check 2: Per-trader max position percentage
        allocated = trade['allocated_capital']
        position_pct = mirror_size / allocated
        max_pct = self.config['per_trader']['max_position_pct']
        
        if position_pct > max_pct:
            return False, f"Exceeds max position %: {position_pct*100:.1f}%"
        
        # Check 3: Global exposure limit
        new_global = self.global_exposure + mirror_size
        if new_global > self.config['global']['max_total_exposure']:
            return False, f"Exceeds global exposure: ${new_global:.2f}"
        
        # Check 4: Per-trader exposure tracking
        trader_exposure = self.current_exposure.get(trader_wallet, 0)
        if trader_exposure + mirror_size > allocated:
            return False, f"Exceeds allocated capital for trader"
        
        # Check 5: Market filters
        if not self._validate_market_filters(trade):
            return False, "Filtered by market rules"
        
        return True, "OK"
```

### 6. Trade Execution with Position Adjustments (`executor.py`)

```python
class TradeExecutor:
    def __init__(self, api_credentials):
        self.client = ClobClient(
            host="https://clob.polymarket.com",
            key=api_credentials['api_key'],
            chain_id=137
        )
        self.our_positions = {}  # Track our mirrored positions
    
    async def execute_mirror_trade(self, original_trade, mirror_size):
        """Execute the mirrored trade with calculated size"""
        try:
            order = self.client.create_order(
                token_id=original_trade['tokenID'],
                price=original_trade['price'],
                size=mirror_size,  # Your proportional size
                side=original_trade['side'],
                orderType='GTC'
            )
            
            result = self.client.post_order(order)
            
            # Track our position
            position_key = f"{original_trade['market']}_{original_trade['tokenID']}"
            if position_key not in self.our_positions:
                self.our_positions[position_key] = 0
            self.our_positions[position_key] += mirror_size
            
            return {
                'success': True,
                'order_id': result['orderID'],
                'original_size': original_trade['size'],
                'mirror_size': mirror_size,
                'trader': original_trade['trader_name']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def execute_position_reduction(self, event, reduction_pct):
        """Reduce existing position by percentage"""
        position_key = f"{event['market']}_{event['tokenID']}"
        
        if position_key not in self.our_positions:
            return {
                'success': False,
                'error': 'No position to reduce'
            }
        
        current_size = self.our_positions[position_key]
        reduce_amount = current_size * reduction_pct
        
        try:
            # Create SELL order to reduce position
            order = self.client.create_order(
                token_id=event['tokenID'],
                price=None,  # Market order for immediate execution
                size=reduce_amount,
                side='SELL',
                orderType='FOK'  # Fill or kill
            )
            
            result = self.client.post_order(order)
            
            # Update tracked position
            self.our_positions[position_key] -= reduce_amount
            if self.our_positions[position_key] < 0.01:
                del self.our_positions[position_key]
            
            return {
                'success': True,
                'action': 'REDUCE',
                'reduction_pct': reduction_pct * 100,
                'amount': reduce_amount,
                'remaining': self.our_positions.get(position_key, 0)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def execute_position_exit(self, event):
        """Fully close a position"""
        position_key = f"{event['market']}_{event['tokenID']}"
        
        if position_key not in self.our_positions:
            return {
                'success': False,
                'error': 'No position to exit'
            }
        
        current_size = self.our_positions[position_key]
        
        try:
            # Create SELL order to close entire position
            order = self.client.create_order(
                token_id=event['tokenID'],
                price=None,  # Market order
                size=current_size,
                side='SELL',
                orderType='FOK'
            )
            
            result = self.client.post_order(order)
            
            # Remove from tracked positions
            del self.our_positions[position_key]
            
            return {
                'success': True,
                'action': 'EXIT',
                'closed_size': current_size
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def execute_position_addition(self, event, addition_size):
        """Add to existing position"""
        position_key = f"{event['market']}_{event['tokenID']}"
        
        try:
            order = self.client.create_order(
                token_id=event['tokenID'],
                price=None,  # Match current market price
                size=addition_size,
                side='BUY',
                orderType='GTC'
            )
            
            result = self.client.post_order(order)
            
            # Update tracked position
            if position_key not in self.our_positions:
                self.our_positions[position_key] = 0
            self.our_positions[position_key] += addition_size
            
            return {
                'success': True,
                'action': 'ADD',
                'added_size': addition_size,
                'new_total': self.our_positions[position_key]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
```

### 7. CLI Interface with Multi-Trader Status (`cli.py`)

```python
@click.group()
def cli():
    """Polymarket Multi-Trader Copy Trading CLI"""
    pass

@cli.command()
@click.option('--config', default='config/settings.yaml')
def start(config):
    """Start monitoring and copying all enabled traders"""
    # Initialize all services
    # Start async monitoring loop
    pass

@cli.command()
def status():
    """Show status for all traders"""
    # Display:
    # - Per trader: allocated capital, current exposure, # of open positions
    # - Global: total exposure, available capital
    # - Recent trades (last 10)
    pass

@cli.command()
@click.option('--trader-name')
def pause(trader_name):
    """Pause copying a specific trader"""
    pass

@cli.command()
@click.option('--trader-name')
def resume(trader_name):
    """Resume copying a specific trader"""
    pass

@cli.command()
def stop():
    """Stop all copytrading"""
    pass
```

### 8. Main Monitoring Loop

```python
async def monitor_and_copy_multi_trader():
    portfolio_tracker = PortfolioTracker()
    monitor = MultiTraderMonitor(config['traders'])
    risk_manager = RiskManager(config['risk_management'], portfolio_tracker)
    executor = TradeExecutor(config['your_account'])
    
    while running:
        # 1. Update portfolio values for all traders (every 60s)
        if should_sync_portfolios():
            for trader in config['traders']:
                if trader['enabled']:
                    await portfolio_tracker.sync_portfolio(trader['wallet_address'])
        
        # 2. Check for new trades from all traders (concurrently)
        all_new_trades = await monitor.monitor_all_traders()
        
        # 3. Flatten trades from all traders
        for trades_list in all_new_trades:
            for trade in trades_list:
                # Calculate proportional size
                mirror_size, reason = risk_manager.calculate_mirror_size(trade)
                
                # Validate against risk rules
                if mirror_size > 0:
                    valid, msg = risk_manager.validate_trade(trade, mirror_size)
                    
                    if valid:
                        # Execute mirror trade
                        result = await executor.execute_mirror_trade(trade, mirror_size)
                        
                        if result['success']:
                            logger.info(f"✓ Copied {trade['trader_name']}: "
                                      f"${mirror_size:.2f} ({reason})")
                            risk_manager.update_exposure(trade, mirror_size)
                        else:
                            logger.error(f"✗ Failed to copy: {result['error']}")
                    else:
                        logger.warning(f"⊘ Rejected: {msg}")
        
        # 4. Wait before next check
        await asyncio.sleep(config['monitoring']['poll_interval'])
```

### 9. Key Features Summary

**Portfolio-Proportional Copying:**

- If trader bets 10% of their portfolio → you bet 10% of your allocated capital
- Automatically scales to your capital allocation
- Fair representation of trader's conviction

**Multi-Trader Management:**

- Monitor unlimited traders simultaneously
- Independent capital allocation per trader
- Enable/disable traders without removing config
- Per-trader exposure tracking

**Risk Controls:**

- Global exposure limit (across all traders)
- Per-trader exposure limit (allocated capital)
- Absolute max bet size
- Market category filters
- Minimum liquidity checks

**Status Reporting:**

```
Trader            Allocated    Exposed    Utilization    P&L      Trades
-------------------------------------------------------------------
Whale Trader      $2,000      $1,450     72.5%          +$125    12
Sharp Bettor      $1,500      $890       59.3%          -$45     8
-------------------------------------------------------------------
TOTAL             $3,500      $2,340     66.9%          +$80     20

Global Exposure: $2,340 / $5,000 (46.8%)
Available Capital: $2,660
```

## Technical Considerations

1. **GraphQL Rate Limits:** Polymarket Subgraph may rate limit. Implement exponential backoff.

2. **Portfolio Calculation:** Query all active positions + calculate current value based on latest market prices.

3. **Concurrent Monitoring:** Use `asyncio.gather()` to monitor all traders in parallel without blocking.

4. **Exposure Tracking:** Update exposure when trades execute AND when positions close.

5. **Capital Efficiency:** Reserve some capital for multiple simultaneous trades.

6. **Trade Timing:** Small delay between traders means prices may shift slightly.

## Security & Best Practices

- Never allocate more than `total_capital`
- Keep reserve capital for fees and slippage
- Start with small allocations to test
- Monitor global exposure closely
- Implement emergency stop (pause all traders)
- Log every decision for audit trail