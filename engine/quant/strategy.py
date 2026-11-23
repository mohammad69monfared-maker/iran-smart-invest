import hashlib
import json
from datetime import date, timedelta
from math import floor, isfinite
from pathlib import Path
from .indicators import indicators


def position_size(capital, risk_pct, entry, stop):
    if not all(map(isfinite,(capital,risk_pct,entry,stop))) or capital <= 0 or not 0 < risk_pct <= 100 or not 0 < stop < entry:
        raise ValueError("پارامتر ریسک نامعتبر")
    return floor(min(capital/entry, capital*risk_pct/100/(entry-stop)))


def evaluate(symbol, bars, *, as_of, market, weights=None):
    day=date.fromisoformat(str(as_of))
    required={"tradable":True,"adjusted":True,"liquid":True,"buy_queue":False,"sell_queue":False}
    if any(market.get(k) is not v for k,v in required.items()):
        return None,"وضعیت معامله، تعدیل، نقدشوندگی یا صف تأیید نشد"
    if not bars or str(bars[-1].get("date"))!=day.isoformat():
        return None,"آخرین جلسه معتبر نیست"
    try:
        ind=indicators(bars)
        close=float(bars[-1]["close"])
        price=float(market["last_price"])
        if not isfinite(price) or price<=0 or float(bars[-1]["volume"])<=0:
            raise ValueError
        optional={k:float(market.get(k) or 0) for k in ("buyer_power","earnings_growth","relative_strength")}
        if not all(map(isfinite,optional.values())):
            raise ValueError
    except (KeyError,TypeError,ValueError,OverflowError):
        return None,"سابقه یا داده معتبر کافی نیست"
    params=json.loads(Path(__file__).with_name("weights.json").read_text(encoding="utf-8-sig"))
    if weights:
        if set(weights)-params.keys():
            raise ValueError("وزن ناشناخته")
        params.update(weights)
    if any(not isfinite(x) or x<0 for x in params.values()) or sum(params.values())<=0:
        raise ValueError("وزن نامعتبر")
    criteria={
        "trend":(close>ind["sma20"]>ind["sma50"] and ind["adx14"]>=20,"روند صعودی"),
        "momentum":(50<=ind["rsi14"]<=75 and ind["macd"]>=ind["macd_signal"],"تأیید مومنتوم"),
        "breakout":(ind["breakout"],"شکست مقاومت"),
        "volume":(float(bars[-1]["volume"])>=1.3*ind["volume_ma20"]>0,"افزایش حجم"),
        "flow":(optional["buyer_power"]>1.2,"برتری قدرت خریدار"),
        "fundamental":(optional["earnings_growth"]>0,"رشد سود دوره هم‌مقایسه"),
        "relative":(optional["relative_strength"]>0,"بازده بالاتر از شاخص")}
    # A missing input is reported as unavailable, never as a failed criterion.
    # Renormalise over criteria that actually have data so that absent Codal
    # or index history cannot silently veto an otherwise valid opportunity.
    available={k:(market.get("buyer_power") is not None if k=="flow" else
                  market.get("earnings_growth") is not None if k=="fundamental" else
                  market.get("relative_strength") is not None if k=="relative" else True)
               for k in criteria}
    usable=sum(params[k] for k in criteria if available[k])
    if usable<=0:
        return None,"داده کافی برای امتیازدهی موجود نیست"
    score=100*sum(params[k] for k,(ok,_) in criteria.items() if ok and available[k])/usable
    atr=ind["atr14"]*price/close
    if not criteria["trend"][0] or score<67 or not 0<atr<price/3:
        return None,"شرایط روند، امتیاز یا ریسک احراز نشد"
    # Prices are quoted in whole rials; publishing float noise is misleading.
    low,high=round(price-.25*atr),round(price+.25*atr)
    stop=round(low-1.5*atr)
    risk=high-stop
    parameters=dict(version="trend-1",weights=params,threshold=67)
    key=json.dumps([symbol,str(day),parameters],sort_keys=True).encode()
    return dict(id=hashlib.sha256(key).hexdigest()[:32],symbol=symbol,date=str(day),score=round(score,2),
                last_price=round(price),entry_low=low,entry_high=high,stop_loss=stop,
                target1=round(high+2*risk),target2=round(high+3*risk),
                reward_risk=2,expires=str(day+timedelta(days=4)),horizon="تا ۱۰ جلسه",risk_level="ریسک بازار سهام",
                status="مشروط",invalidation="شکستن حد ضرر، انقضا یا توقف معامله",
                risks=["احتمال تشکیل صف و اجرا نشدن در قیمت هدف"],reasons=[r for ok,r in criteria.values() if ok],
                parameters=parameters,sources=market.get("sources",[])),"پذیرفته شد"

