from flask import Flask, request, redirect, url_for, render_template, session, abort, flash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import uuid
import os
import json
import logging
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "changeme")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/data/expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class SessionModel(db.Model):
    __tablename__ = 'session_model'
    id = db.Column(db.String(36), primary_key=True)
    owner_secret = db.Column(db.String(36), nullable=False)
    password = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    person_categories_json = db.Column(db.Text, nullable=True)   # JSON of {person: [categories]}
    transactions_json = db.Column(db.Text, nullable=True)         # JSON of [[debtor, creditor, amount], ...]

class Person(db.Model):
    __tablename__ = 'person'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey('session_model.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey('session_model.id'), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)

class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey('session_model.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False, unique=True)

with app.app_context():
    db.create_all()

# Helper Functions
def is_admin(session_id):
    """
    Returns True if the user's session has both 'session_id' and 'owner_secret'
    matching the database's 'owner_secret' for this session_id.
    """
    if 'session_id' in session and 'owner_secret' in session:
        if session['session_id'] == session_id:
            sm = SessionModel.query.filter_by(id=session_id).first()
            if sm and sm.owner_secret == session['owner_secret']:
                return True
    return False

def can_edit(session_id):
    """
    Returns True if the user is admin OR the session has a password AND
    the user has 'edit_access' for this session_id in their Flask session.
    """
    if is_admin(session_id):
        return True
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        return False
    if not sm.password or sm.password.strip() == "":
        return False
    # 'edit_access' is set if user enters the correct password at least once
    if 'edit_access' in session and session['edit_access'].get(session_id) == True:
        return True
    return False

def add_expense_to_dict(expenses_data, person, amount, category):
    if person not in expenses_data:
        expenses_data[person] = {}
    if category not in expenses_data[person]:
        expenses_data[person][category] = 0
    expenses_data[person][category] += amount

def minimize_transactions(people, expenses_data):
    """
    Standard minimal transactions logic:
    1. Sum total spent by each person.
    2. Subtract fair share, splitting debtors and creditors.
    3. Match them to reduce transactions.
    """
    total_per_person = {p: sum(expenses_data.get(p, {}).values()) for p in people}
    total_expenses = sum(total_per_person.values())
    n = len(people)
    if n == 0:
        return []
    fair_share = total_expenses / n

    balance = {p: total_per_person[p] - fair_share for p in people}
    debtors, creditors = [], []
    for p, b in balance.items():
        if b < 0:
            debtors.append([p, b])
        elif b > 0:
            creditors.append([p, b])

    debtors.sort(key=lambda x: x[1])  # ascending
    creditors.sort(key=lambda x: x[1], reverse=True)  # descending

    transactions = []
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        creditor, c_amount = creditors[i]
        debtor, d_amount = debtors[j]
        pay_amount = min(c_amount, -d_amount)

        transactions.append((debtor, creditor, pay_amount))

        creditors[i][1] -= pay_amount
        debtors[j][1] += pay_amount

        if creditors[i][1] == 0:
            i += 1
        if debtors[j][1] == 0:
            j += 1

    return transactions

# Decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(session_id, *args, **kwargs):
        if not is_admin(session_id):
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for('view_session', session_id=session_id))
        return f(session_id, *args, **kwargs)
    return decorated_function

def can_edit_required(f):
    @wraps(f)
    def decorated_function(session_id, *args, **kwargs):
        if not can_edit(session_id):
            flash("You do not have permission to perform this action.", "error")
            return redirect(url_for('view_session', session_id=session_id))
        return f(session_id, *args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def initial_page():
    return render_template('initial_setup.html')

@app.route('/create_session', methods=['POST'])
def create_session():
    name = request.form.get('session_name')
    password = request.form.get('password')

    if not name or not password:
        flash("Please provide both a session name and a password.", "error")
        return redirect(url_for('initial_page'))

    sid = str(uuid.uuid4())
    owner_secret = str(uuid.uuid4())
    session['session_id'] = sid
    session['owner_secret'] = owner_secret

    s = SessionModel(
        id=sid,
        owner_secret=owner_secret,
        password=password.strip(),
        name=name.strip(),
        person_categories_json=json.dumps({}),
        transactions_json=json.dumps([])
    )
    db.session.add(s)
    db.session.commit()

    flash("Session created successfully.", "success")
    return redirect(url_for('view_session', session_id=sid))

# IMPORTANT CHANGE: Removed any @login_required so anyone can view
@app.route('/session/<session_id>')
def view_session(session_id):
    """
    Anyone with the link can see the session in "view mode."
    The admin/edit logic is still behind is_admin/can_edit checks.
    """
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    # Figures out if the current user is admin or can edit
    admin = is_admin(session_id)
    editable = can_edit(session_id)

    persons = Person.query.filter_by(session_id=session_id).all()
    expenses = Expense.query.filter_by(session_id=session_id).all()

    person_name_map = {p.id: p.name for p in persons}
    person_categories = json.loads(sm.person_categories_json or '{}')
    transactions = json.loads(sm.transactions_json or '[]')

    all_categories = sorted([c.name for c in Category.query.filter_by(session_id=session_id).all()])

    # Build aggregated expenses data if needed
    aggregated_expenses = {}
    for e in expenses:
        aggregated_expenses[e.category] = aggregated_expenses.get(e.category, 0) + e.amount

    # Person→Category→Amount
    person_category_expenses = {}
    for e in expenses:
        pname = person_name_map[e.person_id]
        cat = e.category
        amt = e.amount
        if pname not in person_category_expenses:
            person_category_expenses[pname] = {}
        if cat not in person_category_expenses[pname]:
            person_category_expenses[pname][cat] = 0
        person_category_expenses[pname][cat] += amt

    return render_template(
        'session_view.html',
        session_id=session_id,
        session_name=sm.name,
        persons=persons,
        expenses=expenses,
        person_name_map=person_name_map,
        editable=editable,
        admin=admin,
        password_required=(sm.password is not None and sm.password.strip() != ""),
        transactions=transactions,
        all_categories=all_categories,
        person_categories=person_categories,
        aggregated_expenses=aggregated_expenses,
        person_category_expenses=person_category_expenses
    )

@app.route('/enter_password/<session_id>', methods=['POST'])
def enter_password(session_id):
    """
    If the user enters the correct password, we set owner_secret in their session,
    making them admin if they match the DB's secret. 
    Otherwise, it just sets 'edit_access' for this session.
    """
    password = request.form.get('password')
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    if sm.password and sm.password.strip() == password.strip():
        # The user becomes admin
        session['session_id'] = session_id
        session['owner_secret'] = sm.owner_secret
        flash("You now have admin access to this session.", "success")
    else:
        flash("Incorrect password.", "error")
    return redirect(url_for('view_session', session_id=session_id))

@app.route('/save_and_exit/<session_id>', methods=['POST'])
def save_and_exit(session_id):
    if 'edit_access' in session and session_id in session['edit_access']:
        del session['edit_access'][session_id]
    flash("Changes saved. Now in view mode.", "success")
    return redirect(url_for('view_session', session_id=session_id))

@app.route('/add_person/<session_id>', methods=['POST'])
@can_edit_required
def add_person(session_id):
    name = request.form.get('name', '').strip()
    if not name:
        flash("Please enter a valid name.", "error")
        return redirect(url_for('view_session', session_id=session_id))
    if not name[0].isupper():
        name = name[0].upper() + name[1:]

    existing_person = Person.query.filter_by(session_id=session_id, name=name).first()
    if existing_person:
        flash("Person already exists.", "error")
        return redirect(url_for('view_session', session_id=session_id))

    new_person = Person(session_id=session_id, name=name)
    db.session.add(new_person)
    db.session.commit()

    # Add to JSON if not present
    sm = SessionModel.query.filter_by(id=session_id).first()
    person_categories = json.loads(sm.person_categories_json or '{}')
    if name not in person_categories:
        person_categories[name] = []
    sm.person_categories_json = json.dumps(person_categories)
    db.session.commit()

    flash(f"Person '{name}' added successfully.", "success")
    return redirect(url_for('view_session', session_id=session_id))

@app.route('/add_expense/<session_id>', methods=['POST'])
@can_edit_required
def add_expense_route(session_id):
    person_id = request.form.get('person_id')
    category = request.form.get('category', '').strip()
    amount_str = request.form.get('amount', '0').strip()

    errors = []
    # Validate person_id
    if not person_id:
        errors.append("Person is required.")
    else:
        try:
            person_id_int = int(person_id)
            person_obj = Person.query.filter_by(id=person_id_int, session_id=session_id).first()
            if not person_obj:
                errors.append("Selected person does not exist.")
        except ValueError:
            errors.append("Invalid person selected.")

    # Validate category
    if not category:
        errors.append("Category is required.")
    else:
        category = category[0].upper() + category[1:].lower()
        existing_cat = Category.query.filter(
            Category.session_id == session_id,
            func.lower(Category.name) == category.lower()
        ).first()
        if not existing_cat:
            new_cat = Category(session_id=session_id, name=category)
            db.session.add(new_cat)
            db.session.commit()

    # Validate amount
    try:
        amount = float(amount_str)
        if amount <= 0:
            errors.append("Amount must be greater than zero.")
    except ValueError:
        errors.append("Invalid amount entered.")

    if errors:
        for err in errors:
            flash(err, "error")
        return redirect(url_for('view_session', session_id=session_id))

    # Add or update expense
    existing_expense = Expense.query.filter_by(
        session_id=session_id, person_id=person_id_int, category=category
    ).first()

    if existing_expense:
        existing_expense.amount += amount
        db.session.commit()
        flash("Expense updated successfully.", "success")
    else:
        new_exp = Expense(session_id=session_id, person_id=person_id_int, category=category, amount=amount)
        db.session.add(new_exp)
        db.session.commit()
        flash("Expense added successfully.", "success")

    return redirect(url_for('view_session', session_id=session_id))

@app.route('/calculate_transactions/<session_id>', methods=['POST'])
def calculate_transactions_route(session_id):
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    persons = Person.query.filter_by(session_id=session_id).all()
    people = [p.name for p in persons]
    expenses = Expense.query.filter_by(session_id=session_id).all()

    person_categories = json.loads(sm.person_categories_json or '{}')

    expenses_data = {}
    for exp in expenses:
        pname = next((p.name for p in persons if p.id == exp.person_id), None)
        if pname and exp.category in person_categories.get(pname, []):
            add_expense_to_dict(expenses_data, pname, exp.amount, exp.category)

    transactions = minimize_transactions(people, expenses_data)
    sm.transactions_json = json.dumps(transactions)
    db.session.commit()

    flash("Transactions calculated successfully.", "success")
    return redirect(url_for('view_session', session_id=session_id))

@app.route('/set_password/<session_id>', methods=['POST'])
def set_password(session_id):
    if not is_admin(session_id):
        flash("Not authorized to set password.", "error")
        return redirect(url_for('view_session', session_id=session_id))
    pw = request.form.get('password')
    sm = SessionModel.query.filter_by(id=session_id).first()
    if sm:
        sm.password = pw.strip() if pw else None
        db.session.commit()
        flash("Password updated successfully.", "success")
    else:
        flash("Session not found.", "error")
    return redirect(url_for('view_session', session_id=session_id))

@app.route('/delete_session/<session_id>', methods=['POST'])
@admin_required
def delete_session(session_id):
    Expense.query.filter_by(session_id=session_id).delete()
    Person.query.filter_by(session_id=session_id).delete()
    Category.query.filter_by(session_id=session_id).delete()
    SessionModel.query.filter_by(id=session_id).delete()
    db.session.commit()
    session.clear()
    flash("Session deleted successfully.", "success")
    return redirect(url_for('initial_page'))

@app.route('/edit_admin/<session_id>', methods=['GET', 'POST'])
@admin_required
def edit_admin(session_id):
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    persons = Person.query.filter_by(session_id=session_id).all()
    categories = Category.query.filter_by(session_id=session_id).all()
    all_categories = sorted([c.name for c in categories])
    expenses = Expense.query.filter_by(session_id=session_id).all()
    person_name_map = {p.id: p.name for p in persons}

    person_category_expenses = {}
    for e in expenses:
        pname = person_name_map[e.person_id]
        cat = e.category
        amt = e.amount
        if pname not in person_category_expenses:
            person_category_expenses[pname] = {}
        if cat not in person_category_expenses[pname]:
            person_category_expenses[pname][cat] = 0
        person_category_expenses[pname][cat] += amt

    admin = is_admin(session_id)

    if request.method == 'GET':
        if 'edit_access' not in session:
            session['edit_access'] = {}
        session['edit_access'][session_id] = True

        return render_template(
            'edit_admin.html',
            session_id=session_id,
            persons=persons,
            all_categories=all_categories,
            expenses=expenses,
            person_name_map=person_name_map,
            person_category_expenses=person_category_expenses,
            admin=admin
        )
    else:
        # handle add_person / add_category here
        if 'add_person' in request.form:
            new_name = request.form.get('name', '').strip()
            if new_name:
                existing_person = Person.query.filter_by(session_id=session_id, name=new_name).first()
                if existing_person:
                    flash("Person already exists.", "error")
                else:
                    new_person = Person(session_id=session_id, name=new_name)
                    db.session.add(new_person)
                    db.session.commit()
                    flash(f"Added new person: {new_name}", "success")
            else:
                flash("Name cannot be empty.", "error")

        if 'add_category' in request.form:
            new_category = request.form.get('category', '').strip()
            if new_category:
                existing_category = Category.query.filter_by(session_id=session_id, name=new_category).first()
                if existing_category:
                    flash("Category already exists.", "error")
                else:
                    new_cat = Category(session_id=session_id, name=new_category)
                    db.session.add(new_cat)
                    db.session.commit()
                    flash(f"Added new category: {new_category}", "success")
            else:
                flash("Category cannot be empty.", "error")

        return redirect(url_for('view_session', session_id=session_id))

@app.route('/edit_category/<session_id>', methods=['POST'])
@admin_required
def edit_category(session_id):
    old_category = request.form.get('old_category')
    new_category = request.form.get('new_category')
    if not new_category:
        flash("Category name cannot be empty.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    category = Category.query.filter_by(session_id=session_id, name=old_category).first()
    if not category:
        flash("Category not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    existing_category = Category.query.filter_by(session_id=session_id, name=new_category).first()
    if existing_category:
        flash("Another category with this name already exists.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    # update all relevant expenses
    Expense.query.filter_by(session_id=session_id, category=old_category).update({'category': new_category})
    category.name = new_category
    db.session.commit()

    flash("Category updated successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/delete_category/<session_id>', methods=['POST'])
@admin_required
def delete_category(session_id):
    category_name = request.form.get('category')
    if not category_name:
        flash("No category specified.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    category = Category.query.filter_by(session_id=session_id, name=category_name).first()
    if not category:
        flash("Category not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    # remove all expenses with this category
    Expense.query.filter_by(session_id=session_id, category=category_name).delete()
    db.session.delete(category)
    db.session.commit()

    flash("Category deleted successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/add_category/<session_id>', methods=['POST'])
@admin_required
def add_category(session_id):
    raw_category = request.form.get('category', '').strip()
    if not raw_category:
        flash("Category name cannot be empty.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    category_str = raw_category[0].upper() + raw_category[1:].lower()
    existing = Category.query.filter(
        Category.session_id == session_id,
        func.lower(Category.name) == category_str.lower()
    ).first()
    if existing:
        flash("Category already exists.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    new_category = Category(session_id=session_id, name=category_str)
    db.session.add(new_category)
    db.session.commit()

    flash(f"Category '{category_str}' added successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/edit_name/<session_id>/<person_id>', methods=['POST'])
@admin_required
def edit_name(session_id, person_id):
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash("Name cannot be empty.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    if not new_name[0].isupper():
        new_name = new_name[0].upper() + new_name[1:]

    existing_person = Person.query.filter_by(session_id=session_id, name=new_name).first()
    if existing_person:
        flash("Another person with this name already exists.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    person = Person.query.filter_by(id=person_id, session_id=session_id).first()
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    old_name = person.name
    person.name = new_name
    db.session.commit()

    # Update person_categories JSON if needed
    person_categories = json.loads(sm.person_categories_json or '{}')
    if old_name in person_categories:
        person_categories[new_name] = person_categories.pop(old_name)
        sm.person_categories_json = json.dumps(person_categories)
        db.session.commit()

    flash("Person name updated successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/delete_person/<session_id>/<person_id>', methods=['POST'])
@admin_required
def delete_person(session_id, person_id):
    person = Person.query.filter_by(session_id=session_id, id=person_id).first()
    if not person:
        flash("Person not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    sm = SessionModel.query.filter_by(id=session_id).first()
    if sm:
        person_categories = json.loads(sm.person_categories_json or '{}')
        if person.name in person_categories:
            del person_categories[person.name]
            sm.person_categories_json = json.dumps(person_categories)
            db.session.commit()

    db.session.delete(person)
    db.session.commit()
    flash("Person deleted successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/edit_expense_amount/<session_id>/<expense_id>', methods=['POST'])
@admin_required
def edit_expense_amount(session_id, expense_id):
    new_amount_str = request.form.get('new_amount', '0')
    try:
        new_amount = float(new_amount_str)
        if new_amount <= 0:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for('edit_admin', session_id=session_id))
    except ValueError:
        flash("Invalid amount entered.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    expense = Expense.query.filter_by(id=expense_id, session_id=session_id).first()
    if not expense:
        flash("Expense not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    expense.amount = new_amount
    db.session.commit()
    flash("Expense amount updated successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/edit_expense_category/<session_id>/<expense_id>', methods=['POST'])
@admin_required
def edit_expense_category(session_id, expense_id):
    new_cat = request.form.get('new_category', '').strip()
    if not new_cat:
        flash("Category name cannot be empty.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    expense = Expense.query.filter_by(id=expense_id, session_id=session_id).first()
    if not expense:
        flash("Expense not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    # Capitalize
    if not new_cat[0].isupper():
        new_cat = new_cat[0].upper() + new_cat[1:]
    
    existing_category = Category.query.filter_by(session_id=session_id, name=new_cat).first()
    if not existing_category:
        # Create the new category if needed
        created_cat = Category(session_id=session_id, name=new_cat)
        db.session.add(created_cat)
        db.session.commit()

    expense.category = new_cat
    db.session.commit()
    flash("Expense category updated successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/delete_expense/<session_id>/<expense_id>', methods=['POST'])
@admin_required
def delete_expense(session_id, expense_id):
    expense = Expense.query.filter_by(id=expense_id, session_id=session_id).first()
    if not expense:
        flash("Expense not found.", "error")
        return redirect(url_for('edit_admin', session_id=session_id))

    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully.", "success")
    return redirect(url_for('edit_admin', session_id=session_id))

@app.route('/apply_categories/<session_id>', methods=['POST'])
def apply_categories(session_id):
    """
    Updates person→category assignments based on posted form checkboxes.
    Then redirects back to the 'view_session' page.
    """
    sm = SessionModel.query.filter_by(id=session_id).first()
    if not sm:
        flash("Session not found.", "error")
        return redirect(url_for('initial_page'))

    persons = Person.query.filter_by(session_id=session_id).all()
    all_categories = sorted([c.name for c in Category.query.filter_by(session_id=session_id).all()])

    # Convert person_categories JSON into a Python dict
    person_categories = json.loads(sm.person_categories_json or '{}')

    # For every person, build a new list of categories from the form
    updated_categories = {}
    for p in persons:
        updated_categories[p.name] = []
        for cat in all_categories:
            # The checkbox is named "<person_name>_<cat>"
            checkbox_name = f"{p.name}_{cat}"
            if checkbox_name in request.form:
                updated_categories[p.name].append(cat)

    # Save it back to the DB
    sm.person_categories_json = json.dumps(updated_categories)
    db.session.commit()

    flash("Categories updated successfully.", "success")
    return redirect(url_for('view_session', session_id=session_id))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=True)