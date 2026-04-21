import os
os.environ['no_proxy'] = '*'
import time
import akshare as ak
import pandas as pd

def get_stock_data(symbol, start_date='20240101'):
    data_dir = "data"
    cache_file = os.path.join(data_dir, f"{symbol}.csv")

    if os.path.exists(cache_file):
        print(f"[缓存] 发现本地缓存，直接读取: {cache_file}")
        cached_df = pd.read_csv(cache_file)
        if 'date' in cached_df.columns:
            cached_df['date'] = pd.to_datetime(cached_df['date'])
        return cached_df

    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"[目录] 创建数据目录: {data_dir}")

    print(f"[网络] 本地无缓存，开始请求股票数据: {symbol}")
    # 获取指定股票的日线历史数据
    last_error = None
    df = None
    for attempt in range(1, 4):
        try:
            print(f"[网络] 第 {attempt}/3 次请求...")
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=pd.Timestamp.now().strftime("%Y%m%d"),
                adjust="qfq"
            )
            print("[网络] 请求成功")
            break
        except Exception as e:
            last_error = e
            print(f"[重试] 第 {attempt}/3 次请求失败: {e}")
            if attempt < 3:
                print("[重试] 2 秒后重试...")
                time.sleep(2)

    if df is None:
        raise RuntimeError(f"请求股票数据失败（已重试 3 次）: {last_error}")
    # 中文列名到英文的映射
    col_map = {
        '日期': 'date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'turnover',
        '振幅': 'amplitude',
        '涨跌幅': 'pct_chg',
        '涨跌额': 'chg',
        '换手率': 'turnover_rate',
    }
    # 重命名列
    df = df.rename(columns=col_map)
    # 股票代码列也要处理为英文
    if '股票代码' in df.columns:
        df = df.rename(columns={'股票代码': 'code'})
    # 日期格式化
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    # 只保留需要的列
    cols_to_keep = ['date', 'code', 'open', 'close', 'high', 'low', 'volume']
    existing_cols = [col for col in cols_to_keep if col in df.columns]
    df = df.loc[:, existing_cols]

    print(f"[缓存] 保存数据到本地: {cache_file}")
    df.to_csv(cache_file, index=False)
    return df

if __name__ == "__main__":
    maotai_df = get_stock_data('600519', start_date='20240101')
    print(maotai_df.info())
    print(maotai_df.head())