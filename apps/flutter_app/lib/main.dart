import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'jalali.dart';
import 'live_markets.dart';
import 'live_prices.dart';
import 'report_store.dart' as data;
import 'symbol_info.dart';

void main() => runApp(const InvestApp());
const gold = Color(0xffe7bf74);
const panels = [
  'داشبورد',
  'فرصت‌ها',
  'تحلیل نماد',
  'سبد سهام',
  'دیده‌بان',
  'عملکرد',
  'تنظیمات',
  'بازارهای جهانی',
];
const icons = [
  Icons.dashboard_outlined,
  Icons.radar,
  Icons.show_chart,
  Icons.account_balance_wallet_outlined,
  Icons.visibility_outlined,
  Icons.insights,
  Icons.settings_outlined,
  Icons.public,
];

class InvestApp extends StatelessWidget {
  const InvestApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'بورس هوشمند ایران',
    theme: ThemeData(
      brightness: Brightness.dark,
      useMaterial3: true,
      fontFamily: 'Vazirmatn',
      scaffoldBackgroundColor: const Color(0xff101720),
      colorScheme: ColorScheme.fromSeed(
        seedColor: gold,
        brightness: Brightness.dark,
      ).copyWith(primary: gold),
    ),
    builder: (_, child) =>
        Directionality(textDirection: TextDirection.rtl, child: child!),
    home: const MarketHome(),
  );
}

class MarketHome extends StatefulWidget {
  const MarketHome({super.key});
  @override
  State<MarketHome> createState() => _MarketHomeState();
}

class _MarketHomeState extends State<MarketHome> {
  final store = data.MarketStore();
  final endpoint = TextEditingController(),
      keyField = TextEditingController(),
      email = TextEditingController(),
      password = TextEditingController(),
      query = TextEditingController(),
      watchQuery = TextEditingController();
  Timer? _sync;
  int page = 0;
  bool busy = false;
  String? error;
  data.Row? report;
  List<data.Row> portfolios = [],
      positions = [],
      trades = [],
      alerts = [];
  data.Row settings = {};
  String? portfolio;
  DateTime? _lastBackPressed;
  final Map<String, LiveQuote> _live = {};
  DateTime? _liveAt;
  bool _liveBusy = false;
  MarketSnapshot? _snapshot;
  List<data.Row> watchLists = [];
  String? watchListId;
  final Map<String, SymbolProfile> _profiles = {};
  final Set<String> _profileBusy = {};
  final Set<String> _profileTried = {};
  static final Random _random = Random();
  final Map<String, MarketQuote> _markets = {};
  DateTime? _marketsAt;
  bool _marketsBusy = false;
  Timer? _marketSync;
  @override
  void initState() {
    super.initState();
    endpoint.text = store.endpoint;
    keyField.text = store.key;
    run(() async {
      await store.restore();
      if (!mounted) return;
      endpoint.text = store.endpoint;
      keyField.text = store.key;
      email.text = store.emailAddress;
      await reload();
    });
    _sync = Timer.periodic(const Duration(seconds: 45), (_) {
      if (!mounted ||
          WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        return;
      }
      if (store.connected && !busy) refresh();
      if (marketOpen) syncLive();
    });
    _marketSync = Timer.periodic(const Duration(seconds: 120), (_) {
      if (!mounted ||
          WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        return;
      }
      if (ratesOpen) syncMarkets();
    });
  }

  @override
  void dispose() {
    _sync?.cancel();
    _marketSync?.cancel();
    for (final t in [endpoint, keyField, email, password, query, watchQuery]) {
      t.dispose();
    }
    super.dispose();
  }

  Future<void> run(Future<void> Function() task) async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await task();
    } catch (e) {
      error = e is SocketException
          ? 'ارتباط با سرور برقرار نشد.'
          : e.toString();
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<List<data.Row>> rows(String path) async =>
      List<data.Row>.from(await store.request('/rest/v1/$path'));
  Future<void> reload() async {
    report = await store.report();
    unawaited(syncLive());
    unawaited(syncMarkets());
    if (!store.connected) return;
    portfolios = await rows('portfolios?select=id,name&order=created_at');
    if (!portfolios.any((v) => v['id'] == portfolio))
      portfolio = portfolios.firstOrNull?['id'];
    if (portfolio != null) {
      final id = Uri.encodeQueryComponent(portfolio!);
      positions = await rows(
        'portfolio_positions?portfolio_id=eq.$id&select=*',
      );
      trades = await rows(
        'portfolio_transactions?portfolio_id=eq.$id&select=*&order=traded_at.desc&limit=100',
      );
    } else {
      positions = [];
      trades = [];
    }
    alerts = await rows('alerts?select=*&order=created_at.desc&limit=30');
    final options = await rows('app_settings?select=settings');
    settings = options.isEmpty
        ? {}
        : Map<String, dynamic>.from(options.first['settings']);
    await _loadWatchLists(options.firstOrNull);
  }

  Future<void> refresh() => run(reload);

  /// بازار تهران: شنبه تا چهارشنبه، ۰۸:۳۰ تا ۱۲:۵۵ به وقت تهران.
  bool get marketOpen {
    final t = DateTime.now().toUtc().add(const Duration(hours: 3, minutes: 30));
    final tradingDay = t.weekday == 6 || t.weekday == 7 || t.weekday <= 3;
    final minutes = t.hour * 60 + t.minute;
    return tradingDay && minutes >= 8 * 60 + 30 && minutes <= 12 * 60 + 55;
  }

  String _clock(DateTime moment) {
    final t = moment.toUtc().add(const Duration(hours: 3, minutes: 30));
    return '${t.hour.toString().padLeft(2, '0')}'
        ':${t.minute.toString().padLeft(2, '0')}';
  }

  String money(num value) {
    final text = value == value.roundToDouble()
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(2);
    return text.replaceAllMapped(
        RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  }

  /// دریافت یک‌بارهٔ فهرست کامل بازار از TSETMC. همین پاسخ هم قیمت زندهٔ
  /// سیگنال‌ها، هم جست‌وجوی نمادها و هم قیمت زندهٔ دیده‌بان را تأمین می‌کند.
  /// خطای شبکه فقط آخرین فهرست معتبر را نگه می‌دارد و به گزارش کاری ندارد.
  Future<void> syncLive() async {
    if (_liveBusy) return;
    _liveBusy = true;
    try {
      final snapshot = await LivePriceClient().fetchSnapshot();
      if (!mounted) return;
      final wanted = <String>{};
      for (final s in opportunities) {
        final symbol = (s['symbol'] ?? s['symbol_id'])?.toString().trim();
        if (symbol != null && symbol.isNotEmpty && symbol != 'ناموجود') {
          wanted.add(symbol);
        }
      }
      setState(() {
        _snapshot = snapshot;
        _live
          ..clear()
          ..addAll(snapshot.quotesFor(wanted));
        _liveAt = snapshot.fetchedAt;
      });
    } catch (_) {
      // دریافت فهرست بازار اختیاری است؛ خطا فقط دادهٔ قبلی را نگه می‌دارد.
    } finally {
      _liveBusy = false;
    }
  }
  /// نرخ‌های طلا و ارز تهران تا حدود ساعت ۲۲ به‌روز می‌شوند.
  bool get ratesOpen {
    final t = DateTime.now().toUtc().add(const Duration(hours: 3, minutes: 30));
    final minutes = t.hour * 60 + t.minute;
    return minutes >= 8 * 60 && minutes <= 22 * 60;
  }

  /// نرخ لحظه‌ای از TGJU؛ خطا هرگز به گزارش یا بقیهٔ صفحه‌ها سرایت نمی‌کند و
  /// آخرین مقدار معتبر روی صفحه می‌ماند.
  Future<void> syncMarkets() async {
    if (_marketsBusy) return;
    _marketsBusy = true;
    try {
      final quotes = await LiveMarketClient().fetch();
      if (!mounted) return;
      setState(() {
        _markets
          ..clear()
          ..addAll(quotes);
        if (quotes.isNotEmpty) _marketsAt = DateTime.now().toUtc();
      });
    } catch (_) {
      // بخش نرخ‌ها اختیاری است؛ نمایش گزارش بدون آن ادامه می‌یابد.
    } finally {
      _marketsBusy = false;
    }
  }

  Widget _marketTile(MarketQuote quote) {
    final value = quote.unit == 'تومان'
        ? money(quote.price / 10)
        : quote.price.toStringAsFixed(2);
    final pct = quote.changePercent;
    final color = pct == null
        ? const Color(0xffaebccc)
        : (pct >= 0 ? const Color(0xff4cc38a) : const Color(0xffe4676b));
    return Container(
      width: 172,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xff16202b),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xff24303d)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(quote.label,
              style:
                  const TextStyle(fontSize: 13, color: Color(0xffaebccc))),
          const SizedBox(height: 8),
          Text(value,
              style: const TextStyle(
                  fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Row(
            children: [
              Text(quote.unit,
                  style:
                      const TextStyle(fontSize: 12, color: Color(0xff7f8fa0))),
              const SizedBox(width: 8),
              Text(
                pct == null
                    ? '—'
                    : '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(2)}%',
                style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.bold, color: color),
              ),
              const SizedBox(width: 8),
              Text(quote.updatedAt ?? '—',
                  style:
                      const TextStyle(fontSize: 11, color: Color(0xff7f8fa0))),
            ],
          ),
        ],
      ),
    );
  }

  Widget _marketBoard() => card('نرخ لحظه‌ای طلا و دلار', [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: _markets.values.map(_marketTile).toList(),
        ),
        const SizedBox(height: 10),
        Text(
          'منبع: TGJU (tgju.org) — به‌روزرسانی'
          '${_marketsAt == null ? '' : ' ${_clock(_marketsAt!)}'}',
          style: const TextStyle(fontSize: 11, color: Color(0xff7f8fa0)),
        ),
      ]);

  List<data.Row> get opportunities => [
        ...(report?['signals'] as List? ?? []),
        ...((((report?['global'] as Map?)?['signals'] as List?) ?? [])),
      ].whereType<data.Row>().toList();
  String get today => DateTime.now()
      .toUtc()
      .add(const Duration(hours: 3, minutes: 30))
      .toIso8601String()
      .substring(0, 10);
  String show(dynamic value) => value == null || value.toString().isEmpty
      ? 'ناموجود'
      : value is List
      ? value.join('، ')
      : value.toString();
  Widget line(String label, dynamic value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Wrap(
      spacing: 12,
      children: [
        Text(label, style: const TextStyle(color: Color(0xffaebccc))),
        SelectableText(show(value)),
      ],
    ),
  );
  Widget card(String title, List<Widget> items) => Card(
    margin: const EdgeInsets.only(bottom: 14),
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: gold,
            ),
          ),
          const SizedBox(height: 9),
          ...items,
        ],
      ),
    ),
  );
  Widget input(TextEditingController c, String label, {bool secret = false}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextField(
          controller: c,
          obscureText: secret,
          autocorrect: false,
          decoration: InputDecoration(
            labelText: label,
            border: const OutlineInputBorder(),
          ),
        ),
      );
  Widget action(String text, VoidCallback onTap) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: FilledButton(onPressed: busy ? null : onTap, child: Text(text)),
  );
  Future<List<String>?> ask(String title, List<String> labels) async {
    final values = List.filled(labels.length, '');
    return showDialog<List<String>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (int i = 0; i < labels.length; i++)
                TextField(
                  decoration: InputDecoration(labelText: labels[i]),
                  onChanged: (v) => values[i] = v.trim(),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('انصراف'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, values),
            child: const Text('ثبت'),
          ),
        ],
      ),
    );
  }

  data.Row? get currentWatchList {
    for (final list in watchLists) {
      if (list['id'] == watchListId) return list;
    }
    return watchLists.isEmpty ? null : watchLists.first;
  }

  List<data.Row> get currentWatchItems =>
      ((currentWatchList?['items'] as List?) ?? const [])
          .whereType<data.Row>()
          .toList();

  String _newWatchId() =>
      '${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}'
      '${_random.nextInt(1 << 30).toRadixString(36)}';

  List<data.Row> _cleanWatchLists(dynamic raw) {
    final out = <data.Row>[];
    if (raw is! List) return out;
    for (final entry in raw) {
      if (entry is! Map) continue;
      final id = entry['id']?.toString().trim() ?? '';
      final name = entry['name']?.toString().trim() ?? '';
      if (id.isEmpty || name.isEmpty) continue;
      final items = <data.Row>[];
      final rawItems = entry['items'];
      if (rawItems is List) {
        for (final item in rawItems) {
          if (item is! Map) continue;
          final symbol = item['symbol']?.toString().trim() ?? '';
          if (symbol.isEmpty) continue;
          items.add({
            'insCode': item['insCode']?.toString() ?? '',
            'symbol': symbol,
            'name': item['name']?.toString() ?? '',
            'sector': item['sector']?.toString() ?? '',
            'board': item['board']?.toString() ?? '',
          });
        }
      }
      out.add({'id': id, 'name': name, 'items': items});
    }
    return out;
  }

  /// دیده‌بان‌های نام‌دار در app_settings حساب ذخیره می‌شوند (بدون تغییر
  /// ساختار پایگاه داده). دادهٔ قدیمی جدول watchlists یک‌بار به «دیده‌بان من»
  /// منتقل می‌شود تا از بین نرود.
  Future<void> _loadWatchLists(data.Row? options) async {
    final raw = settings['watchlists'];
    if (raw is List) {
      watchLists = _cleanWatchLists(raw);
    } else {
      final legacy = await rows(
          'watchlists?select=symbol_id,alert_price&order=created_at');
      watchLists = [
        {
          'id': _newWatchId(),
          'name': 'دیده‌بان من',
          'items': <data.Row>[
            for (final row in legacy)
              {
                'insCode': '',
                'symbol': row['symbol_id']?.toString() ?? '',
                'name': '',
                'sector': '',
                'board': '',
              },
          ],
        },
      ];
      if (legacy.isNotEmpty) await _writeWatchLists(options);
    }
    if (!watchLists.any((list) => list['id'] == watchListId)) {
      watchListId =
          watchLists.isEmpty ? null : watchLists.first['id']?.toString();
    }
    final list = currentWatchList;
    if (list != null) unawaited(_hydrateProfiles(list));
  }

  Future<void> _writeWatchLists([data.Row? known]) async {
    var current = known;
    current ??= (await rows('app_settings?select=settings')).firstOrNull;
    final payload = <String, dynamic>{
      ...?(current?['settings'] as Map?),
      'watchlists': watchLists,
    };
    final owner = Uri.encodeQueryComponent(store.owner ?? '');
    await store.request(
      current == null
          ? '/rest/v1/app_settings'
          : '/rest/v1/app_settings?owner_id=eq.$owner',
      method: current == null ? 'POST' : 'PATCH',
      body: {'settings': payload},
    );
    settings = payload;
  }

  Future<void> _newWatchList() async {
    final values = await ask('دیده‌بان جدید', ['نام دیده‌بان']);
    if (values == null || values.first.trim().isEmpty) return;
    final name = values.first.trim();
    if (watchLists.any((list) => list['name']?.toString().trim() == name)) {
      _say('دیده‌بانی با این نام وجود دارد.');
      return;
    }
    await run(() async {
      final id = _newWatchId();
      setState(() {
        watchLists.add({'id': id, 'name': name, 'items': <data.Row>[]});
        watchListId = id;
        watchQuery.clear();
      });
      await _writeWatchLists();
    });
  }

  Future<void> _renameWatchList() async {
    final list = currentWatchList;
    if (list == null) return;
    final values = await ask('تغییر نام دیده‌بان', ['نام جدید']);
    if (values == null || values.first.trim().isEmpty) return;
    final name = values.first.trim();
    if (watchLists.any(
        (other) => other != list && other['name']?.toString().trim() == name)) {
      _say('دیده‌بانی با این نام وجود دارد.');
      return;
    }
    await run(() async {
      setState(() => list['name'] = name);
      await _writeWatchLists();
    });
  }

  Future<void> _deleteWatchList() async {
    final list = currentWatchList;
    if (list == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف دیده‌بان'),
        content: Text(
            'دیده‌بان «${show(list['name'])}» و همهٔ نمادهایش حذف شود؟'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('انصراف'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('حذف'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await run(() async {
      setState(() {
        watchLists.remove(list);
        if (watchListId == list['id']) {
          watchListId = watchLists.isEmpty
              ? null
              : watchLists.first['id']?.toString();
        }
      });
      await _writeWatchLists();
    });
  }

  /// افزودن از نتایج جست‌وجو. شناسنامه یک‌بار و فقط برای همین نماد گرفته
  /// می‌شود تا گروه و بازارش همراه آیتم ذخیره شود.
  Future<void> _addToWatch(SymbolRow row) async {
    final list = currentWatchList;
    if (list == null) {
      _say('اول یک دیده‌بان بسازید.');
      return;
    }
    final items = currentWatchItems;
    final exists = items.any((item) {
      final code = item['insCode']?.toString() ?? '';
      return code.isNotEmpty
          ? code == row.insCode
          : item['symbol']?.toString() == row.symbol;
    });
    if (exists) {
      _say('«${row.symbol}» در این دیده‌بان هست.');
      return;
    }
    await run(() async {
      final profile = await _profile(row.insCode);
      items.add({
        'insCode': row.insCode,
        'symbol': row.symbol,
        'name': row.name,
        'sector': profile?.sector ?? '',
        'board': profile?.place ?? '',
      });
      list['items'] = items;
      await _writeWatchLists();
      _say('«${row.symbol}» به «${show(list['name'])}» اضافه شد.');
    });
  }

  Future<void> _removeWatch(data.Row item) async {
    final list = currentWatchList;
    if (list == null) return;
    await run(() async {
      list['items'] = currentWatchItems
          .where((other) =>
              !(other['insCode'] == item['insCode'] &&
                  other['symbol'] == item['symbol']))
          .toList();
      await _writeWatchLists();
    });
    if (mounted) setState(() {});
  }

  Future<SymbolProfile?> _profile(String insCode) async {
    if (insCode.isEmpty) return null;
    final known = _profiles[insCode];
    if (known != null) return known;
    if (_profileBusy.contains(insCode)) return null;
    _profileBusy.add(insCode);
    try {
      final profile = await SymbolInfoClient().fetch(insCode);
      _profiles[insCode] = profile;
      return profile;
    } catch (_) {
      return null;
    } finally {
      _profileBusy.remove(insCode);
      _profileTried.add(insCode);
    }
  }

  /// شناسنامهٔ نمادهای دیده‌بان فعال را حداکثر چهارتایی می‌گیرد تا هم گروه و
  /// بازار نمایش داده شود و هم سرور با درخواست پشت‌سرهم تحت فشار نباشد.
  Future<void> _hydrateProfiles(data.Row list) async {
    final items =
        ((list['items'] as List?) ?? const []).whereType<data.Row>().toList();
    var changed = false;
    for (final item in items) {
      if ((item['insCode']?.toString() ?? '').isEmpty) {
        final row = _rowFor(item);
        if (row != null) {
          item['insCode'] = row.insCode;
          changed = true;
        }
      }
    }
    final pending = items.where((item) {
      final code = item['insCode']?.toString() ?? '';
      return code.isNotEmpty &&
          !_profiles.containsKey(code) &&
          !_profileTried.contains(code);
    }).take(24).toList();
    if (pending.isEmpty) {
      if (changed) {
        try {
          await _writeWatchLists();
        } catch (_) {}
      }
      return;
    }
    for (var i = 0; i < pending.length; i += 4) {
      final batch = pending.skip(i).take(4);
      final results = await Future.wait(batch.map((item) async {
        final profile = await _profile(item['insCode']!.toString());
        return MapEntry(item, profile);
      }));
      for (final entry in results) {
        final profile = entry.value;
        if (profile == null) continue;
        entry.key['sector'] = profile.sector ?? '';
        entry.key['board'] = profile.place;
        final currentName = entry.key['name']?.toString() ?? '';
        if (currentName.isEmpty) entry.key['name'] = profile.label;
        changed = true;
      }
      if (mounted) setState(() {});
    }
    if (changed) {
      try {
        await _writeWatchLists();
      } catch (_) {}
    }
  }

  SymbolRow? _rowFor(data.Row item) {
    final snapshot = _snapshot;
    if (snapshot == null) return null;
    return snapshot.rowFor(
      item['insCode']?.toString(),
      item['symbol']?.toString(),
    );
  }

  data.Row? _signalFor(String symbol) {
    for (final signal in opportunities) {
      final name = (signal['symbol'] ?? signal['symbol_id'])?.toString().trim();
      if (name == symbol) return signal;
    }
    return null;
  }

  String _pct(double value) =>
      '${value >= 0 ? '+' : ''}${value.toStringAsFixed(2)}%';

  void _say(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Widget _symbolTile({
    required String symbol,
    required String name,
    SymbolRow? row,
    SymbolProfile? profile,
    String? category,
    Widget? trailing,
    VoidCallback? onTap,
  }) {
    final pct = row?.changePercent;
    final last = row?.last;
    final pctColor = pct == null
        ? const Color(0xffaebccc)
        : (pct >= 0 ? const Color(0xff4cc38a) : const Color(0xffe4676b));
    final label = (category ?? profile?.category ?? '').trim();
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xff16202b),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xff24303d)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        symbol,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 12, color: Color(0xffaebccc)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 10,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        last == null
                            ? 'قیمت: ناموجود'
                            : '${money(last)} ریال',
                        style: const TextStyle(fontSize: 13),
                      ),
                      if (pct != null)
                        Text(
                          _pct(pct),
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: pctColor,
                          ),
                        ),
                      if (row != null && !row.traded)
                        const Text(
                          'بدون معامله',
                          style: TextStyle(
                              fontSize: 11, color: Color(0xff7f8fa0)),
                        ),
                    ],
                  ),
                  if (label.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      label,
                      style: const TextStyle(
                          fontSize: 11, color: Color(0xff7f8fa0)),
                    ),
                  ],
                ],
              ),
            ),
            if (trailing != null) trailing,
          ],
        ),
      ),
    );
  }

  Future<void> _openSymbol(String insCode, String symbol, String name) async {
    final row = _snapshot?.rowFor(insCode, symbol);
    var profile = insCode.isEmpty ? null : _profiles[insCode];
    if (profile == null && insCode.isNotEmpty) {
      profile = await _profile(insCode);
    }
    if (!mounted) return;
    final signalRow = _signalFor(symbol);
    final list = currentWatchList;
    final saved = currentWatchItems.any((item) {
      final code = item['insCode']?.toString() ?? '';
      return code.isNotEmpty
          ? code == insCode
          : item['symbol']?.toString() == symbol;
    });
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(symbol),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _symbolTile(
                  symbol: symbol,
                  name: name,
                  row: row,
                  profile: profile,
                ),
                const Divider(),
                if (profile != null) ...[
                  line('گروه صنعت', profile.sector),
                  line('بازار / تابلو', profile.place),
                  if (profile.eps != null)
                    line('EPS اعلامی (ریال)', money(profile.eps!)),
                  if (profile.sectorPe != null)
                    line('P/E گروه', profile.sectorPe),
                  if (profile.psr != null) line('PSR', profile.psr),
                  if (profile.shares != null)
                    line('سهام منتشرشده', money(profile.shares!)),
                  if (profile.baseVolume != null)
                    line('حجم مبنا (سهم)', money(profile.baseVolume!)),
                  if (profile.averageVolume != null)
                    line('میانگین حجم ۳۰ روز', money(profile.averageVolume!)),
                  if (profile.weekLow != null || profile.weekHigh != null)
                    line(
                      'کمینه / بیشینه ۵۲ هفته',
                      '${profile.weekLow == null ? '—' : money(profile.weekLow!)}'
                          ' / '
                          '${profile.weekHigh == null ? '—' : money(profile.weekHigh!)}',
                    ),
                  if ((profile.nav ?? 0) > 0)
                    line('NAV (ریال)', money(profile.nav!)),
                  if ((profile.isin ?? '').isNotEmpty)
                    line('ISIN', profile.isin),
                  const SizedBox(height: 8),
                  Text(
                    profile.summary,
                    style: const TextStyle(
                        fontSize: 12, color: Color(0xffaebccc)),
                  ),
                ] else if (insCode.isNotEmpty) ...[
                  const Text(
                    'شناسنامهٔ این نماد دریافت نشد.',
                    style: TextStyle(color: Color(0xffe4676b)),
                  ),
                  TextButton(
                    onPressed: () {
                      Navigator.pop(ctx);
                      unawaited(_openSymbol(insCode, symbol, name));
                    },
                    child: const Text('تلاش دوباره'),
                  ),
                ] else
                  const Text(
                    'برای این نماد شناسهٔ رسمی ثبت نشده است؛ آن را دوباره از جست‌وجو اضافه کنید.',
                  ),
                if (signalRow != null) ...[
                  const Divider(),
                  const Text(
                    'تحلیل گزارش روزانه',
                    style: TextStyle(
                        color: gold, fontWeight: FontWeight.bold),
                  ),
                  line('محدوده ورود',
                      signalRow['entry_range'] ?? signalRow['entry']),
                  line('حد ضرر', signalRow['stop_loss'] ?? signalRow['stop']),
                  line('اهداف خروج', signalRow['targets']),
                ],
                const SizedBox(height: 10),
                const Text(
                  'منبع شناسنامه: TSETMC. این اطلاعات فقط توصیف نماد است و '
                  'توصیهٔ خرید یا فروش نیست.',
                  style:
                      TextStyle(fontSize: 11, color: Color(0xff7f8fa0)),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('بستن'),
          ),
          if (list != null && !saved)
            FilledButton(
              onPressed: () async {
                Navigator.pop(ctx);
                await _addToWatch(
                  row ?? SymbolRow(insCode: insCode, symbol: symbol, name: name),
                );
              },
              child: Text('افزودن به «${show(list['name'])}»'),
            ),
          if (list != null && saved)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Text(
                'در دیده‌بان هست',
                style: TextStyle(fontSize: 11, color: Color(0xff7f8fa0)),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> addTrade(bool buy) async {
    final v = await ask(buy ? 'ثبت خرید' : 'ثبت فروش', [
      'شناسه نماد',
      'تعداد',
      'قیمت واحد (ریال)',
      'کارمزد کل (ریال)',
    ]);
    if (v == null) return;
    await run(() async {
      final n = int.tryParse(v[1]),
          p = double.tryParse(v[2]),
          f = v[3].isEmpty ? 0.0 : double.tryParse(v[3]);
      if (v[0].isEmpty ||
          n == null ||
          n < 1 ||
          p == null ||
          !p.isFinite ||
          p <= 0 ||
          f == null ||
          !f.isFinite ||
          f < 0)
        throw const FormatException(
          'تعداد و قیمت باید مثبت و کارمزد نامنفی باشد.',
        );
      await store.request(
        '/rest/v1/portfolio_transactions',
        method: 'POST',
        body: {
          'portfolio_id': portfolio,
          'symbol_id': v[0],
          'side': buy ? 'buy' : 'sell',
          'quantity': n,
          'price': p,
          'fee': f,
        },
      );
      await reload();
    });
  }

  static const appVersion = '1.4.4';

  int _compareVersion(String a, String b) {
    final x = a.split('.').map((e) => int.tryParse(e) ?? 0).toList();
    final y = b.split('.').map((e) => int.tryParse(e) ?? 0).toList();
    for (var i = 0; i < 3; i++) {
      final left = i < x.length ? x[i] : 0;
      final right = i < y.length ? y[i] : 0;
      if (left != right) return left > right ? 1 : -1;
    }
    return 0;
  }

  Future<void> checkForUpdate() async {
    const manifest = 'https://raw.githubusercontent.com/'
        'mohammad69monfared-maker/iran-smart-invest/main/apps/flutter_app/version.json';
    final client = HttpClient();
    client.findProxy = (_) => 'DIRECT';
    try {
      final req = await client.getUrl(Uri.parse(manifest));
      final res = await req.close().timeout(const Duration(seconds: 20));
      final info = jsonDecode(await utf8.decoder.bind(res).join()) as Map<String, dynamic>;
      final latest = (info['version'] ?? '').toString();
      if (_compareVersion(latest, appVersion) <= 0) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('شما از آخرین نسخه استفاده میکنید.')));
        }
        return;
      }
      final link = (info['url'] ?? '').toString();
      final notes = (info['notes'] ?? '').toString();
      if (link.isEmpty || !link.startsWith('https://')) {
        throw const FormatException('آدرس نسخه جدید معتبر نیست.');
      }
      if (!mounted) return;
      final install = await showDialog<bool>(
        context: context,
        builder: (_) => Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            title: Text('نسخهٔ $latest در دسترس است'),
            content: Text(notes.isEmpty ? 'آیا صفحهٔ دانلود باز شود؟' : notes),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context, false),
                  child: const Text('بعداً')),
              TextButton(onPressed: () => Navigator.pop(context, true),
                  child: const Text('دانلود')),
            ],
          ),
        ),
      );
      if (install == true) {
        await launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication);
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('بررسی بروزرسانی ناموفق بود.')));
      }
    } finally {
      client.close(force: true);
    }
  }

  Widget loginHint() => card('ورود به حساب', [
    const Text('برای نمایش داده‌های شخصی وارد حساب خود شوید.'),
    action('تنظیم اتصال', () => setState(() => page = 6)),
  ]);
  Widget signal(data.Row s) {
    final id = show(s['symbol'] ?? s['symbol_id']);
    final symbol = (s['symbol'] ?? s['symbol_id'])?.toString().trim() ?? '';
    final quote = _live[symbol];
    return card(id, [
      line('آخرین قیمت (ریال)', s['price'] ?? s['last_price']),
      if (quote != null)
        line(
          'قیمت زنده (به‌روز ${_clock(quote.fetchedAt)})',
          '${money(quote.price)}'
              '${quote.changePercent == null ? '' : ' · ${_pct(quote.changePercent!)}'}',
        ),
      line(
        'محدوده ورود',
        s['entry_range'] ??
            s['entry'] ??
            [s['entry_low'], s['entry_high']].whereType<num>().join(' – '),
      ),
      line('حد ضرر', s['stop_loss'] ?? s['stop']),
      line(
        'اهداف خروج',
        s['targets'] ??
            [
              s['target1'] ?? s['target_1'],
              s['target2'] ?? s['target_2'],
            ].whereType<num>().toList(),
      ),
      line('نسبت سود به زیان', s['reward_risk'] ?? s['risk_reward']),
      line('دلایل', s['reasons']),
      line('شرایط ابطال', s['invalidation']),
      if (s['expires'] != null)
        line('اعتبار تا', faDate(s['expires'].toString())),
      line('منبع', s['sources'] ?? s['source']),
      if (s['market'] != null) line('بازار', s['market']),
      if (s['technical'] is Map)
        line('تکنیکال', (s['technical'] as Map)['note'] ?? ''),
      if (s['fundamental_note'] != null)
        line('بنیادی', s['fundamental_note']),
      if (s['backtest'] is Map)
        line('بک‌تست (شبیه‌سازی)',
             'بازده ${(((s['backtest'] as Map)['return_after_costs'] as num?) ?? 0) * 100}% · '
             'بیشترین افت ${(((s['backtest'] as Map)['maximum_drawdown'] as num?) ?? 0) * 100}% · '
             'نرخ پیروزی ${(((s['backtest'] as Map)['win_rate'] as num?) ?? 0) * 100}% · '
             'تعداد معاملات ${(s['backtest'] as Map)['number_of_trades'] ?? 0}'),
    ]);
  }
  List<Widget> content() {
    final stale = report != null && report!['date'] != today;
    switch (page) {
      case 0:
        return [
          if (_markets.isNotEmpty) _marketBoard(),
          card('آخرین گزارش', [
            if (report == null)
              Text(
                store.connected
                    ? 'برای این حساب گزارشی از سرور دریافت نشد. انتشار گزارش و دسترسی حساب به گزارش‌ها را بررسی کنید.'
                    : 'برای همگام‌سازی، در هر دو دستگاه با یک حساب و یک پروژه وارد شوید.',
              ),
            if (report != null) ...[
              Text(store.connected ? 'منبع گزارش: حساب ابری' : 'منبع گزارش: فایل محلی ویندوز'),
              if (stale)
                const Text('گزارش بایگانی‌شده', style: TextStyle(color: gold)),
              line('تاریخ داده', faDate(report!['date']?.toString())),
              line('زمان تولید', faDate(report!['generated_at']?.toString())),
              line('خلاصه', report!['summary']),
              line('نمادهای بررسی‌شده', report!['scanned']),
              line('نمادهای ردشده', report!['rejected']),
            ],
          ]),
          if (report != null)
            card('سلامت منابع', [
              for (final e in (report!['sources'] as Map? ?? {}).entries)
                line(e.key.toString(), e.value),
            ]),
          ...alerts.map(
            (a) => card('هشدار', [
              line('شرح', a['message']),
              line('زمان', faDate(a['created_at']?.toString())),
            ]),
          ),
          for (final a in report?['alerts'] as List? ?? [])
            card('هشدار گزارش', [Text(show(a))]),
        ];
      case 1:
        return [
          if (stale) card('گزارش تاریخی', [line('تاریخ', report!['date'])]),
          if (opportunities.isNotEmpty && _liveAt != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(
                'قیمت‌های زنده از تالار بورس — به‌روزرسانی ${_clock(_liveAt!)}',
                style: const TextStyle(
                    color: Color(0xffaebccc), fontSize: 12),
              ),
            ),
          if (opportunities.isEmpty)
            card('فرصت‌های گزارش', [
              Text(
                report == null
                    ? 'گزارشی دریافت نشده است.'
                    : show(report!['summary']),
              ),
            ]),
          ...opportunities.map(signal),
        ];
      case 2:
        final term = query.text.trim();
        final hits = term.isEmpty
            ? const <SymbolRow>[]
            : searchSymbols(_snapshot, term, limit: 20);
        final fallback = term.isEmpty
            ? const <data.Row>[]
            : opportunities
                .where(
                    (s) => show(s['symbol'] ?? s['symbol_id']).contains(term))
                .toList();
        return [
          Text(
            'نام یا بخشی از نام هر نماد بازار را جست‌وجو کنید؛ '
            '${_snapshot == null ? 'فهرست بازار در حال دریافت است' : '${money(_snapshot!.rows.length)} نماد در فهرست است'} و '
            'برای دیدن شناسنامه و قیمت زنده روی نتیجه بزنید.',
            style: const TextStyle(fontSize: 12, color: Color(0xffaebccc)),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: query,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              labelText: 'نام یا بخشی از نام نماد',
              prefixIcon: Icon(Icons.search),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          if (term.isEmpty)
            const Text('مثال: «فولاد»، «شپنا» یا «طلا».')
          else if (_snapshot == null) ...[
            const Text('فهرست نمادهای بازار هنوز دریافت نشده است.'),
            action('دریافت فهرست بازار', () => unawaited(syncLive())),
          ] else if (hits.isEmpty)
            const Text('نمادی با این نام پیدا نشد.')
          else ...[
            Text(
              '${money(hits.length)} نتیجه — برای شناسنامه و تحلیل روی نماد بزنید.',
              style: const TextStyle(fontSize: 12, color: Color(0xffaebccc)),
            ),
            const SizedBox(height: 8),
            ...hits.map(
              (row) => _symbolTile(
                symbol: row.symbol,
                name: row.name,
                row: row,
                profile: _profiles[row.insCode],
                trailing: _signalFor(row.symbol) == null
                    ? null
                    : const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 6),
                        child: Icon(Icons.insights, size: 18, color: gold),
                      ),
                onTap: () =>
                    _openSymbol(row.insCode, row.symbol, row.name),
              ),
            ),
          ],
          if (_snapshot == null && fallback.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...fallback.map(signal),
          ],
        ];
      case 3:
        return [
          if (!store.connected)
            loginHint()
          else ...[
            card('سبدها', [
              if (portfolios.isNotEmpty)
                DropdownButton<String>(
                  value: portfolio,
                  items: portfolios
                      .map(
                        (p) => DropdownMenuItem<String>(
                          value: p['id'],
                          child: Text(show(p['name'])),
                        ),
                      )
                      .toList(),
                  onChanged: busy
                      ? null
                      : (v) {
                          portfolio = v;
                          refresh();
                        },
                ),
              action('ایجاد سبد', () async {
                final v = await ask('ایجاد سبد', ['نام سبد']);
                if (v != null && v.first.isNotEmpty)
                  await run(() async {
                    await store.request(
                      '/rest/v1/portfolios',
                      method: 'POST',
                      body: {'name': v.first},
                    );
                    await reload();
                  });
              }),
            ]),
            if (portfolio != null)
              card('معاملات دستی', [
                Wrap(
                  spacing: 12,
                  children: [
                    action('ثبت خرید', () => addTrade(true)),
                    action('ثبت فروش', () => addTrade(false)),
                  ],
                ),
              ]),
            for (final p in positions)
              card(show(p['symbol_id']), [
                line('تعداد', p['quantity']),
                line('بهای تمام‌شده', p['cost_basis']),
                line('سود و زیان تحقق‌یافته', p['realized_pnl']),
              ]),
            if (trades.isNotEmpty)
              card('آخرین معاملات', [
                for (final t in trades)
                  line(
                    '${t['symbol_id']} · ${t['side'] == 'buy' ? 'خرید' : 'فروش'}',
                    '${t['quantity']} × ${t['price']}',
                  ),
              ]),
          ],
        ];
      case 4:
        if (!store.connected) return [loginHint()];
        final list = currentWatchList;
        final items = currentWatchItems;
        final term = watchQuery.text.trim();
        final hits = term.isEmpty
            ? const <SymbolRow>[]
            : searchSymbols(_snapshot, term, limit: 15);
        final activeId = watchLists.any((l) => l['id'] == watchListId)
            ? watchListId
            : (watchLists.isEmpty
                ? null
                : watchLists.first['id']?.toString());
        return [
          card('دیده‌بان‌ها', [
            if (watchLists.length > 1)
              DropdownButton<String>(
                isExpanded: true,
                value: activeId,
                items: [
                  for (final l in watchLists)
                    DropdownMenuItem<String>(
                      value: l['id']!.toString(),
                      child: Text(
                        '${show(l['name'])}'
                        ' (${((l['items'] as List?) ?? const []).length})',
                      ),
                    ),
                ],
                onChanged: busy
                    ? null
                    : (value) {
                        setState(() {
                          watchListId = value;
                          watchQuery.clear();
                        });
                        final active = currentWatchList;
                        if (active != null) {
                          unawaited(_hydrateProfiles(active));
                        }
                      },
              )
            else if (list != null)
              line('دیده‌بان فعال', list['name']),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              runSpacing: 4,
              children: [
                action('دیده‌بان جدید', _newWatchList),
                if (list != null)
                  TextButton(
                    onPressed: busy ? null : _renameWatchList,
                    child: const Text('تغییر نام'),
                  ),
                if (list != null)
                  TextButton(
                    onPressed: busy ? null : _deleteWatchList,
                    child: const Text('حذف دیده‌بان'),
                  ),
              ],
            ),
            const Text(
              'هر دیده‌بان یک فهرست با نام دلخواه است؛ می‌توانید چند دیده‌بان '
              'بسازید (مثلاً «طلا»، «سهام بزرگ» یا «کالا»).',
              style: TextStyle(fontSize: 11, color: Color(0xff7f8fa0)),
            ),
          ]),
          card('افزودن نماد', [
            TextField(
              controller: watchQuery,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                labelText: 'جست‌وجو با بخشی از نام نماد',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            if (term.isEmpty)
              const Text(
                'مثلاً «فول» یا «شپنا». همهٔ نمادهای بازار در فهرست است و '
                'نوشتن نام کامل لازم نیست.',
                style: TextStyle(fontSize: 12, color: Color(0xffaebccc)),
              )
            else if (_snapshot == null) ...[
              const Text('فهرست نمادها هنوز دریافت نشده است.'),
              action('دریافت فهرست بازار', () => unawaited(syncLive())),
            ] else if (hits.isEmpty)
              const Text('نمادی با این نام پیدا نشد.')
            else
              ...hits.map(
                (row) => _symbolTile(
                  symbol: row.symbol,
                  name: row.name,
                  row: row,
                  profile: _profiles[row.insCode],
                  onTap: () =>
                      _openSymbol(row.insCode, row.symbol, row.name),
                  trailing: IconButton(
                    tooltip: 'افزودن به دیده‌بان',
                    onPressed:
                        busy || list == null ? null : () => _addToWatch(row),
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                ),
              ),
          ]),
          if (list == null)
            card('دیده‌بان', [
              const Text('هنوز دیده‌بانی نساخته‌اید. دکمهٔ «دیده‌بان جدید» را بزنید.'),
            ])
          else
            card('نمادهای «${show(list['name'])}»', [
              if (items.isEmpty)
                const Text(
                  'هنوز نمادی اضافه نشده است. از کادر بالا جست‌وجو و اضافه کنید.',
                )
              else
                for (final item in items)
                  _symbolTile(
                    symbol: show(item['symbol']),
                    name: show(item['name']) == 'ناموجود'
                        ? ''
                        : show(item['name']),
                    row: _rowFor(item),
                    profile: _profiles[item['insCode']?.toString() ?? ''],
                    category: [item['sector'], item['board']]
                        .where((v) =>
                            v != null && v.toString().trim().isNotEmpty)
                        .join(' — '),
                    onTap: () => _openSymbol(
                      item['insCode']?.toString() ?? '',
                      item['symbol']?.toString() ?? '',
                      item['name']?.toString() ?? '',
                    ),
                    trailing: IconButton(
                      tooltip: 'حذف از دیده‌بان',
                      onPressed: busy ? null : () => _removeWatch(item),
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ),
            ]),
        ];
      case 5:
        return [
          card('این بخش چه فایده‌ای دارد؟', [
            const Text(
              '«عملکرد زنده» نتیجهٔ سیگنال‌های منتشرشدهٔ گذشته را با قیمت '
              'واقعی بازار می‌سنجد و «بک‌تست» یک شبیه‌سازی تاریخی است. '
              'هیچ‌کدام سود آینده را تضمین نمی‌کنند؛ هدف، سنجش صادقانهٔ '
              'کیفیت سیگنال‌هاست.',
              style: TextStyle(fontSize: 12, color: Color(0xffaebccc)),
            ),
          ]),
          for (final e in {
            'عملکرد زنده': 'performance',
            'بک‌تست': 'backtest',
          }.entries)
            card(e.key, [
              if (report?[e.value] is Map)
                for (final m in (report![e.value] as Map).entries)
                  line(m.key.toString(), m.value)
              else
                const Text('نتیجهٔ ثبت‌شده‌ای در گزارش موجود نیست.'),
            ]),
        ];
      case 7:
        final global = (report?['global'] as Map?) ?? {};
        final items = (global['summaries'] as List? ?? []).whereType<data.Row>().toList();
        return [
          card('بازارهای جهانی', [
            if (items.isEmpty)
              Text(report?['status'] == 'closed'
                  ? 'بازارهای جهانی در این نوبت واکشی نشد (خارج از بازه تحلیل روزانه).'
                  : 'داده معتبری از منابع عمومی دریافت نشد.'),
            ...items.map((item) {
              final tech = (item['technical'] as Map?) ?? {};
              return card(
                '${show(item['symbol'])} — ${show(item['group'])}',
                [
                  line('تاریخ داده', faDate(item['date']?.toString())),
                  line('آخرین قیمت', item['last_price']),
                  line('واحد', item['currency']),
                  line('RSI14', tech['rsi14']),
                  line('ADX14', tech['adx14']),
                  line('توضیح تکنیکال', tech['note']),
                  line('نتیجه', item['signal'] == true
                      ? 'سیگنال دارد'
                      : (item['reason'] ?? 'بدون سیگنال')),
                  line('منبع', item['source']),
                ],
              );
            }),
          ]),
        ];
      default:
        return [
          card('بروزرسانی برنامه', [
            action('بررسی نسخهٔ جدید', checkForUpdate),
          ]),
          if (!store.connected)
            card('اتصال به حساب', [
              input(endpoint, 'نشانی پروژه Supabase'),
              input(keyField, 'کلید عمومی پروژه'),
              input(email, 'ایمیل'),
              input(password, 'رمز عبور', secret: true),
              action(
                'ورود',
                () => run(() async {
                  store.endpoint = endpoint.text;
                  store.key = keyField.text;
                  await store.login(email.text, password.text);
                  password.clear();
                  await reload();
                }),
              ),
            ])
          else ...[
            card('تنظیمات ریسک', [
              line('ریسک هر معامله (درصد)', settings['risk_percent']),
              action('ویرایش ریسک', () async {
                final v = await ask('ریسک هر معامله', ['درصد سرمایه']);
                if (v == null) return;
                await run(() async {
                  final risk = double.tryParse(v.first);
                  if (risk == null || !risk.isFinite || risk <= 0 || risk > 100)
                    throw const FormatException('درصد باید بین صفر و صد باشد.');
                  final current = await rows('app_settings?select=settings');
                  final opts = {
                    ...?(current.firstOrNull?['settings'] as Map?),
                    'risk_percent': risk,
                  };
                  await store.request(
                    '/rest/v1/app_settings${current.isEmpty ? '' : '?owner_id=eq.${store.owner}'}',
                    method: current.isEmpty ? 'POST' : 'PATCH',
                    body: {'settings': opts},
                  );
                  await reload();
                });
              }),
            ]),
            action(
              'خروج از حساب',
              () => run(() async {
                await store.logout();
                portfolio = null;
                positions = [];
                portfolios = [];
                watchLists = [];
                watchListId = null;
                watchQuery.clear();
                _profiles.clear();
                _profileTried.clear();
                trades = [];
                alerts = [];
                settings = {};
                report = null;
                await reload();
              }),
            ),
          ],
        ];
      }
    }

    /// دکمه برگشت: اگر در صفحهٔ داشبورد نیستیم، به داشبورد برمیگردد.
    /// اگر در داشبورد هستیم و دو بار پیاپی در مدت کوتاه بزنیم، برنامه خارج میشود.
    Future<bool> _onWillPop() async {
      final now = DateTime.now();
      if (page != 0) {
        if (mounted) setState(() => page = 0);
        return false;
      }
      if (_lastBackPressed == null ||
          now.difference(_lastBackPressed!) >
              const Duration(seconds: 2)) {
        _lastBackPressed = now;
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('برای خروج از برنامه دکمه برگشت را دوباره بزنید.'),
              duration: Duration(seconds: 2),
            ),
          );
        }
        return false;
      }
      return true;
    }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 820;
    final menu = ListView(
      children: [
        const Padding(
          padding: EdgeInsets.all(20),
          child: Text(
            'بورس هوشمند ایران',
            style: TextStyle(
              color: gold,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        for (var i = 0; i < panels.length; i++)
          ListTile(
            selected: i == page,
            leading: Icon(icons[i]),
            title: Text(panels[i]),
            onTap: () {
              if (!wide) Navigator.of(context).pop();
              setState(() => page = i);
            },
          ),
      ],
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(panels[page]),
        actions: [
          IconButton(
            tooltip: 'به‌روزرسانی',
            onPressed: busy ? null : refresh,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      drawer: wide ? null : Drawer(child: menu),
      body: WillPopScope(
        onWillPop: _onWillPop,
        child: Row(
          children: [
            if (wide) SizedBox(width: 220, child: menu),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  if (busy) const LinearProgressIndicator(),
                  if (error != null) card('خطا', [SelectableText(error!)]),
                  ...content(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
