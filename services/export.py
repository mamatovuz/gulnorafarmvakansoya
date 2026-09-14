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
