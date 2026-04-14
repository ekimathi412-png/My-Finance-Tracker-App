from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import pandas as pd
import io
from datetime import datetime
from collections import defaultdict
import json
import os
import uuid

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"

# -------------------- DATABASE CONFIG --------------------

DATA_FILE = "data.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///finance.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True)
    Type = Column(String, nullable=False)
    Category = Column(String, nullable=False)
    Amount = Column(Float, nullable=False)
    Date = Column(String, nullable=False)

Base.metadata.create_all(bind=engine)


def txn_to_dict(t):
    return {
        "id": t.id,
        "Type": t.Type,
        "Category": t.Category,
        "Amount": t.Amount,
        "Date": t.Date
    }


def get_db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def load_transactions(filter_date=None):
    session = SessionLocal()
    try:
        query = session.query(Transaction)
        if filter_date:
            query = query.filter(Transaction.Date == filter_date)
        return [txn_to_dict(t) for t in query.order_by(Transaction.Date).all()]
    finally:
        session.close()


def get_transaction(tid):
    session = SessionLocal()
    try:
        return session.get(Transaction, tid)
    finally:
        session.close()


def save_transaction(transaction_data):
    session = SessionLocal()
    try:
        transaction = Transaction(**transaction_data)
        session.add(transaction)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_transaction(transaction, new_data):
    session = SessionLocal()
    try:
        transaction.Type = new_data["Type"]
        transaction.Category = new_data["Category"]
        transaction.Amount = new_data["Amount"]
        transaction.Date = new_data["Date"]
        session.add(transaction)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_transaction(tid):
    session = SessionLocal()
    try:
        transaction = session.get(Transaction, tid)
        if transaction:
            session.delete(transaction)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate_data_json():
    if not os.path.exists(DATA_FILE):
        return

    session = SessionLocal()
    try:
        if session.query(Transaction).first() is not None:
            return

        with open(DATA_FILE, "r") as f:
            saved = json.load(f)

        for t in saved.get("transactions", []):
            if t.get("id") and session.get(Transaction, t["id"]) is None:
                session.add(Transaction(
                    id=t["id"],
                    Type=t["Type"],
                    Category=t["Category"],
                    Amount=t["Amount"],
                    Date=t["Date"]
                ))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


migrate_data_json()

categories = {}


# ----------------------------- DASHBOARD -----------------------------

@app.route('/')
def index():
    filter_date = request.args.get("date")

    balance = 0
    total_income = 0
    total_expense = 0

    categories.clear()
    filtered = load_transactions(filter_date)

    for t in filtered:
        if t['Type'] == 'Income':
            total_income += t['Amount']
            balance += t['Amount']
        else:
            total_expense += t['Amount']
            balance -= t['Amount']

        key = (t['Type'], t['Category'])
        categories[key] = categories.get(key, 0) + t['Amount']

    return render_template(
        'index.html',
        balance=balance,
        transactions=filtered,
        categories=categories,
        total_income=total_income,
        total_expense=total_expense,
        filter_date=filter_date
    )


# ----------------------------- ADD TRANSACTION -----------------------------

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        t_type = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])
        date = request.form['date']

        new_t = {
            "id": str(uuid.uuid4()),
            "Type": t_type,
            "Category": category,
            "Amount": amount,
            "Date": date
        }

        save_transaction(new_t)
        return redirect(url_for('index'))

    return render_template('add.html')


# ----------------------------- EDIT TRANSACTION -----------------------------

@app.route('/edit/<tid>', methods=['GET', 'POST'])
def edit(tid):
    session = SessionLocal()
    try:
        transaction = session.get(Transaction, tid)
        if not transaction:
            return "Transaction not found", 404

        if request.method == 'POST':
            transaction.Type = request.form['type']
            transaction.Category = request.form['category']
            transaction.Amount = float(request.form['amount'])
            transaction.Date = request.form['date']

            session.add(transaction)
            session.commit()
            return redirect(url_for('index'))

        return render_template('edit.html', t=txn_to_dict(transaction))
    finally:
        session.close()


# ----------------------------- DELETE TRANSACTION -----------------------------

@app.route('/delete/<tid>')
def delete(tid):
    delete_transaction(tid)
    return redirect(url_for('index'))


# ----------------------------- REPORTS -----------------------------

@app.route('/reports')
@app.route('/reports/<period>')
def reports(period='all'):
    selected_month = request.args.get('month')
    selected_year = request.args.get('year')

    transactions = load_transactions()

    if period == 'year':
        if selected_year:
            filtered_transactions = [t for t in transactions if t['Date'].startswith(selected_year)]
        else:
            current_year = datetime.now().strftime('%Y')
            filtered_transactions = [t for t in transactions if t['Date'].startswith(current_year)]
            selected_year = current_year
    elif period == 'month':
        if selected_month:
            filtered_transactions = [t for t in transactions if t['Date'].startswith(selected_month)]
        else:
            selected_month = datetime.now().strftime('%Y-%m')
            filtered_transactions = [t for t in transactions if t['Date'].startswith(selected_month)]
    else:
        filtered_transactions = transactions

    insights = calculate_insights(filtered_transactions)
    tips = generate_tips(filtered_transactions, insights)
    month_options = get_available_months(transactions)

    chart_data = {
        'monthly_spending': insights.get('monthly_spending', {"labels": [], "values": []}),
        'categories': insights.get('categories', {}),
        'balance': insights.get('balance', {'income': 0, 'expenses': 0}),
        'top_category': insights.get('top_category', 'None'),
        'saving_rate': insights.get('saving_rate', 0) / 100,
        'transactions': filtered_transactions,
        'period': period,
        'record_count': len(filtered_transactions),
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_options': month_options
    }

    return render_template(
        'reports.html',
        insights=insights,
        chart_data=chart_data,
        current_period=period,
        tips=tips,
        selected_month=selected_month,
        selected_year=selected_year
    )


# ----------------------------- INSIGHTS -----------------------------

def calculate_insights(transactions):
    if not transactions:
        return {
            'saving_rate': 0,
            'top_category': 'None',
            'top_category_pct': 0,
            'total_income': 0,
            'total_expense': 0,
            'categories': {},
            'monthly_spending': {"labels": [], "values": []},
            'balance': {'income': 0, 'expenses': 0}
        }

    income_total = sum(t['Amount'] for t in transactions if t['Type'] == 'Income')
    expense_total = sum(t['Amount'] for t in transactions if t['Type'] == 'Expense')

    cat_expenses = defaultdict(float)
    for t in transactions:
        if t['Type'] == 'Expense':
            cat_expenses[t['Category']] += t['Amount']

    if cat_expenses:
        top_cat = max(cat_expenses.items(), key=lambda x: x[1])
        top_pct = (top_cat[1] / expense_total) * 100 if expense_total else 0
    else:
        top_cat = ('None', 0)
        top_pct = 0

    saving_rate = ((income_total - expense_total) / income_total * 100) if income_total else 0

    return {
        'saving_rate': max(0, saving_rate),
        'top_category': top_cat[0],
        'top_category_pct': round(top_pct, 1),
        'total_income': round(income_total, 2),
        'total_expense': round(expense_total, 2),
        'categories': dict(cat_expenses),
        'monthly_spending': get_monthly_spending(transactions),
        'balance': {'income': income_total, 'expenses': expense_total}
    }


def get_monthly_spending(transactions):
    monthly = defaultdict(float)
    for t in transactions:
        if t['Type'] == 'Expense':
            month = t['Date'][:7]
            monthly[month] += t['Amount']

    items = sorted(monthly.items())[-6:]
    labels = [key for key, _ in items]
    values = [round(value, 2) for _, value in items]

    return {"labels": labels, "values": values}


def get_available_months(transactions):
    months = sorted({t['Date'][:7] for t in transactions if t.get('Date')})
    return months[-12:][::-1]


def generate_tips(transactions, insights):
    tips = []
    if not transactions:
        return [
            'No data yet. Add income and expenses to get helpful insights.',
            'Use the monthly selector to review each month once you start tracking transactions.'
        ]

    expense_total = insights['total_expense']
    income_total = insights['total_income']
    top_category = insights['top_category']
    top_pct = insights['top_category_pct']
    saving_rate = insights['saving_rate']

    if income_total == 0:
        tips.append('Add income entries first so the app can calculate savings and recommend budgets.')
    elif expense_total > income_total:
        tips.append('Your expenses are higher than your income. Look for cuts in non-essential spending this month.')
    elif saving_rate >= 25:
        tips.append('Excellent work—your saving rate is strong. Keep this momentum going.')
    elif saving_rate >= 10:
        tips.append('You are saving a portion of your income. Try trimming one category to improve your savings further.')
    else:
        tips.append('Your saving rate is low. Aim to reduce spending and keep expenses below 80% of income.')

    if top_category != 'None' and top_pct > 30:
        tips.append(f'{top_category} makes up {top_pct}% of your expenses. Review this category for possible savings.')
    elif top_category != 'None':
        tips.append(f'{top_category} is your top spend category. Keep tracking it to avoid overspending.')

    monthly = insights.get('monthly_spending', {})
    labels = monthly.get('labels', [])
    values = monthly.get('values', [])
    if len(values) >= 2:
        if values[-1] > values[-2]:
            tips.append('Your latest monthly spending increased. Check if recurring costs or one-time purchases caused the rise.')
        else:
            tips.append('Spending has stabilized or declined recently. Continue the good habit of monitoring transactions.')

    if len(labels) > 0:
        tips.append(f'Track monthly performance by choosing a month from the selector above. You have {len(labels)} spend months available.')

    return tips


# ----------------------------- EXPORT -----------------------------

@app.route('/export/transactions')
def export_transactions():
    period = request.args.get('period', 'all')
    selected_month = request.args.get('month')
    selected_year = request.args.get('year')

    transactions = load_transactions()

    if period == 'year':
        year = selected_year or datetime.now().strftime('%Y')
        filtered = [t for t in transactions if t['Date'].startswith(year)]
    elif period == 'month':
        month = selected_month or datetime.now().strftime('%Y-%m')
        filtered = [t for t in transactions if t['Date'].startswith(month)]
    else:
        filtered = transactions

    df_transactions = pd.DataFrame(filtered)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_transactions.to_excel(writer, sheet_name='Transactions', index=False)

    output.seek(0)

    filename = f"finance_report_{period}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# ----------------------------- RUN SERVER -----------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)