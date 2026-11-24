import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Live last prices fetched straight from TSETMC for the symbols that are
/// already in the published report. These quotes are shown next to the
/// report's end-of-session price; they never modify the signals themselves.
class LiveQuote {
  const LiveQuote({
    required this.symbol,
    required this.price,
    required this.fetchedAt,
    this.date,
    this.ceiling,
    this.floor,
  });

  final String symbol;
  final double price;
  final String? date;
  final DateTime fetchedAt;
  final double? ceiling;
  final double? floor;
}

class LivePriceClient {
  /// Hard cap for one market-watch response (the payload is a few MB).
  static const int maxBytes = 8 * 1024 * 1024;

  static const String _endpoint =
      'https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch'
      '?market=0&industrialGroup=&paperTypes%5B0%5D=1&showTraded=false'
      '&withBestLimits=true&hEven=0&RefID=0';

  /// Returns quotes only for the requested symbols; unknown symbols are
  /// ignored, so gold/FX rows from the global section never match.
  Future<Map<String, LiveQuote>> fetch(Set<String> symbols) async {
    if (symbols.isEmpty) return const {};
    final body = await _download();
    return parseWatch(body, symbols, DateTime.now().toUtc());
  }

  Future<String> _download() async {
    final client = HttpClient();
    client.findProxy = (_) => 'DIRECT';
    client.connectionTimeout = const Duration(seconds: 12);
    Object? lastError;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final req = await client.getUrl(Uri.parse(_endpoint));
        // Redirects from the CDN are never followed (supply-chain safety).
        req.followRedirects = false;
        req.persistentConnection = false;
        req.headers.set('Accept', 'application/json, text/plain, */*');
        req.headers.set(
          'User-Agent',
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        );
        req.headers.set('Referer', 'https://www.tsetmc.com/');
        req.headers.set('Origin', 'https://www.tsetmc.com');
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
    throw lastError ?? const HttpException('دریافت قیمت زنده ناموفق بود.');
  }
}

/// Pure parser so the validation rules can be unit-tested offline.
/// Rows with missing, non-positive or physically impossible prices are
/// skipped instead of guessed: only exchange-validated numbers are shown.
Map<String, LiveQuote> parseWatch(String body, Set<String> symbols,
    DateTime received) {
  if (symbols.isEmpty) return const {};
  final decoded = _decode(body);
  if (decoded is! Map) {
    throw const FormatException('ساختار پاسخ نامعتبر است.');
  }
  final rows = decoded['marketwatch'];
  if (rows is! List) {
    throw const FormatException('فهرست نمادها در پاسخ نیست.');
  }
  final out = <String, LiveQuote>{};
  for (final raw in rows) {
    if (raw is! Map) continue;
    final name = raw['lva'] ?? raw['l18'] ?? raw['lVal18AFC'];
    if (name is! String) continue;
    final symbol = name.trim();
    if (symbol.isEmpty || !symbols.contains(symbol)) continue;
    final price = _number(raw['pdv'] ?? raw['pl'] ?? raw['pDrCotVal']);
    if (price == null || price <= 0) continue;
    final ceiling = _number(raw['pMax'] ?? raw['tmax']);
    final floor = _number(raw['pMin'] ?? raw['tmin']);
    if (ceiling != null && floor != null &&
        (ceiling < floor || price > ceiling || price < floor)) {
      continue;
    }
    out[symbol] = LiveQuote(
      symbol: symbol,
      price: price,
      date: _sessionDate(raw['dEven'] ?? raw['deven']),
      fetchedAt: received,
      ceiling: ceiling,
      floor: floor,
    );
  }
  return out;
}

Object? _decode(String body) {
  try {
    return jsonDecode(body);
  } on FormatException {
    throw const FormatException('پاسخ بازار قابل خواندن نیست.');
  }
}

double? _number(dynamic value) {
  double? parsed;
  if (value is bool) return null;
  if (value is num) {
    parsed = value.toDouble();
  } else if (value is String) {
    parsed = double.tryParse(value);
  }
  if (parsed == null || !parsed.isFinite) return null;
  return parsed;
}

String? _sessionDate(dynamic value) {
  final text = value is num ? value.toInt().toString() : value?.toString();
  if (text == null || !RegExp(r'^\d{8}$').hasMatch(text)) return null;
  return '${text.substring(0, 4)}-${text.substring(4, 6)}-${text.substring(6)}';
}
