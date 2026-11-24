import 'package:flutter_test/flutter_test.dart';
import 'package:iran_smart_invest/live_markets.dart';

// دادهٔ مصنوعی آزمون؛ هیچ رقمی از بازار واقعی در این فایل نیست.
const synthetic = '''
{"current":{
  "price_dollar_rl":{"p":"111,111","dp":1.5,"ts":"2026-11-24 12:00:00"},
  "geram18":{"p":"222,222","dp":-2.0,"ts":"2026-11-24 12:01:07"},
  "mesghal":{"p":"0","dp":1,"ts":"2026-11-24 12:02:00"},
  "sekeb":{"p":"قیمت نامعتبر","dp":1},
  "ons":{"p":"3333.5","dp":0.25,"ts":"2026-11-24 22:00:00"},
  "unknown_key":{"p":"1"}
}}
''';

void main() {
  final received = DateTime.utc(2026, 11, 24, 12, 30);

  test('فقط نرخ‌های معتبر کاتالوگ برمی‌گردند و ترتیب حفظ می‌شود', () {
    final rates = parseMarkets(synthetic, received);
    expect(rates.keys.toList(),
        ['price_dollar_rl', 'geram18', 'ons']);
    final dollar = rates['price_dollar_rl']!;
    expect(dollar.price, 111111);
    expect(dollar.changePercent, 1.5);
    expect(dollar.unit, 'تومان');
    expect(dollar.updatedAt, '12:00');
    expect(dollar.fetchedAt, received);
    expect(rates['geram18']!.changePercent, -2.0);
    expect(rates['geram18']!.updatedAt, '12:01');
    expect(rates['ons']!.unit, 'دلار');
  });

  test('پاسخ بدون بخش current رد می‌شود', () {
    expect(() => parseMarkets('{"x":1}', received), throwsFormatException);
    expect(() => parseMarkets('not-json', received), throwsFormatException);
    expect(() => parseMarkets('[]', received), throwsFormatException);
  });
}
