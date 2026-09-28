#!/usr/bin/env python3
"""SocialRadar 自动同步与部署脚本 (本地 -> 阿里云)."""

import os
import sys
import subprocess
import tempfile
import tarfile
from pathlib import Path

REMOTE_HOST = os.environ.get("ALIYUN_HOST", "aliyun")
REMOTE_DIR = os.environ.get("ALIYUN_DIR", "/root/social_radar")

INCLUDE_ITEMS = [
    "radar",
    "config",
    "deploy",
    "tests",
    "run.py",
    "requirements.txt",
    "README.md"
]

EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "venv",
    "config.yaml",  # 保护服务器上的真实配置与热更新 Cookie 不被本地模板覆盖
    "data"  # 保护服务器已记录的 SQLite 数据库不被覆盖
}


def should_exclude(tarinfo: tarfile.TarInfo) -> bool:
    parts = Path(tarinfo.name).parts
    for p in parts:
        if p in EXCLUDE_PATTERNS or p.endswith(".pyc"):
            return True
    return False


def main():
    print("=" * 60)
    print(f"🚀 SocialRadar 本地代码同步 -> 阿里云服务器 ({REMOTE_HOST})")
    print("=" * 60)

    base_dir = Path(__file__).resolve().parent

    print(f"[*] 检查与远程主机 [{REMOTE_HOST}] 的连接...")
    test_cmd = ["ssh", "-o", "ConnectTimeout=5", REMOTE_HOST, "echo OK"]
    try:
        res = subprocess.run(test_cmd, capture_output=True, text=True, check=True)
        if "OK" not in res.stdout:
            raise RuntimeError("SSH 握手返回异常")
        print("    SSH 连接畅通！")
    except Exception as e:
        print(f"\n[错误] 无法连接到远程主机 {REMOTE_HOST}: {e}")
        sys.exit(1)

    print(f"[*] 确保远程目录存在: {REMOTE_DIR}")
    subprocess.run(["ssh", REMOTE_HOST, f"mkdir -p {REMOTE_DIR}"], check=True)

    print("[*] 正在打包本地代码增量 (自动排除缓存与本地数据库)...")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_tar_path = tmp.name

    try:
        with tarfile.open(tmp_tar_path, "w:gz") as tar:
            for item in INCLUDE_ITEMS:
                full_path = base_dir / item
                if full_path.exists():
                    tar.add(str(full_path), arcname=item, filter=lambda ti: None if should_exclude(ti) else ti)

        print(f"[*] 正在推送更新至 {REMOTE_HOST}:{REMOTE_DIR} ...")
        with open(tmp_tar_path, "rb") as f:
            proc = subprocess.Popen(
                ["ssh", REMOTE_HOST, f"tar -xzf - -C {REMOTE_DIR}"],
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                print(f"[错误] 解压推送失败: {stderr.decode()}")
                sys.exit(1)

        print("    代码同步完成！")

    finally:
        if os.path.exists(tmp_tar_path):
            try:
                os.remove(tmp_tar_path)
            except Exception:
                pass

    # 注册或重启服务
    print("[*] 配置并重启远程 social_radar 服务...")
    setup_cmd = (
        "cp /root/social_radar/deploy/social_radar.service /etc/systemd/system/ && "
        "systemctl daemon-reload && "
        "systemctl enable --now social_radar && "
        "systemctl restart social_radar"
    )
    subprocess.run(["ssh", REMOTE_HOST, setup_cmd], check=True)
    print("🎉 [成功] 阿里云上的 SocialRadar 服务已启动并载入最新代码！")

    print("=" * 60)
    print("✅ 一键同步完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
