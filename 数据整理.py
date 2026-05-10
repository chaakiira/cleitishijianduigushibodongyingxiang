# ============================================================
# 事件研究分析模板 (Event Study - AR / CAR 计算框架)
# ============================================================
import pandas as pd
import numpy as np
from datetime import timedelta

# 1. 读入事件表
df_events = pd.read_excel("事件整理总表（增强版）.xlsx", sheet_name="事件总表（增强版）")
df_events["发生日期"] = pd.to_datetime(df_events["发生日期"])

# 2. 读入股价数据（示例结构）
# df_prices: columns = ['date', 'ticker', 'close', 'return']
#df_prices = pd.read_csv("stock_prices.csv", parse_dates=["date"])

# 3. 事件研究核心函数
def compute_car(event_date, ticker, window_start, window_end,
                estimation_window=120):
    """
    计算单个事件的 AR / CAR
    - 估计期: 事件日前 estimation_window 个交易日
    - 事件窗口: [window_start, window_end] 相对交易日
    """
    stock = df_prices[df_prices['ticker'] == ticker].copy()
    stock = stock.sort_values('date').set_index('date')

    # 找到事件日在时间序列中的位置
    if event_date not in stock.index:
        return None
    event_pos = stock.index.get_loc(event_date)

    # 估计期收益率
    est_start = event_pos - estimation_window
    est_end   = event_pos - 1
    if est_start < 0:
        return None
    est_returns = stock['return'].iloc[est_start:est_end]
    mu = est_returns.mean()          # 预期收益（均值模型）

    # 事件窗口 AR
    win_start = max(0, event_pos + window_start)
    win_end   = min(len(stock), event_pos + window_end + 1)
    window_returns = stock['return'].iloc[win_start:win_end]
    ar = window_returns - mu         # 异常收益 AR
    car = ar.sum()                   # 累积异常收益 CAR

    return {
        'ticker': ticker,
        'event_date': event_date,
        'CAR': round(car, 4),
        'AR_series': ar.values.tolist()
    }

# 4. 批量计算所有事件
results = []
for _, ev in df_events.iterrows():
    # 从'影响公司/行业'列解析股票代码（示例：手动维护映射表）
    ticker = ticker_map.get(ev['事件名称'], None)
    if ticker is None:
        continue
    res = compute_car(
        event_date   = ev['发生日期'],
        ticker       = ticker,
        window_start = ev['窗口开始\n(相对天数)'],
        window_end   = ev['窗口结束\n(相对天数)']
    )
    if res:
        res['影响强度'] = ev['影响强度']
        res['类型']    = ev['类型']
        results.append(res)

df_car = pd.DataFrame(results)

# 5. 分组统计
summary = df_car.groupby('类型')['CAR'].agg(['mean','std','count'])
print(summary)

# 6. 按影响强度分组
by_strength = df_car.groupby('影响强度')['CAR'].mean()
print(by_strength)

# 7. 输出结果
df_car.to_excel("event_study_results.xlsx", index=False)
