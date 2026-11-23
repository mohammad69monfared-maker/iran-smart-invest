// Telegram webhook: instant replies, independent of the local network and
// GitHub Actions scheduling. Telegram sends no JWT, so verify JWT is disabled.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

const KEYBOARD = {
  keyboard: [
    ['گزارش امروز', 'فرصت\u200cها'],
    ['هشدارها', 'سبد من'],
    ['دیده\u200cبان', 'وضعیت', 'راهنما'],
  ],
  resize_keyboard: true,
  one_time_keyboard: false,
};

const LABELS: Record<string, string> = {
  'گزارش امروز': '/report',
  'فرصت\u200cها': '/signals',
  'هشدارها': '/alerts',
  'سبد من': '/portfolio',
  'دیده\u200cبان': '/watch',
  'وضعیت': '/status',
  'راهنما': '/help',
};

function formatSignals(signals: any[]): string {
  if (!signals?.length) return 'فرصت مناسبی شناسایی نشد.';
  return signals.slice(0, 5).map((s) => {
    const tech = s.technical?.note ? `\nتکنیکال: ${s.technical.note}` : '';
    const fund = s.fundamental_note ? `\nبنیادی: ${s.fundamental_note}` : '';
    return [
      `نماد: ${s.symbol ?? '—'} ${s.market ? `(${s.market})` : ''}`,
      `قیمت: ${s.last_price ?? '—'}`,
      `ورود: ${s.entry_low ?? '—'} – ${s.entry_high ?? '—'}`,
      `حد ضرر: ${s.stop_loss ?? '—'} · هدف ۱: ${s.target1 ?? '—'} · هدف ۲: ${s.target2 ?? '—'}`,
      `امتیاز: ${s.score ?? '—'} · اعتبار تا ${s.expires ?? '—'}`,
      `دلیل: ${(s.reasons ?? []).join('، ') || '—'}`,
      `ابطال: ${s.invalidation ?? '—'}`,
    ].join('\n') + tech + fund;
  }).join('\n\n');
}

function render(command: string, report: any): string {
  if (command === '/start' || command === '/help') {
    return 'دستورها:\n/report گزارش امروز\n/signals فرصت\u200cها\n/alerts هشدارها\n/portfolio سبد من\n/watch دیده\u200cبان\n/status وضعیت\n/help راهنما\n\nاز دکمه\u200cهای زیر هم می\u200cتوانید استفاده کنید.';
  }
  if (command === '/status') {
    return `جلسه: ${report?.date ?? '—'}\nانتشار: ${String(report?.generated_at ?? '').slice(0, 10)}\nوضعیت: ${report?.status ?? '—'}\n${report?.summary ?? ''}`;
  }
  if (command === '/signals') {
    const all = [...(report?.signals ?? []), ...((report?.global as any)?.signals ?? [])];
    return formatSignals(all);
  }
  if (command === '/alerts') {
    const items = report?.alerts ?? [];
    return items.length ? items.map((a: any) => `• ${a}`).join('\n') : 'هشداری در گزارش ثبت نشده است.';
  }
  if (command === '/portfolio') {
    return report?.portfolio ? JSON.stringify(report.portfolio).slice(0, 1200) : 'اطلاعات سبد موجود نیست.';
  }
  if (command === '/watch' || command === '/unwatch') {
    return 'برای مدیریت دیده\u200cبان از نرم\u200cافزار استفاده کنید: /watch نماد';
  }
  return `گزارش بورس ${report?.date ?? '—'}\n${report?.summary ?? ''}\n\n${render('/signals', report)}`;
}

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') return new Response('ok', { status: 200 });
  try {
    const update = await req.json();
    const msg = update.message;
    if (!msg?.text) return new Response('ok', { status: 200 });
    const chat = String(msg.chat?.id ?? '');
    if (chat !== Deno.env.get('TELEGRAM_CHAT_ID')) return new Response('ok', { status: 200 });

    const token = Deno.env.get('TELEGRAM_BOT_TOKEN')!;
    const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
    const { data } = await admin.from('daily_reports')
      .select('report').order('report_date', { ascending: false }).limit(1);
    const report = data?.[0]?.report ?? {};
    const text = (msg.text as string).startsWith('/')
      ? msg.text.split(' ')[0].split('@')[0].toLowerCase()
      : (LABELS[msg.text.trim()] ?? '/help');
    const body = JSON.stringify({
      chat_id: chat,
      text: render(text, report).slice(0, 3900),
      reply_markup: KEYBOARD,
    });
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
    });
  } catch (_error) {
    // Never leak internals to Telegram.
  }
  return new Response('ok', { status: 200 });
});
