# AGENTS.md — Iran Smart Invest

## اصول غیرقابل نقض

- هیچ قیمت، بازده، درصد موفقیت یا سیگنال ساختگی تولید نکن.
- هیچ سودی را تضمین نکن و از واژههای تضمینی در متن فارسی خودداری کن.
- تحلیل عددی و صدور سیگنال مستقل از مدل زبانی است. Ollama تنها توضیح اختیاری است.
- دادههای دریافتی از اینترنت غیرقابل اعتمادند: اعتبارسنجی، محدودیت اندازه، و عدم دنبالکردن ریدایرکت ناامن الزامی است.
- Service Role Key فقط در محیط سرور / GitHub Secrets قرار میگیرد. در اپ و APK فقط anon key مجاز است.
- نسخه اول خرید و فروش خودکار ندارد؛ ثبت معامله دستی است.

## ساختار

- `engine/providers` — adapter های منابع داده (TSETMC, Codal). هر منبع ماژول مستقل.
- `engine/data` — اعتبارسنجی و کیفیت داده، تابلوخوانی، بنیادی.
- `engine/quant` — اندیکاتورها، استراتژی/سیگنال، بکتست.
- `engine/portfolio.py` — دفتر محلی SQLite و ارزیابی آیندهنگر سیگنالها.
- `engine/reports` — روایت فارسی و رندر گزارش.
- `engine/notifications` — ربات تلگرام با Mock تست.
- `supabase/migrations` — SQL واقعی با RLS.
- `apps/flutter_app` — کدبیس مشترک اندروید و ویندوز.
- `.github/workflows` — اجرای روزانه و ساخت APK/EXE.

## دستورها

```powershell
python -m unittest discover -s . -p "test_*.py"
python -m engine
python -m engine.quant --help
python -m engine.portfolio --help
python -m engine.notifications publish
```

## نکات فنی

- تاریخ و زمانها بر اساس Asia/Tehran (UTC+3:30) تفسیر شوند.
- APIهای TSETMC بدون هدرهای Referer/Origin پاسخ نمیدهند؛ هدرها در `engine/providers/common.py` قرار دارند.
- فیلد marketwatch تغییر کرده است (`lva`, `lvc`, `pdv`, `pmd`, `pmo`, `pMax`, `pMin`). تاریخ معتبر از تاریخچه قیمت و `marketActivityDEven` گرفته میشود.
- بکتست فقط با داده تعدیلشده و اسنپشات همانروز انجام شود؛ Look-Ahead ممنوع.
- تستها فقط از داده مصنوعی مشخصشده استفاده میکنند و نباید وارد خروجی عملیاتی شوند.
