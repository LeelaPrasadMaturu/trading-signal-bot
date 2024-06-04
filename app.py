import ccxt
import pandas as pd
import pandas_ta as ta
from flask import Flask, render_template, jsonify
import pytz
import logging
import time

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize exchange (using Binance as an example)
exchange = ccxt.binance()

# Parameters
cryptos = ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT', 'LTC/USDT', 'SHIB/USDT']
timeframe = '1h'  # 1-hour timeframe
limit = 50  # Reduce the limit to ensure fetching recent data
max_retries = 3  # Maximum number of retries

# Function to fetch OHLCV data with retry logic
def fetch_ohlcv(symbol):
    for attempt in range(max_retries):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except ccxt.NetworkError as e:
            logging.error(f"Network error while fetching data for {symbol}: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying... ({attempt + 1}/{max_retries})")
                time.sleep(5)  # Wait for 5 seconds before retrying
            else:
                raise

# Function to calculate indicators and generate buy signals
def generate_signals(df):
    df['MA'] = df['close'].rolling(window=50).mean()
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_signal'] = macd['MACDs_12_26_9']
    
    # Conditions for each indicator
    df['MA_condition'] = df['close'] > df['MA']
    df['RSI_condition'] = df['RSI'] < 30
    df['MACD_condition'] = df['MACD'] > df['MACD_signal']
    df['Volume_condition'] = df['volume'] > df['volume'].rolling(window=50).mean()
    
    # Buy signal conditions
    df['conditions_met'] = df[['MA_condition', 'RSI_condition', 'MACD_condition', 'Volume_condition']].sum(axis=1)
    df['buy_signal'] = df['conditions_met'] == 4  # All conditions must be met
    
    return df

def get_signals():
    signals = []
    for symbol in cryptos:
        try:
            df = fetch_ohlcv(symbol)
            df = generate_signals(df)
            latest_signal = df['buy_signal'].iloc[-1]
            conditions_met = df['conditions_met'].iloc[-1]
            probability = conditions_met / 4  # Calculate probability based on conditions met
            timestamp = df.index[-1]
            
            # Localize to UTC before converting to IST
            utc = pytz.utc
            ist = pytz.timezone('Asia/Kolkata')
            if timestamp.tzinfo is None:
                timestamp_utc = utc.localize(timestamp)
            else:
                timestamp_utc = timestamp.astimezone(utc)
            timestamp_ist = timestamp_utc.astimezone(ist).strftime('%Y-%m-%d %H:%M:%S')
            
            # Log the timestamp for debugging
            logging.info(f"Symbol: {symbol}, UTC Timestamp: {timestamp_utc}, IST Timestamp: {timestamp_ist}, Buy Signal: {latest_signal}, Conditions Met: {conditions_met}, Probability: {probability}")
            
            signals.append({
                'symbol': symbol,
                'buy_signal': bool(latest_signal),
                'conditions_met': conditions_met,
                'probability': probability,
                'timestamp': timestamp_ist
            })
        except ccxt.NetworkError:
            logging.error(f"Failed to fetch data for {symbol} after {max_retries} attempts.")
            signals.append({
                'symbol': symbol,
                'buy_signal': False,
                'conditions_met': 0,
                'probability': 0.0,
                'timestamp': 'N/A'
            })
    return signals

@app.route('/')
def index():
    signals = get_signals()
    return render_template('index.html', signals=signals)

@app.route('/generate_signals')
def generate_signals_route():
    signals = get_signals()
    return jsonify(signals)

if __name__ == '__main__':
    app.run(debug=True)
