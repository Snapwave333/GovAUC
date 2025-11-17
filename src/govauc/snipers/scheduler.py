"""
Scheduler for managing multiple snipe operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from govauc.models import AuctionListing, BidStrategy, PlacedBid
from govauc.snipers.engine import SnipeEngine
from govauc.snipers.strategies import BiddingStrategy, CalculatedStrategy

logger = logging.getLogger(__name__)


class SnipeScheduler:
    """
    Manages scheduling and execution of multiple snipe operations.

    Features:
    - Queue management for multiple auctions
    - Priority-based scheduling
    - Conflict resolution (overlapping end times)
    - Budget management across bids
    """

    def __init__(
        self,
        engine: SnipeEngine,
        total_budget: float = 10000.0,
        max_concurrent_snipes: int = 5,
    ):
        """
        Initialize the scheduler.

        Args:
            engine: The snipe engine to use
            total_budget: Total budget for all bids
            max_concurrent_snipes: Max simultaneous snipe operations
        """
        self.engine = engine
        self.total_budget = total_budget
        self.remaining_budget = total_budget
        self.max_concurrent = max_concurrent_snipes

        self.scheduled_snipes: dict[str, dict] = {}  # listing_id -> snipe info
        self.completed_snipes: list[PlacedBid] = []
        self.running = False

        self.strategy = CalculatedStrategy()

    def schedule_snipe(
        self,
        listing: AuctionListing,
        max_bid: Optional[float] = None,
        strategy: Optional[BidStrategy] = None,
    ) -> bool:
        """
        Schedule a snipe operation for a listing.

        Args:
            listing: Listing to snipe
            max_bid: Maximum bid amount (optional, calculated if not provided)
            strategy: Bid strategy to use (optional)

        Returns:
            True if scheduled successfully
        """
        if listing.id in self.scheduled_snipes:
            logger.warning(f"Listing {listing.id} already scheduled")
            return False

        # Calculate strategy if not provided
        if not strategy:
            if not max_bid:
                max_bid = min(
                    self.remaining_budget,
                    listing.estimated_market_value * 0.65
                    if listing.estimated_market_value
                    else self.remaining_budget * 0.1,
                )

            calculated = self.strategy.calculate_bid(listing, max_bid)
            if not calculated:
                logger.warning(f"Could not calculate strategy for {listing.id}")
                return False
            strategy = calculated

        # Check budget
        if strategy.max_bid > self.remaining_budget:
            logger.warning(
                f"Insufficient budget for {listing.id}: "
                f"need ${strategy.max_bid:.2f}, have ${self.remaining_budget:.2f}"
            )
            return False

        # Reserve budget
        self.remaining_budget -= strategy.max_bid

        self.scheduled_snipes[listing.id] = {
            "listing": listing,
            "strategy": strategy,
            "scheduled_at": datetime.utcnow(),
            "status": "pending",
        }

        logger.info(
            f"Scheduled snipe for {listing.id}: "
            f"max_bid=${strategy.max_bid:.2f}, "
            f"snipe_timing={strategy.snipe_seconds_before_end}s"
        )

        return True

    def cancel_snipe(self, listing_id: str) -> bool:
        """
        Cancel a scheduled snipe.

        Args:
            listing_id: ID of the listing to cancel

        Returns:
            True if cancelled successfully
        """
        if listing_id not in self.scheduled_snipes:
            return False

        snipe_info = self.scheduled_snipes[listing_id]

        # Return reserved budget
        self.remaining_budget += snipe_info["strategy"].max_bid

        del self.scheduled_snipes[listing_id]

        logger.info(f"Cancelled snipe for {listing_id}")
        return True

    async def run_scheduler(self):
        """
        Run the scheduler loop.

        Continuously monitors scheduled snipes and executes them at the right time.
        """
        self.running = True
        logger.info("Snipe scheduler started")

        try:
            while self.running:
                # Get snipes that need to execute soon
                pending_snipes = self._get_pending_snipes()

                if pending_snipes:
                    # Execute snipes concurrently (up to max_concurrent)
                    tasks = []
                    for listing_id, snipe_info in pending_snipes[:self.max_concurrent]:
                        task = asyncio.create_task(
                            self._execute_snipe(listing_id, snipe_info)
                        )
                        tasks.append(task)

                    if tasks:
                        await asyncio.gather(*tasks)

                # Sleep briefly before checking again
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            self.running = False
            logger.info("Snipe scheduler stopped")

    def stop_scheduler(self):
        """Stop the scheduler loop."""
        self.running = False

    def _get_pending_snipes(self) -> list[tuple[str, dict]]:
        """
        Get snipes that should execute soon.

        Returns:
            List of (listing_id, snipe_info) tuples sorted by urgency
        """
        pending = []

        for listing_id, snipe_info in self.scheduled_snipes.items():
            if snipe_info["status"] != "pending":
                continue

            listing = snipe_info["listing"]
            strategy = snipe_info["strategy"]

            # Check if we should start the snipe operation
            remaining = listing.time_remaining_seconds
            if remaining is None:
                continue

            # Start snipe operation if within preparation window
            # (2x snipe timing to account for setup)
            if remaining <= strategy.snipe_seconds_before_end * 2:
                pending.append((listing_id, snipe_info))

        # Sort by end time (soonest first)
        pending.sort(
            key=lambda x: x[1]["listing"].time_remaining_seconds or float("inf")
        )

        return pending

    async def _execute_snipe(self, listing_id: str, snipe_info: dict):
        """
        Execute a single snipe operation.

        Args:
            listing_id: ID of the listing
            snipe_info: Snipe configuration
        """
        listing = snipe_info["listing"]
        strategy = snipe_info["strategy"]

        # Mark as executing
        snipe_info["status"] = "executing"
        logger.info(f"Executing snipe for {listing_id}")

        try:
            # Execute the snipe
            bid = await self.engine.snipe_auction(listing, strategy)

            # Update status based on result
            if bid.status in [BidStatus.PLACED, BidStatus.WINNING, BidStatus.WON]:
                snipe_info["status"] = "completed"

                # Return unused budget
                actual_spent = bid.amount
                budget_reserved = strategy.max_bid
                self.remaining_budget += budget_reserved - actual_spent

                logger.info(
                    f"Snipe completed for {listing_id}: "
                    f"bid=${bid.amount:.2f}, status={bid.status.value}"
                )
            else:
                snipe_info["status"] = "failed"
                # Return full reserved budget on failure
                self.remaining_budget += strategy.max_bid

                logger.warning(
                    f"Snipe failed for {listing_id}: status={bid.status.value}"
                )

            snipe_info["result"] = bid
            self.completed_snipes.append(bid)

        except Exception as e:
            logger.error(f"Snipe execution error for {listing_id}: {e}")
            snipe_info["status"] = "failed"
            self.remaining_budget += strategy.max_bid

    def get_schedule_summary(self) -> dict:
        """
        Get summary of all scheduled snipes.

        Returns:
            Summary dictionary
        """
        pending = [s for s in self.scheduled_snipes.values() if s["status"] == "pending"]
        executing = [s for s in self.scheduled_snipes.values() if s["status"] == "executing"]
        completed = [s for s in self.scheduled_snipes.values() if s["status"] == "completed"]
        failed = [s for s in self.scheduled_snipes.values() if s["status"] == "failed"]

        reserved_budget = sum(
            s["strategy"].max_bid for s in pending
        )

        return {
            "total_scheduled": len(self.scheduled_snipes),
            "pending": len(pending),
            "executing": len(executing),
            "completed": len(completed),
            "failed": len(failed),
            "total_budget": self.total_budget,
            "remaining_budget": self.remaining_budget,
            "reserved_budget": reserved_budget,
            "upcoming_snipes": [
                {
                    "listing_id": s["listing"].id,
                    "title": s["listing"].title[:50],
                    "max_bid": s["strategy"].max_bid,
                    "time_remaining": s["listing"].time_remaining_seconds,
                }
                for s in sorted(
                    pending,
                    key=lambda x: x["listing"].time_remaining_seconds or float("inf"),
                )[:10]
            ],
        }

    def auto_schedule_gems(
        self,
        listings: list[AuctionListing],
        budget_per_item: Optional[float] = None,
    ) -> int:
        """
        Automatically schedule snipes for gem opportunities.

        Args:
            listings: Analyzed listings with opportunity scores
            budget_per_item: Max budget per item (optional)

        Returns:
            Number of snipes scheduled
        """
        # Filter for gems
        gems = [l for l in listings if l.is_gem]

        # Sort by opportunity score
        gems.sort(key=lambda l: l.opportunity_score, reverse=True)

        scheduled_count = 0

        for listing in gems:
            if budget_per_item:
                max_bid = min(budget_per_item, self.remaining_budget)
            else:
                max_bid = self.remaining_budget

            if max_bid < listing.current_bid:
                continue

            if self.schedule_snipe(listing, max_bid=max_bid):
                scheduled_count += 1

            # Stop if budget exhausted
            if self.remaining_budget <= 0:
                break

        logger.info(
            f"Auto-scheduled {scheduled_count} snipes from {len(gems)} gems"
        )

        return scheduled_count
