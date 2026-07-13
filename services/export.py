"""Excel (.xlsx) hisobotlarni tayyorlash."""
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from aiogram.types import BufferedInputFile

from database.db import STATUS_LABELS

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
        "Forma", "Kutilayotgan maosh", "Sana",
    ]
    uniform = {"yes": "Bor", "no": "Yo'q"}
    rows = []
    for a in apps:
        rows.append([
            a.get("id"),
            a.get("full_name") or "-",
            a.get("vacancy_title") or a.get("position") or "-",
            a.get("branch_name") or "-",
            STATUS_LABELS.get(a.get("status"), a.get("status") or "-"),
            a.get("phone") or "-",
            a.get("city") or "-",
            a.get("district") or "-",
            a.get("birth_date") or "-",
            a.get("education") or "-",
            a.get("exp_years") or "-",
            uniform.get(a.get("uniform_status"), "Noma'lum"),
            a.get("expected_salary") or "-",
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

    headers = ["№", "Ism-familiya", "Karta raqami", "Filial", "Lavozim", "Telefon"]
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
        values = [
            idx,
            r.get("full_name") or "-",
            r.get("card_number") or "-",
            r.get("branch_name") or "-",
            r.get("position") or "-",
            r.get("phone") or "-",
        ]
        for col_i, val in enumerate(values, start=1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.border = border
            cell.alignment = center if col_i in (1,) else left
            if idx % 2 == 0:
                cell.fill = alt_fill
        # karta raqami matn sifatida (raqam formatlanmasin)
        ws.cell(row=row_i, column=3).number_format = "@"

    # Ustun kengliklari
    widths = [6, 28, 24, 26, 20, 18]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = f"A{header_row + 1}"
    return _finish(wb, f"avans_{period}")


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
