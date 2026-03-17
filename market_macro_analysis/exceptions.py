class MacroAnalysisError(Exception):
    """market-macro-analysis の基底例外クラス"""
    pass


class FetchError(MacroAnalysisError):
    """データ取得失敗"""
    pass


class DataStoreError(MacroAnalysisError):
    """DB操作失敗"""
    pass


class ChartError(MacroAnalysisError):
    """チャート生成失敗"""
    pass


class ReportError(MacroAnalysisError):
    """レポート生成失敗"""
    pass
