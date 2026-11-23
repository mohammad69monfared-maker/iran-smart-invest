import 'dart:io';

import 'package:flutter/material.dart';

import 'report_store.dart' as data;

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
];
const icons = [
  Icons.dashboard_outlined,
  Icons.radar,
  Icons.show_chart,
  Icons.account_balance_wallet_outlined,
  Icons.visibility_outlined,
  Icons.insights,
  Icons.settings_outlined,
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
      query = TextEditingController();
  int page = 0;
  bool busy = false;
  String? error;
  data.Row? report;
  List<data.Row> portfolios = [],
      positions = [],
      trades = [],
      watches = [],
      alerts = [];
  data.Row settings = {};
  String? portfolio;
  @override
  void initState() {
    super.initState();
    endpoint.text = store.endpoint;
    keyField.text = store.key;
    refresh();
  }

  @override
  void dispose() {
    for (final t in [endpoint, keyField, email, password, query]) {
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
    watches = await rows('watchlists?select=*&order=created_at');
    alerts = await rows('alerts?select=*&order=created_at.desc&limit=30');
    final options = await rows('app_settings?select=settings');
    settings = options.isEmpty
        ? {}
        : Map<String, dynamic>.from(options.first['settings']);
  }

  Future<void> refresh() => run(reload);
  List<data.Row> get opportunities =>
      (report?['signals'] as List? ?? []).whereType<data.Row>().toList();
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

  Future<void> addWatch() async {
    final v = await ask('افزودن به دیده‌بان', [
      'شناسه نماد',
      'قیمت هشدار (اختیاری، ریال)',
    ]);
    if (v == null) return;
    await run(() async {
      final price = v[1].isEmpty ? null : double.tryParse(v[1]);
      if (v.first.isEmpty ||
          (v[1].isNotEmpty && (price == null || !price.isFinite || price <= 0)))
        throw const FormatException('نماد و قیمت را بررسی کنید.');
      await store.request(
        '/rest/v1/watchlists',
        method: 'POST',
        body: {'symbol_id': v[0], 'alert_price': price},
      );
      await reload();
    });
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

  Widget loginHint() => card('ورود به حساب', [
    const Text('برای نمایش داده‌های شخصی وارد حساب خود شوید.'),
    action('تنظیم اتصال', () => setState(() => page = 6)),
  ]);
  Widget signal(data.Row s) => card(show(s['symbol'] ?? s['symbol_id']), [
    line('آخرین قیمت (ریال)', s['price'] ?? s['last_price']),
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
    line('منبع', s['sources'] ?? s['source']),
  ]);
  List<Widget> content() {
    final stale = report != null && report!['date'] != today;
    switch (page) {
      case 0:
        return [
          card('آخرین گزارش', [
            if (report == null)
              Text(
                Platform.isWindows
                    ? 'هنوز گزارشی در دسترس نیست. با اجرای موتور تحلیل یا اتصال حساب، گزارش اینجا نمایش داده می‌شود.'
                    : 'برای دریافت گزارش، وارد حساب شوید.',
              ),
            if (report != null) ...[
              if (stale)
                const Text('گزارش بایگانی‌شده', style: TextStyle(color: gold)),
              line('تاریخ داده', report!['date']),
              line('زمان تولید', report!['generated_at']),
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
              line('زمان', a['created_at']),
            ]),
          ),
          for (final a in report?['alerts'] as List? ?? [])
            card('هشدار گزارش', [Text(show(a))]),
        ];
      case 1:
        return [
          if (stale) card('گزارش تاریخی', [line('تاریخ', report!['date'])]),
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
        return [
          TextField(
            controller: query,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              labelText: 'جست‌وجوی نماد در آخرین گزارش',
              prefixIcon: Icon(Icons.search),
            ),
          ),
          const SizedBox(height: 16),
          ...opportunities
              .where((s) => show(s['symbol'] ?? s['symbol_id']).contains(term))
              .map(signal),
          if (!opportunities.any(
            (s) => show(s['symbol'] ?? s['symbol_id']).contains(term),
          ))
            const Text('تحلیلی برای این نماد در گزارش موجود نیست.'),
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
        return [
          if (!store.connected)
            loginHint()
          else ...[
            action('افزودن نماد', addWatch),
            for (final w in watches)
              card(show(w['symbol_id']), [
                line('قیمت هشدار', w['alert_price']),
                TextButton(
                  onPressed: busy
                      ? null
                      : () async {
                          await run(() async {
                            await store.request(
                              '/rest/v1/watchlists?id=eq.${Uri.encodeQueryComponent(w['id'])}',
                              method: 'DELETE',
                            );
                            await reload();
                          });
                        },
                  child: const Text('حذف از دیده‌بان'),
                ),
              ]),
          ],
        ];
      case 5:
        return [
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
      default:
        return [
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
                store.logout();
                portfolio = null;
                positions = [];
                portfolios = [];
                watches = [];
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
      body: Row(
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
    );
  }
}
