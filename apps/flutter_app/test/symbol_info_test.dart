import 'package:flutter_test/flutter_test.dart';
import 'package:iran_smart_invest/symbol_info.dart';

// دادهٔ مصنوعی آزمون؛ هیچ رقمی از یک نماد واقعی نیست.
const synthetic = '''
{"instrumentInfo":{
  "insCode":"9001",
  "lVal18AFC":"آزمون",
  "lVal30":"شركت آزمون نمونه",
  "flowTitle":"بازار بورس",
  "cgrValCotTitle":"بازار اول (تابلوی اصلی) بورس",
  "sector":{"lSecVal":"فلزات اساسي"},
  "eps":{"estimatedEPS":"693","sectorPE":11.19,"psr":2541.02},
  "zTitad":1935000000000,
  "baseVol":1,
  "qTotTran5JAvg":2066218099,
  "minWeek":4850,
  "maxWeek":5270,
  "minYear":2182,
  "maxYear":5320,
  "nav":0,
  "cIsin":"IRO1TEST0001"
}}
''';

void main() {
  test('شناسنامه با همهٔ فیلدهای موجود خوانده می‌شود', () {
    final profile = parseProfile(synthetic);
    expect(profile.insCode, '9001');
    expect(profile.symbol, 'آزمون');
    expect(profile.name, 'شركت آزمون نمونه');
    expect(profile.sector, 'فلزات اساسي');
    expect(profile.market, 'بازار بورس');
    expect(profile.board, 'بازار اول (تابلوی اصلی) بورس');
    expect(profile.place, 'بازار اول (تابلوی اصلی) بورس');
    expect(profile.eps, 693);
    expect(profile.sectorPe, 11.19);
    expect(profile.psr, 2541.02);
    expect(profile.shares, 1935000000000);
    expect(profile.baseVolume, 1);
    expect(profile.averageVolume, 2066218099);
    expect(profile.weekLow, 4850);
    expect(profile.weekHigh, 5270);
    expect(profile.isin, 'IRO1TEST0001');
  });

  test('توضیح فارسی فقط از دادهٔ برگشتی ساخته می‌شود', () {
    final profile = parseProfile(synthetic);
    expect(profile.summary, contains('آزمون'));
    expect(profile.summary, contains('فلزات اساسي'));
    expect(profile.summary, contains('بازار اول'));
    expect(profile.summary, isNot(contains('توصیه')));
    expect(profile.category, contains('فلزات اساسي'));
    expect(profile.category, contains('بازار اول'));
  });

  test('پاسخ ناقص یا نامعتبر رد می‌شود', () {
    expect(() => parseProfile('{"x":1}'), throwsFormatException);
    expect(() => parseProfile('not-json'), throwsFormatException);
    expect(() => parseProfile('[]'), throwsFormatException);
    expect(
      () => parseProfile('{"instrumentInfo":{"insCode":"x","lVal18AFC":"آ"}}'),
      throwsFormatException,
    );
    expect(
      () => parseProfile('{"instrumentInfo":{"insCode":"9001"}}'),
      throwsFormatException,
    );
  });
}
