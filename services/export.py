"""Excel (.xlsx) hisobotlarni tayyorlash."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from aiogram.types import BufferedInputFile

from database.db import application_status_label

_HEADER_FILL = PatternFill("solid", fgColor="2E7D32")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _autosize(ws):
    for col in ws.columns:
        width = 10
        letter = get_column_letter(col[0].column)
        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            width = max(width, min(len(value) + 2, 50))
        ws.column_dimensions[letter].width = width


def _write_sheet(ws, headers, rows):
    ws.append(headers)
    for i, cell in enumerate(ws[1], start=1):
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    for row in rows:
        ws.append(row)
    _autosize(ws)


def _finish(wb, prefix):
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    from utils import now_tk
    stamp = now_tk().strftime("%Y%m%d_%H%M")
    return BufferedInputFile(buf.read(), filename=f"{prefix}_{stamp}.xlsx")


def build_applications_xlsx(apps):
    wb = Workbook()
    ws = wb.active
    ws.title = "Arizalar"
    headers = [
        "#", "Ism-sharif", "Lavozim", "Filial", "Status", "Telefon",
        "Shahar", "Tuman", "Tug'ilgan sana", "Ma'lumot", "Tajriba",
        "Forma", "Sana",
    ]
    uniform = {"yes": "Bor", "no": "Yo'q"}
    rows = []
    for a in apps:
        rows.append([
            a.get("id"),
            a.get("full_name") or "-",
            a.get("vacancy_title") or a.get("position") or "-",
            a.get("branch_name") or "-",
            application_status_label(a),
            a.get("phone") or "-",
            a.get("city") or "-",
            a.get("district") or "-",
            a.get("birth_date") or "-",
            a.get("education") or "-",
            a.get("exp_years") or "-",
            uniform.get(a.get("uniform_status"), "Noma'lum"),
            a.get("created_at") or "-",
        ])
    _write_sheet(ws, headers, rows)
    return _finish(wb, "arizalar")


def build_users_xlsx(users):
    wb = Workbook()
    ws = wb.active
    ws.title = "Foydalanuvchilar"
    headers = ["#", "TG ID", "Ism-sharif", "Username", "Telefon", "Rol", "Filial", "Holat", "Sana"]
    rows = []
    for u in users:
        rows.append([
            u.get("id"),
            u.get("tg_id"),
            u.get("full_name") or "-",
            ("@" + u["username"]) if u.get("username") else "-",
            u.get("phone") or "-",
            u.get("role") or "-",
            u.get("branch_name") or "-",
            "Bloklangan" if u.get("blocked") else "Faol",
            u.get("created_at") or "-",
        ])
    _write_sheet(ws, headers, rows)
    return _finish(wb, "foydalanuvchilar")


def build_advance_xlsx(rows, period, pay_date=None):
    """Avans oluvchilar ro'yxati — chiroyli, tushunarli dizayn bilan.

    rows — list_advances() natijasi (ism, karta, filial, lavozim, telefon).
    period — 'YYYY-MM'. pay_date — to'lov sanasi (masalan '15.07.2026').
    """
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_fill = PatternFill("solid", fgColor="1B5E20")
    title_font = Font(bold=True, color="FFFFFF", size=16)
    sub_font = Font(bold=True, color="1B5E20", size=11)
    alt_fill = PatternFill("solid", fgColor="E8F5E9")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    headers = ["№", "Ism-familiya", "Avans miqdori", "Karta raqami",
               "Filial", "Lavozim", "Telefon"]
    ncols = len(headers)
    last_col = get_column_letter(ncols)

    wb = Workbook()
    ws = wb.active
    ws.title = "Avans"
    ws.sheet_view.showGridLines = False

    # 1-qator: sarlavha banneri
    ws.merge_cells(f"A1:{last_col}1")
    c = ws["A1"]
    c.value = "GULNORA FARM — AVANS OLUVCHILAR RO'YXATI"
    c.fill = title_fill
    c.font = title_font
    c.alignment = center
    ws.row_dimensions[1].height = 30

    # 2-qator: davr / to'lov sanasi / jami
    ws.merge_cells(f"A2:{last_col}2")
    info = f"Davr: {period}"
    if pay_date:
        info += f"    |    To'lov sanasi: {pay_date}"
    info += f"    |    Jami: {len(rows)} nafar"
    c2 = ws["A2"]
    c2.value = info
    c2.font = sub_font
    c2.alignment = center
    ws.row_dimensions[2].height = 20

    # 3-qator: ustun sarlavhalari
    ws.append([])  # 3-qatorga o'tkazish uchun bo'sh — keyin qo'lda yozamiz
    header_row = 3
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=i, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[header_row].height = 22

    # Ma'lumot qatorlari
    for idx, r in enumerate(rows, start=1):
        row_i = header_row + idx
        amount = r.get("amount")
        values = [
            idx,
            r.get("full_name") or "-",
            int(amount) if amount else "-",
            r.get("card_number") or "-",
            r.get("branch_name") or "-",
            r.get("position") or "-",
            r.get("phone") or "-",
        ]
        for col_i, val in enumerate(values, start=1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.border = border
            cell.alignment = center if col_i in (1, 3) else left
            if idx % 2 == 0:
                cell.fill = alt_fill
        # avans miqdori — minglar ajratgichi bilan (son bo'lsa)
        if amount:
            ws.cell(row=row_i, column=3).number_format = "#,##0"
        # karta raqami matn sifatida (raqam formatlanmasin)
        ws.cell(row=row_i, column=4).number_format = "@"

    # Ustun kengliklari
    widths = [6, 28, 18, 24, 26, 20, 18]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = f"A{header_row + 1}"
    return _finish(wb, f"avans_{period}")


def _styled_header_row(ws, row_i, headers, border, center):
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_i, column=i, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[row_i].height = 22


def build_dayoff_xlsx(branches_data, date_display):
    """Kunlik dam olish hisoboti — filial bo'lim-bo'lim, chiroyli dizayn.

    branches_data — [{branch_name, items:[{full_name, position, day_status}]}].
    """
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_fill = PatternFill("solid", fgColor="1B5E20")
    title_font = Font(bold=True, color="FFFFFF", size=16)
    sub_font = Font(bold=True, color="1B5E20", size=11)
    branch_fill = PatternFill("solid", fgColor="C8E6C9")
    branch_font = Font(bold=True, color="1B5E20", size=12)
    off_fill = PatternFill("solid", fgColor="FFF3E0")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    headers = ["№", "Ism-familiya", "Lavozim", "Holat"]
    ncols = len(headers)
    last_col = get_column_letter(ncols)

    wb = Workbook()
    ws = wb.active
    ws.title = "Dam olish"
    ws.sheet_view.showGridLines = False

    ws.merge_cells(f"A1:{last_col}1")
    c = ws["A1"]
    c.value = "GULNORA FARM — KUNLIK DAM OLISH HISOBOTI"
    c.fill = title_fill
    c.font = title_font
    c.alignment = center
    ws.row_dimensions[1].height = 30

    total_off = sum(
        sum(1 for it in b["items"] if it.get("day_status") == "off")
        for b in branches_data
    )
    ws.merge_cells(f"A2:{last_col}2")
    c2 = ws["A2"]
    c2.value = (f"Sana: {date_display}    |    Filiallar: {len(branches_data)}"
                f"    |    Jami dam oluvchi: {total_off} nafar")
    c2.font = sub_font
    c2.alignment = center
    ws.row_dimensions[2].height = 20

    row_i = 4
    for b in branches_data:
        off_items = [it for it in b["items"] if it.get("day_status") == "off"]
        # Filial sarlavhasi
        ws.merge_cells(start_row=row_i, start_column=1, end_row=row_i, end_column=ncols)
        bc = ws.cell(row=row_i, column=1,
                     value=f"🏢 {b['branch_name']}  —  dam oluvchi: {len(off_items)} nafar")
        bc.fill = branch_fill
        bc.font = branch_font
        bc.alignment = left
        for col_i in range(1, ncols + 1):
            ws.cell(row=row_i, column=col_i).border = border
        ws.row_dimensions[row_i].height = 20
        row_i += 1
        # Ustun sarlavhalari
        _styled_header_row(ws, row_i, headers, border, center)
        row_i += 1
        if not off_items:
            ws.merge_cells(start_row=row_i, start_column=1, end_row=row_i, end_column=ncols)
            ec = ws.cell(row=row_i, column=1, value="— Bu filialda ertaga dam oluvchi yo'q —")
            ec.alignment = center
            for col_i in range(1, ncols + 1):
                ws.cell(row=row_i, column=col_i).border = border
            row_i += 2
            continue
        for idx, it in enumerate(off_items, start=1):
            values = [idx, it.get("full_name") or "-", it.get("position") or "-", "🛌 Dam oladi"]
            for col_i, val in enumerate(values, start=1):
                cell = ws.cell(row=row_i, column=col_i, value=val)
                cell.border = border
                cell.alignment = center if col_i in (1, 4) else left
                cell.fill = off_fill
            row_i += 1
        row_i += 1  # bo'lim orasida bo'sh qator

    widths = [6, 30, 24, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    return _finish(wb, "dam_olish")


def build_report_xlsx(stats, branches, vacancies):
    """Umumiy hisobot: statistika + filiallar + lavozimlar kesimi."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    _write_sheet(ws, ["Ko'rsatkich", "Qiymat"], [
        ["Bugungi arizalar", stats.get("today", 0)],
        ["Haftalik arizalar", stats.get("week", 0)],
        ["Oylik arizalar", stats.get("month", 0)],
        ["Yangi", stats.get("new", 0)],
        ["Suhbatga chaqirilgan", stats.get("interview", 0)],
        ["Qabul qilingan", stats.get("accepted", 0)],
        ["Rad etilgan", stats.get("rejected", 0)],
        ["Jami arizalar", stats.get("total", 0)],
    ])

    ws_b = wb.create_sheet("Filiallar")
    _write_sheet(ws_b, ["Filial", "Arizalar soni"],
                 [[b.get("name") or "Nomsiz", b.get("cnt", 0)] for b in branches])

    ws_v = wb.create_sheet("Lavozimlar")
    _write_sheet(ws_v, ["Lavozim", "Arizalar soni"],
                 [[v.get("name") or "Nomsiz", v.get("cnt", 0)] for v in vacancies])

    return _finish(wb, "hisobot")


def _hours_str(h):
    if h is None:
        return "-"
    try:
        h = float(h)
    except (TypeError, ValueError):
        return "-"
    if h < 1:
        return f"{int(round(h * 60))} daqiqa"
    d, rem = divmod(h, 24)
    if d >= 1:
        return f"{int(d)} kun {rem:.1f} soat"
    return f"{h:.1f} soat"


def build_tech_stats_xlsx(period_label, overall, by_tech, by_cat, by_branch):
    """Texnik ishlar statistikasi: Umumiy + Xodimlar + Kategoriya + Filiallar."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    avg_rating = overall.get("avg_rating")
    _write_sheet(ws, ["Ko'rsatkich", "Qiymat"], [
        ["Davr", period_label],
        ["Jami topshiriqlar", overall.get("total", 0) or 0],
        ["Yakunlangan", overall.get("done", 0) or 0],
        ["Bekor qilingan", overall.get("cancelled", 0) or 0],
        ["Faol (jarayonda)", overall.get("active", 0) or 0],
        ["Shoshilinch", overall.get("urgent", 0) or 0],
        ["O'rtacha baho", f"{avg_rating:.2f}" if avg_rating else "-"],
        ["O'rtacha bajarish vaqti", _hours_str(overall.get("avg_hours"))],
        ["Umumiy xarajat (so'm)", int(overall.get("total_cost") or 0)],
    ])

    ws_t = wb.create_sheet("Xodimlar")
    _write_sheet(
        ws_t,
        ["Texnik xodim", "Jami", "Yakunlangan", "O'rtacha baho", "O'rtacha vaqt"],
        [[
            r.get("name") or "-", r.get("total", 0), r.get("done", 0),
            f"{r['avg_rating']:.2f}" if r.get("avg_rating") else "-",
            _hours_str(r.get("avg_hours")),
        ] for r in by_tech],
    )

    ws_c = wb.create_sheet("Kategoriya")
    _write_sheet(
        ws_c, ["Kategoriya", "Soni", "Xarajat (so'm)"],
        [[r.get("cat") or "-", r.get("total", 0), int(r.get("total_cost") or 0)]
         for r in by_cat],
    )

    ws_b = wb.create_sheet("Filiallar")
    _write_sheet(
        ws_b, ["Filial", "Jami", "Yakunlangan"],
        [[r.get("branch") or "-", r.get("total", 0), r.get("done", 0)]
         for r in by_branch],
    )

    return _finish(wb, "texnik_statistika")


# ================= MOLIYA: JARIMALAR HISOBOTI =================
UZ_MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]

_ROLE_TITLES = {
    "pharmacist": "Farmatsevt", "manager": "Filial rahbari",
    "director": "Direktor", "accountant": "Moliya bo'limi",
    "employee": "Oddiy xodim", "hr": "HR", "it": "IT xodim",
    "tech": "Texnik xodim", "admin": "Admin",
}


def period_label(period):
    """'2026-09' -> 'Sentabr 2026'."""
    try:
        y, m = str(period).split("-")[:2]
        return f"{UZ_MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return str(period or "-")


def _fine_amount(f):
    d = "".join(c for c in str(f.get("amount") or "") if c.isdigit())
    return int(d) if d else 0


def _fine_position(f):
    return (f.get("position")
            or _ROLE_TITLES.get(f.get("emp_role") or "", f.get("emp_role"))
            or "-")


def _fine_date(f):
    """'2026-09-14 10:22:05' -> '14.09.2026 10:22'."""
    s = str(f.get("created_at") or "")
    if len(s) >= 10 and s[4] == "-":
        out = f"{s[8:10]}.{s[5:7]}.{s[0:4]}"
        if len(s) >= 16:
            out += f" {s[11:16]}"
        return out
    return s or "-"


def _fine_period(f):
    return f.get("period") or str(f.get("created_at") or "")[:7]


def _som(n):
    return f"{n:,}".replace(",", " ") + " so'm"


def build_fines_report_xlsx(fines, periods, generated_at=None):
    """Moliya bo'limi uchun jarimalar hisoboti (1/2/3 oylik).

    fines — q.fines_report() natijasi; periods — eskidan yangiga ['YYYY-MM', ...].
    1-varaq «Jarimalar»: tepada statistika kartochkalari + to'liq jadval.
    2-varaq «Statistika»: oylar / filiallar / xodimlar / sabablar kesimida
    jamlanmalar va oylar bo'yicha diagramma.
    """
    from collections import defaultdict
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.label import DataLabelList

    # ---- Ranglar va uslublar ----
    GREEN_DARK, GREEN, GREEN_LIGHT = "1B5E20", "2E7D32", "E8F5E9"
    RED, RED_LIGHT = "C62828", "FFEBEE"
    GREY, GREY_LIGHT = "757575", "F5F5F5"
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    money_fmt = '#,##0" so\'m"'
    no_fill = PatternFill(fill_type=None)

    def fill(color):
        return PatternFill("solid", fgColor=color)

    def banner(ws_, row, last_col, text, size=16, height=34):
        ws_.merge_cells(f"A{row}:{last_col}{row}")
        c_ = ws_[f"A{row}"]
        c_.value = text
        c_.fill = fill(GREEN_DARK)
        c_.font = Font(bold=True, color="FFFFFF", size=size)
        c_.alignment = center
        ws_.row_dimensions[row].height = height

    def subtitle(ws_, row, last_col, text):
        ws_.merge_cells(f"A{row}:{last_col}{row}")
        c_ = ws_[f"A{row}"]
        c_.value = text
        c_.font = Font(bold=True, color=GREEN_DARK, size=11)
        c_.fill = fill(GREEN_LIGHT)
        c_.alignment = center
        ws_.row_dimensions[row].height = 22

    def header(ws_, row, headers_):
        for i, h in enumerate(headers_, start=1):
            if h is None:
                continue
            c_ = ws_.cell(row=row, column=i, value=h)
            c_.fill = fill(GREEN)
            c_.font = Font(bold=True, color="FFFFFF", size=11)
            c_.alignment = center
            c_.border = border
        ws_.row_dimensions[row].height = 26

    def section_title(ws_, row, ncols, text):
        line = Border(bottom=Side(style="medium", color=GREEN))
        ws_.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
        c_ = ws_.cell(row=row, column=1, value=text)
        c_.font = Font(bold=True, color=GREEN_DARK, size=13)
        c_.alignment = Alignment(horizontal="left", vertical="center")
        for col in range(1, ncols + 1):
            ws_.cell(row=row, column=col).border = line
        ws_.row_dimensions[row].height = 24

    def data_rows(ws_, start_row, rows, money_cols=(), center_cols=(1,)):
        """Zebra uslubidagi qatorlar; oxirgi yozilgan qator raqamini qaytaradi."""
        r_ = start_row - 1
        for k, vals in enumerate(rows, start=1):
            r_ = start_row + k - 1
            for col_i, val in enumerate(vals, start=1):
                cell = ws_.cell(row=r_, column=col_i, value=val)
                cell.border = border
                cell.alignment = center if col_i in center_cols else left
                if k % 2 == 0:
                    cell.fill = fill(GREEN_LIGHT)
                if col_i in money_cols:
                    cell.number_format = money_fmt
                    cell.alignment = right
                    cell.font = Font(bold=True, color=RED)
            ws_.row_dimensions[r_].height = 20
        return r_

    def total_line(ws_, row, values, money_cols=()):
        for col_i, val in enumerate(values, start=1):
            cell = ws_.cell(row=row, column=col_i, value=val)
            cell.fill = fill(GREEN_DARK)
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.border = border
            cell.alignment = right if col_i in money_cols else center
            if col_i in money_cols:
                cell.number_format = money_fmt
        ws_.row_dimensions[row].height = 24

    # ---- Hisob-kitob ----
    active = [f for f in fines if not f.get("cancelled")]
    cancelled = [f for f in fines if f.get("cancelled")]
    total_sum = sum(_fine_amount(f) for f in active)
    cancelled_sum = sum(_fine_amount(f) for f in cancelled)
    people = {f.get("employee_user_id") for f in active}
    avg = round(total_sum / len(active)) if active else 0

    def new_month():
        return {"cnt": 0, "sum": 0, "ccnt": 0, "csum": 0, "people": set()}

    by_month = {p: new_month() for p in periods}
    by_emp = defaultdict(lambda: {"cnt": 0, "sum": 0, "name": "-", "pos": "-", "branch": "-"})
    by_branch = defaultdict(lambda: {"cnt": 0, "sum": 0, "people": set()})
    by_reason = defaultdict(lambda: {"cnt": 0, "sum": 0, "text": ""})
    by_source = {"hr": [0, 0], "finance": [0, 0]}
    for f in fines:
        amt = _fine_amount(f)
        m = by_month.setdefault(_fine_period(f), new_month())
        if f.get("cancelled"):
            m["ccnt"] += 1
            m["csum"] += amt
            continue
        m["cnt"] += 1
        m["sum"] += amt
        m["people"].add(f.get("employee_user_id"))
        e = by_emp[f.get("employee_user_id")]
        e["cnt"] += 1
        e["sum"] += amt
        e["name"] = f.get("employee_name") or "-"
        e["pos"] = _fine_position(f)
        e["branch"] = f.get("branch_name") or "-"
        br = by_branch[f.get("branch_name") or "Filialsiz"]
        br["cnt"] += 1
        br["sum"] += amt
        br["people"].add(f.get("employee_user_id"))
        reason = (f.get("reason") or "-").strip()
        rs = by_reason[" ".join(reason.lower().split())]
        rs["cnt"] += 1
        rs["sum"] += amt
        rs["text"] = rs["text"] or reason
        src = by_source.setdefault(f.get("source") or "finance", [0, 0])
        src[0] += 1
        src[1] += amt

    top_emp = max(by_emp.values(), key=lambda e: (e["sum"], e["cnt"]), default=None)
    n_months = len(periods)
    period_text = (period_label(periods[0]) if n_months == 1
                   else f"{period_label(periods[0])} — {period_label(periods[-1])}")
    if generated_at is None:
        from utils import now_tk
        generated_at = now_tk().strftime("%d.%m.%Y %H:%M")

    wb = Workbook()

    # ================= 1-VARAQ: JARIMALAR =================
    ws = wb.active
    ws.title = "Jarimalar"
    ws.sheet_view.showGridLines = False
    headers = ["№", "Sana", "Ism-familiya", "Lavozim", "Filial",
               "Jarima summasi", "Jarima sababi", "Kim yozgan", "Holat"]
    ncols = len(headers)
    last = get_column_letter(ncols)
    for i, w in enumerate([6, 18, 30, 22, 24, 20, 46, 26, 16], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    banner(ws, 1, last, "GULNORA FARM — JARIMALAR HISOBOTI", size=18, height=40)
    subtitle(ws, 2, last, f"Davr: {period_text}  ({n_months} oylik)      |      "
                          f"Tayyorlangan: {generated_at}")

    # ---- Statistika kartochkalari (2 qator × 4 ta) ----
    card_spans = [(1, 3), (4, 5), (6, 7), (8, 9)]

    def card_row(top_row, cards):
        for (c1, c2), (label, value, color, fmt, vsize) in zip(card_spans, cards):
            ws.merge_cells(start_row=top_row, start_column=c1, end_row=top_row, end_column=c2)
            ws.merge_cells(start_row=top_row + 1, start_column=c1,
                           end_row=top_row + 1, end_column=c2)
            lc = ws.cell(row=top_row, column=c1, value=label)
            lc.font = Font(bold=True, color=GREY, size=10)
            lc.alignment = center
            vc = ws.cell(row=top_row + 1, column=c1, value=value)
            vc.font = Font(bold=True, color=color, size=vsize)
            vc.alignment = center
            if fmt:
                vc.number_format = fmt
            accent = Side(style="thick", color=color)
            for col in range(c1, c2 + 1):
                for rr in (top_row, top_row + 1):
                    cell = ws.cell(row=rr, column=col)
                    cell.fill = fill(GREY_LIGHT)
                    cell.border = Border(
                        left=accent if col == c1 else None,
                        right=thin if col == c2 else None,
                        top=thin if rr == top_row else None,
                        bottom=thin if rr == top_row + 1 else None,
                    )
        ws.row_dimensions[top_row].height = 20
        ws.row_dimensions[top_row + 1].height = 32

    card_row(4, [
        ("JAMI JARIMALAR SONI", f"{len(active)} ta", GREEN_DARK, None, 18),
        ("JAMI JARIMA SUMMASI", total_sum, RED, money_fmt, 18),
        ("JARIMALANGAN XODIMLAR", f"{len(people)} nafar", "1565C0", None, 18),
        ("O'RTACHA JARIMA", avg, "E65100", money_fmt, 18),
    ])
    card_row(7, [
        ("BEKOR QILINGAN", f"{len(cancelled)} ta · {_som(cancelled_sum)}", GREY, None, 12),
        ("ENG KO'P JARIMA OLGAN",
         f"{top_emp['name']} ({top_emp['cnt']} ta)" if top_emp else "—", RED, None, 12),
        ("HR YOZGAN", f"{by_source['hr'][0]} ta · {_som(by_source['hr'][1])}",
         "1565C0", None, 12),
        ("MOLIYA YOZGAN",
         f"{by_source['finance'][0]} ta · {_som(by_source['finance'][1])}",
         "6A1B9A", None, 12),
    ])

    # ---- Jadval ----
    head_row = 10
    header(ws, head_row, headers)
    src_names = {"hr": "HR", "finance": "Moliya"}
    row_i = head_row
    for idx, f in enumerate(fines, start=1):
        row_i = head_row + idx
        is_cancel = bool(f.get("cancelled"))
        who = src_names.get(f.get("source"), f.get("source") or "-")
        if f.get("created_by_name"):
            who += f": {f['created_by_name']}"
        values = [
            idx, _fine_date(f), f.get("employee_name") or "-", _fine_position(f),
            f.get("branch_name") or "-", _fine_amount(f),
            (f.get("reason") or "-").strip(), who,
            "Bekor qilingan" if is_cancel else "Faol",
        ]
        for col_i, val in enumerate(values, start=1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.border = border
            cell.alignment = center if col_i in (1, 2, 9) else left
            if idx % 2 == 0:
                cell.fill = fill(GREEN_LIGHT)
            if is_cancel:
                cell.font = Font(color="9E9E9E", italic=True)
        amt_cell = ws.cell(row=row_i, column=6)
        amt_cell.number_format = money_fmt
        amt_cell.alignment = right
        amt_cell.font = (Font(color="9E9E9E", italic=True, strike=True) if is_cancel
                         else Font(bold=True, color=RED))
        st = ws.cell(row=row_i, column=9)
        st.fill = fill("EEEEEE" if is_cancel else RED_LIGHT)
        st.font = Font(bold=True, color="9E9E9E" if is_cancel else RED)
        ws.row_dimensions[row_i].height = 20

    if not fines:
        row_i = head_row + 1
        ws.merge_cells(f"A{row_i}:{last}{row_i}")
        c = ws[f"A{row_i}"]
        c.value = "Bu davrda jarimalar yozilmagan"
        c.font = Font(italic=True, color=GREY, size=12)
        c.alignment = center
        ws.row_dimensions[row_i].height = 30
    else:
        ws.auto_filter.ref = f"A{head_row}:{last}{row_i}"
        # Jami qatori — faqat «Faol» holatdagi jarimalar summasi (jonli formula)
        total_row = row_i + 1
        total_line(ws, total_row, ["JAMI (faol jarimalar):", "", "", "", "",
                                   f'=SUMIF(I{head_row + 1}:I{row_i},"Faol",'
                                   f'F{head_row + 1}:F{row_i})',
                                   "", "", f"{len(active)} ta"], money_cols=(6,))
        ws.merge_cells(f"A{total_row}:E{total_row}")
        ws[f"A{total_row}"].alignment = Alignment(horizontal="right", vertical="center")

    ws.freeze_panes = f"A{head_row + 1}"
    ws.print_title_rows = f"{head_row}:{head_row}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    # ================= 2-VARAQ: STATISTIKA =================
    sw = wb.create_sheet("Statistika")
    sw.sheet_view.showGridLines = False
    SN = 7  # ustunlar soni
    for i, w in enumerate([6, 30, 22, 24, 14, 20, 14], start=1):
        sw.column_dimensions[get_column_letter(i)].width = w
    banner(sw, 1, "G", "JARIMALAR STATISTIKASI", size=16)
    subtitle(sw, 2, "G", f"Davr: {period_text}  ({n_months} oylik)")

    # --- Oylar bo'yicha (+ diagramma) ---
    r = 4
    section_title(sw, r, SN, "Oylar bo'yicha")
    header(sw, r + 1, ["№", "Oy", "Jarimalar soni", "Jarima summasi",
                       "Bekor qil.", "Bekor summa", "Xodimlar"])
    month_list = sorted(by_month)
    m_first = r + 2
    m_last = data_rows(sw, m_first, [
        [i, period_label(p), by_month[p]["cnt"], by_month[p]["sum"],
         by_month[p]["ccnt"], by_month[p]["csum"], len(by_month[p]["people"])]
        for i, p in enumerate(month_list, start=1)
    ], money_cols=(4, 6), center_cols=(1, 3, 5, 7))
    total_line(sw, m_last + 1, ["", "JAMI", len(active), total_sum,
                                len(cancelled), cancelled_sum, len(people)],
               money_cols=(4, 6))

    if month_list and total_sum:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Oylar bo'yicha jarima summasi (so'm)"
        chart.y_axis.numFmt = "#,##0"
        chart.y_axis.majorGridlines = None
        chart.legend = None
        chart.add_data(Reference(sw, min_col=4, min_row=m_first - 1, max_row=m_last),
                       titles_from_data=True)
        chart.set_categories(Reference(sw, min_col=2, min_row=m_first, max_row=m_last))
        series = chart.series[0]
        series.graphicalProperties.solidFill = RED
        series.graphicalProperties.line.solidFill = RED
        series.dLbls = DataLabelList()
        series.dLbls.showVal = True
        series.dLbls.showSerName = False
        series.dLbls.showCatName = False
        series.dLbls.showLegendKey = False
        series.dLbls.numFmt = "#,##0"
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart.height = 8
        chart.width = 17
        sw.add_chart(chart, "I4")

    # --- Filiallar bo'yicha ---
    r = m_last + 4
    section_title(sw, r, 6, "Filiallar bo'yicha")
    header(sw, r + 1, ["№", "Filial", "Jarimalar soni", "Jarima summasi",
                       "Xodimlar", "Ulushi", None])
    br_rows = sorted(by_branch.items(), key=lambda kv: (-kv[1]["sum"], kv[0]))
    b_last = data_rows(sw, r + 2, [
        [i, name, v["cnt"], v["sum"], len(v["people"]),
         (v["sum"] / total_sum) if total_sum else 0]
        for i, (name, v) in enumerate(br_rows, start=1)
    ], money_cols=(4,), center_cols=(1, 3, 5, 6))
    for rr in range(r + 2, b_last + 1):
        sw.cell(row=rr, column=6).number_format = "0.0%"
    if br_rows:
        b_last += 1
        total_line(sw, b_last, ["", "JAMI", len(active), total_sum,
                                len(people), 1 if total_sum else 0], money_cols=(4,))
        sw.cell(row=b_last, column=6).number_format = "0%"

    # --- Xodimlar reytingi ---
    r = max(b_last, r + 1) + 3
    section_title(sw, r, 6, "Eng ko'p jarima olgan xodimlar (TOP 15)")
    header(sw, r + 1, ["№", "Ism-familiya", "Lavozim", "Filial",
                       "Soni", "Jami summa", None])
    emp_rows = sorted(by_emp.values(), key=lambda e: (-e["sum"], -e["cnt"]))[:15]
    e_last = data_rows(sw, r + 2, [
        [i, e["name"], e["pos"], e["branch"], e["cnt"], e["sum"]]
        for i, e in enumerate(emp_rows, start=1)
    ], money_cols=(6,), center_cols=(1, 5))
    for k, color in enumerate(("FFD54F", "E0E0E0", "FFCC80")):  # oltin/kumush/bronza
        if k < len(emp_rows):
            medal = sw.cell(row=r + 2 + k, column=1)
            medal.fill = fill(color)
            medal.font = Font(bold=True)

    # --- Sabablar bo'yicha ---
    r = max(e_last, r + 1) + 3
    section_title(sw, r, 6, "Jarima sabablari (TOP 10)")
    header(sw, r + 1, ["№", "Sabab", None, None, "Soni", "Jami summa", None])
    sw.merge_cells(start_row=r + 1, start_column=2, end_row=r + 1, end_column=4)
    reason_rows = sorted(by_reason.values(), key=lambda v: (-v["cnt"], -v["sum"]))[:10]
    s_last = data_rows(sw, r + 2, [
        [i, v["text"], None, None, v["cnt"], v["sum"]]
        for i, v in enumerate(reason_rows, start=1)
    ], money_cols=(6,), center_cols=(1, 5))
    for rr in range(r + 2, s_last + 1):
        sw.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=4)

    sw.page_setup.orientation = "portrait"
    sw.sheet_properties.pageSetUpPr.fitToPage = True
    sw.page_setup.fitToWidth = 1
    sw.page_setup.fitToHeight = 0

    return _finish(wb, f"jarimalar_{n_months}oylik")
