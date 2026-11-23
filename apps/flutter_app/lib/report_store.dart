import 'dart:async';
import 'dart:convert';
import 'dart:io';

typedef Row = Map<String, dynamic>;

class MarketStore {
  String endpoint = const String.fromEnvironment('SUPABASE_URL');
  String key = const String.fromEnvironment('SUPABASE_ANON_KEY');
  String? token;
  String? owner;
  String? _refreshToken;

  bool get connected => token != null;

  Uri _validate() {
    final base = Uri.parse(endpoint.trim());
    if (base.scheme != 'https' ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        (base.path.isNotEmpty && base.path != '/') ||
        base.query.isNotEmpty) {
      throw const FormatException('نشانی HTTPS معتبر وارد کنید.');
    }
    return base;
  }

  /// Some Windows networks close a reused TLS connection before the response
  /// headers arrive. Each call therefore uses a fresh DIRECT connection and a
  /// single retry; no request is ever duplicated once it has been answered.
  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Row? body,
    bool retry = true,
    bool auth = true,
  }) async {
    final base = _validate();
    Object? lastError;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        return await _send(base, path, method: method, body: body,
            retry: retry, auth: auth);
      } on SocketException catch (error) {
        lastError = error;
      } on HttpException catch (error) {
        if (attempt == 0 &&
            !error.message.toLowerCase().contains('header') &&
            !error.message.toLowerCase().contains('closed')) {
          rethrow;
        }
        lastError = error;
      }
    }
    throw lastError ?? const HttpException('درخواست ناموفق بود.');
  }

  Future<dynamic> _send(
    Uri base,
    String path, {
    required String method,
    Row? body,
    required bool retry,
    required bool auth,
  }) async {
    final client = HttpClient();
    client.findProxy = (_) => 'DIRECT';
    client.connectionTimeout = const Duration(seconds: 15);
    client.idleTimeout = const Duration(seconds: 10);
    try {
      final req = await client.openUrl(method, base.resolve(path));
      req.followRedirects = false;
      req.persistentConnection = false;
      req.headers.set('apikey', key.trim());
      req.headers.set('User-Agent', 'IranSmartInvest/1.0');
      if (auth && token != null) {
        req.headers.set('Authorization', 'Bearer $token');
      }
      if (body != null) {
        req.headers.contentType = ContentType.json;
        req.write(jsonEncode(body));
      }
      final res = await req.close().timeout(const Duration(seconds: 25));
      final raw = await utf8.decoder
          .bind(res)
          .join()
          .timeout(const Duration(seconds: 25));
      if (res.statusCode == 401 && auth && retry && _refreshToken != null) {
        final session = await request(
          '/auth/v1/token?grant_type=refresh_token',
          method: 'POST',
          body: {'refresh_token': _refreshToken},
          auth: false,
        );
        _session(session);
        return await request(path, method: method, body: body, retry: false);
      }
      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw HttpException('درخواست پذیرفته نشد (HTTP ${res.statusCode}).');
      }
      return raw.isEmpty ? null : jsonDecode(raw);
    } finally {
      client.close(force: true);
    }
  }

  void _session(dynamic data) {
    token = data['access_token'] as String;
    owner = data['user']['id'] as String;
    _refreshToken = data['refresh_token'] as String?;
  }

  Future<void> login(String email, String password) async {
    logout();
    _session(
      await request(
        '/auth/v1/token?grant_type=password',
        method: 'POST',
        body: {'email': email.trim(), 'password': password},
        auth: false,
      ),
    );
  }

  void logout() {
    token = null;
    owner = null;
    _refreshToken = null;
  }

  Future<Row?> report() async {
    if (connected) {
      final rows = await request(
        '/rest/v1/daily_reports?select=report&order=report_date.desc&limit=1',
      );
      return rows.isEmpty ? null : rows.first['report'] as Row;
    }
    if (!Platform.isWindows) return null;
    final roots = [Directory.current, File(Platform.resolvedExecutable).parent];
    for (var root in roots) {
      for (var i = 0; i < 12; i++) {
        final file = File('${root.path}/data/latest.json');
        if (await file.exists()) {
          return jsonDecode(await file.readAsString()) as Row;
        }
        if (root.parent.path == root.path) break;
        root = root.parent;
      }
    }
    return null;
  }
}
