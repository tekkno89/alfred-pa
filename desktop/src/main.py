#!/usr/bin/env python3
"""Alfred Desktop Voice Agent - CLI Entry Point"""
import argparse
import asyncio
import logging
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


def setup_logging(verbose: bool = False):
    """Configure logging for the voice agent."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(message)s',  # Let individual loggers format their own messages
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )
    
    # Set specific loggers to INFO (they use their own formatting)
    logging.getLogger('src.services.chatterbox_tts').setLevel(logging.INFO)
    logging.getLogger('src.pipeline.phases').setLevel(logging.INFO)
    logging.getLogger('src.processors.sentence_aggregator').setLevel(logging.INFO)
    
    # Suppress noisy third-party loggers
    logging.getLogger('chatterbox').setLevel(logging.WARNING)
    logging.getLogger('perth').setLevel(logging.WARNING)
    logging.getLogger('diffusers').setLevel(logging.WARNING)
    logging.getLogger('torch').setLevel(logging.WARNING)


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
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging"
    )
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    
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
