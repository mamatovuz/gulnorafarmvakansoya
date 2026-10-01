"""Direktor va Moliya bo'limi uchun Excel hisobotlari (1/2/3 oylik).

Har bir hisobot bir xil dizaynda:
  1-varaq — sarlavha banneri, davr, tepada statistika kartochkalari va to'liq jadval;
  2-varaq «Statistika» — kesimlar (oylar / filiallar / lavozimlar ...) va diagrammalar.

`build_*` — tayyor ma'lumotdan .xlsx yasaydi (sof funksiyalar, test qilish oson);
`make_report(kind, months)` — bazadan ma'lumot yig'ib, tayyor fayl qaytaradi.
"""
from collections import defaultdict
from io import BytesIO

from aiogram.types import BufferedInputFile
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from database.db import (
    ACCEPT_KIND_LABELS, EMP_STATUS_LABELS, STATUS_LABELS, ST_ACCEPTED,
)

# ================= DIZAYN =================
GREEN_DARK, GREEN, GREEN_LIGHT = "1B5E20", "2E7D32", "E8F5E9"
RED, RED_LIGHT = "C62828", "FFEBEE"
BLUE, ORANGE, PURPLE, TEAL = "1565C0", "E65100", "6A1B9A", "00838F"
GREY, GREY_LIGHT, MUTED = "757575", "F5F5F5", "9E9E9E"
INK = "263238"  # oddiy (jarima bo'lmagan) summalar rangi

MONEY_FMT = '#,##0" so\'m"'
_THIN = Side(style="thin", color="D0D0D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_RIGHT = Alignment(horizontal="right", vertical="center")

UZ_MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]

ROLE_TITLES = {
    "pharmacist": "Farmatsevt", "manager": "Filial rahbari",
    "director": "Direktor", "accountant": "Moliya bo'limi",
    "employee": "Oddiy xodim", "hr": "HR", "it": "IT xodim",
    "tech": "Texnik xodim", "admin": "Admin", "candidate": "Nomzod",
}


def _fill(color):
    return PatternFill("solid", fgColor=color)


def period_label(period):
    """'2026-09' -> 'Sentabr 2026'."""
    try:
        y, m = str(period).split("-")[:2]
        return f"{UZ_MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return str(period or "-")


def periods_text(periods):
    if len(periods) == 1:
        return period_label(periods[0])
    return f"{period_label(periods[0])} — {period_label(periods[-1])}"


class DateRange:
    """Hisobot davri: [start, end] (ikkalasi ham kiradi), datetime.date."""

    def __init__(self, start, end, months=None):
        if end < start:
            start, end = end, start
        self.start, self.end, self.months = start, end, months

    @property
    def since(self):
        return self.start.strftime("%Y-%m-%d")

    @property
    def until(self):
        """Yuqori chegara (kirmaydi): end + 1 kun."""
        from datetime import timedelta
        return (self.end + timedelta(days=1)).strftime("%Y-%m-%d")

    @property
    def periods(self):
        """Davr qamragan oylar: ['2026-09', '2026-10']."""
        out, y, m = [], self.start.year, self.start.month
        while (y, m) <= (self.end.year, self.end.month):
            out.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def text(self):
        dates = f"{self.start:%d.%m.%Y} — {self.end:%d.%m.%Y}"
        if self.months:
            return f"{periods_text(self.periods)} ({self.months} oylik: {dates})"
        return f"{dates} ({self.days} kun)"

    @property
    def tag(self):
        if self.months:
            return f"{self.months}oylik"
        return f"{self.start:%Y%m%d}-{self.end:%Y%m%d}"


def month_range(n, now=None):
    """Joriy oy bilan oxirgi n oy: eng eski oyning 1-sanasidan bugungacha."""
    from datetime import date
    if now is None:
        from utils import now_tk
        now = now_tk()
    first = last_periods(n, now)[0]
    return DateRange(date(int(first[:4]), int(first[5:7]), 1), now.date(), months=n)


def parse_date(text):
    """'15.09.2026' / '15.09.26' / '15/09/2026' / '2026-09-15' -> date (yoki None)."""
    from datetime import datetime
    t = (text or "").strip().replace("/", ".").replace("-", ".").replace(",", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y.%m.%d"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def last_periods(n, now=None):
    """Joriy oy bilan birga oxirgi n oy, eskidan yangiga: ['2026-08', '2026-09', ...]."""
    if now is None:
        from utils import now_tk
        now = now_tk()
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def money(value):
    """«200 000 so'm» / 200000 / None -> int."""
    d = "".join(c for c in str(value or "") if c.isdigit())
    return int(d) if d else 0


def som(n):
    return f"{int(n):,}".replace(",", " ") + " so'm"


def plain(text):
    """Boshidagi emoji/belgilarni olib tashlaydi: '✅ Qabul' -> 'Qabul'."""
    s = str(text or "").strip()
    i = 0
    while i < len(s) and not s[i].isalnum():
        i += 1
    return s[i:] or s


def fmt_date(value, with_time=True):
    """'2026-09-14 10:22:05' -> '14.09.2026 10:22'."""
    s = str(value or "")
    if len(s) >= 10 and s[4] == "-":
        out = f"{s[8:10]}.{s[5:7]}.{s[0:4]}"
        if with_time and len(s) >= 16:
            out += f" {s[11:16]}"
        return out
    return s or "-"


def position_of(row, pos_key="position", role_key="emp_role"):
    pos = row.get(pos_key)
    if pos:
        return pos
    role = row.get(role_key)
    return ROLE_TITLES.get(role or "", role) or "-"


def _month_of(value):
    return str(value or "")[:7]


def pct(part, whole):
    return (part / whole) if whole else 0


# ---------------- Varaq bo'laklari ----------------
def _banner(ws, ncols, text, size=18, height=40):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=text)
    c.fill = _fill(GREEN_DARK)
    c.font = Font(bold=True, color="FFFFFF", size=size)
    c.alignment = _CENTER
    ws.row_dimensions[1].height = height


def _subtitle(ws, ncols, text, row=2):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(bold=True, color=GREEN_DARK, size=11)
    c.fill = _fill(GREEN_LIGHT)
    c.alignment = _CENTER
    ws.row_dimensions[row].height = 22


def _header(ws, row, headers, merges=()):
    for i, h in enumerate(headers, start=1):
        if h is None:
            continue
        c = ws.cell(row=row, column=i, value=h)
        c.fill = _fill(GREEN)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.alignment = _CENTER
        c.border = _BORDER
    for c1, c2 in merges:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    ws.row_dimensions[row].height = 26


def _section_title(ws, row, ncols, text):
    line = Border(bottom=Side(style="medium", color=GREEN))
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(bold=True, color=GREEN_DARK, size=13)
    c.alignment = Alignment(horizontal="left", vertical="center")
    for col in range(1, ncols + 1):
        ws.cell(row=row, column=col).border = line
    ws.row_dimensions[row].height = 24


def _card_spans(ncols, n=4):
    """ncols ustunni n ta kartochkaga taqsimlaydi: [(c1, c2), ...]."""
    base, extra = divmod(ncols, n)
    spans, start = [], 1
    for i in range(n):
        width = base + (1 if i < extra else 0)
        spans.append((start, start + width - 1))
        start += width
    return spans


def _cards(ws, top_row, ncols, cards):
    """Statistika kartochkalari qatori. cards: [(label, value, color, fmt|None), ...]."""
    spans = _card_spans(ncols, len(cards))
    for (c1, c2), card in zip(spans, cards):
        label, value, color = card[0], card[1], card[2]
        fmt = card[3] if len(card) > 3 else None
        big = isinstance(value, (int, float)) or len(str(value)) <= 14
        ws.merge_cells(start_row=top_row, start_column=c1, end_row=top_row, end_column=c2)
        ws.merge_cells(start_row=top_row + 1, start_column=c1,
                       end_row=top_row + 1, end_column=c2)
        lc = ws.cell(row=top_row, column=c1, value=label.upper())
        lc.font = Font(bold=True, color=GREY, size=10)
        lc.alignment = _CENTER
        vc = ws.cell(row=top_row + 1, column=c1, value=value)
        vc.font = Font(bold=True, color=color, size=18 if big else 12)
        vc.alignment = _CENTER
        if fmt:
            vc.number_format = fmt
        accent = Side(style="thick", color=color)
        for col in range(c1, c2 + 1):
            for rr in (top_row, top_row + 1):
                cell = ws.cell(row=rr, column=col)
                cell.fill = _fill(GREY_LIGHT)
                cell.border = Border(
                    left=accent if col == c1 else None,
                    right=_THIN if col == c2 else None,
                    top=_THIN if rr == top_row else None,
                    bottom=_THIN if rr == top_row + 1 else None,
                )
    ws.row_dimensions[top_row].height = 20
    ws.row_dimensions[top_row + 1].height = 32


def _data_rows(ws, start_row, rows, money_cols=(), center_cols=(1,), pct_cols=(),
               muted=None, badge_col=None, badges=None, merges=(), money_color=RED,
               strike=False):
    """Zebra uslubidagi qatorlar. Oxirgi yozilgan qator raqamini qaytaradi."""
    r = start_row - 1
    for k, vals in enumerate(rows, start=1):
        r = start_row + k - 1
        is_muted = bool(muted and muted[k - 1])
        for col_i, val in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=col_i, value=val)
            cell.border = _BORDER
            cell.alignment = _CENTER if col_i in center_cols else _LEFT
            if k % 2 == 0:
                cell.fill = _fill(GREEN_LIGHT)
            if col_i in money_cols:
                cell.number_format = MONEY_FMT
                cell.alignment = _RIGHT
                cell.font = (Font(color=MUTED, italic=True, strike=strike) if is_muted
                             else Font(bold=True, color=(money_color.get(col_i, RED)
                                                         if isinstance(money_color, dict)
                                                         else money_color)))
            elif col_i in pct_cols:
                cell.number_format = "0.0%"
                cell.alignment = _CENTER
            elif is_muted:
                cell.font = Font(color=MUTED, italic=True)
        if badge_col and badges:
            cell = ws.cell(row=r, column=badge_col)
            fill_c, font_c = badges.get(cell.value, (None, None))
            if fill_c:
                cell.fill = _fill(fill_c)
                cell.font = Font(bold=True, color=font_c)
                cell.alignment = _CENTER
        for c1, c2 in merges:
            ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        ws.row_dimensions[r].height = 20
    return r


def _total_line(ws, row, values, money_cols=(), pct_cols=(), label_span=None):
    for col_i, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col_i, value=val)
        cell.fill = _fill(GREEN_DARK)
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.border = _BORDER
        cell.alignment = _RIGHT if col_i in money_cols else _CENTER
        if col_i in money_cols:
            cell.number_format = MONEY_FMT
        elif col_i in pct_cols:
            cell.number_format = "0%"
    if label_span and label_span > 1:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=label_span)
        ws.cell(row=row, column=1).alignment = Alignment(
            horizontal="right", vertical="center")
    ws.row_dimensions[row].height = 24


def _bar_chart(ws, anchor, title, cat_col, val_col, header_row, first, last, color=RED,
               num_fmt="#,##0", horizontal=False):
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    chart.title = title
    chart.legend = None
    chart.y_axis.numFmt = num_fmt
    chart.y_axis.majorGridlines = None
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.add_data(Reference(ws, min_col=val_col, min_row=header_row, max_row=last),
                   titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=cat_col, min_row=first, max_row=last))
    s = chart.series[0]
    s.graphicalProperties.solidFill = color
    s.graphicalProperties.line.solidFill = color
    s.dLbls = DataLabelList()
    s.dLbls.showVal = True
    s.dLbls.showSerName = False
    s.dLbls.showCatName = False
    s.dLbls.showLegendKey = False
    s.dLbls.numFmt = num_fmt
    chart.height = 7.5
    chart.width = 16
    ws.add_chart(chart, anchor)


def _print_setup(ws, landscape=True, title_row=None):
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if title_row:
        ws.print_title_rows = f"{title_row}:{title_row}"


def _finish(wb, prefix):
    from utils import now_tk
    buf = BytesIO()
    wb.save(buf)
    stamp = now_tk().strftime("%Y%m%d_%H%M")
    return BufferedInputFile(buf.getvalue(), filename=f"{prefix}_{stamp}.xlsx")


def _generated_at():
    from utils import now_tk
    return now_tk().strftime("%d.%m.%Y %H:%M")


# ---------------- Umumiy hisobot karkasi ----------------
def build_report(*, title, file_prefix, subtitle, card_rows, sheet_name, headers,
                 widths, rows, money_cols=(), center_cols=(1,), pct_cols=(),
                 muted=None, badge_col=None, badges=None, total=None,
                 empty_text="Bu davrda ma'lumot yo'q", main_chart=None,
                 stats_title=None, sections=(), stats_widths=None,
                 money_color=RED, strike=False):
    """Barcha hisobotlar uchun yagona dizayn.

    card_rows — [[(label, value, color, fmt), ...4 ta], ...] kartochka qatorlari;
    total — jadval oxiridagi JAMI qatori qiymatlari (list) yoki None;
    main_chart — 1-varaqdagi jadval yonidagi diagramma: dict(title, cat_col, val_col, color);
    sections — «Statistika» varag'idagi bo'limlar: dict(title, headers, rows,
        money_cols, pct_cols, center_cols, total, chart=dict(title, cat_col, val_col, color),
        medals=bool, merges=[(c1, c2)]).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.sheet_view.showGridLines = False
    ncols = len(headers)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    _banner(ws, ncols, f"GULNORA FARM — {title}")
    _subtitle(ws, ncols, subtitle)
    row = 4
    for cards in card_rows:
        _cards(ws, row, ncols, cards)
        row += 3

    head_row = row
    _header(ws, head_row, headers)
    last = _data_rows(ws, head_row + 1, rows, money_cols=money_cols,
                      center_cols=center_cols, pct_cols=pct_cols, muted=muted,
                      badge_col=badge_col, badges=badges, money_color=money_color,
                      strike=strike)
    if not rows:
        last = head_row + 1
        ws.merge_cells(start_row=last, start_column=1, end_row=last, end_column=ncols)
        c = ws.cell(row=last, column=1, value=empty_text)
        c.font = Font(italic=True, color=GREY, size=12)
        c.alignment = _CENTER
        ws.row_dimensions[last].height = 30
    else:
        ws.auto_filter.ref = f"A{head_row}:{get_column_letter(ncols)}{last}"
        if total is not None:
            label_span = 1
            while label_span < len(total) and total[label_span] in ("", None):
                label_span += 1
            _total_line(ws, last + 1, total, money_cols=money_cols,
                        pct_cols=pct_cols, label_span=label_span)
        if main_chart:
            _bar_chart(ws, f"{get_column_letter(ncols + 2)}{head_row}",
                       main_chart["title"], main_chart["cat_col"], main_chart["val_col"],
                       head_row, head_row + 1, last,
                       color=main_chart.get("color", RED),
                       num_fmt=main_chart.get("num_fmt", "#,##0"))
    ws.freeze_panes = f"A{head_row + 1}"
    _print_setup(ws, landscape=True, title_row=head_row)

    if sections:
        sw = wb.create_sheet("Statistika")
        sw.sheet_view.showGridLines = False
        sn = max(6, max(len(s["headers"]) for s in sections))
        for i, w in enumerate(stats_widths or [6, 32, 18, 20, 16, 18, 16, 16][:sn], start=1):
            sw.column_dimensions[get_column_letter(i)].width = w
        _banner(sw, sn, stats_title or f"{title} — STATISTIKA", size=15, height=34)
        _subtitle(sw, sn, subtitle.split("|")[0].strip())
        r = 4
        for sec in sections:
            width = len(sec["headers"])
            _section_title(sw, r, width, sec["title"])
            _header(sw, r + 1, sec["headers"], merges=sec.get("merges", ()))
            first = r + 2
            srows = sec["rows"]
            if srows:
                s_last = _data_rows(
                    sw, first, srows, money_cols=sec.get("money_cols", ()),
                    center_cols=sec.get("center_cols", (1,)),
                    pct_cols=sec.get("pct_cols", ()), merges=sec.get("merges", ()),
                    money_color=sec.get("money_color", RED))
            else:
                s_last = first
                sw.merge_cells(start_row=first, start_column=1, end_row=first,
                               end_column=width)
                c = sw.cell(row=first, column=1, value="Ma'lumot yo'q")
                c.font = Font(italic=True, color=GREY)
                c.alignment = _CENTER
            if sec.get("medals"):
                for k, color in enumerate(("FFD54F", "E0E0E0", "FFCC80")):
                    if k < len(srows):
                        mc = sw.cell(row=first + k, column=1)
                        mc.fill = _fill(color)
                        mc.font = Font(bold=True)
            end = s_last
            if srows and sec.get("total") is not None:
                end += 1
                _total_line(sw, end, sec["total"], money_cols=sec.get("money_cols", ()),
                            pct_cols=sec.get("pct_cols", ()))
            chart = sec.get("chart")
            has_chart = bool(chart and srows and any(
                (row_[chart["val_col"] - 1] or 0) for row_ in srows))
            if has_chart:
                _bar_chart(sw, f"{get_column_letter(sn + 2)}{r}", chart["title"],
                           chart["cat_col"], chart["val_col"], r + 1, first, s_last,
                           color=chart.get("color", GREEN),
                           num_fmt=chart.get("num_fmt", "#,##0"),
                           horizontal=chart.get("horizontal", False))
            r = max(end + 3, r + 17 if has_chart else 0)
        _print_setup(sw, landscape=True)

    return _finish(wb, file_prefix)


def _subtitle_text(rng, extra=""):
    text = f"Davr: {rng.text}      |      Tayyorlangan: {_generated_at()}"
    return text + (f"      |      {extra}" if extra else "")


def _group(items, key, amount=None):
    """items ni kalit bo'yicha guruhlaydi: {k: {'cnt', 'sum', 'people'}}."""
    out = defaultdict(lambda: {"cnt": 0, "sum": 0, "people": set()})
    for it in items:
        g = out[key(it)]
        g["cnt"] += 1
        if amount:
            g["sum"] += amount(it)
        if it.get("user_id") or it.get("employee_user_id"):
            g["people"].add(it.get("user_id") or it.get("employee_user_id"))
    return out


def _month_section(periods, title, items, date_key, chart_title, color=GREEN,
                   amount=None, extra_header=None):
    """Oylar bo'yicha bo'lim (har bir oy ko'rinadi, bo'sh oylar ham)."""
    g = _group(items, lambda it: _month_of(it.get(date_key)), amount)
    headers = ["№", "Oy", "Soni"] + (["Summa"] if amount else [])
    rows = []
    for i, p in enumerate(periods, start=1):
        row = [i, period_label(p), g[p]["cnt"]]
        if amount:
            row.append(g[p]["sum"])
        rows.append(row)
    total = ["", "JAMI", sum(r[2] for r in rows)]
    if amount:
        total.append(sum(r[3] for r in rows))
    return dict(
        title=title, headers=extra_header or headers, rows=rows, total=total,
        center_cols=(1, 3), money_cols=(4,) if amount else (),
        chart=dict(title=chart_title, cat_col=2, val_col=4 if amount else 3, color=color),
    )


def _ranked_section(title, groups, name_header, color=GREEN, amount=False, limit=None,
                    money_color=RED):
    """Kalit bo'yicha guruhlangan (filial / lavozim / sabab ...) bo'lim, kamayish tartibida."""
    items = sorted(groups.items(), key=lambda kv: (-(kv[1]["sum"] if amount else kv[1]["cnt"]),
                                                   -kv[1]["cnt"], str(kv[0])))
    if limit:
        items = items[:limit]
    whole = sum(v["sum"] if amount else v["cnt"] for v in groups.values())
    headers = ["№", name_header, "Soni"] + (["Summa"] if amount else []) + ["Ulushi"]
    rows = []
    for i, (name, v) in enumerate(items, start=1):
        row = [i, name or "-", v["cnt"]]
        if amount:
            row.append(v["sum"])
        row.append(pct(v["sum"] if amount else v["cnt"], whole))
        rows.append(row)
    pct_col = 5 if amount else 4
    return dict(
        title=title, headers=headers, rows=rows, center_cols=(1, 3),
        money_cols=(4,) if amount else (), pct_cols=(pct_col,), money_color=money_color,
        chart=dict(title=title, cat_col=2, val_col=4 if amount else 3, color=color,
                   horizontal=len(rows) > 6),
    )


# ================= 1) JARIMALAR =================
def build_fines_report(fines, rng):
    active = [f for f in fines if not f.get("cancelled")]
    cancelled = [f for f in fines if f.get("cancelled")]
    total_sum = sum(money(f.get("amount")) for f in active)
    cancelled_sum = sum(money(f.get("amount")) for f in cancelled)
    people = {f.get("employee_user_id") for f in active}
    by_emp = defaultdict(lambda: {"cnt": 0, "sum": 0, "name": "-", "pos": "-", "branch": "-"})
    for f in active:
        e = by_emp[f.get("employee_user_id")]
        e["cnt"] += 1
        e["sum"] += money(f.get("amount"))
        e["name"] = f.get("employee_name") or "-"
        e["pos"] = position_of(f)
        e["branch"] = f.get("branch_name") or "-"
    top = max(by_emp.values(), key=lambda e: (e["sum"], e["cnt"]), default=None)
    src = {"hr": [0, 0], "finance": [0, 0]}
    for f in active:
        s = src.setdefault(f.get("source") or "finance", [0, 0])
        s[0] += 1
        s[1] += money(f.get("amount"))

    src_names = {"hr": "HR", "finance": "Moliya"}
    rows, muted = [], []
    for i, f in enumerate(fines, start=1):
        who = src_names.get(f.get("source"), f.get("source") or "-")
        if f.get("created_by_name"):
            who += f": {f['created_by_name']}"
        rows.append([
            i, fmt_date(f.get("created_at")), f.get("employee_name") or "-", position_of(f),
            f.get("branch_name") or "-", money(f.get("amount")),
            (f.get("reason") or "-").strip(), who,
            "Bekor qilingan" if f.get("cancelled") else "Faol",
        ])
        muted.append(bool(f.get("cancelled")))

    # Oylar bo'yicha — faol va bekor qilingan alohida
    months = []
    for i, p in enumerate(rng.periods, start=1):
        a = [f for f in active if _month_of(f.get("created_at")) == p]
        c = [f for f in cancelled if _month_of(f.get("created_at")) == p]
        months.append([i, period_label(p), len(a), sum(money(f.get("amount")) for f in a),
                       len(c), sum(money(f.get("amount")) for f in c),
                       len({f.get("employee_user_id") for f in a})])
    by_branch = _group(active, lambda f: f.get("branch_name") or "Filialsiz",
                       lambda f: money(f.get("amount")))
    reasons = defaultdict(lambda: {"cnt": 0, "sum": 0, "people": set(), "text": ""})
    for f in active:
        reason = (f.get("reason") or "-").strip()
        g = reasons[" ".join(reason.lower().split())]
        g["cnt"] += 1
        g["sum"] += money(f.get("amount"))
        g["text"] = g["text"] or reason
    reason_groups = {v["text"]: v for v in reasons.values()}
    emp_rows = sorted(by_emp.values(), key=lambda e: (-e["sum"], -e["cnt"]))[:15]

    return build_report(
        title="JARIMALAR HISOBOTI", file_prefix=f"jarimalar_{rng.tag}",
        subtitle=_subtitle_text(rng),
        card_rows=[
            [("Jami jarimalar soni", f"{len(active)} ta", GREEN_DARK),
             ("Jami jarima summasi", total_sum, RED, MONEY_FMT),
             ("Jarimalangan xodimlar", f"{len(people)} nafar", BLUE),
             ("O'rtacha jarima", round(total_sum / len(active)) if active else 0,
              ORANGE, MONEY_FMT)],
            [("Bekor qilingan", f"{len(cancelled)} ta · {som(cancelled_sum)}", GREY),
             ("Eng ko'p jarima olgan",
              f"{top['name']} ({top['cnt']} ta)" if top else "—", RED),
             ("HR yozgan", f"{src['hr'][0]} ta · {som(src['hr'][1])}", BLUE),
             ("Moliya yozgan", f"{src['finance'][0]} ta · {som(src['finance'][1])}", PURPLE)],
        ],
        sheet_name="Jarimalar",
        headers=["№", "Sana", "Ism-familiya", "Lavozim", "Filial", "Jarima summasi",
                 "Jarima sababi", "Kim yozgan", "Holat"],
        widths=[6, 18, 30, 22, 24, 20, 46, 26, 16],
        rows=rows, money_cols=(6,), center_cols=(1, 2, 9), muted=muted, strike=True,
        badge_col=9, badges={"Faol": (RED_LIGHT, RED), "Bekor qilingan": ("EEEEEE", MUTED)},
        total=["JAMI (faol jarimalar):", "", "", "", "", total_sum, "", "",
               f"{len(active)} ta"],
        empty_text="Bu davrda jarimalar yozilmagan",
        stats_title="JARIMALAR STATISTIKASI",
        sections=[
            dict(title="Oylar bo'yicha",
                 headers=["№", "Oy", "Jarimalar soni", "Jarima summasi", "Bekor qil.",
                          "Bekor summa", "Xodimlar"],
                 rows=months, center_cols=(1, 3, 5, 7), money_cols=(4, 6),
                 total=["", "JAMI", len(active), total_sum, len(cancelled),
                        cancelled_sum, len(people)],
                 chart=dict(title="Oylar bo'yicha jarima summasi (so'm)",
                            cat_col=2, val_col=4, color=RED)),
            _ranked_section("Filiallar bo'yicha", by_branch, "Filial", RED, amount=True),
            dict(title="Eng ko'p jarima olgan xodimlar (TOP 15)",
                 headers=["№", "Ism-familiya", "Lavozim", "Filial", "Soni", "Jami summa"],
                 rows=[[i, e["name"], e["pos"], e["branch"], e["cnt"], e["sum"]]
                       for i, e in enumerate(emp_rows, start=1)],
                 center_cols=(1, 5), money_cols=(6,), medals=True),
            _ranked_section("Jarima sabablari (TOP 10)", reason_groups, "Sabab", ORANGE,
                            amount=True, limit=10),
        ],
        stats_widths=[6, 32, 20, 22, 14, 18, 14],
    )


# ================= 2) YANGI ISHGA OLINGANLAR =================
def _emp_status(row):
    return plain(EMP_STATUS_LABELS.get(row.get("emp_status") or "regular", "-"))


def build_hired_report(hired, rng):
    left = [h for h in hired if h.get("has_left")]
    probation = [h for h in hired if not h.get("has_left")
                 and (h.get("emp_status") or "regular") != "regular"]
    rows = []
    for i, h in enumerate(hired, start=1):
        rows.append([
            i, fmt_date(h.get("created_at")), h.get("full_name") or "-", position_of(h),
            h.get("branch_name") or "-",
            "-" if h.get("has_left") else _emp_status(h),
            plain(h.get("shift")) if h.get("shift") else "-",
            money(h.get("monthly_salary")) or "-", h.get("phone") or "-",
            "Ketgan" if h.get("has_left") else "Ishlayapti",
            h.get("created_by_name") or "-",
        ])
    salaries = [money(h.get("monthly_salary")) for h in hired if money(h.get("monthly_salary"))]
    by_branch = _group(hired, lambda h: h.get("branch_name") or "Filialsiz")
    by_pos = _group(hired, position_of)
    return build_report(
        title="YANGI ISHGA OLINGANLAR", file_prefix=f"yangi_xodimlar_{rng.tag}",
        subtitle=_subtitle_text(rng),
        card_rows=[[
            ("Jami ishga olingan", f"{len(hired)} nafar", GREEN_DARK),
            ("Hozir ishlayapti", f"{len(hired) - len(left)} nafar", BLUE),
            ("Keyin ketgan", f"{len(left)} nafar", RED),
            ("Sinov / o'rganuvchi", f"{len(probation)} nafar", ORANGE),
        ], [
            ("O'rtacha oylik", round(sum(salaries) / len(salaries)) if salaries else 0,
             PURPLE, MONEY_FMT),
            ("Saqlanib qolish", f"{pct(len(hired) - len(left), len(hired)):.0%}"
             if hired else "—", TEAL),
            ("Eng ko'p olgan filial", _top_name(by_branch), GREEN_DARK),
            ("Eng ko'p lavozim", _top_name(by_pos), BLUE),
        ]],
        sheet_name="Yangi xodimlar",
        headers=["№", "Ishga olingan sana", "Ism-familiya", "Lavozim", "Filial", "Maqom",
                 "Smena", "Oylik", "Telefon", "Holat", "Kim qabul qildi"],
        widths=[6, 18, 30, 22, 24, 16, 18, 18, 18, 14, 24],
        rows=rows, money_cols=(8,), center_cols=(1, 2, 6, 7, 10), money_color=INK,
        muted=[bool(h.get("has_left")) for h in hired],
        badge_col=10, badges={"Ishlayapti": (GREEN_LIGHT, GREEN_DARK),
                              "Ketgan": (RED_LIGHT, RED)},
        empty_text="Bu davrda yangi xodim ishga olinmagan",
        stats_title="YANGI XODIMLAR STATISTIKASI",
        sections=[
            _month_section(rng.periods, "Oylar bo'yicha", hired, "created_at",
                           "Oylar bo'yicha ishga olinganlar", GREEN),
            _ranked_section("Filiallar bo'yicha", by_branch, "Filial", BLUE),
            _ranked_section("Lavozimlar bo'yicha", by_pos, "Lavozim", PURPLE),
        ],
    )


def _top_name(groups):
    if not groups:
        return "—"
    name, v = max(groups.items(), key=lambda kv: (kv[1]["cnt"], kv[1]["sum"]))
    return f"{name} ({v['cnt']})"


# ================= 3) ISHDAN BO'SHAGANLAR =================
def build_dismissed_report(rows_in, rng):
    rehired = [d for d in rows_in if d.get("rehired")]
    rows = []
    for i, d in enumerate(rows_in, start=1):
        rows.append([
            i, fmt_date(d.get("dismissed_at")), d.get("full_name") or "-",
            position_of(d, role_key="role"), d.get("branch_name") or "-",
            money(d.get("monthly_salary")) or "-", (d.get("reason") or "-").strip(),
            d.get("dismissed_by_name") or "-",
            "Qayta olingan" if d.get("rehired") else "Ketgan",
        ])
    by_branch = _group(rows_in, lambda d: d.get("branch_name") or "Filialsiz")
    by_pos = _group(rows_in, lambda d: position_of(d, role_key="role"))
    by_reason = _group(rows_in, lambda d: (d.get("reason") or "Sabab ko'rsatilmagan").strip())
    return build_report(
        title="ISHDAN BO'SHAGANLAR", file_prefix=f"ishdan_boshaganlar_{rng.tag}",
        subtitle=_subtitle_text(rng),
        card_rows=[[
            ("Jami ketganlar", f"{len(rows_in)} nafar", RED),
            ("Qayta ishga olingan", f"{len(rehired)} nafar", GREEN_DARK),
            ("Eng ko'p ketgan filial", _top_name(by_branch), ORANGE),
            ("Eng ko'p ketgan lavozim", _top_name(by_pos), PURPLE),
        ]],
        sheet_name="Ketganlar",
        headers=["№", "Sana", "Ism-familiya", "Lavozim", "Filial", "Oxirgi oylik",
                 "Sabab", "Kim bo'shatdi", "Holat"],
        widths=[6, 18, 30, 22, 24, 18, 40, 24, 16],
        rows=rows, money_cols=(6,), center_cols=(1, 2, 9), money_color=INK,
        badge_col=9, badges={"Ketgan": (RED_LIGHT, RED),
                             "Qayta olingan": (GREEN_LIGHT, GREEN_DARK)},
        empty_text="Bu davrda hech kim ishdan bo'shamagan",
        stats_title="ISHDAN BO'SHAGANLAR STATISTIKASI",
        sections=[
            _month_section(rng.periods, "Oylar bo'yicha", rows_in, "dismissed_at",
                           "Oylar bo'yicha ketganlar", RED),
            _ranked_section("Filiallar bo'yicha", by_branch, "Filial", ORANGE),
            _ranked_section("Lavozimlar bo'yicha", by_pos, "Lavozim", PURPLE),
            _ranked_section("Sabablar (TOP 10)", by_reason, "Sabab", RED, limit=10),
        ],
    )


# ================= 4) ARIZALAR (NOMZODLAR) =================
def _app_status(a):
    if a.get("status") == ST_ACCEPTED and a.get("accept_kind") in ACCEPT_KIND_LABELS:
        return plain(ACCEPT_KIND_LABELS[a["accept_kind"]])
    return plain(STATUS_LABELS.get(a.get("status"), a.get("status") or "-"))


def build_applications_report(apps, rng):
    accepted = [a for a in apps if a.get("status") == ST_ACCEPTED]
    rejected = [a for a in apps if a.get("status") == "rejected"]
    pending = [a for a in apps if a.get("status") in ("new", "interview", "waiting")]
    rows = []
    for i, a in enumerate(apps, start=1):
        rows.append([
            i, fmt_date(a.get("created_at")), a.get("full_name") or "-",
            a.get("vacancy_title") or a.get("position") or "-",
            a.get("branch_name") or "-", a.get("phone") or "-",
            a.get("city") or "-", a.get("exp_years") or "-", _app_status(a),
        ])
    by_status = _group(apps, _app_status)
    by_vac = _group(apps, lambda a: a.get("vacancy_title") or a.get("position") or "-")
    by_branch = _group(apps, lambda a: a.get("branch_name") or "Filialsiz")
    badges = {}
    for a in apps:
        st = _app_status(a)
        if a.get("status") == ST_ACCEPTED:
            badges[st] = (GREEN_LIGHT, GREEN_DARK)
        elif a.get("status") == "rejected":
            badges[st] = (RED_LIGHT, RED)
        else:
            badges[st] = ("FFF3E0", ORANGE)
    return build_report(
        title="ARIZALAR (NOMZODLAR) HISOBOTI", file_prefix=f"arizalar_{rng.tag}",
        subtitle=_subtitle_text(rng),
        card_rows=[[
            ("Jami arizalar", f"{len(apps)} ta", GREEN_DARK),
            ("Qabul qilingan", f"{len(accepted)} ta", BLUE),
            ("Rad etilgan", f"{len(rejected)} ta", RED),
            ("Ko'rib chiqilmoqda", f"{len(pending)} ta", ORANGE),
        ], [
            ("Qabul ulushi (konversiya)", f"{pct(len(accepted), len(apps)):.0%}"
             if apps else "—", TEAL),
            ("Eng ko'p ariza (lavozim)", _top_name(by_vac), PURPLE),
            ("Eng ko'p ariza (filial)", _top_name(by_branch), BLUE),
            ("Oyiga o'rtacha", f"{round(len(apps) / len(rng.periods))} ta", GREEN_DARK),
        ]],
        sheet_name="Arizalar",
        headers=["№", "Sana", "Ism-familiya", "Vakansiya / lavozim", "Filial", "Telefon",
                 "Shahar", "Tajriba", "Holat"],
        widths=[6, 18, 30, 26, 24, 18, 18, 14, 24],
        rows=rows, center_cols=(1, 2, 8, 9), badge_col=9, badges=badges,
        empty_text="Bu davrda ariza tushmagan",
        stats_title="ARIZALAR STATISTIKASI",
        sections=[
            _month_section(rng.periods, "Oylar bo'yicha", apps, "created_at",
                           "Oylar bo'yicha arizalar", GREEN),
            _ranked_section("Holat bo'yicha", by_status, "Holat", BLUE),
            _ranked_section("Vakansiya / lavozim bo'yicha", by_vac, "Lavozim", PURPLE,
                            limit=15),
            _ranked_section("Filiallar bo'yicha", by_branch, "Filial", ORANGE),
        ],
    )


# ================= 5) XODIMLAR TARKIBI (joriy holat) =================
def build_staff_report(profiles):
    salaries = [money(p.get("monthly_salary")) for p in profiles]
    fund = sum(salaries)
    paid = [s for s in salaries if s]
    uniform_yes = sum(1 for p in profiles if p.get("uniform_status") == "yes")
    rows = []
    ordered = sorted(profiles, key=lambda p: ((p.get("branch_name") or "яя"),
                                              p.get("full_name") or ""))
    for i, p in enumerate(ordered, start=1):
        rows.append([
            i, p.get("full_name") or "-", position_of(p, role_key="role"),
            p.get("branch_name") or "-", _emp_status(p),
            plain(p.get("shift")) if p.get("shift") else "-",
            money(p.get("monthly_salary")) or "-",
            fmt_date(p.get("since"), with_time=False) if p.get("since") else "-",
            p.get("phone") or "-", p.get("education") or "-",
            {"yes": "Bor", "no": "Yo'q"}.get(p.get("uniform_status"), "Noma'lum"),
        ])
    by_branch = defaultdict(lambda: {"cnt": 0, "sum": 0, "people": set()})
    for p in profiles:
        g = by_branch[p.get("branch_name") or "Filialsiz"]
        g["cnt"] += 1
        g["sum"] += money(p.get("monthly_salary"))
    branch_rows = []
    for i, (name, v) in enumerate(sorted(by_branch.items(), key=lambda kv: -kv[1]["cnt"]),
                                  start=1):
        branch_rows.append([i, name, v["cnt"], v["sum"],
                            round(v["sum"] / v["cnt"]) if v["cnt"] else 0,
                            pct(v["cnt"], len(profiles))])
    by_pos = _group(profiles, lambda p: position_of(p, role_key="role"),
                    lambda p: money(p.get("monthly_salary")))
    by_status = _group(profiles, _emp_status)
    from utils import now_tk
    return build_report(
        title="XODIMLAR TARKIBI", file_prefix="xodimlar_tarkibi",
        subtitle=f"Holat: {now_tk().strftime('%d.%m.%Y')} sanasiga      |      "
                 f"Tayyorlangan: {_generated_at()}",
        card_rows=[[
            ("Jami xodimlar", f"{len(profiles)} nafar", GREEN_DARK),
            ("Oylik fondi (oyiga)", fund, RED, MONEY_FMT),
            ("O'rtacha oylik", round(sum(paid) / len(paid)) if paid else 0, PURPLE,
             MONEY_FMT),
            ("Filiallar soni", f"{len(by_branch)} ta", BLUE),
        ], [
            ("Sinovda / o'rganuvchi",
             f"{sum(1 for p in profiles if (p.get('emp_status') or 'regular') != 'regular')}"
             " nafar", ORANGE),
            ("Oyligi belgilanmagan", f"{len(profiles) - len(paid)} nafar", GREY),
            ("Formasi bor", f"{uniform_yes} nafar ({pct(uniform_yes, len(profiles)):.0%})"
             if profiles else "—", TEAL),
            ("Eng katta filial", _top_name(by_branch), GREEN_DARK),
        ]],
        sheet_name="Xodimlar",
        headers=["№", "Ism-familiya", "Lavozim", "Filial", "Maqom", "Smena", "Oylik",
                 "Ish boshlagan", "Telefon", "Ma'lumoti", "Forma"],
        widths=[6, 30, 22, 24, 16, 18, 18, 15, 18, 20, 12],
        rows=rows, money_cols=(7,), center_cols=(1, 5, 6, 8, 11), money_color=INK,
        total=["JAMI OYLIK FONDI:", "", "", "", "", "", fund, "", "", "",
               f"{len(profiles)} nafar"],
        empty_text="Xodimlar yo'q",
        stats_title="XODIMLAR TARKIBI — STATISTIKA",
        sections=[
            dict(title="Filiallar bo'yicha",
                 headers=["№", "Filial", "Xodimlar", "Oylik fondi", "O'rtacha oylik",
                          "Ulushi"],
                 rows=branch_rows, center_cols=(1, 3), money_cols=(4, 5), pct_cols=(6,),
                 money_color=INK,
                 total=["", "JAMI", len(profiles), fund,
                        round(sum(paid) / len(paid)) if paid else 0, 1 if profiles else 0],
                 chart=dict(title="Filiallar bo'yicha xodimlar soni", cat_col=2,
                            val_col=3, color=BLUE, horizontal=len(branch_rows) > 6)),
            _ranked_section("Lavozimlar bo'yicha (oylik fondi bilan)", by_pos, "Lavozim",
                            PURPLE, amount=True, money_color=INK),
            _ranked_section("Maqom bo'yicha", by_status, "Maqom", ORANGE),
        ],
    )


# ================= 6) UMUMIY STATISTIKA =================
def build_summary_report(rng, *, profiles, hired, dismissed, apps, fines,
                         advances, tech):
    active_f = [f for f in fines if not f.get("cancelled")]
    accepted = [a for a in apps if a.get("status") == ST_ACCEPTED]
    tech_done = [t for t in tech if t.get("status") in ("done", "rated")]
    fund = sum(money(p.get("monthly_salary")) for p in profiles)
    fines_sum = sum(money(f.get("amount")) for f in active_f)
    adv_sum = sum(money(a.get("amount")) for a in advances)
    tech_cost = sum(money(t.get("cost")) for t in tech)
    net = len(hired) - len(dismissed)
    turnover = pct(len(dismissed), len(profiles) + len(dismissed))

    def in_month(items, key, p):
        return [it for it in items if _month_of(it.get(key)) == p]

    rows = []
    for i, p in enumerate(rng.periods, start=1):
        mf = [f for f in active_f if _month_of(f.get("created_at")) == p]
        ma = in_month(apps, "created_at", p)
        rows.append([
            i, period_label(p), len(ma),
            sum(1 for a in ma if a.get("status") == ST_ACCEPTED),
            len(in_month(hired, "created_at", p)), len(in_month(dismissed, "dismissed_at", p)),
            len(mf), sum(money(f.get("amount")) for f in mf),
            sum(money(a.get("amount")) for a in advances if a.get("period") == p),
            len(in_month(tech, "created_at", p)),
        ])
    total = ["", "JAMI", len(apps), len(accepted), len(hired), len(dismissed),
             len(active_f), fines_sum, adv_sum, len(tech)]

    # Filiallar kesimi
    names = set()
    for coll in (profiles, hired, dismissed, active_f, apps, tech):
        names.update((it.get("branch_name") or "Filialsiz") for it in coll)
    branch_rows = []
    for name in names:
        def cnt(coll):
            return sum(1 for it in coll if (it.get("branch_name") or "Filialsiz") == name)
        staff = [p for p in profiles if (p.get("branch_name") or "Filialsiz") == name]
        bf = [f for f in active_f if (f.get("branch_name") or "Filialsiz") == name]
        branch_rows.append([
            None, name, len(staff), sum(money(p.get("monthly_salary")) for p in staff),
            cnt(hired), cnt(dismissed), len(bf), sum(money(f.get("amount")) for f in bf),
            cnt(apps),
        ])
    branch_rows.sort(key=lambda r: (-r[2], r[1]))
    for i, r in enumerate(branch_rows, start=1):
        r[0] = i

    return build_report(
        title="UMUMIY STATISTIKA (DIREKTOR)", file_prefix=f"umumiy_statistika_{rng.tag}",
        subtitle=_subtitle_text(rng),
        card_rows=[[
            ("Hozirgi xodimlar", f"{len(profiles)} nafar", GREEN_DARK),
            ("Yangi ishga olingan", f"+{len(hired)} nafar", BLUE),
            ("Ishdan bo'shagan", f"-{len(dismissed)} nafar", RED),
            ("Kadrlar o'zgarishi", f"{net:+d} nafar", GREEN_DARK if net >= 0 else RED),
        ], [
            ("Oylik fondi (oyiga)", fund, PURPLE, MONEY_FMT),
            ("Jarimalar", f"{len(active_f)} ta · {som(fines_sum)}", RED),
            ("Avanslar", f"{len(advances)} ta · {som(adv_sum)}", ORANGE),
            ("Kadrlar qo'nimsizligi", f"{turnover:.1%}", TEAL),
        ], [
            ("Arizalar", f"{len(apps)} ta", GREEN_DARK),
            ("Qabul qilingan arizalar",
             f"{len(accepted)} ta ({pct(len(accepted), len(apps)):.0%})", BLUE),
            ("Texnik ishlar", f"{len(tech_done)}/{len(tech)} bajarildi", PURPLE),
            ("Texnik xarajat", tech_cost, ORANGE, MONEY_FMT),
        ]],
        sheet_name="Umumiy",
        headers=["№", "Oy", "Arizalar", "Qabul qilingan", "Yangi xodimlar", "Ketganlar",
                 "Jarimalar", "Jarima summasi", "Avans summasi", "Texnik ishlar"],
        widths=[6, 18, 14, 16, 16, 14, 14, 20, 20, 16],
        rows=rows, money_cols=(8, 9), center_cols=(1, 3, 4, 5, 6, 7, 10),
        money_color={8: RED, 9: INK},
        total=total, empty_text="Ma'lumot yo'q",
        stats_title="FILIALLAR KESIMI",
        sections=[
            dict(title="Filiallar bo'yicha umumiy ko'rsatkichlar",
                 headers=["№", "Filial", "Xodimlar", "Oylik fondi", "Yangi", "Ketgan",
                          "Jarimalar", "Jarima summasi", "Arizalar"],
                 rows=branch_rows, center_cols=(1, 3, 5, 6, 7, 9), money_cols=(4, 8),
                 money_color={4: INK, 8: RED},
                 total=["", "JAMI", len(profiles), fund, len(hired), len(dismissed),
                        len(active_f), fines_sum, len(apps)],
                 chart=dict(title="Filiallar bo'yicha xodimlar soni", cat_col=2,
                            val_col=3, color=BLUE, horizontal=len(branch_rows) > 6)),
            dict(title="Oylar bo'yicha kadrlar harakati",
                 headers=["№", "Oy", "Yangi xodimlar", "Ketganlar", "Farq"],
                 rows=[[r[0], r[1], r[4], r[5], r[4] - r[5]] for r in rows],
                 center_cols=(1, 3, 4, 5),
                 total=["", "JAMI", len(hired), len(dismissed), net],
                 chart=dict(title="Oylar bo'yicha yangi ishga olinganlar", cat_col=2,
                            val_col=3, color=GREEN)),
        ],
        stats_widths=[6, 30, 14, 20, 12, 12, 14, 20, 12],
    )


# ================= MA'LUMOT YIG'ISH + TAYYOR FAYL =================
# (kalit, tugma matni, davr tanlanadimi)
DIRECTOR_REPORTS = [
    ("summary", "📊 Umumiy statistika", True),
    ("hired", "🆕 Yangi ishga olinganlar", True),
    ("left", "🚪 Ishdan bo'shaganlar", True),
    ("fines", "💸 Jarimalar", True),
    ("apps", "📥 Arizalar (nomzodlar)", True),
    ("staff", "👥 Xodimlar tarkibi va oylik fondi", False),
]
REPORT_TITLES = {k: t for k, t, _ in DIRECTOR_REPORTS}
REPORT_NEEDS_PERIOD = {k: p for k, _, p in DIRECTOR_REPORTS}


async def make_report(kind, rng):
    """Hisobot faylini (BufferedInputFile) va qisqa izohni qaytaradi.

    rng — DateRange (month_range(n) yoki foydalanuvchi tanlagan sanalar)."""
    from database import queries as q
    since, until, span = rng.since, rng.until, f"📅 {rng.text}"
    if kind == "fines":
        fines = await q.fines_report(since, until)
        active = [f for f in fines if not f.get("cancelled")]
        total = sum(money(f.get("amount")) for f in active)
        return build_fines_report(fines, rng), (
            f"💸 Jarimalar: <b>{len(active)}</b> ta · <b>{som(total)}</b>\n"
            f"👥 Jarimalangan: <b>{len({f.get('employee_user_id') for f in active})}</b> nafar\n"
            f"🚫 Bekor qilingan: <b>{len(fines) - len(active)}</b> ta\n{span}")
    if kind == "hired":
        hired = await q.report_hired(since, until)
        left = sum(1 for h in hired if h.get("has_left"))
        return build_hired_report(hired, rng), (
            f"🆕 Ishga olingan: <b>{len(hired)}</b> nafar\n"
            f"✅ Ishlayapti: <b>{len(hired) - left}</b> · 🚪 Ketgan: <b>{left}</b>\n{span}")
    if kind == "left":
        rows = await q.report_dismissed(since, until)
        return build_dismissed_report(rows, rng), (
            f"🚪 Ishdan bo'shaganlar: <b>{len(rows)}</b> nafar\n{span}")
    if kind == "apps":
        apps = await q.report_applications(since, until)
        acc = sum(1 for a in apps if a.get("status") == ST_ACCEPTED)
        return build_applications_report(apps, rng), (
            f"📥 Arizalar: <b>{len(apps)}</b> ta · ✅ Qabul: <b>{acc}</b>\n{span}")
    if kind == "staff":
        profiles = await q.list_employee_profiles()
        fund = sum(money(p.get("monthly_salary")) for p in profiles)
        return build_staff_report(profiles), (
            f"👥 Xodimlar: <b>{len(profiles)}</b> nafar\n"
            f"💰 Oylik fondi: <b>{som(fund)}</b>")
    if kind == "summary":
        periods = rng.periods
        data = dict(
            profiles=await q.list_employee_profiles(),
            hired=await q.report_hired(since, until),
            dismissed=await q.report_dismissed(since, until),
            apps=await q.report_applications(since, until),
            fines=await q.fines_report(since, until),
            advances=await q.report_advances(periods[0], periods[-1]),
            tech=await q.report_tech_tasks(since, until),
        )
        return build_summary_report(rng, **data), (
            f"👥 Xodimlar: <b>{len(data['profiles'])}</b> · "
            f"🆕 +{len(data['hired'])} · 🚪 -{len(data['dismissed'])}\n"
            f"📥 Arizalar: <b>{len(data['apps'])}</b>\n{span}")
    raise ValueError(f"Noma'lum hisobot turi: {kind}")
