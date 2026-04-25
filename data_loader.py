import os
import time
import warnings
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd

os.environ["no_proxy"] = "*"


class StockDataLoader:
    def __init__(self, data_dir: str = "data") -> None:
        """初始化数据目录，所有股票缓存 CSV 都存放在这里。"""
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def get_data(self, symbol: str, start_date: str = "20240101") -> pd.DataFrame:
        """
        获取股票数据（优先缓存，必要时增量更新）。

        逻辑：
        1) 缓存不存在 -> 直接网络抓取并缓存。
        2) 缓存存在 -> 判断最后交易日是否过期；过期则尝试增量更新。
        3) 更新失败 -> 返回已有缓存并给出 warning，避免程序崩溃。
        """
        cache_file = os.path.join(self.data_dir, f"{symbol}.csv")
        cached_df = pd.DataFrame()

        # 第一步：优先读取本地缓存，读取失败时退化为重新抓取。
        if os.path.exists(cache_file):
            try:
                cached_df = pd.read_csv(cache_file)
                cached_df = self._clean_data(cached_df, symbol=symbol)
            except Exception as exc:
                warnings.warn(f"读取缓存失败，将尝试重新抓取。原因: {exc}", RuntimeWarning)
                cached_df = pd.DataFrame()
        else:
            return self._fetch_and_cache(symbol=symbol, start_date=start_date, cache_file=cache_file)

        if cached_df.empty:
            return self._fetch_and_cache(symbol=symbol, start_date=start_date, cache_file=cache_file)

        # 第二步：检查“数据新鲜度”，判断是否需要更新。
        last_cached_date = cached_df["date"].max()
        expected_latest_trade_date = self._get_expected_latest_trade_date()

        if last_cached_date < expected_latest_trade_date:
            # 增量更新从“最后一条缓存日期 + 1天”开始抓，避免重复全量拉取。
            incremental_start = (last_cached_date + timedelta(days=1)).strftime("%Y%m%d")
            try:
                latest_df = self._fetch_from_network(symbol=symbol, start_date=incremental_start)
                latest_df = self._clean_data(latest_df, symbol=symbol)
                if not latest_df.empty:
                    # 合并后再走一次统一清洗，确保去重、排序和类型一致。
                    merged_df = pd.concat([cached_df, latest_df], ignore_index=True)
                    merged_df = self._clean_data(merged_df, symbol=symbol)
                    merged_df.to_csv(cache_file, index=False)
                    return merged_df
            except Exception as exc:
                warnings.warn(
                    f"增量更新失败，返回本地缓存。原因: {exc}",
                    RuntimeWarning,
                )
                return cached_df

        return cached_df

    def _fetch_and_cache(self, symbol: str, start_date: str, cache_file: str) -> pd.DataFrame:
        """网络抓取 + 清洗 + 缓存保存的一次性流程。"""
        try:
            df = self._fetch_from_network(symbol=symbol, start_date=start_date)
            df = self._clean_data(df, symbol=symbol)
            if not df.empty:
                df.to_csv(cache_file, index=False)
            return df
        except Exception as exc:
            warnings.warn(f"网络抓取失败且无可用缓存，返回空数据。原因: {exc}", RuntimeWarning)
            return pd.DataFrame(columns=["date", "code", "open", "close", "high", "low", "volume"])

    def _fetch_from_network(self, symbol: str, start_date: str) -> pd.DataFrame:
        """调用 akshare 抓取数据，内置 3 次重试。"""
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                return ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=pd.Timestamp.now().strftime("%Y%m%d"),
                    adjust="qfq",
                )
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(2)
        raise RuntimeError(f"请求股票数据失败（已重试 3 次）: {last_error}")

    def _clean_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        统一清洗入口：无论数据来自网络还是本地 CSV，都走同样的流程。
        包含列名标准化、类型转换、字段筛选、按日期去重排序。
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "code", "open", "close", "high", "low", "volume"])

        col_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "turnover",
            "振幅": "amplitude",
            "涨跌幅": "pct_chg",
            "涨跌额": "chg",
            "换手率": "turnover_rate",
            "股票代码": "code",
        }
        cleaned = df.rename(columns=col_map).copy()

        if "date" in cleaned.columns:
            cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")

        if "code" not in cleaned.columns:
            cleaned["code"] = symbol

        numeric_cols = ["open", "close", "high", "low", "volume"]
        for col in numeric_cols:
            if col in cleaned.columns:
                cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")

        cols_to_keep = ["date", "code", "open", "close", "high", "low", "volume"]
        existing_cols = [col for col in cols_to_keep if col in cleaned.columns]
        cleaned = cleaned.loc[:, existing_cols]

        if "date" not in cleaned.columns:
            cleaned["date"] = pd.NaT
        if "code" not in cleaned.columns:
            cleaned["code"] = symbol

        cleaned = cleaned.dropna(subset=["date"]).drop_duplicates(subset=["date"]).sort_values("date")
        cleaned = cleaned.reset_index(drop=True)
        return cleaned

    def _get_expected_latest_trade_date(self) -> pd.Timestamp:
        """
        计算“理论上应有的最新交易日”：
        - 15:00 前：视为上一交易日；
        - 15:00 后：视为当天；
        - 周末自动回退到最近工作日。
        """
        now = datetime.now()
        candidate = now.date()
        if now.hour < 15:
            candidate = candidate - timedelta(days=1)

        while candidate.weekday() >= 5:
            candidate = candidate - timedelta(days=1)

        return pd.Timestamp(candidate)


if __name__ == "__main__":
    loader = StockDataLoader(data_dir="data")
    maotai_df = loader.get_data("600519", start_date="20240101")
    print(maotai_df.info())
    print(maotai_df.head())
