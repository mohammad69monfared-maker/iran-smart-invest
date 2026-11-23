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

پس از دانلود محلی موفق، محتوای همین صفحهها در پوشههای `android/` و `windows/` همین مسیر قرار میگیرد.
