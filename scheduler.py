"""
Simple scheduler to run the full weekly pulse pipeline on a fixed schedule.

It uses the existing CLI pipeline (main.main) and forces the recipient to
spnsn9@gmail.com for scheduled runs.

Usage:
    python scheduler.py

Keep this process running; it will trigger once a week at 17:35 local time.
For IST, run this on a machine whose system timezone is set to Asia/Kolkata.
"""

import os
import time

import schedule

from main import main as pipeline_main


SCHEDULED_RECIPIENT = "spnsn9@gmail.com"
SCHEDULED_WEEKS = 8
SCHEDULED_COUNT = 1000


def run_weekly_pulse():
    """
    Run the full pipeline once, forcing the scheduled recipient and limits (8 weeks, 1000 reviews).
    """
    os.environ["GMAIL_RECIPIENT"] = SCHEDULED_RECIPIENT
    print("\n=== Scheduled Weekly Pulse Run ===")
    print(f"GMAIL_RECIPIENT set to {SCHEDULED_RECIPIENT}")
    print(f"Scrape: last {SCHEDULED_WEEKS} weeks, up to {SCHEDULED_COUNT} reviews")
    pipeline_main(weeks=SCHEDULED_WEEKS, count=SCHEDULED_COUNT)
    print("=== Scheduled Weekly Pulse Finished ===\n")


def main():
    """
    Start the scheduler loop.

    Currently configured to run every Monday at 17:35 local time.
    Adjust the day/time below if needed.
    """
    # Weekly at 17:35 local time (e.g. 5:35 PM IST if system clock is IST)
    schedule.every().monday.at("17:35").do(run_weekly_pulse)

    print("Scheduler started.")
    print("Configured to run weekly pulse every Monday at 17:35 (local time).")
    print("Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()

