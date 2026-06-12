"""RBAC 演示 Client — 普通员工 employeeQwenpaw（含越权攻击步骤）。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://localhost:3000/mcp"
TOKEN_FILE = ROOT / "jwt" / "employeeQwenpaw.key"
FORUM_READ_TOOL = "forum_list_posts"
FORUM_WRITE_TOOL = "forum_create_post"
SENSITIVE_TOOL = "hr_get_employee"
EXPECTED_TOOLS = {FORUM_READ_TOOL, FORUM_WRITE_TOOL}


def read_token(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _is_gateway_block(exc: BaseException) -> bool:
    parts: list[str] = [str(exc)]
    if isinstance(exc, BaseExceptionGroup):
        parts.extend(str(e) for e in exc.exceptions)
    combined = " ".join(parts)
    return any(k in combined for k in ("Unknown tool", "400", "403", "401", "Forbidden"))


async def run(url: str, token_path: Path) -> int:
    headers = {"Authorization": f"Bearer {read_token(token_path)}"}
    print("=" * 64)
    print("角色: employeeQwenpaw（论坛作者 — 读 + 发帖）")
    print(f"Gateway: {url}")
    print("=" * 64)

    try:
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("\n[OK] JWT 认证通过，MCP 握手完成")

                tools = [t.name for t in (await session.list_tools()).tools]
                print(f"\n[List Tools] 可见 {len(tools)} 个工具:")
                for name in tools:
                    print(f"  - {name}")

                if set(tools) == EXPECTED_TOOLS:
                    print("\n[OK] RBAC：论坛读 + 发帖权限")
                else:
                    print(f"\n[WARN] 预期 {EXPECTED_TOOLS}，实际 {set(tools)}")

                print(f"\n[合法] 调用 {FORUM_READ_TOOL}")
                ok = await session.call_tool(FORUM_READ_TOOL, arguments={"limit": 5})
                text = ok.content[0].text if ok.content else str(ok)
                print(text)

                print(f"\n[合法] 调用 {FORUM_WRITE_TOOL}")
                post = await session.call_tool(
                    FORUM_WRITE_TOOL,
                    arguments={
                        "author": "employeeQwenpaw",
                        "title": "RBAC demo post",
                        "content": "Author token can create posts.",
                    },
                )
                print(post.content[0].text if post.content else post)

                print(f"\n[攻击] 越权窃取员工 PII → {SENSITIVE_TOOL}")
                print("  （攻击者从文档得知工具名，List Tools 中不可见）")
                blocked = False
                try:
                    await session.call_tool(SENSITIVE_TOOL, arguments={})
                    print("  [FAIL] 未被拦截，敏感工具返回了数据")
                    return 1
                except BaseException as exc:
                    if _is_gateway_block(exc):
                        blocked = True
                        print("  [BLOCKED] 网关拦截（HTTP/JSON-RPC 拒绝）")
                        print("\n拦截原因: mcpAuthorization — employee 角色无 hr_get_employee 权限")
                    else:
                        print(f"  [ERROR] 意外失败: {exc}")
                        return 1

                return 0 if blocked else 1
    except BaseException as exc:
        if _is_gateway_block(exc):
            print("\n[BLOCKED] 网关拦截（会话层）")
            print("拦截原因: mcpAuthorization — employee 角色无 hr_get_employee 权限")
            return 0
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--token", type=Path, default=TOKEN_FILE)
    args = parser.parse_args()
    if not args.token.is_file():
        print(f"Token 不存在: {args.token}", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(run(args.url, args.token)))


if __name__ == "__main__":
    main()
