"""Launch the graphical game or the terminal edition."""
import argparse


def main():
    parser = argparse.ArgumentParser(description='Pineapple Open Face Chinese Poker')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--terminal', action='store_true', help='Play in the terminal')
    mode.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.terminal:
        from chinesepoker.ui.cli import main as play
    elif args.smoke_test:
        from chinesepoker.ui.gui import smoke_test as play
    else:
        from chinesepoker.ui.gui import main as play
    play()


if __name__ == '__main__':
    main()
