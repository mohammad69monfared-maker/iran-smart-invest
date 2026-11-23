# ساخت APK و EXE

فایلهای اجرایی توسط گردشکار `.github/workflows/build.yml` روی سرورهای GitHub ساخته میشوند:

1. به آدرس https://github.com/mohammad69monfared-maker/iran-smart-invest/actions/actions بروید.
2. از لیست سمت چپ، گردشکار **Build Android and Windows** را انتخاب کنید.
3. آخرین اجرای موفق (مثلاً `45159911022`) را باز کنید.
4. در پایین صفحه، Artifactهای `IranSmartInvest-android` و `IranSmartInvest-windows` را دانلود کنید.
5. فایل zip را باز کنید:
   - اندروید: `build/app/outputs/flutter-apk/app-debug.apk`
   - ویندوز: پوشهٔ `build/windows/x64/runner/Release/` و فایل اجرای داخل آن.

ساخت مجدد: از تب Actions دکمهٔ **Run workflow** را بزنید. تنظیمات Supabase (URL و anon key) هنگام ساخت از Secrets مخزن خوانده میشوند؛ کلید service role وارد APK نمیشود.

## فایلهای دانلودشده روی این دستگاه

- ویندوز (جدید، شامل اصلاح اتصال و دکمههای فارسی): `artifacts/windows-v2/iran_smart_invest.exe` بههمراه پوشهٔ `data/` و فایل `flutter_windows.dll`. قبل از اجرا، نسخهٔ قدیمی را ببندید (فایلهایش در حال استفادهاند) و EXE جدید را از این پوشه باز کنید.
- اندروید (جدید): `C:\Users\amard\AppData\Local\Temp\opencode\artifacts\extract-android-v2\build\app\outputs\flutter-apk\app-debug.apk` — چون حجم آن حدود ۱۴۸ مگابایت است و فضای آزاد درایو D کافی نبود، در پوشهٔ موقت C نگهداری میشود. نسخهٔ همیشهموجود همان Artifact مخزن است.

پس از آزاد کردن فضا روی درایو D میتوانید فایل APK را به `artifacts/android/` منتقل کنید.
