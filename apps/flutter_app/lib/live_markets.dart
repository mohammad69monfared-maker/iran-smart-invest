import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Live Iranian gold and currency rates from TGJU (tgju.org), the public
/// gold/FX reference. Values are shown exactly as published: Iranian items in
/// Rial, the world ounce in US Dollars. Nothing is interpolated or invented.
class MarketQuote {
  const MarketQuote({
    required this.key,
    required this.label,
    required this.unit,
    required this.price,
    required this.fetchedAt,
    this.changePercent,
    this.updatedAt,
  });

  final String key;
  final String label;
  final String unit;
  final double price;
  final DateTime fetchedAt;
  final double? changePercent;
  final String? updatedAt;
}

class MarketSpec {
  const MarketSpec(this.key, this.label, this.unit);
  final String key;
  final String label;
  final String unit;
}

/// Order matters: the dashboard shows the tiles in this order.
const List<MarketSpec> marketCatalog = [
  MarketSpec('price_dollar_rl', 'دلار آزاد', 'تومان'),
  MarketSpec('geram18', 'طلا ۱۸ عیار (گرم)', 'تومان'),
  MarketSpec('mesghal', 'مثقال طلا', 'تومان'),
  MarketSpec('sekeb', 'سکه امامی', 'تومان'),
  MarketSpec('ons', 'اونس جهانی', 'دلار'),
];

class LiveMarketClient {
  static const int maxBytes = 3 * 1024 * 1024;

  static const String _endpoint = 'https://call1.tgju.org/ajax.json';

  Future<Map<String, MarketQuote>> fetch() async {
    final body = await _download();
    return parseMarkets(body, DateTime.now().toUtc());
  }

  Future<String> _download() async {
    final client = HttpClient();
    client.findProxy = (_) => 'DIRECT';
    client.connectionTimeout = const Duration(seconds: 12);
    Object? lastError;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final req = await client.getUrl(Uri.parse(_endpoint));
        // Only the known HTTPS endpoint is contacted; redirects are refused.
        req.followRedirects = false;
        req.persistentConnection = false;
        req.headers.set('Accept', 'application/json, text/plain, */*');
        req.headers.set(
          'User-Agent',
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        );
        req.headers.set('Referer', 'https://www.tgju.org/');
        req.headers.set('Origin', 'https://www.tgju.org');
        final res = await req.close().timeout(const Duration(seconds: 20));
        if (res.statusCode != 200) {
          throw HttpException('HTTP ${res.statusCode}');
        }
        final builder = BytesBuilder(copy: false);
        var size = 0;
        await for (final chunk in res.timeout(const Duration(seconds: 20))) {
          size += chunk.length;
          if (size > maxBytes) {
            throw const HttpException('پاسخ بزرگ‌تر از حد مجاز است.');
          }
          builder.add(chunk);
        }
        return utf8.decode(builder.takeBytes());
      } on SocketException catch (error) {
        lastError = error;
      } on HttpException catch (error) {
        lastError = error;
      } on TimeoutException catch (error) {
        lastError = error;
      }
    }
    throw lastError ?? const HttpException('دریافت نرخ لحظه‌ای ناموفق بود.');
  }
}

/// Pure parser for offline unit tests. Keys outside the catalog and rows with
/// a missing, zero or unreadable price are skipped rather than guessed.
Map<String, MarketQuote> parseMarkets(String body, DateTime received) {
  final decoded = _decode(body);
  if (decoded is! Map) {
    throw const FormatException('ساختار پاسخ نرخ‌ها نامعتبر است.');
  }
  final current = decoded['current'];
  if (current is! Map) {
    throw const FormatException('نرخ‌های جاری در پاسخ نیست.');
  }
  final out = <String, MarketQuote>{};
  for (final spec in marketCatalog) {
    final raw = current[spec.key];
    if (raw is! Map) continue;
    final price = _number(raw['p']);
    if (price == null || price <= 0) continue;
    out[spec.key] = MarketQuote(
      key: spec.key,
      label: spec.label,
      unit: spec.unit,
      price: price,
      changePercent: _number(raw['dp']),
      updatedAt: _clock(raw['ts']),
      fetchedAt: received,
    );
  }
  return out;
}

Object? _decode(String body) {
  try {
    return jsonDecode(body);
  } on FormatException {
    throw const FormatException('پاسخ نرخ‌ها قابل خواندن نیست.');
  }
}

double? _number(dynamic value) {
  if (value is bool) return null;
  double? parsed;
  if (value is num) {
    parsed = value.toDouble();
  } else if (value is String) {
    parsed = double.tryParse(value.replaceAll(',', '').trim());
  }
  if (parsed == null || !parsed.isFinite) return null;
  return parsed;
}

/// "2026-11-24 19:59:40" (Tehran) -> "19:59".
String? _clock(dynamic value) {
  if (value is! String) return null;
  final match = RegExp(r'(\d{1,2}):(\d{2})').firstMatch(value);
  if (match == null) return null;
  final hour = match.group(1)!.padLeft(2, '0');
  return '$hour:${match.group(2)}';
}
