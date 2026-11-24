import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Official identity and sector data for one instrument, read from TSETMC's
/// instrument-info endpoint. Every displayed value comes from that response;
/// missing fields stay null and are simply not shown.
class SymbolProfile {
  const SymbolProfile({
    required this.insCode,
    required this.symbol,
    required this.name,
    this.sector,
    this.market,
    this.board,
    this.isin,
    this.eps,
    this.sectorPe,
    this.psr,
    this.nav,
    this.shares,
    this.baseVolume,
    this.averageVolume,
    this.weekLow,
    this.weekHigh,
    this.yearLow,
    this.yearHigh,
  });

  final String insCode;
  final String symbol;
  final String name;
  final String? sector;
  final String? market;
  final String? board;
  final String? isin;
  final double? eps;
  final double? sectorPe;
  final double? psr;
  final double? nav;
  final double? shares;
  final int? baseVolume;
  final double? averageVolume;
  final double? weekLow;
  final double? weekHigh;
  final double? yearLow;
  final double? yearHigh;

  String get label => name.isEmpty ? symbol : name;

  /// Market/board text, preferring the most specific official title.
  String get place {
    final boardText = (board ?? '').trim();
    if (boardText.isNotEmpty) return boardText;
    return (market ?? '').trim();
  }

  /// Short category line for tiles: industry group plus market/board.
  String get category {
    final parts = <String>[];
    if ((sector ?? '').trim().isNotEmpty) parts.add(sector!.trim());
    if (place.isNotEmpty) parts.add(place);
    return parts.join(' — ');
  }

  /// Neutral Persian sentence built only from the returned fields. It never
  /// judges the instrument or recommends buying/selling it.
  String get summary {
    final parts = <String>['«$label» با نماد «$symbol»'];
    final sectorText = (sector ?? '').trim();
    if (sectorText.isNotEmpty) parts.add('در گروه «$sectorText»');
    if (place.isNotEmpty) parts.add(sectorText.isEmpty ? 'و $place' : 'در $place');
    parts.add('قرار دارد.');
    return parts.join(' ');
  }
}

class SymbolInfoClient {
  /// The instrument-info payload is small; cap it well below the market watch.
  static const int maxBytes = 2 * 1024 * 1024;

  Future<SymbolProfile> fetch(String insCode) async {
    final code = insCode.trim();
    if (!RegExp(r'^[0-9]{1,20}$').hasMatch(code)) {
      throw const FormatException('شناسهٔ نماد نامعتبر است.');
    }
    final profile = parseProfile(await _download(code));
    if (profile.insCode != code) {
      throw const FormatException('شناسهٔ نماد با پاسخ مطابقت ندارد.');
    }
    return profile;
  }

  Future<String> _download(String code) async {
    final client = HttpClient();
    client.findProxy = (_) => 'DIRECT';
    client.connectionTimeout = const Duration(seconds: 10);
    Object? lastError;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final req = await client.getUrl(Uri.parse(
            'https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/$code'));
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
    throw lastError ?? const HttpException('دریافت شناسنامهٔ نماد ناموفق بود.');
  }
}

/// Pure parser for the TSETMC instrument-info response.
SymbolProfile parseProfile(String body) {
  final Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException {
    throw const FormatException('پاسخ شناسنامه قابل خواندن نیست.');
  }
  if (decoded is! Map) {
    throw const FormatException('ساختار پاسخ شناسنامه نامعتبر است.');
  }
  final info = decoded['instrumentInfo'];
  if (info is! Map) {
    throw const FormatException('شناسنامهٔ نماد در پاسخ نیست.');
  }
  final insCode = (info['insCode'] ?? '').toString().trim();
  if (!RegExp(r'^[0-9]{1,20}$').hasMatch(insCode)) {
    throw const FormatException('شناسهٔ نماد در پاسخ نامعتبر است.');
  }
  final symbol = (info['lVal18AFC'] ?? '').toString().trim();
  if (symbol.isEmpty) {
    throw const FormatException('نام نماد در پاسخ نیست.');
  }
  final sectorMap = info['sector'];
  final epsMap = info['eps'];
  final sector = sectorMap is Map
      ? (_text(sectorMap['lSecVal']) ?? '')
      : '';
  return SymbolProfile(
    insCode: insCode,
    symbol: symbol,
    name: (info['lVal30'] ?? '').toString().trim(),
    sector: sector.isEmpty ? null : sector,
    market: _text(info['flowTitle']),
    board: _text(info['cgrValCotTitle']),
    isin: _text(info['cIsin']),
    eps: epsMap is Map ? _number(epsMap['estimatedEPS']) : null,
    sectorPe: epsMap is Map ? _number(epsMap['sectorPE']) : null,
    psr: epsMap is Map ? _number(epsMap['psr']) : null,
    nav: _number(info['nav']),
    shares: _number(info['zTitad']),
    baseVolume: _integer(info['baseVol']),
    averageVolume: _number(info['qTotTran5JAvg']),
    weekLow: _number(info['minWeek']),
    weekHigh: _number(info['maxWeek']),
    yearLow: _number(info['minYear']),
    yearHigh: _number(info['maxYear']),
  );
}

String? _text(dynamic value) {
  final text = value?.toString().trim() ?? '';
  // TSETMC uses dash/quote placeholders for instruments with no board title.
  if (text.replaceAll(RegExp(r'''[\s'"\-]+'''), '').isEmpty) return null;
  return text;
}

double? _number(dynamic value) {
  if (value is bool) return null;
  double? parsed;
  if (value is num) {
    parsed = value.toDouble();
  } else if (value is String) {
    parsed = double.tryParse(value.replaceAll(',', '').trim());
  }
  return parsed != null && parsed.isFinite ? parsed : null;
}

int? _integer(dynamic value) {
  if (value is int) return value;
  final parsed = _number(value);
  return parsed == null || parsed != parsed.roundToDouble()
      ? null
      : parsed.toInt();
}
