#!/usr/bin/env python3
"""Alfred Desktop Voice Agent - CLI Entry Point"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings
from src.pipeline.phases import (
    run_phase_1,
    run_phase_2,
    run_phase_3,
    run_phase_4,
    run_phase_5,
    run_phase_6,
)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Alfred Desktop Voice Agent POC"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[0, 1, 2, 3, 4, 5, 6],
        default=0,
        help="Development phase to run (default: 0 for research/notes)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to config file (default: config/settings.yaml)"
    )
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Load configuration
    print(f"Loading config from {args.config}...")
    settings = Settings.load(args.config)
    
    # Run the appropriate phase
    if args.phase == 0:
        print("Phase 0: Research & Documentation")
        print("Review docs/ directory for implementation notes before coding.")
        print("See Phase 0 tasks in the plan for research checklist.")
    elif args.phase == 1:
        await run_phase_1(settings)
    elif args.phase == 2:
        await run_phase_2(settings)
    elif args.phase == 3:
        await run_phase_3(settings)
    elif args.phase == 4:
        await run_phase_4(settings)
    elif args.phase == 5:
        await run_phase_5(settings)
    elif args.phase == 6:
        await run_phase_6(settings)
    else:
        print(f"Phase {args.phase} not implemented yet")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
