# conftest.py — 共享 fixtures 和 BDD 配置
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "src")

# 显式注入仓库根目录和 src/，避免依赖外部 editable install。
sys.path.insert(0, ROOT)
sys.path.insert(0, SRC)
