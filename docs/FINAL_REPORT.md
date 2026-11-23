# گزارش نهایی وضعیت پروژه Iran Smart Invest

تاریخ: ۱۴۰۵/۰۹/۰۲ (۲۰۲۶-۱۱-۲۳)

## ۱. بخشهای ساختهشده

| بخش | وضعیت | محل |
|---|---|---|
| موتور تحلیل پایتون | ساخته و اجراشونده | `engine/` |
| Adapter داده TSETMC | کار میکند با هدرهای مرورگر | `engine/providers/tsetmc.py` |
| Adapter اطلاعیه کدال | کد و تست Mock دارد | `engine/providers/codal.py` |
| اعتبارسنجی و کیفیتداده | ساخته + تست | `engine/data/quality.py` |
| تابلوخوانی | ساخته + تست | `engine/data/tablovani.py` |
| تحلیل بنیادی (بدون عدد حدسی) | ساخته + تست | `engine/data/fundamentals.py` |
| اندیکاتورها و استراتژی و بکتست | ساخته + تست | `engine/quant/` |
| دفتر سبد و ارزیابی آیندهنگر سیگنال | ساخته + تست | `engine/portfolio.py` |
| روایت فارسی + Ollama اختیاری | ساخته + تست | `engine/reports/` |
| ربات تلگرام + دستورها | ساخته + تست Mock | `engine/notifications/` |
| Supabase Migration (دو فایل) | نوشتهشده، اعمال نشده | `supabase/migrations/` |
| GitHub Actions (روزانه + ساخت) | نوشتهشده، فعال نشده | `.github/workflows/` |
| اپ Flutter (اندروید/ویندوز) | سورس موجود، Build محلی نشده | `apps/flutter_app/` |
| لانچر ویندوز | EXE واقعی (PE) + Start.cmd | `IranSmartInvest.exe`, `Start.cmd` |

## ۲. منابع داده واقعی

- **TSETMC**: کار میکند. ۳٬۷۳۶ نماد در marketwatch، تاریخچه ۳۰۰ تا ۱٬۲۰۰ جلسهای، تابلو و شاخص. آخرین جلسه معاملاتی: `2026-11-22`.
- **Codal**: پارسگر سلولهای صورتهای مالی ساختهشده و تست شده است. دسترسی شبکهای پایدار تأیید نشده و در نبود داده، وضعیت بنیادی «ناموجود» اعلام میشود.
- **pytse-client / Ollama**: اختیاری و بدون نیاز عملیاتی.

## ۳. تستها

`python -m unittest discover -s . -p "test_*.py"` → **۳۴ تست، همگی موفق**.

شامل: اندیکاتورها، بازده، حد ضرر و نسبت سود به زیان، جلوگیری از نگاه به آینده، داده ناقص/قدیمی/متوقف، نقدشوندگی، بکتست و Walk-Forward، دفتر سبد، سیاست RLS، ربات تلگرام با Mock، و خط لوله کامل تحلیل.

## ۴. محدودیتها و کار باقیمانده

- فلاتر SDK نصب نیست → APK و EXE فلتر ساخته نشدند. workflow `build.yml` آماده است و با push به مخزن و اجرای دستی قابل ساخت است.
- Supabase بدون URL/Service Key اعمال نشد. دستورالعمل در `supabase/README.md`.
- ربات تلگرام بدون Token/Chat ID ارسال واقعی نکرد (کد و تست Mock موفق است).
- اجرای ابری GitHub Actions نیاز به مخزن و Secrets دارد.
- تاکنون هیچ ادعایی درباره دقت یا سودآوری سیستم وجود ندارد و هیچ سودی تضمین نمیشود.

## ۵. دستورها

```powershell
python -m unittest discover -s . -p "test_*.py"
python -m engine                 # تحلیل روزانه (فقط بعد از ۱۲:۳۵ تهران)
python -m engine --force         # اجرای مجدد دستی
python -m engine.portfolio --help
python -m engine.quant --help
python -m engine.notifications publish
Start.cmd                        # اجرا + باز کردن report.html
```
