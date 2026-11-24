import 'package:flutter_test/flutter_test.dart';
import 'package:iran_smart_invest/live_prices.dart';

// تمام ردیف‌های این فایل دادهٔ مصنوعی آزمون هستند و هرگز منتشر نمی‌شوند.
const synthetic = '''
{"marketwatch":[
  {"insCode":"1001","lva":"آزمون","pdv":12345,"dEven":20261124,"pMax":13000,"pMin":12000},
  {"insCode":"1002","l18":"قدیمی","pl":9876,"deven":20261123},
  {"insCode":"1003","lva":"صفر","pdv":0,"dEven":20261124},
  {"insCode":"1004","lva":"منفی","pdv":-5,"dEven":20261124},
  {"insCode":"1005","lva":"بیرون‌بازه","pdv":99999,"dEven":20261124,"pMax":13000,"pMin":12000},
  {"insCode":"1006","lva":"ناشناس","pdv":500,"dEven":20261124},
  {"insCode":"1007","lva":"بدون‌تاریخ","pdv":777},
  "ردیف نامعتبر"
]}
''';

void main() {
  final received = DateTime.utc(2026, 11, 24, 9, 30);

  test('فقط نمادهای خواسته‌شده با قیمت معتبر برمی‌گردند', () {
    final quotes = parseWatch(
        synthetic, {'آزمون', 'قدیمی', 'صفر', 'منفی', 'بیرون‌بازه', 'بدون‌تاریخ'}, received);
    expect(quotes.keys.toSet(), {'آزمون', 'قدیمی', 'بدون‌تاریخ'});
    expect(quotes['آزمون']!.price, 12345);
    expect(quotes['آزمون']!.date, '2026-11-24');
    expect(quotes['آزمون']!.ceiling, 13000);
    expect(quotes['آزمون']!.floor, 12000);
    expect(quotes['آزمون']!.fetchedAt, received);
    // نام فیلدهای قدیمی هم پشتیبانی می‌شود.
    expect(quotes['قدیمی']!.price, 9876);
    expect(quotes['قدیمی']!.date, '2026-11-23');
    expect(quotes['بدون‌تاریخ']!.date, isNull);
  });

  test('نمادهای خارج از فهرست درخواست نادیده گرفته می‌شوند', () {
    final quotes = parseWatch(synthetic, {'آزمون'}, received);
    expect(quotes.keys.toList(), ['آزمون']);
    expect(parseWatch(synthetic, const <String>{}, received), isEmpty);
  });

  test('پاسخ بدون فهرست نمادها رد می‌شود', () {
    expect(() => parseWatch('{"other":1}', {'آزمون'}, received),
        throwsFormatException);
    expect(() => parseWatch('[]', {'آزمون'}, received), throwsFormatException);
    expect(() => parseWatch('not-json', {'آزمون'}, received),
        throwsFormatException);
  });
}
