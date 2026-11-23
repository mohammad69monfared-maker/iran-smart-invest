/// Solar Hijri (Shamsi) dates for display. ISO strings remain in stored data.
int _daysFromCivil(int year, int month, int day) {
  if (month <= 2) year -= 1;
  final era = (year >= 0 ? year : year - 399) ~/ 400;
  final yoe = year - era * 400;
  final doy = (153 * (month > 2 ? month - 3 : month + 9) + 2) ~/ 5 + day - 1;
  final doe = yoe * 365 + yoe ~/ 4 - yoe ~/ 100 + doy;
  return era * 146097 + doe - 719468;
}

const _monthDays = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
const _faDigits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

bool _leap(int year) =>
    ((((year - 474) % 2820) + 474 + 38) * 682) % 2816 < 682;

String _persian(String text) => text.split('').map((ch) {
      final index = int.tryParse(ch);
      return index == null ? ch : _faDigits[index];
    }).join();

String toJalali(String iso) {
  final parsed = DateTime.tryParse(iso.trim());
  if (parsed == null) return iso;
  var days = _daysFromCivil(parsed.year, parsed.month, parsed.day) -
      _daysFromCivil(622, 3, 22);
  var year = 1;
  while (true) {
    final length = _leap(year) ? 366 : 365;
    if (days < length) break;
    days -= length;
    year += 1;
  }
  var month = 1;
  for (final length in _monthDays) {
    if (days < length) break;
    days -= length;
    month += 1;
  }
  return _persist(year, month, days + 1);
}

String _persist(int year, int month, int day) => _persian(
      '${year.toString().padLeft(4, '0')}/${month.toString().padLeft(2, '0')}/${day.toString().padLeft(2, '0')}',
    );

/// Persian date followed by the original ISO date for machine verification.
String faDate(String? iso) {
  if (iso == null || iso.isEmpty) return '—';
  return '${toJalali(iso)} ($iso)';
}
