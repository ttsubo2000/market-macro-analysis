"""
E2E テスト用 conftest.py

重要: env var のセットはモジュールレベルで行う。
     テストファイルの import より前に実行されるため、
     config.py の DB_NAME 等が正しくオーバーライドされる。
"""
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# ── モジュールレベル: E2E 用一時ディレクトリを作成し env var をセット ──
_E2E_TMPDIR = Path(tempfile.mkdtemp(prefix="macro_analysis_e2e_"))
_E2E_DB_PATH = _E2E_TMPDIR / "e2e_test.db"
_E2E_REPORT_DIR = str(_E2E_TMPDIR / "report") + "/"
_E2E_PNG_DIR = str(_E2E_TMPDIR / "report" / "png") + "/"

(_E2E_TMPDIR / "report" / "png").mkdir(parents=True)

os.environ["MACRO_ANALYSIS_DB_NAME"] = str(_E2E_DB_PATH)
os.environ["MACRO_ANALYSIS_REPORT_DIR"] = _E2E_REPORT_DIR
os.environ["MACRO_ANALYSIS_REPORT_PNG_DIR"] = _E2E_PNG_DIR


def _has_estat_toml() -> bool:
    return Path("estat-api.toml").exists()


# ── Fixtures ──

@pytest.fixture(scope="session")
def require_estat():
    """estat-api.toml が存在しない場合はスキップ"""
    if not _has_estat_toml():
        pytest.skip("estat-api.toml が存在しないため E2E テストをスキップ")


@pytest.fixture(scope="session")
def e2e_db(require_estat):
    """E2E 用 SQLite 接続（セッション共有）"""
    conn = sqlite3.connect(str(_E2E_DB_PATH), isolation_level=None)
    print(f"\n[E2E] DB パス       : {_E2E_DB_PATH}")
    print(f"[E2E] レポート出力先: {_E2E_REPORT_DIR}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def e2e_tmp(require_estat):
    """E2E 用一時ディレクトリ（セッション共有）"""
    return _E2E_TMPDIR
