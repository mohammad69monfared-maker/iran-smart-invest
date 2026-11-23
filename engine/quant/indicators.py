"""Daily indicators. Each output uses only the supplied observation window."""
from datetime import date
from math import isfinite
from statistics import fmean, pstdev


def smooth(values, period, alpha):
    result = [fmean(values[:period])]
    for x in values[period:]:
        result.append(result[-1] + alpha * (x - result[-1]))
    return result


def indicators(bars, benchmark_closes=None):
    if len(bars) < 60:
        raise ValueError("حداقل ۶۰ جلسه لازم است")
    days = [date.fromisoformat(str(b["date"])) for b in bars]
    if any(a >= b for a, b in zip(days, days[1:])):
        raise ValueError("تاریخ تکراری یا نامرتب")
    o,h,l,c,v = [[float(b[k]) for b in bars] for k in ("open","high","low","close","volume")]
    for values in zip(o,h,l,c,v):
        op,hi,lo,cl,vol = values
        if not all(map(isfinite, values)) or not 0 < lo <= min(op,cl) <= max(op,cl) <= hi or vol < 0:
            raise ValueError("قیمت یا حجم نامعتبر")
    delta = [y-x for x,y in zip(c,c[1:])]
    gain = smooth([max(x,0) for x in delta],14,1/14)[-1]
    loss = smooth([max(-x,0) for x in delta],14,1/14)[-1]
    tr,plus,minus = [],[],[]
    for i in range(1,len(c)):
        tr.append(max(h[i],c[i-1])-min(l[i],c[i-1]))
        up,dn = h[i]-h[i-1],l[i-1]-l[i]
        plus.append(up if up > max(0,dn) else 0)
        minus.append(dn if dn > max(0,up) else 0)
    dx = [100*abs(p-m)/(p+m) if p+m else 0 for p,m in zip(smooth(plus,14,1/14),smooth(minus,14,1/14))]
    fast,slow = smooth(c,12,2/13),smooth(c,26,2/27)
    macd = [a-b for a,b in zip(fast[14:],slow)]
    mid,spread = fmean(c[-20:]),2*pstdev(c[-20:])
    rs = None
    if benchmark_closes is not None:
        if len(benchmark_closes)!=len(c) or any(not isfinite(x) or x<=0 for x in benchmark_closes):
            raise ValueError("شاخص هم‌تاریخ معتبر لازم است")
        rs=(c[-1]/c[-21])/(benchmark_closes[-1]/benchmark_closes[-21])-1
    return dict(sma20=mid,sma50=fmean(c[-50:]),ema12=fast[-1],ema26=slow[-1],
                rsi14=100*gain/(gain+loss) if gain+loss else 50,macd=macd[-1],
                macd_signal=smooth(macd,9,0.2)[-1],bollinger_upper=mid+spread,bollinger_lower=mid-spread,
                atr14=smooth(tr,14,1/14)[-1],adx14=smooth(dx,14,1/14)[-1],
                obv=sum(vol*((d>0)-(d<0)) for vol,d in zip(v[1:],delta)),volume_ma20=fmean(v[-21:-1]),
                support=min(l[-21:-1]),resistance=max(h[-21:-1]),breakout=c[-1]>max(h[-21:-1]),relative_strength=rs)

