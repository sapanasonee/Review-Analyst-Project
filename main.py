from src.phase1 import scraper
from src.phase2 import analyzer
from src.phase3 import report
from src.phase4 import emailer


def main(weeks: int = 12, count: int = 500):
    # Phase 1
    reviews = scraper.run(weeks=weeks, count=count)
    print(f"\nPhase 1 complete — {len(reviews)} reviews ready for analysis.\n")

    # Phase 2A
    themes = analyzer.run_step_a()
    print(f"\nPhase 2A complete — {len(themes)} themes identified.\n")

    # Phase 3
    report.run()
    print("\nPhase 3 complete — Weekly pulse saved to output/.\n")

    # Phase 4
    emailer.run()
    print("\nPhase 4 complete — Gmail draft created.\n")


if __name__ == "__main__":
    main()
