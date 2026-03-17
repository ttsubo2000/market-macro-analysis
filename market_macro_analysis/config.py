import os

# Database
DB_NAME = os.environ.get("MACRO_ANALYSIS_DB_NAME", "macro_analysis.db")

# Output paths
REPORT_DIR = os.environ.get("MACRO_ANALYSIS_REPORT_DIR", "report/")
REPORT_PNG_DIR = os.environ.get("MACRO_ANALYSIS_REPORT_PNG_DIR", "report/png/")

# Log directory
LOG_DIR = os.environ.get("MACRO_ANALYSIS_LOG_DIR", "logs/")
COMMAND_LOG_PATH = os.environ.get("MACRO_ANALYSIS_COMMAND_LOG_PATH", "logs/command_history.log")

# API endpoints
BOJ_STATS_BASE_URL = "https://www.stat-search.boj.or.jp"
ESTAT_API_BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app"
CAO_GDP_URL = "https://www5.cao.go.jp/keizai3/getsurei/gap.html"

# Retry settings
MAX_RETRY_COUNT = 3
RETRY_WAIT_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 30
