#!/usr/bin/env python3
"""
Trading Signal Performance Tracker
Processes orderbook CSVs, tracks daily performance, calculates metrics,
and generates SL hit CSV with reentry points.
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

ORDERBOOK_DIR = Path('orderbook')
SIGNALS_DIR = Path('signals')
SL_HIT_DIR = Path('sl_hits')
SIGNALS_DIR.mkdir(exist_ok=True)
SL_HIT_DIR.mkdir(exist_ok=True)

def get_candle_data(symbol, start_date, end_date=None):
    """Fetch historical candle data from Yahoo Finance."""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"  Fetching data for {symbol} from {start_date} to {end_date}")
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df = ticker.history(start=start_date, end=end_date, interval='1d')
        if df.empty:
            print(f"    .NS empty, trying without suffix")
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval='1d')
        print(f"    Got {len(df)} rows")
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def calculate_daily_performance(df, entry, sl, tp, direction):
    """Calculate daily max profit, max loss, and check TP/SL hits."""
    if df.empty:
        return []
    
    results = []
    entry_price = float(entry)
    sl_price = float(sl)
    tp_price = float(tp)
    
    for idx, row in df.iterrows():
        date_str = idx.strftime('%Y-%m-%d')
        high = row['High']
        low = row['Low']
        close = row['Close']
        open_price = row['Open']
        
        if direction == 'Buy':
            max_profit_pct = ((high - entry_price) / entry_price) * 100
            max_loss_pct = ((low - entry_price) / entry_price) * 100
            tp_hit = high >= tp_price
            sl_hit = low <= sl_price
        else:  # Sell
            max_profit_pct = ((entry_price - low) / entry_price) * 100
            max_loss_pct = ((entry_price - high) / entry_price) * 100
            tp_hit = low <= tp_price
            sl_hit = high >= sl_price
        
        results.append({
            'Date': date_str,
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': close,
            'MaxProfit%': round(max_profit_pct, 2),
            'MaxLoss%': round(max_loss_pct, 2),
            'TP_Hit': tp_hit,
            'SL_Hit': sl_hit,
            'ClosePrice': close
        })
    
    return results

def find_reentry(symbol, sl_hit_date, direction, sl_price):
    """Find reentry point after SL hit - next closed candle in same direction."""
    try:
        start_date = (datetime.strptime(sl_hit_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
        df = get_candle_data(symbol, start_date)
        
        if df.empty:
            return None
        
        sl_hit_idx = df.index.get_loc(pd.Timestamp(sl_hit_date)) if sl_hit_date in [d.strftime('%Y-%m-%d') for d in df.index] else -1
        
        if sl_hit_idx == -1 or sl_hit_idx >= len(df) - 1:
            return None
        
        for i in range(sl_hit_idx + 1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]
            candle_date = df.index[i].strftime('%Y-%m-%d')
            
            if direction == 'Buy':
                is_green = row['Close'] > row['Open']
                if is_green:
                    return {
                        'ReentryDate': candle_date,
                        'ReentryPrice': round(row['Close'], 2),
                        'ReentryType': 'Green Candle Close'
                    }
            else:  # Sell
                is_red = row['Close'] < row['Open']
                if is_red:
                    return {
                        'ReentryDate': candle_date,
                        'ReentryPrice': round(row['Close'], 2),
                        'ReentryType': 'Red Candle Close'
                    }
        
        return None
    except Exception as e:
        print(f"Error finding reentry for {symbol}: {e}")
        return None

def process_orderbook_file(filepath):
    """Process a single orderbook CSV file."""
    df = pd.read_csv(filepath)
    signal_date = Path(filepath).stem.replace('orderbook', '')
    
    if signal_date.startswith('2026-') or signal_date.startswith('2025-'):
        pass
    else:
        signal_date = signal_date
    
    print(f"Processing {filepath} for date {signal_date}")
    
    signals_file = SIGNALS_DIR / f"{signal_date}.csv"
    existing_signals = pd.DataFrame()
    
    if signals_file.exists():
        existing_signals = pd.read_csv(signals_file)
    
    sl_hits_data = []
    updated_rows = []
    
    for _, row in df.iterrows():
        symbol = row['Symbol']
        direction = row['Buy/Sell']
        entry = row['Entry']
        sl = row['Stoploss']
        tp = row['TargetPrice']
        
        existing_row = existing_signals[existing_signals['Symbol'] == symbol] if not existing_signals.empty else pd.DataFrame()
        
        if not existing_row.empty and existing_row.iloc[0]['Status'] in ['TP Hit', 'SL Hit']:
            updated_rows.append(existing_row.iloc[0].to_dict())
            continue
        
        start_date = signal_date
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        price_data = get_candle_data(symbol, start_date, end_date)
        
        if price_data.empty:
            print(f"  No price data for {symbol}")
            daily_perf = []
            status = 'Open'
            exit_price = ''
            exit_date = ''
            max_drawdown = 0
            max_profit = 0
        else:
            daily_perf = calculate_daily_performance(price_data, entry, sl, tp, direction)
            
            max_profit = max([d['MaxProfit%'] for d in daily_perf]) if daily_perf else 0
            max_drawdown = min([d['MaxLoss%'] for d in daily_perf]) if daily_perf else 0
            
            tp_hit_row = next((d for d in daily_perf if d['TP_Hit']), None)
            sl_hit_row = next((d for d in daily_perf if d['SL_Hit']), None)
            
            if tp_hit_row:
                status = 'TP Hit'
                exit_price = tp
                exit_date = tp_hit_row['Date']
            elif sl_hit_row:
                status = 'SL Hit'
                exit_price = sl
                exit_date = sl_hit_row['Date']
                
                reentry = find_reentry(symbol, exit_date, direction, sl)
                if reentry:
                    sl_hits_data.append({
                        'Symbol': symbol,
                        'OriginalSignalDate': signal_date,
                        'Direction': direction,
                        'Entry': entry,
                        'Stoploss': sl,
                        'TargetPrice': tp,
                        'SLHitDate': exit_date,
                        'SLHitPrice': sl,
                        'MaxDrawdown%': round(max_drawdown, 2),
                        'MaxProfit%': round(max_profit, 2),
                        'ReentryDate': reentry['ReentryDate'],
                        'ReentryPrice': reentry['ReentryPrice'],
                        'ReentryType': reentry['ReentryType']
                    })
            else:
                status = 'Open'
                exit_price = ''
                exit_date = ''
        
        signal_row = {
            'Symbol': symbol,
            'Entry': entry,
            'SL': sl,
            'TP': tp,
            'Status': status,
            'ExitPrice': exit_price,
            'ExitDate': exit_date,
        }
        
        for d in daily_perf:
            signal_row[f"{d['Date']}_MaxProfit"] = d['MaxProfit%']
            signal_row[f"{d['Date']}_MaxLoss"] = d['MaxLoss%']
        
        signal_row['MaxDrawdown%'] = round(max_drawdown, 2)
        signal_row['MaxProfit%'] = round(max_profit, 2)
        
        updated_rows.append(signal_row)
    
    if updated_rows:
        result_df = pd.DataFrame(updated_rows)
        result_df.to_csv(signals_file, index=False)
        print(f"  Updated {signals_file}")
    
    if sl_hits_data:
        sl_hits_df = pd.DataFrame(sl_hits_data)
        sl_hit_file = SL_HIT_DIR / f"sl_hits_{signal_date}.csv"
        if sl_hit_file.exists():
            existing_sl = pd.read_csv(sl_hit_file)
            combined = pd.concat([existing_sl, sl_hits_df], ignore_index=True)
            combined.drop_duplicates(subset=['Symbol', 'OriginalSignalDate', 'SLHitDate'], keep='last', inplace=True)
            combined.to_csv(sl_hit_file, index=False)
        else:
            sl_hits_df.to_csv(sl_hit_file, index=False)
        print(f"  Saved SL hits to {sl_hit_file}")

def consolidate_sl_hits():
    """Consolidate all SL hit files into a master file."""
    all_sl_files = list(SL_HIT_DIR.glob('sl_hits_*.csv'))
    if not all_sl_files:
        return
    
    all_sl_data = []
    for f in all_sl_files:
        df = pd.read_csv(f)
        all_sl_data.append(df)
    
    if all_sl_data:
        master = pd.concat(all_sl_data, ignore_index=True)
        master.drop_duplicates(subset=['Symbol', 'OriginalSignalDate', 'SLHitDate'], keep='last', inplace=True)
        master.to_csv(SL_HIT_DIR / 'sl_hits_master.csv', index=False)
        print(f"Consolidated SL hits: {len(master)} records")

def main():
    print("Starting signal processing...")
    print(f"Current dir: {os.getcwd()}")
    print(f"Orderbook dir exists: {ORDERBOOK_DIR.exists()}")
    
    orderbook_files = sorted(ORDERBOOK_DIR.glob('orderbook*.csv'))
    print(f"Found {len(orderbook_files)} orderbook files:")
    for f in orderbook_files:
        print(f"  - {f}")
    
    for f in orderbook_files:
        try:
            process_orderbook_file(f)
        except Exception as e:
            print(f"Error processing {f}: {e}")
            import traceback
            traceback.print_exc()
    
    consolidate_sl_hits()
    print("Processing complete!")
    print(f"Signals dir exists: {SIGNALS_DIR.exists()}")
    print(f"SL_HIT_DIR exists: {SL_HIT_DIR.exists()}")
    if SIGNALS_DIR.exists():
        signals = list(SIGNALS_DIR.glob('*.csv'))
        print(f"Generated {len(signals)} signal files:")
        for s in signals:
            print(f"  - {s}")
    if SL_HIT_DIR.exists():
        sl_hits = list(SL_HIT_DIR.glob('*.csv'))
        print(f"Generated {len(sl_hits)} SL hit files:")
        for s in sl_hits:
            print(f"  - {s}")

if __name__ == '__main__':
    main()