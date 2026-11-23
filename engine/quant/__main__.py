"""Backtest a real point-in-time dataset. See --help for the input schema."""
import argparse
import json
from pathlib import Path
from .simulation import backtest, walk_forward


def main():
    parser=argparse.ArgumentParser(description="Backtest one symbol using dated adjusted bars and point-in-time market snapshots.")
    parser.add_argument("dataset",type=Path,help="UTF-8 JSON object containing symbol, bars and snapshots keyed by ISO session date")
    parser.add_argument("--buy-fee",type=float,required=True,help="Entry commission as a fraction")
    parser.add_argument("--sell-fee",type=float,required=True,help="Exit commission as a fraction")
    parser.add_argument("--slippage",type=float,required=True,help="Adverse fill slippage as a fraction")
    parser.add_argument("--walk-forward",action="store_true",help="Split into successive 60-session out-of-sample folds")
    args=parser.parse_args()
    try:
        data=json.loads(args.dataset.read_text(encoding="utf-8-sig"))
        execute=walk_forward if args.walk_forward else backtest
        result=execute(data["symbol"],data["bars"],data["snapshots"],buy_fee=args.buy_fee,
                       sell_fee=args.sell_fee,slippage=args.slippage)
    except (KeyError,TypeError,ValueError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":
    main()

