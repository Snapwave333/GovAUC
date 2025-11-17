"""
Command-line interface for GovAUC - Government Auction Sniper Bot.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.live import Live
from rich import box

from govauc import __version__
from govauc.core import AuctionBot
from govauc.database import AuctionRepository
from govauc.models import AuctionSite
from govauc.utils import load_config, save_config, setup_logging, get_default_config

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="GovAUC")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def main(ctx, config, log_level):
    """
    GovAUC - Government Auction Sniper Bot

    Find undervalued assets at government auctions and snipe them for profit.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["log_level"] = log_level
    setup_logging(log_level)


@main.command()
@click.pass_context
def dashboard(ctx):
    """Show the main dashboard with statistics and opportunities."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    console.clear()
    console.print(
        Panel.fit(
            f"[bold blue]GovAUC[/bold blue] - Government Auction Sniper Bot v{__version__}",
            border_style="blue",
        )
    )

    # Statistics
    stats = repo.get_statistics()

    stats_table = Table(title="System Statistics", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green", justify="right")

    stats_table.add_row("Total Listings", str(stats["total_listings"]))
    stats_table.add_row("Active Listings", str(stats["active_listings"]))
    stats_table.add_row("Gems Found", f"[yellow]{stats['gems_found']}[/yellow]")
    stats_table.add_row("Sites Configured", str(stats["sites_configured"]))
    stats_table.add_row("Total Bids Placed", str(stats["total_bids_placed"]))
    stats_table.add_row("Winning Bids", str(stats["winning_bids"]))
    stats_table.add_row(
        "Total Profit Potential",
        f"[green]${stats['total_profit_potential']:,.2f}[/green]",
    )

    console.print(stats_table)
    console.print()

    # Top Gems
    gems = repo.get_gems(0.8)[:10]

    if gems:
        gems_table = Table(title="Top Gem Opportunities", box=box.ROUNDED)
        gems_table.add_column("Title", style="cyan", max_width=40)
        gems_table.add_column("Category", style="blue")
        gems_table.add_column("Current Bid", justify="right")
        gems_table.add_column("Est. Value", justify="right", style="green")
        gems_table.add_column("ROI %", justify="right", style="yellow")
        gems_table.add_column("Score", justify="right", style="magenta")
        gems_table.add_column("Ends", justify="right")

        for gem in gems:
            time_left = "N/A"
            if gem.end_time:
                delta = gem.end_time - datetime.utcnow()
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    time_left = f"[red]{int(hours * 60)}m[/red]"
                elif hours < 24:
                    time_left = f"[yellow]{int(hours)}h[/yellow]"
                else:
                    time_left = f"{int(hours / 24)}d"

            gems_table.add_row(
                gem.title[:40] + "..." if len(gem.title) > 40 else gem.title,
                gem.category,
                f"${gem.current_bid:,.2f}",
                f"${gem.estimated_market_value:,.2f}"
                if gem.estimated_market_value
                else "N/A",
                f"{gem.roi_percentage:.0f}%",
                f"{gem.opportunity_score:.2f}",
                time_left,
            )

        console.print(gems_table)
    else:
        console.print("[yellow]No gem opportunities found yet. Run 'scrape' to find deals![/yellow]")

    console.print()

    # Ending Soon
    ending_soon = repo.get_ending_soon(24)[:5]

    if ending_soon:
        urgent_table = Table(title="Ending Soon (24h)", box=box.ROUNDED)
        urgent_table.add_column("Title", style="cyan", max_width=40)
        urgent_table.add_column("Current Bid", justify="right")
        urgent_table.add_column("Time Left", justify="right", style="red")

        for item in ending_soon:
            if item.end_time:
                delta = item.end_time - datetime.utcnow()
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    time_left = f"{int(hours * 60)}m"
                else:
                    time_left = f"{hours:.1f}h"

                urgent_table.add_row(
                    item.title[:40],
                    f"${item.current_bid:,.2f}",
                    time_left,
                )

        console.print(urgent_table)


@main.command()
@click.option("--sites", "-s", multiple=True, help="Specific sites to scrape")
@click.option("--all-sites", is_flag=True, help="Scrape all configured sites")
@click.pass_context
def scrape(ctx, sites, all_sites):
    """Scrape auction sites for new listings."""
    config = load_config(ctx.obj.get("config_path"))

    console.print("[bold blue]Starting auction scrape...[/bold blue]")

    async def run_scrape():
        bot = AuctionBot(config)
        await bot.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        ) as progress:
            if all_sites or not sites:
                task = progress.add_task("Scraping all sites...", total=100)
                results = await bot.scrape_all_sites()
                progress.update(task, completed=100)
            else:
                task = progress.add_task(f"Scraping {', '.join(sites)}...", total=100)
                results = await bot.scrape_sites(list(sites))
                progress.update(task, completed=100)

        console.print(f"\n[green]Scrape completed![/green]")
        console.print(f"Total listings found: {results['total_listings']}")
        console.print(f"New gems identified: {results['gems_found']}")
        console.print(
            f"Total profit potential: [green]${results['total_profit_potential']:,.2f}[/green]"
        )

    asyncio.run(run_scrape())


@main.command()
@click.option("--min-score", default=0.8, help="Minimum opportunity score")
@click.option("--limit", default=20, help="Maximum results to show")
@click.pass_context
def gems(ctx, min_score, limit):
    """Find and display gem opportunities."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    gems_list = repo.get_gems(min_score)[:limit]

    if not gems_list:
        console.print("[yellow]No gems found. Try lowering the score threshold or running a scrape.[/yellow]")
        return

    console.print(f"\n[bold green]Found {len(gems_list)} Gem Opportunities[/bold green]\n")

    for i, gem in enumerate(gems_list, 1):
        console.print(
            Panel(
                f"[bold]{gem.title}[/bold]\n\n"
                f"Category: {gem.category}\n"
                f"Location: {gem.location or 'N/A'}\n"
                f"Current Bid: [yellow]${gem.current_bid:,.2f}[/yellow]\n"
                f"Estimated Value: [green]${gem.estimated_market_value:,.2f}[/green]\n"
                f"Profit Potential: [bold green]${gem.profit_potential:,.2f}[/bold green]\n"
                f"ROI: [bold yellow]{gem.roi_percentage:.0f}%[/bold yellow]\n"
                f"Opportunity Score: {gem.opportunity_score:.3f}\n"
                f"URL: {gem.listing_url}",
                title=f"#{i} - Score: {gem.opportunity_score:.2f}",
                border_style="green" if gem.opportunity_score >= 0.9 else "yellow",
            )
        )
        console.print()


@main.command()
@click.argument("category")
@click.option("--limit", default=20, help="Maximum results")
@click.pass_context
def browse(ctx, category, limit):
    """Browse listings by category."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    listings = repo.get_listings_by_category(category)[:limit]

    if not listings:
        console.print(f"[yellow]No listings found in category: {category}[/yellow]")
        console.print("Available categories: vehicle, electronics, real_estate, jewelry, equipment, furniture")
        return

    table = Table(title=f"Listings: {category.upper()}", box=box.ROUNDED)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Bid", justify="right")
    table.add_column("Value", justify="right", style="green")
    table.add_column("ROI", justify="right", style="yellow")
    table.add_column("Score", justify="right")

    for listing in listings:
        table.add_row(
            listing.title[:40],
            f"${listing.current_bid:,.2f}",
            f"${listing.estimated_market_value:,.2f}"
            if listing.estimated_market_value
            else "N/A",
            f"{listing.roi_percentage:.0f}%",
            f"{listing.opportunity_score:.2f}",
        )

    console.print(table)


@main.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search listings by keyword."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    results = repo.search_listings(query)

    if not results:
        console.print(f"[yellow]No listings found matching: {query}[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results)} results for '{query}'[/bold]\n")

    for result in results[:20]:
        console.print(
            f"[cyan]{result.title}[/cyan]\n"
            f"  Category: {result.category} | Bid: ${result.current_bid:,.2f} | "
            f"Score: {result.opportunity_score:.2f}\n"
            f"  {result.listing_url}\n"
        )


@main.command()
@click.pass_context
def analyze(ctx):
    """Run full analysis on all listings."""
    config = load_config(ctx.obj.get("config_path"))

    console.print("[bold blue]Running full analysis...[/bold blue]")

    async def run_analysis():
        bot = AuctionBot(config)
        await bot.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            task = progress.add_task("Analyzing listings...", total=None)
            report = await bot.run_full_analysis()
            progress.update(task, completed=True)

        console.print("\n[green]Analysis complete![/green]\n")

        # Display report
        console.print(
            Panel(
                f"Date: {report['date']}\n"
                f"Total Listings: {report['total_listings_analyzed']}\n\n"
                f"[bold]Opportunity Summary:[/bold]\n"
                f"  Gems: [green]{report['summary']['gems']}[/green]\n"
                f"  Good: {report['summary']['good_opportunities']}\n"
                f"  Moderate: {report['summary']['moderate_opportunities']}\n"
                f"  Low: {report['summary']['low_opportunities']}\n\n"
                f"[bold]Gems Analysis:[/bold]\n"
                f"  Total Profit Potential: [green]${report['gems_analysis']['total_profit_potential']:,.2f}[/green]\n"
                f"  Average ROI: [yellow]{report['gems_analysis']['average_roi_percent']:.0f}%[/yellow]\n"
                f"  Ending Soon: {report['gems_analysis']['ending_soon_count']}",
                title="Analysis Report",
                border_style="blue",
            )
        )

    asyncio.run(run_analysis())


@main.command()
@click.option("--budget", default=10000.0, help="Total budget for sniping")
@click.option("--max-per-item", default=1000.0, help="Max bid per item")
@click.option("--dry-run", is_flag=True, help="Simulate without placing real bids")
@click.pass_context
def snipe(ctx, budget, max_per_item, dry_run):
    """Start the automated sniping engine."""
    config = load_config(ctx.obj.get("config_path"))

    if not config["sniping"]["enabled"] and not dry_run:
        console.print(
            "[red]Sniping is disabled in config. Enable it or use --dry-run.[/red]"
        )
        return

    console.print(
        f"[bold yellow]Starting Snipe Engine[/bold yellow]\n"
        f"Budget: ${budget:,.2f}\n"
        f"Max per item: ${max_per_item:,.2f}\n"
        f"Mode: {'[yellow]DRY RUN[/yellow]' if dry_run else '[red]LIVE[/red]'}"
    )

    if not dry_run:
        if not click.confirm("This will place REAL bids. Continue?"):
            return

    async def run_sniper():
        bot = AuctionBot(config)
        await bot.initialize()

        # Set budget
        bot.set_sniping_budget(budget, max_per_item)

        # Auto-schedule gems
        console.print("\n[blue]Scheduling snipes for gem opportunities...[/blue]")
        scheduled = await bot.auto_schedule_snipes()
        console.print(f"Scheduled {scheduled} snipe operations")

        if scheduled > 0:
            summary = bot.get_snipe_schedule()
            console.print(f"\nUpcoming snipes:")
            for snipe_info in summary.get("upcoming_snipes", [])[:5]:
                console.print(
                    f"  - {snipe_info['title'][:40]} | "
                    f"Max: ${snipe_info['max_bid']:,.2f} | "
                    f"Time: {snipe_info['time_remaining']}s"
                )

            if not dry_run:
                console.print("\n[bold]Starting snipe scheduler...[/bold]")
                await bot.run_snipe_scheduler()
        else:
            console.print("[yellow]No auctions to snipe. Run scrape first.[/yellow]")

    asyncio.run(run_sniper())


@main.command()
@click.argument("name")
@click.argument("url")
@click.option("--type", "site_type", default="generic", help="Site type")
@click.option("--scraper", default="GenericScraper", help="Scraper class to use")
@click.pass_context
def add_site(ctx, name, url, site_type, scraper):
    """Add a new auction site to monitor."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    site = AuctionSite(
        name=name,
        url=url,
        site_type=site_type,
        scraper_class=scraper,
    )

    repo.add_site(site)
    console.print(f"[green]Added site: {name} ({url})[/green]")


@main.command()
@click.pass_context
def sites(ctx):
    """List all configured auction sites."""
    config = load_config(ctx.obj.get("config_path"))
    repo = AuctionRepository(config["database"]["url"])

    sites_list = repo.get_enabled_sites()

    if not sites_list:
        console.print("[yellow]No sites configured. Use 'add-site' to add one.[/yellow]")
        return

    table = Table(title="Configured Auction Sites", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("URL", style="blue")
    table.add_column("Type")
    table.add_column("Scraper")
    table.add_column("Last Scraped")

    for site in sites_list:
        last_scraped = site.last_scraped.strftime("%Y-%m-%d %H:%M") if site.last_scraped else "Never"
        table.add_row(
            site.name,
            site.url[:50] + "..." if len(site.url) > 50 else site.url,
            site.site_type,
            site.scraper_class,
            last_scraped,
        )

    console.print(table)


@main.command()
@click.pass_context
def init(ctx):
    """Initialize GovAUC with default configuration."""
    config_path = ctx.obj.get("config_path") or "config/config.json"

    # Create default config
    config = get_default_config()

    # Add default government auction sites
    config["sites"] = [
        {
            "name": "GSA Auctions",
            "url": "https://gsaauctions.gov",
            "site_type": "federal",
            "scraper_class": "GSAScraper",
        },
        {
            "name": "GovPlanet",
            "url": "https://www.govplanet.com",
            "site_type": "federal",
            "scraper_class": "GovPlanetScraper",
        },
        {
            "name": "PublicSurplus",
            "url": "https://www.publicsurplus.com",
            "site_type": "state_local",
            "scraper_class": "PublicSurplusScraper",
        },
    ]

    save_config(config, config_path)

    # Initialize database
    repo = AuctionRepository(config["database"]["url"])

    # Add default sites to database
    for site_config in config["sites"]:
        site = AuctionSite(**site_config)
        repo.add_site(site)

    console.print(f"[green]GovAUC initialized![/green]")
    console.print(f"Config saved to: {config_path}")
    console.print(f"Database created: {config['database']['url']}")
    console.print(f"Added {len(config['sites'])} default auction sites")
    console.print("\nNext steps:")
    console.print("  1. Run 'govauc scrape' to find auctions")
    console.print("  2. Run 'govauc gems' to see opportunities")
    console.print("  3. Run 'govauc dashboard' to view statistics")


@main.command()
@click.pass_context
def report(ctx):
    """Generate and display a detailed report."""
    config = load_config(ctx.obj.get("config_path"))

    async def generate_report():
        bot = AuctionBot(config)
        await bot.initialize()
        report_data = await bot.generate_daily_report()

        # Save report
        repo = AuctionRepository(config["database"]["url"])
        repo.save_daily_report(report_data)

        # Display
        console.print(
            Panel(
                json.dumps(report_data, indent=2, default=str),
                title="Daily Report",
                border_style="blue",
            )
        )

    asyncio.run(generate_report())


if __name__ == "__main__":
    main()
