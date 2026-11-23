"""Single-symbol point-in-time simulation. No fills assumed for missing execution flags."""
from math import isfinite, sqrt
from statistics import fmean, stdev
from .strategy import evaluate


def backtest(symbol, bars, snapshots, *, buy_fee, sell_fee, slippage, start=60, end=None, weights=None):
    """Snapshots keyed by ISO day. OHLC must share a single constant adjusted-price basis.
    Absolute price limits, if provided, must use that same basis. Buy at next open only.
    Missing/locked snapshots defer exits. Open positions remain marked on the final day.
    """
    if any(not isfinite(x) or not 0<=x<1 for x in (buy_fee,sell_fee,slippage)):
        raise ValueError("هزینه نامعتبر")
    days=[str(b["date"]) for b in bars]
    if days!=sorted(set(days)):
        raise ValueError("ترتیب تاریخ‌ها نامعتبر است")
    if start<1:
        raise ValueError("نقطه شروع نامعتبر است")
    stop_index=min(end if end is not None else len(bars),len(bars))
    position=None
    trades=[]
    cash=peak=1.
    drawdown=0.
    daily=[]
    previous=1.
    for i in range(start,stop_index):
        b=bars[i]
        day=days[i]
        snap=snapshots.get(day,{})
        # Full-day queue flags conservatively suppress fills, never trigger them.
        active=snap.get("tradable") is True and b["volume"]>0 and snap.get("adjusted") is True
        opening,high,low,close=[float(b[k]) for k in ("open","high","low","close")]
        lower=float(snap.get("limit_low",low))
        upper=float(snap.get("limit_high",high))
        if not all(map(isfinite,(opening,high,low,close,lower,upper))) or not 0<low<=min(opening,close)<=max(opening,close)<=high:
            raise ValueError("قیمت نامعتبر در بک‌تست")
        if position is None and active and snap.get("buy_queue") is False:
            prev=snapshots.get(days[i-1],{})
            signal,_=evaluate(symbol,bars[:i],as_of=days[i-1],market=prev,weights=weights)
            if signal and day<=signal["expires"]:
                scale=float(bars[i-1]["close"])/signal["last_price"]
                fill=opening*(1+slippage)
                if signal["entry_low"]*scale<=fill<=signal["entry_high"]*scale and max(lower,low)<=fill<=min(upper,high):
                    position=dict(index=i,day=day,fill=fill,qty=cash/(fill*(1+buy_fee)),
                                  stop=signal["stop_loss"]*scale,target=signal["target1"]*scale,capital=cash)
                    cash=0.
        if position and active and snap.get("sell_queue") is False:
            raw=None
            if low<=position["stop"]:
                raw=min(opening,position["stop"])
            elif high>=position["target"]:
                raw=position["target"]
            elif i-position["index"]>=10:
                raw=close
            if raw is not None:
                fill=raw*(1-slippage)
                if max(lower,low)<=fill<=min(upper,high):
                    cash=position["qty"]*fill*(1-sell_fee)
                    trades.append(dict(entry_date=position["day"],exit_date=day,entry=position["fill"],exit=fill,
                                       holding_sessions=i-position["index"]+1,net_return=cash/position["capital"]-1))
                    position=None
        equity=cash if position is None else position["qty"]*close
        peak=max(peak,equity)
        drawdown=max(drawdown,1-equity/peak)
        daily.append(equity/previous-1)
        previous=equity
    returns=[t["net_return"] for t in trades]
    losses=-sum(r for r in returns if r<0)
    sd=stdev(daily) if len(daily)>1 else 0
    return dict(kind="backtest",trades=trades,number_of_trades=len(trades),open_position=position is not None,
                return_after_costs=previous-1,maximum_drawdown=drawdown,
                sharpe_ratio=sqrt(250)*fmean(daily)/sd if sd else None,
                profit_factor=sum(r for r in returns if r>0)/losses if losses else None,
                win_rate=sum(r>0 for r in returns)/len(returns) if returns else None,
                average_return=fmean(returns) if returns else None,expectancy=fmean(returns) if returns else None,
                average_holding_period=fmean(t["holding_sessions"] for t in trades) if trades else None)


def walk_forward(symbol,bars,snapshots,*,warmup=60,fold_size=60,**costs):
    """Fixed strategy evaluated on successive disjoint test windows with expanding historical context."""
    if fold_size<1 or warmup<60:
        raise ValueError("اندازه پنجره نامعتبر")
    return [dict(from_date=bars[i]["date"],to_date=bars[min(i+fold_size,len(bars))-1]["date"],
                 result=backtest(symbol,bars,snapshots,start=i,end=i+fold_size,**costs))
            for i in range(warmup,len(bars),fold_size)]

