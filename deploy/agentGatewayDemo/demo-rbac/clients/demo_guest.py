"""RBAC 演示 Client — 无 Token 游客（仅论坛读）。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = "http://localhost:3000/mcp"
FORUM_READ_TOOL = "forum_list_posts"
FORUM_WRITE_TOOL = "forum_create_post"


def _is_gateway_block(exc: BaseException) -> bool:
    parts: list[str] = [str(exc)]
    if isinstance(exc, BaseExceptionGroup):
        parts.extend(str(e) for e in exc.exceptions)
    combined = " ".join(parts)
    return any(k in combined for k in ("Unknown tool", "400", "403", "401", "Forbidden"))


async def run(url: str) -> int:
    print("=" * 64)
    print("角色: 游客（无 Authorization Token）")
    print(f"Gateway: {url}")
    print("=" * 64)

    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("\n[OK] MCP 握手完成（未携带 JWT）")

                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"\n[List Tools] 可见 {len(tools)} 个工具:")
                for name in tools:
                    print(f"  - {name}")

                if set(tools) == {FORUM_READ_TOOL}:
                    print("\n[OK] RBAC：游客仅论坛读权限")
                else:
                    print(f"\n[WARN] 预期仅 {FORUM_READ_TOOL}，实际 {set(tools)}")

                print(f"\n[合法] 调用 {FORUM_READ_TOOL}")
                ok = await session.call_tool(FORUM_READ_TOOL, arguments={"limit": 3})
                print(ok.content[0].text if ok.content else ok)

                print(f"\n[越权测试] 调用 {FORUM_WRITE_TOOL}（应被拒绝）")
                blocked = False
                try:
                    await session.call_tool(
                        FORUM_WRITE_TOOL,
                        arguments={"author": "guest", "title": "x", "content": "y"},
                    )
                    print("  [FAIL] 未被拦截")
                    return 1
                except BaseException as exc:
                    if _is_gateway_block(exc):
                        blocked = True
                        print("  [BLOCKED] 网关拦截（游客无发帖权限）")
                    else:
                        print(f"  [ERROR] 意外失败: {exc}")
                        return 1

                return 0 if blocked else 1
    except BaseException as exc:
        if _is_gateway_block(exc):
            print("\n[BLOCKED] 网关拦截（会话层）")
            return 0
        raise

    return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.url)))


if __name__ == "__main__":
    main()
