"""Launch the graphical game or the terminal edition."""
import argparse
from multiprocessing import freeze_support


def main():
    freeze_support()
    parser = argparse.ArgumentParser(description='Pineapple Open Face Chinese Poker')
    parser.add_argument('--strategy', help='Experimental normal single-hand MCCFR checkpoint (JSON)')
    parser.add_argument('--cpu-level', choices=['easy','normal','hard','hybrid','adaptive'], default='easy', help=argparse.SUPPRESS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--terminal', action='store_true', help='Play in the terminal')
    mode.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    mode.add_argument('--cpu-smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.strategy:
        from pathlib import Path
        if args.terminal or args.smoke_test:
            parser.error('--strategy is only available in the graphical game')
        if not Path(args.strategy).is_file():
            parser.error('Strategy file does not exist')
        if args.cpu_smoke_test:
            from chinesepoker.ui.gui import cpu_smoke_test as play
        else:
            from chinesepoker.ui.gui import main as play
        play(strategy_path=str(Path(args.strategy).resolve()))
        return
    if args.terminal:
        from chinesepoker.ui.cli import main as play
    elif args.cpu_smoke_test:
        from chinesepoker.ui.gui import cpu_smoke_test as play
        play(difficulty=args.cpu_level)
        return
    elif args.smoke_test:
        from chinesepoker.ui.gui import smoke_test as play
    else:
        from chinesepoker.ui.gui import main as play
    play()


if __name__ == '__main__':
    main()
