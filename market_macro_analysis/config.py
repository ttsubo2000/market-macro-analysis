import os
import tomllib
from pathlib import Path

# Database
DB_NAME = os.environ.get("MACRO_ANALYSIS_DB_NAME", "macro_analysis.db")

# Output paths
REPORT_DIR = os.environ.get("MACRO_ANALYSIS_REPORT_DIR", "report/")
REPORT_PNG_DIR = os.environ.get("MACRO_ANALYSIS_REPORT_PNG_DIR", "report/png/")

# Log directory
LOG_DIR = os.environ.get("MACRO_ANALYSIS_LOG_DIR", "logs/")
COMMAND_LOG_PATH = os.environ.get("MACRO_ANALYSIS_COMMAND_LOG_PATH", "logs/command_history.log")

# API config
ESTAT_API_CONFIG_PATH = os.environ.get("ESTAT_API_CONFIG_PATH", "estat-api.toml")

# API endpoints
ESTAT_API_BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app"
BOJ_STATS_BASE_URL = "https://www.stat-search.boj.or.jp"
BOJ_CALL_RATE_CSV_URL = "https://www.stat-search.boj.or.jp/ssi/mtshtml/csv/fm02_m_1.csv"
CAO_GDP_INDEX_URL = "https://www5.cao.go.jp/keizai3/getsurei/getsurei-index.html"

# e-Stat 統計ID
ESTAT_CPI_STATS_DATA_ID = "0003427113"       # 2020年基準消費者物価指数
ESTAT_CPI_CAT01_CORE = "0161"                # 生鮮食品を除く総合（コアCPI）
ESTAT_CPI_TAB_YOY = "3"                      # 前年同月比
ESTAT_CPI_AREA_NATIONAL = "00000"            # 全国

MHLW_WAGE_STATS_DATA_ID = "0003138254"       # 毎月勤労統計調査：就業形態別所定内給与 指数及び増減率

BEI_URL = "https://stock-marketdata.com/bei.html"

# Retry settings
MAX_RETRY_COUNT = 3
RETRY_WAIT_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 30


def load_estat_api_key(config_path: str = ESTAT_API_CONFIG_PATH) -> str:
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    return config["estat-api"]["app_id"]
