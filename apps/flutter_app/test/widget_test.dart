import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iran_smart_invest/main.dart';
import 'package:iran_smart_invest/report_store.dart';

void main() {
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

  test('store starts disconnected and forgets the session on logout', () {
    final store = MarketStore();
    expect(store.connected, isFalse);
    store.logout();
    expect(store.connected, isFalse);
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
