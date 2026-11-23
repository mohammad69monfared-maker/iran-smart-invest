# ایران اسمارت اینوست

این پوشه شامل کد موتور پایتون، برنامهٔ Flutter، ربات تلگرام، مهاجرت‌های Supabase و گردش‌کارهای GitHub Actions است. متن درخواست اولیه در `docs/original-request.md` قرار دارد.

## اجرای محلی

فایل `Start.cmd` موتور را اجرا می‌کند و گزارش فارسی را باز می‌کند. نتیجهٔ هر اجرا در `data/latest.json` و `data/report.html` قرار می‌گیرد. تاریخ داخل گزارش زمان اعتبار آن است. در صورت نبود دادهٔ تازه، موتور گزارش وضعیت می‌دهد. اجرای پایتون به نصب کتابخانهٔ تحلیلی یا کلید OpenAI احتیاج ندارد.

```powershell
python -m engine
python -m engine.portfolio --help
python -m engine.quant --help
python -m engine.notifications --help
```

## داده و تحلیل

منبع قیمت و تابلو TSETMC است. فهرست نمادها از تابلو درخواست می‌شود. موتور تاریخ تهران و تاریخ آخرین معامله را بررسی می‌کند. سری تعدیل‌شده، حجم، روند، نقدشوندگی و وضعیت صف در انتخاب دخالت دارند. مقادیر وزن‌های پیش‌فرض در `engine/quant/weights.json` هستند. تغییر وزن دلخواه در کلید weights فایل strategy.json انجام می‌شود. خروجی هر سیگنال نسخهٔ استراتژی، قیمت‌های ورود، حد ضرر، هدف‌ها و شرایط ابطال دارد.

در تعطیلی رسمی وسط هفته، تاریخ تحلیل از آخرین جلسهای میآید که قیمت واقعاً منتشر شده است. اگر آن جلسه بیش از ۴ روز قدیمی باشد، سیگنالی صادر نمیشود.

## راه‌اندازی اختیاری سرویس‌ها

راهنمای اتصال حساب شخصی و اجرای SQL در `supabase/README.md` است. متغیرهای محیطی سرور شامل SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY هستند. ربات از TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID استفاده می‌کند. کلید سرویس فقط متعلق به محیط سرور است. اسکریپت `scripts/install-schedule.ps1` زمان‌بندی حساب جاری ویندوز را نصب می‌کند. پوشهٔ `.github/workflows` شامل اجرای روزانه و ساخت اپ است. فعال‌شدن اجرای ابری به قرارگرفتن پروژه در مخزن کاربر و تنظیم Secrets همان مخزن وابسته است.

## اپلیکیشن

سورس مشترک در `apps/flutter_app` است. از داخل این پوشه، با SDK و ابزار ساخت نصب‌شده:

```powershell
flutter pub get
flutter build apk --debug
flutter build windows --release
```

## ارزیابی

سبد محلی در SQLite نگهداری می‌شود. ثبت معامله دستی است. مشاهدات بعدی سیگنال با گزارش بک‌تست جدا نگهداری می‌شود. بک‌تست به تاریخچه و وضعیت قابل معاملهٔ هر جلسه و فرض کارمزد و لغزش نیاز دارد. در این پروژه بازده واقعی یا نرخ موفقیت زنده هنوز اندازه‌گیری نشده است.


## استقرار زنده

- مخزن: `https://github.com/mohammad69monfared-maker/iran-smart-invest` (شاخه `main`).
- Supabase: پروژه `kskrukdiilmvywsnwbxc` — migrations اعمالشده، RLS فعال. کلید service role فقط در Secrets مخزن و `.env` محلی سرور نگهداری میشود.
- Secrets مخزن: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- ربات: `@Smartborss1bot` — پاسخ فقط در چت خصوصی صاحب ربات. دستورها: `/report`, `/signals`, `/alerts`, `/portfolio`, `/watch`, `/unwatch`, `/status`, `/help`.
- گردشکارها: `daily.yml` (هر روز ۱۰:۳۵ UTC = ۱۴:۰۵ تهران، شنبه تا چهارشنبه + اجرای دستی)، `telegram-bot.yml` (هر ۱۰ دقیقه + اجرای دستی)، `build.yml` (دستی؛ خروجی APK و EXE بهصورت Artifact).
- زمانبندی محلی: وظیفهٔ `IranSmartInvestDaily` در Task Scheduler ویندوز نصبشده و هر روز ساعت ۱۴:۰۵ به زمان تهران اجرا میشود.
- ربات تلگرام: گردشکار `telegram-bot.yml` پنجرههای کوتاه long-polling را زنجیره میکند تا پیامها با تأخیر کم پاسخ بگیرند. وظیفهٔ محلی `IranSmartInvestBot` فقط جایگزین اختیاری است و بهطور پیشفرض غیرفعال است.
- اسکن کامل بازار حدود ۸ دقیقه با ۸ کارگر موازی طول میکشد؛ سقف زمانی قابلتنظیم است (`SCAN_WORKERS`, `SCAN_BUDGET_SECONDS`).

هیچ سیگنال تضمینی وجود ندارد و خرید و فروش خودکار در نسخهٔ حاضر نیست.
