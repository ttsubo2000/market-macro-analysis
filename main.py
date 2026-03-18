import argparse
import logging
import os
import sys
import sqlite3
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from market_macro_analysis.exceptions import MacroAnalysisError
from market_macro_analysis.config import DB_NAME, COMMAND_LOG_PATH
from market_macro_analysis.controller import fetch_controller, chart_controller, report_controller

STAGE_TYPES = [
    "fetch_data",
    "make_chart",
    "make_report",
]

BLOCK_TYPES = [
    "all",
    "financial",
    "economic",
    "price",
]


def stage_action(stage_type, block_type):
    with sqlite3.connect(DB_NAME, isolation_level=None) as conn_db:
        if stage_type == "fetch_data":
            if block_type in ("all", "price"):
                fetch_controller.fetch_price_data(conn_db)
            if block_type in ("all", "financial"):
                fetch_controller.fetch_financial_data(conn_db)
            if block_type in ("all", "economic"):
                fetch_controller.fetch_economic_data(conn_db)
        elif stage_type == "make_chart":
            chart_controller.make_chart(conn_db, block_type)
        elif stage_type == "make_report":
            report_controller.make_report(conn_db, block_type)
        else:
            raise ValueError(f"Invalid stage_type: {stage_type}")


def setup_command_logger():
    log_dir = os.path.dirname(COMMAND_LOG_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        COMMAND_LOG_PATH,
        maxBytes=1 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("command_history")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger


def log_command(logger, stage_type, block_type, status, elapsed):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{ts} | {stage_type} | {block_type} | {status} | {elapsed}s")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="日銀マクロ経済モニタリング＆予測ツール"
    )
    parser.add_argument(
        "stage_type",
        choices=STAGE_TYPES,
        help="実行するステージの種別",
    )
    parser.add_argument(
        "block_type",
        choices=BLOCK_TYPES,
        help="分析対象のブロック種別",
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()
    logger = setup_command_logger()
    start = time.time()
    exit_code = 0
    status = "FAILED"

    try:
        stage_action(args.stage_type, args.block_type)
        status = "SUCCESS"
    except MacroAnalysisError as e:
        print(f"エラーが発生しました: {e}")
        exit_code = 1
    finally:
        log_command(logger, args.stage_type, args.block_type, status, int(time.time() - start))

    sys.exit(exit_code)
