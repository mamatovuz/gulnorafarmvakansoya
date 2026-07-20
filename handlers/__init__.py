"""Barcha routerlarni ro'yxatga olish."""
from aiogram import Dispatcher
from handlers import (
    common, candidate, hr, admin, staff, staffreg, attendance, accountant,
    dayoff, positions, advance, it, salaryraise, dayoff_plan,
)


def register_all(dp: Dispatcher):
    dp.include_router(common.router)
    dp.include_router(candidate.router)
    dp.include_router(hr.router)
    dp.include_router(admin.router)
    dp.include_router(staff.router)
    dp.include_router(staffreg.router)
    dp.include_router(attendance.router)
    dp.include_router(accountant.router)
    dp.include_router(dayoff.router)
    dp.include_router(positions.router)
    dp.include_router(advance.router)
    dp.include_router(it.router)
    dp.include_router(salaryraise.router)
    dp.include_router(dayoff_plan.router)
