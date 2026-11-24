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

// کاتالوگ مصنوعی برای آزمون جست‌وجو؛ هیچ رقمی از بازار واقعی نیست.
const catalogue = '''
{"marketwatch":[
  {"insCode":"2001","lva":"فولاد","lvc":"فولاد مباركه اصفهان","pdv":5270,"py":5120,
   "pMax":5300,"pMin":5000,"qtj":1000,"qtc":5270000,"flow":1,"cGrValCot":"N1","pe":"7.6","ztt":12},
  {"insCode":"2002","lva":"فولادح","lvc":"حق تقدم فولاد مباركه اصفهان","pdv":1200,"py":1000,
   "pMax":1300,"pMin":900,"qtj":50,"qtc":60000},
  {"insCode":"2003","lva":"شپنا","lvc":"پالايش نفت اصفهان","pdv":0,"py":500},
  {"insCode":"2004","lva":"طلا","lvc":"صندوق س. كالاي پارسيان","pdv":25000,"py":24000,"flow":7},
  {"insCode":"2005","lva":"خساپا","lvc":"سايپا","pdv":3000,"py":3100},
  {"insCode":"bad","lva":"بدون‌شناسه","pdv":10},
  {"insCode":"2006","lva":"","pdv":10}
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

  test('کاتالوگ هویت نماد را حتی با قیمت نامعتبر نگه می‌دارد', () {
    final snapshot = parseSnapshot(catalogue, received);
    expect(snapshot.rows.length, 5);
    final foolad = snapshot.byInsCode['2001']!;
    expect(foolad.symbol, 'فولاد');
    expect(foolad.name, 'فولاد مباركه اصفهان');
    expect(foolad.last, 5270);
    expect(foolad.previous, 5120);
    expect(foolad.changePercent, closeTo(2.9296875, 0.0001));
    expect(foolad.flow, 1);
    expect(foolad.pe, 7.6);
    expect(foolad.traded, isTrue);
    // قیمت صفر رد می‌شود ولی نماد برای جست‌وجو می‌ماند.
    final shepna = snapshot.rowFor('2003', 'شپنا')!;
    expect(shepna.last, isNull);
    expect(shepna.traded, isFalse);
    // ردیف‌های بدون شناسهٔ عددی یا نام حذف می‌شوند.
    expect(snapshot.byInsCode.containsKey('bad'), isFalse);
    expect(snapshot.bySymbol.containsKey(''), isFalse);
    expect(snapshot.rowFor(null, 'خساپا')!.last, 3000);
  });

  test('جست‌وجوی بخشی از نام، نتیجهٔ دقیق را اول می‌آورد', () {
    final snapshot = parseSnapshot(catalogue, received);
    final hits = searchSymbols(snapshot, 'فولاد');
    expect(hits.first.symbol, 'فولاد');
    expect(hits.map((row) => row.symbol), contains('فولادح'));
  });

  test('جست‌وجو ي/ك عربی و فاصلهٔ مجازی را یکسان می‌کند', () {
    final snapshot = parseSnapshot(catalogue, received);
    expect(searchSymbols(snapshot, 'پالایش').map((row) => row.symbol),
        contains('شپنا'));
    expect(searchSymbols(snapshot, 'کالا').map((row) => row.symbol),
        contains('طلا'));
    expect(searchSymbols(snapshot, 'فولاد  اصفهان').length, 2);
  });

  test('جست‌وجوی خالی یا کاتالوگ ناموجود نتیجه نمی‌دهد', () {
    final snapshot = parseSnapshot(catalogue, received);
    expect(searchSymbols(snapshot, '   '), isEmpty);
    expect(searchSymbols(snapshot, ''), isEmpty);
    expect(searchSymbols(null, 'فولاد'), isEmpty);
    expect(searchSymbols(snapshot, 'فولاد', limit: 1).length, 1);
  });
}
