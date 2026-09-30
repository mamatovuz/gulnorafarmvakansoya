"""API kalitlarini boshqarish CLI.

  python -m api.manage create-key --name staffora --preset staffora [--expires 2027-12-31]
  python -m api.manage create-key --name admin --scopes admin
  python -m api.manage list-keys
  python -m api.manage revoke-key 3
  python -m api.manage rotate-key 3
  python -m api.manage scopes
"""
import argparse
import asyncio
import sys

from api.security import (SCOPES, STAFFORA_DEFAULT_SCOPES, create_api_key, list_api_keys,
                          public_key, revoke_api_key, rotate_api_key)


async def _main(args):
    from api.migrations import run_migrations
    from config import DB_PATH
    await run_migrations(DB_PATH)
    if args.cmd == "scopes":
        for k, v in SCOPES.items():
            print(f"{k:24} {v}")
    elif args.cmd == "create-key":
        scopes = STAFFORA_DEFAULT_SCOPES if args.preset == "staffora" else []
        if args.scopes:
            scopes = scopes + [s.strip() for s in args.scopes.split(",") if s.strip()]
        if not scopes:
            sys.exit("--scopes yoki --preset staffora kerak")
        expires = f"{args.expires} 23:59:59" if args.expires else None
        row, raw = await create_api_key(args.name, scopes, expires, args.description, "cli")
        print("API kalit yaratildi. SAQLAB QO'YING — qayta ko'rsatilmaydi:\n")
        print(f"  {raw}\n")
        print(f"id={row['id']}  scopes={row['scopes']}  expires={row['expires_at'] or '-'}")
    elif args.cmd == "list-keys":
        for k in await list_api_keys():
            pk = public_key(k)
            state = "REVOKED" if pk["revoked"] else "active"
            print(f"#{pk['id']:<3} {pk['name']:<20} {pk['key_prefix']:<18} {state:<8} "
                  f"last_used={pk['last_used_at'] or '-'}  scopes={' '.join(pk['scopes'])}")
    elif args.cmd == "revoke-key":
        print("Bekor qilindi." if await revoke_api_key(args.id) else "Topilmadi / allaqachon bekor.")
    elif args.cmd == "rotate-key":
        row, raw = await rotate_api_key(args.id)
        if not row:
            sys.exit("Topilmadi.")
        print(f"Yangi kalit (eski ishlamaydi):\n\n  {raw}\n")


def main():
    p = argparse.ArgumentParser(prog="python -m api.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-key")
    c.add_argument("--name", required=True)
    c.add_argument("--scopes", help="vergul bilan: employees:read,branches:read")
    c.add_argument("--preset", choices=["staffora"])
    c.add_argument("--expires", help="YYYY-MM-DD")
    c.add_argument("--description")
    sub.add_parser("list-keys")
    sub.add_parser("scopes")
    for name in ("revoke-key", "rotate-key"):
        s = sub.add_parser(name)
        s.add_argument("id", type=int)
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
