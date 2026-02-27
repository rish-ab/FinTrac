from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired

class FinTracForm(FlaskForm):
    # User Data Entry Fields
    income = FloatField('Monthly Income', validators=[DataRequired()])
    expenses = FloatField('Monthly Expenses', validators=[DataRequired()])
    
    # Risk Profile Selection
    risk_profile = SelectField('Risk Profile', choices=[
        ('aggressive', 'Aggressive'),
        ('conservative', 'Conservative')
    ])
    
    # Search Query Interface
    ticker = StringField('Stock Ticker (e.g., AAPL)', validators=[DataRequired()])
    
    submit = SubmitField('Analyze Portfolio')