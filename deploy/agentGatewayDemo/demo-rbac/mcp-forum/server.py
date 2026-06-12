"""MCP 论坛服务 — 读帖 / 发帖 / 删帖。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9002
DEFAULT_PATH = "/mcp"
DATA_FILE = Path(__file__).resolve().parent / "posts.json"


def load_posts() -> list[dict]:
    if DATA_FILE.is_file():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def save_posts(posts: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")


def create_server(host: str, port: int, path: str) -> FastMCP:
    return FastMCP("Forum MCP Server", host=host, port=port, streamable_http_path=path)


def register_handlers(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_posts(limit: int = 10) -> str:
        """读取论坛帖子列表。"""
        posts = load_posts()[: max(1, min(limit, 50))]
        if not posts:
            return "（暂无帖子）"
        lines = []
        for p in posts:
            lines.append(f"[{p['id']}] {p['author']}: {p['title']} — {p['content'][:40]}")
        return "\n".join(lines)

    @mcp.tool()
    def create_post(title: str, content: str, author: str = "anonymous") -> str:
        """发布新帖。"""
        posts = load_posts()
        post_id = f"P{len(posts) + 1:04d}"
        posts.insert(
            0,
            {
                "id": post_id,
                "title": title,
                "content": content,
                "author": author,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        save_posts(posts)
        return f"发帖成功 id={post_id} title={title}"

    @mcp.tool()
    def delete_post(post_id: str) -> str:
        """删除指定帖子（管理员操作）。"""
        posts = load_posts()
        new_posts = [p for p in posts if p["id"] != post_id]
        if len(new_posts) == len(posts):
            return f"未找到帖子: {post_id}"
        save_posts(new_posts)
        return f"已删除帖子 {post_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forum MCP Server")
    parser.add_argument("--host", default=os.getenv("MCP_FORUM_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_FORUM_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--path", default=os.getenv("MCP_FORUM_PATH", DEFAULT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mcp = create_server(args.host, args.port, args.path)
    register_handlers(mcp)
    url = f"http://{args.host}:{args.port}{args.path}"
    print("Forum MCP Server (论坛)")
    print(f"  URL: {url}")
    print("  工具: list_posts, create_post, delete_post")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
