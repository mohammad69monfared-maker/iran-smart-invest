import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Live last prices fetched straight from TSETMC. The same response also lists
/// every instrument traded on the Iranian market, so it doubles as the local
/// symbol catalogue used by search and by the named watchlists.
class LiveQuote {
  const LiveQuote({
    required this.symbol,
    required this.price,
    required this.fetchedAt,
    this.date,
    this.ceiling,
    this.floor,
    this.changePercent,
  });

  final String symbol;
  final double price;
  final String? date;
  final DateTime fetchedAt;
  final double? ceiling;
  final double? floor;
  final double? changePercent;
}

/// One row of TSETMC's market watch. Identity fields (code, symbol, name) are
/// kept even when the price is rejected as out of range, so the instrument is
/// still searchable; only the invalid numbers are dropped.
class SymbolRow {
  const SymbolRow({
    required this.insCode,
    required this.symbol,
    required this.name,
    this.last,
    this.close,
    this.previous,
    this.changePercent,
    this.high,
    this.low,
    this.volume,
    this.value,
    this.trades,
    this.flow,
    this.groupCode,
    this.pe,
    this.sessionDate,
  });

  final String insCode;
  final String symbol;
  final String name;
  final double? last;
  final double? close;
  final double? previous;
  final double? changePercent;
  final double? high;
  final double? low;
  final double? volume;
  final double? value;
  final double? trades;
  final int? flow;
  final String? groupCode;
  final double? pe;
  final String? sessionDate;

  bool get traded => (volume ?? 0) > 0;
}

class MarketSnapshot {
  MarketSnapshot({required List<SymbolRow> rows, required this.fetchedAt})
      : rows = List<SymbolRow>.unmodifiable(rows);

  final List<SymbolRow> rows;
  final DateTime fetchedAt;

  late final Map<String, SymbolRow> byInsCode = {
    for (final row in rows) row.insCode: row,
  };
  late final Map<String, SymbolRow> bySymbol = {
    for (final row in rows) row.symbol: row,
  };

  SymbolRow? rowFor(String? insCode, String? symbol) {
    final code = (insCode ?? '').trim();
    if (code.isNotEmpty) {
      final match = byInsCode[code];
      if (match != null) return match;
    }
    final name = (symbol ?? '').trim();
    return name.isEmpty ? null : bySymbol[name];
  }

  /// Quotes only for the requested symbols; unknown symbols are ignored.
  Map<String, LiveQuote> quotesFor(Set<String> symbols) {
    if (symbols.isEmpty) return const {};
    final out = <String, LiveQuote>{};
    for (final row in rows) {
      if (!symbols.contains(row.symbol) || row.last == null) continue;
      out[row.symbol] = LiveQuote(
        symbol: row.symbol,
        price: row.last!,
        date: row.sessionDate,
        fetchedAt: fetchedAt,
        ceiling: row.high,
        floor: row.low,
        changePercent: row.changePercent,
      );
    }
    return out;
  }
}

class LivePriceClient {
  /// Hard cap for one market-watch response (the payload is a few MB).
  static const int maxBytes = 8 * 1024 * 1024;

  // Best limits are not used by the app; omitting them more than halves the
  // response while keeping every instrument and its last/closing prices.
  static const String _endpoint =
      'https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch'
      '?market=0&industrialGroup=&paperTypes%5B0%5D=1&showTraded=false'
      '&withBestLimits=false&hEven=0&RefID=0';

  /// Whole market in one request. Used for search, watchlists and the live
  /// price shown next to each report signal.
  Future<MarketSnapshot> fetchSnapshot() async {
    final body = await _download();
    return parseSnapshot(body, DateTime.now().toUtc());
  }

  /// Kept for callers that only need a few quotes.
  Future<Map<String, LiveQuote>> fetch(Set<String> symbols) async {
    if (symbols.isEmpty) return const {};
    final snapshot = await fetchSnapshot();
    return snapshot.quotesFor(symbols);
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
        final res = await req.close().timeout(const Duration(seconds: 25));
        if (res.statusCode != 200) {
          throw HttpException('HTTP ${res.statusCode}');
        }
        final builder = BytesBuilder(copy: false);
        var size = 0;
        await for (final chunk in res.timeout(const Duration(seconds: 25))) {
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
    throw lastError ?? const HttpException('دریافت فهرست بازار ناموفق بود.');
  }
}

/// Pure parser so every validation rule stays unit-testable offline.
MarketSnapshot parseSnapshot(String body, DateTime received) {
  final decoded = _decode(body);
  if (decoded is! Map) {
    throw const FormatException('ساختار پاسخ نامعتبر است.');
  }
  final rawRows = decoded['marketwatch'];
  if (rawRows is! List) {
    throw const FormatException('فهرست نمادها در پاسخ نیست.');
  }
  final rows = <SymbolRow>[];
  final seen = <String>{};
  for (final raw in rawRows) {
    if (raw is! Map) continue;
    final insCode = (raw['insCode'] ?? '').toString().trim();
    if (!RegExp(r'^[0-9]{1,20}$').hasMatch(insCode) || !seen.add(insCode)) {
      continue;
    }
    final rawSymbol = raw['lva'] ?? raw['l18'] ?? raw['lVal18AFC'];
    if (rawSymbol is! String || rawSymbol.trim().isEmpty) continue;
    final symbol = rawSymbol.trim();
    final rawName = raw['lvc'] ?? raw['l30'] ?? raw['lVal30'];
    final name = rawName is String ? rawName.trim() : '';

    final price = _number(raw['pdv'] ?? raw['pl'] ?? raw['pDrCotVal']);
    final high = _number(raw['pMax'] ?? raw['tmax']);
    final low = _number(raw['pMin'] ?? raw['tmin']);
    final valid = _validPrice(price, high, low);
    final previous = _number(raw['py'] ?? raw['priceYesterday']);
    final close = _number(raw['pcl'] ?? raw['pClosing']);
    final change = valid && previous != null && previous > 0
        ? ((price! - previous) / previous) * 100
        : null;
    final volume = _number(raw['qtj'] ?? raw['qTotTran5J']);
    final value = _number(raw['qtc'] ?? raw['qTotCap']);

    rows.add(SymbolRow(
      insCode: insCode,
      symbol: symbol,
      name: name,
      last: valid ? price : null,
      close: valid && close != null && close > 0 ? close : null,
      previous: valid && previous != null && previous > 0 ? previous : null,
      changePercent: change != null && change.isFinite ? change : null,
      high: valid ? high : null,
      low: valid ? low : null,
      volume: volume != null && volume >= 0 ? volume : null,
      value: value != null && value >= 0 ? value : null,
      trades: _number(raw['ztt']),
      flow: _integer(raw['flow']),
      groupCode: (raw['cGrValCot'] ?? raw['cgrValCot'])?.toString().trim(),
      pe: _number(raw['pe']),
      sessionDate: _sessionDate(raw['dEven'] ?? raw['deven']),
    ));
  }
  if (rows.isEmpty) {
    throw const FormatException('هیچ نماد معتبری در پاسخ نبود.');
  }
  return MarketSnapshot(rows: rows, fetchedAt: received);
}

/// Legacy helper: quotes for a requested set of symbols.
Map<String, LiveQuote> parseWatch(
    String body, Set<String> symbols, DateTime received) {
  if (symbols.isEmpty) return const {};
  return parseSnapshot(body, received).quotesFor(symbols);
}

/// Persian text normalisation for forgiving search: Arabic ي/ك and the
/// alef variants are folded, ZWNJ and diacritics are removed, whitespace is
/// collapsed. Only the comparison key changes; displayed names stay intact.
String normalizeSymbolText(String value) => value
    .replaceAll('\u064a', '\u06cc') // ي -> ی
    .replaceAll('\u0643', '\u06a9') // ك -> ک
    .replaceAll('\u0623', '\u0627') // أ -> ا
    .replaceAll('\u0625', '\u0627') // إ -> ا
    .replaceAll('\u0622', '\u0627') // آ -> ا
    .replaceAll('\u0629', '\u0647') // ة -> ه
    .replaceAll('\u0649', '\u06cc') // ى -> ی
    .replaceAll('\u200c', ' ')
    .replaceAll(RegExp(r'[\u064b-\u065f\u0670]'), '')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim()
    .toLowerCase();

/// All-token search over the downloaded catalogue. Results are ranked so an
/// exact symbol wins, then symbol prefixes, then names; ties keep a stable
/// alphabetical order. Returns an empty list for an empty catalogue/query.
List<SymbolRow> searchSymbols(MarketSnapshot? snapshot, String query,
    {int limit = 30}) {
  if (snapshot == null || limit < 1) return const [];
  final needle = normalizeSymbolText(query);
  if (needle.isEmpty) return const [];
  final tokens = needle.split(' ');
  final scored = <({int score, SymbolRow row})>[];
  for (final row in snapshot.rows) {
    final symbol = normalizeSymbolText(row.symbol);
    final name = normalizeSymbolText(row.name);
    final haystack = '$symbol $name';
    if (!tokens.every(haystack.contains)) continue;
    final int score;
    if (symbol == needle) {
      score = 0;
    } else if (symbol.startsWith(needle)) {
      score = 1;
    } else if (symbol.contains(needle)) {
      score = 2;
    } else if (name.startsWith(needle)) {
      score = 3;
    } else {
      score = 4;
    }
    scored.add((score: score, row: row));
  }
  scored.sort((a, b) {
    final byScore = a.score.compareTo(b.score);
    if (byScore != 0) return byScore;
    final byLength = a.row.symbol.length.compareTo(b.row.symbol.length);
    if (byLength != 0) return byLength;
    return a.row.symbol.compareTo(b.row.symbol);
  });
  return scored.take(limit).map((entry) => entry.row).toList();
}

Object? _decode(String body) {
  try {
    return jsonDecode(body);
  } on FormatException {
    throw const FormatException('پاسخ بازار قابل خواندن نیست.');
  }
}

bool _validPrice(double? price, double? high, double? low) {
  if (price == null || !price.isFinite || price <= 0) return false;
  if (high != null && low != null) {
    if (!high.isFinite || !low.isFinite || high < low) return false;
    if (price > high || price < low) return false;
  }
  return true;
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

int? _integer(dynamic value) {
  if (value is int) return value;
  final parsed = _number(value);
  return parsed == null || parsed != parsed.roundToDouble()
      ? null
      : parsed.toInt();
}

String? _sessionDate(dynamic value) {
  final text = value is num ? value.toInt().toString() : value?.toString();
  if (text == null || !RegExp(r'^\d{8}$').hasMatch(text)) return null;
  return '${text.substring(0, 4)}-${text.substring(4, 6)}-${text.substring(6)}';
}
