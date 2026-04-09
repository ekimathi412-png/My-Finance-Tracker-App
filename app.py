from flask import Flask, render_template, request, redirect, url_for, session, make_response, send_file, flash
from flask import jsonify
import pandas as pd
import io
from datetime import datetime
from collections import defaultdict
import json
import os
import hashlib


app = Flask(__name__)
app.secret_key = "secret123"


# -------------------- FILE STORAGE / USERS --------------------

DATA_FILE = "data.json"


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def load_data():
    default = {"transactions": [], "users": {}}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            loaded = json.load(f)
        default.update(loaded)
    return default


def save_data(data):
    # Always keep both transactions and users
    data_to_save = {
        "transactions": data.get("transactions", []),
        "users": data.get("users", {}),
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data_to_save, f, indent=2)


# Load data on startup
data_store = load_data()
transactions = data_store["transactions"]
users = data_store["users"]
categories = {}  # ← FIXED: this was missing


# ----------------------------- DASHBOARD ROUTE -----------------------------

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    filter_date = request.args.get("date")

    balance = 0
    total_income = 0
    total_expense = 0

    # Clear categories each time
    categories.clear()

    # Only show this user's transactions
    user_transactions = [t for t in transactions if t.get('user') == session['user']]

    if filter_date:
        filtered = [t for t in user_transactions if t["Date"] == filter_date]
    else:
        filtered = user_transactions

    for t in filtered:
        if t['Type'] == 'Income':
            total_income += t['Amount']
            balance += t['Amount']
        else:
            total_expense += t['Amount']
            balance -= t['Amount']

        key = (t['Type'], t['Category'])
        categories[key] = categories.get(key, 0) + t['Amount']

    # Regenerate IDs so /edit /delete work
    for i, t in enumerate(filtered):
        t["id"] = i

    return render_template(
        'index.html',
        balance=balance,
        transactions=filtered,
        categories=categories,
        total_income=total_income,
        total_expense=total_expense,
        filter_date=filter_date
    )


# ----------------------------- SIGNUP -----------------------------

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
            return redirect(url_for('signup'))

        if len(password) < 4:
            flash("Password must be at least 4 characters.", "error")
            return redirect(url_for('signup'))

        if username in users:
            flash("Username already taken.", "error")
            return redirect(url_for('signup'))

        # Save user
        users[username] = {"password": hash_password(password)}

        # Save to disk
        save_data({"transactions": transactions, "users": users})

        flash("Account created! You can now log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')


# ----------------------------- LOGIN -----------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if user exists and password matches
        user_info = users.get(username)
        if user_info and user_info["password"] == hash_password(password):
            session['user'] = username
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


# ----------------------------- LOGOUT -----------------------------

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# ----------------------------- ADD TRANSACTION -----------------------------

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        t_type = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])
        date = request.form['date']

        new_t = {
            "id": len(transactions),
            "Type": t_type,
            "Category": category,
            "Amount": amount,
            "Date": date,
            "user": session['user']
        }

        transactions.append(new_t)

        # Recalculate IDs
        for i, t in enumerate(transactions):
            t["id"] = i

        # Save to JSON
        save_data({"transactions": transactions, "users": users})

        return redirect(url_for('index'))

    return render_template('add.html')


# ----------------------------- EDIT TRANSACTION -----------------------------

@app.route('/edit/<int:tid>', methods=['GET', 'POST'])
def edit(tid):
    if 'user' not in session:
        return redirect(url_for('login'))

    transaction = next((t for t in transactions if t["id"] == tid), None)
    if not transaction:
        return "Transaction not found", 404

    if request.method == 'POST':
        transaction["Type"] = request.form['type']
        transaction["Category"] = request.form['category']
        transaction["Amount"] = float(request.form['amount'])
        transaction["Date"] = request.form['date']

        # Save to JSON
        save_data({"transactions": transactions, "users": users})

        return redirect(url_for('index'))

    return render_template('edit.html', t=transaction)


# ----------------------------- DELETE TRANSACTION -----------------------------

@app.route('/delete/<int:tid>')
def delete(tid):
    if 'user' not in session:
        return redirect(url_for('login'))

    global transactions

    transactions = [t for t in transactions if t["id"] != tid]

    # Recalculate IDs
    for i, t in enumerate(transactions):
        t["id"] = i

    # Save to JSON
    save_data({"transactions": transactions, "users": users})

    return redirect(url_for('index'))


# ----------------------------- REPORTS -----------------------------

@app.route('/reports')
@app.route('/reports/<period>')
def reports(period='all'):
    if 'user' not in session:
        return redirect(url_for('login'))

    user_transactions = [t for t in transactions if t.get('user') == session['user']]

    if period == 'year':
        current_year = datetime.now().strftime('%Y')
        filtered_transactions = [t for t in user_transactions if t['Date'].startswith(current_year)]
    elif period == 'month':
        current_month = datetime.now().strftime('%Y-%m')
        filtered_transactions = [t for t in user_transactions if t['Date'].startswith(current_month)]
    else:
        filtered_transactions = user_transactions

    insights = calculate_insights(filtered_transactions)

    chart_data = {
        'monthly_spending': insights.get('monthly_spending', {"labels": [], "values": []}),
        'categories': insights.get('categories', {}),
        'balance': insights.get('balance', {'income': 0, 'expenses': 0}),
        'top_category': insights.get('top_category', 'None'),
        'saving_rate': insights.get('saving_rate', 0) / 100,
        'transactions': filtered_transactions[:10],
        'period': period,
        'record_count': len(filtered_transactions)
    }

    return render_template(
        'reports.html',
        insights=insights,
        chart_data=chart_data,
        current_period=period
    )


# ----------------------------- INSIGHTS / STATS HELPERS -----------------------------

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


def calculate_summary_stats(transactions):
    insights = calculate_insights(transactions)
    return {
        'Total Income': insights['total_income'],
        'Total Expenses': insights['total_expense'],
        'Savings Rate (%)': f"{insights['saving_rate']:.1f}%",
        'Top Category': insights['top_category'],
        'Records': len(transactions)
    }


def get_monthly_spending(transactions):
    monthly = defaultdict(float)
    for t in transactions:
        if t['Type'] == 'Expense':
            month = t['Date'][:7]  # YYYY‑MM
            monthly[month] += t['Amount']
    items = sorted(monthly.items())[-6:]
    labels = [key for key, _ in items]
    values = [round(value, 2) for _, value in items]
    return {"labels": labels, "values": values}


# ----------------------------- EXPORT EXCEL -----------------------------

@app.route('/export/transactions')
def export_transactions():
    if 'user' not in session:
        return redirect(url_for('login'))

    period = request.args.get('period', 'all')
    user_transactions = [t for t in transactions if t.get('user') == session['user']]

    if period != 'all':
        if period == 'year':
            user_transactions = [t for t in user_transactions if t['Date'].startswith('2026')]
        elif period == 'month':
            user_transactions = [t for t in user_transactions if t['Date'].startswith('2026-04')]

    df_transactions = pd.DataFrame(user_transactions)
    summary = calculate_summary_stats(user_transactions)
    df_summary = pd.DataFrame([summary])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_transactions.to_excel(writer, sheet_name='Transactions', index=False)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
    output.seek(0)

    filename = f"finance_report_{period}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# ----------------------------- START SERVER -----------------------------

if __name__ == '__main__':
    app.run(debug=True)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)