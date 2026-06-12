"""RBAC 演示 Client — 管理员 managerQwenpaw（全部权限）。"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://localhost:3000/mcp"
TOKEN_FILE = ROOT / "jwt" / "managerQwenpaw.key"


def read_token(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


async def run(url: str, token_path: Path) -> None:
    headers = {"Authorization": f"Bearer {read_token(token_path)}"}
    print("=" * 64)
    print("角色: managerQwenpaw（管理员）")
    print(f"Gateway: {url}")
    print("=" * 64)

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"\n[List Tools] 可见 {len(tools)} 个工具:")
            for name in sorted(tools):
                print(f"  - {name}")

            print("\n[OK] 读取员工信息 hr_get_employee（无参数，返回全部 4 条）")
            hr = await session.call_tool("hr_get_employee", arguments={})
            print(hr.content[0].text if hr.content else hr)

            print("\n[OK] 读取论坛 forum_list_posts")
            posts = await session.call_tool("forum_list_posts", arguments={"limit": 3})
            print(posts.content[0].text if posts.content else posts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--token", type=Path, default=TOKEN_FILE)
    args = parser.parse_args()
    asyncio.run(run(args.url, args.token))


if __name__ == "__main__":
    main()
