from flask import Flask, render_template, request, redirect, url_for
import os
# Import your existing logic
from engine.FinTrac_Final import TradingEngine 

app = Flask(__name__)

# Initialize your existing engine
engine = TradingEngine(db_path='engine/FinTrac.db')

@app.route('/')
def index():
    """Form for User Cash Flow and Risk Profile."""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_ticker():
    """Interface for Ticker Search and AI Sentiment."""
    ticker = request.form.get('ticker').upper()
    risk_profile = request.form.get('risk_profile') # Aggressive vs Conservative
    
    # Trigger your existing backend logic
    result = engine.get_trade_recommendation(ticker, risk_profile)
    
    # result: {'score': 85, 'signal': 'BUY', 'sentiment': 'Positive'}
    return render_template('search.html', result=result, ticker=ticker)

@app.route('/dashboard')
def dashboard():
    """Display generated Matplotlib/Seaborn charts."""
    # Assuming your backend saves charts to static/charts/
    chart_path = engine.generate_portfolio_report() 
    analysis_text = engine.get_macro_summary()
    
    return render_template('dashboard.html', 
                           chart_url=chart_path, 
                           analysis=analysis_text)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)