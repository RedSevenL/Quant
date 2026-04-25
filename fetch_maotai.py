from data_loader import StockDataLoader


def get_stock_data(symbol, start_date="20240101"):  # symbol: 股票代码
    # 兼容旧调用入口：内部转调新的类实现。
    loader = StockDataLoader(data_dir="data")
    return loader.get_data(symbol=symbol, start_date=start_date)

if __name__ == "__main__":
    maotai_df = get_stock_data("600519", start_date="20240101")
    print(maotai_df.info())
    print(maotai_df.head())