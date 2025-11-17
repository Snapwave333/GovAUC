# GovAUC - Government Auction Sniper Bot

A powerful, AI-driven bot that automatically scrapes government auction sites, analyzes deals, and snipes high-value assets for profit.

## Overview

GovAUC exploits the fact that governments are legally required to auction off seized and surplus property through intentionally obscure, fragmented online platforms. This bot:

1. **Scrapes** 1000+ government auction sites (GSA Auctions, police impound lots, county tax liens)
2. **Analyzes** messy listings using AI-powered data cleaning to identify high-value assets
3. **Estimates** real market values using KBB, eBay completed sales, and other pricing sources
4. **Scores** opportunities based on ROI potential, timing, and confidence
5. **Snipes** auctions automatically in the final seconds to win deals

## Features

### Web Scraping Engine
- Modular scraper framework supporting multiple site types
- Rate limiting and retry logic
- User agent rotation to avoid detection
- Support for both static and JavaScript-rendered pages
- Built-in scrapers for:
  - GSA Auctions (federal surplus)
  - GovPlanet (government vehicles & equipment)
  - PublicSurplus (state & local government)
  - Police impound lot auctions

### AI-Powered Data Cleaning
- Extracts structured data from messy government descriptions
- Automatic category detection (vehicles, electronics, real estate, jewelry, equipment)
- VIN extraction and vehicle detail parsing
- Quantity detection for bulk lots
- Condition assessment from text

### Market Value Analysis
- Multi-source price estimation:
  - Kelley Blue Book (vehicles)
  - eBay sold listings
  - Amazon retail prices
  - Metal/gemstone spot prices (jewelry)
- Weighted confidence scoring
- Automatic depreciation calculations
- ROI and profit potential computation

### Opportunity Scoring
- Scores listings from 0-1 based on:
  - Profit potential (30%)
  - ROI percentage (25%)
  - Confidence in estimate (20%)
  - Time remaining (15%)
  - Category liquidity (10%)
- Automatic "gem" identification (score >= 0.8)
- Daily opportunity reports
- Alert system for urgent deals

### Automated Sniping
- Place bids in the final seconds of auctions
- Multiple bidding strategies:
  - Conservative (50% of market value, 30s snipe)
  - Aggressive (70% of market value, 10s snipe)
  - Calculated (based on opportunity score)
- Auto-counter bidding if outbid
- Budget management and allocation
- Concurrent snipe scheduling

### Database & Persistence
- SQLite database for all data
- Track listings, bids, alerts, and reports
- Favorite listings
- Search and filter capabilities
- Historical performance tracking

### Rich CLI Dashboard
- Real-time statistics display
- Opportunity browsing
- Category filtering
- Keyword search
- Visual status indicators
- Detailed reporting

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd GovAUC

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Quick Start

```bash
# Initialize GovAUC with default configuration
govauc init

# Scrape all configured auction sites
govauc scrape --all-sites

# View the dashboard with statistics
govauc dashboard

# Find gem opportunities (high-value deals)
govauc gems

# Browse listings by category
govauc browse vehicle
govauc browse electronics

# Search for specific items
govauc search "Ford F-150"
govauc search "Dell laptops"

# Run full analysis
govauc analyze

# Generate daily report
govauc report
```

## Configuration

Copy the example config and customize:

```bash
cp config/config.example.json config/config.json
```

Key configuration options:

```json
{
  "analysis": {
    "min_profit_threshold": 100,
    "min_roi_percentage": 50,
    "gem_score_threshold": 0.8
  },
  "sniping": {
    "enabled": false,
    "default_snipe_seconds": 30
  },
  "budget": {
    "total_budget": 10000.0,
    "max_per_item": 1000.0
  }
}
```

## Adding Custom Auction Sites

```bash
# Add via CLI
govauc add-site "County Sheriff" "https://sheriff.county.gov/auctions" --type police

# Or add to config.json sites array
```

## Automated Sniping

**WARNING: Sniping places real bids with real money. Use with caution.**

```bash
# Dry run (simulate without real bids)
govauc snipe --dry-run --budget 5000

# Live sniping (will prompt for confirmation)
govauc snipe --budget 10000 --max-per-item 500
```

The sniper will:
1. Identify gem opportunities
2. Calculate optimal bid amounts
3. Schedule snipes based on auction end times
4. Place bids automatically at the configured timing
5. Monitor and counter-bid if outbid (if enabled)

## Example Use Case: Laptop Flipping

1. **Discovery**: Bot scrapes GSA Auctions and finds:
   ```
   "Lot of 50 Dell Latitude 5520 Laptops - Seized Property"
   Current Bid: $1,000
   ```

2. **Analysis**:
   - Data cleaner extracts: Dell, Latitude 5520, Qty: 50
   - Market analyzer estimates: $150/unit on eBay = $7,500 total
   - Opportunity score: 0.92 (gem!)

3. **Sniping**:
   - Bot schedules snipe for 30 seconds before end
   - Max bid set to $2,000 (still 275% ROI)
   - Wins auction at $1,250

4. **Profit**:
   - Buy: $1,250
   - Clean & test: $200
   - Sell on eBay: $7,500
   - **Net profit: $6,050**

## Project Structure

```
GovAUC/
├── src/govauc/
│   ├── __init__.py           # Package init
│   ├── cli.py                # Command-line interface
│   ├── core.py               # Main orchestrator
│   ├── models.py             # Data models
│   ├── scrapers/             # Web scraping modules
│   ├── analyzers/            # Analysis modules
│   ├── snipers/              # Automated bidding
│   ├── database/             # Persistence layer
│   └── utils/                # Utilities
├── config/                   # Configuration files
├── data/                     # Data storage
├── logs/                     # Log files
└── tests/                    # Test suite
```

## Legal & Ethical Considerations

- This bot is designed for **legitimate participation** in public government auctions
- Always comply with auction site terms of service
- Sniping is a legal practice in most jurisdictions
- Ensure you have funds available for any bids placed

## Disclaimer

This software is provided for educational and research purposes. The authors are not responsible for any financial losses, legal issues, or other problems arising from the use of this software. Always do your own due diligence before bidding on auctions.
