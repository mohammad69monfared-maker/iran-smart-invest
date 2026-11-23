import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iran_smart_invest/jalali.dart';
import 'package:iran_smart_invest/main.dart';
import 'package:iran_smart_invest/report_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  test('store rejects a non-HTTPS endpoint', () async {
    final store = MarketStore()..endpoint = 'http://example.com';
    await expectLater(
      store.request('/rest/v1/daily_reports'),
      throwsA(isA<FormatException>()),
    );
  });

  test('store refuses endpoints that embed credentials', () async {
    final store = MarketStore()..endpoint = 'https://user:pass@example.com';
    await expectLater(
      store.request('/rest/v1/daily_reports'),
      throwsA(isA<FormatException>()),
    );
  });

  test('store starts disconnected and forgets the session on logout', () async {
    final store = MarketStore();
    expect(store.connected, isFalse);
    await store.logout();
    expect(store.connected, isFalse);
  });

  test('restores owner and endpoint and removes persisted session on logout', () async {
    FlutterSecureStorage.setMockInitialValues({MarketStore.sessionKey:
        '{"endpoint":"https://example.com","key":"test","email":"test@example.com","access":"test","refresh":"test","owner":"owner"}'});
    final store = MarketStore();
    await store.restore();
    expect(store.owner, 'owner');
    expect(store.emailAddress, 'test@example.com');
    expect(store.endpoint, 'https://example.com');
    await store.logout();
    final next = MarketStore();
    await next.restore();
    expect(next.connected, isFalse);
  });

  test('solar hijri conversion is correct', () {
    expect(toJalali('2026-11-23'), '۱۴۰۵/۰۹/۰۲');
    expect(toJalali('2026-03-21'), '۱۴۰۵/۰۱/۰۱');
    expect(toJalali('not-a-date'), 'not-a-date');
  });

  testWidgets('app renders right-to-left with the dark shell', (tester) async {
    await tester.pumpWidget(const InvestApp());
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Directionality &&
            widget.textDirection == TextDirection.rtl,
      ),
      findsWidgets,
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
