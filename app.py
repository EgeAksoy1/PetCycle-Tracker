from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from functools import wraps
from datetime import date, datetime, timedelta

app = Flask(__name__)
app.secret_key = 'petcycle-super-secret-key'
DATABASE = 'petcycle.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            species TEXT NOT NULL,
            daily_food_gram INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_and_routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            total_amount INTEGER,
            interval_days INTEGER,
            next_due_date DATE,
            last_action_date DATE DEFAULT (date('now', 'localtime')),
            FOREIGN KEY (pet_id) REFERENCES pets (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen önce giriş yapın.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ─── BUSINESS LOGIC ──────────────────────────────────────────────────────────

def calculate_food_remaining(total_amount, daily_food_gram, last_action_date_str, today=None):
    if today is None:
        today = date.today()
    action_date = datetime.strptime(last_action_date_str[:10], '%Y-%m-%d').date()
    days_passed = max((today - action_date).days, 0)
    consumed = days_passed * daily_food_gram
    remaining_amount = max(total_amount - consumed, 0)
    remaining_days = remaining_amount // daily_food_gram if daily_food_gram > 0 else 0
    return {
        'calculated_remaining_amount': remaining_amount,
        'food_remaining_days': remaining_days
    }

def calculate_next_due_date(last_action_date_str, interval_days):
    if not interval_days:
        return None
    if last_action_date_str:
        base_date = datetime.strptime(last_action_date_str[:10], '%Y-%m-%d').date()
    else:
        base_date = date.today()
    return (base_date + timedelta(days=int(interval_days))).strftime('%Y-%m-%d')

def calculate_days_left(next_due_date_str, today=None):
    if today is None:
        today = date.today()
    if not next_due_date_str:
        return None
    target = datetime.strptime(next_due_date_str[:10], '%Y-%m-%d').date()
    return (target - today).days

def calculate_fed(total_amount, daily_food_gram):
    return max((total_amount or 0) - daily_food_gram, 0)

# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Kullanıcı adı ve şifre boş bırakılamaz.', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                         (username, password))
            conn.commit()
            flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Bu kullanıcı adı zaten alınmış.', 'danger')
            return redirect(url_for('register'))
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Hoş geldin, {user["username"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Hatalı kullanıcı adı veya şifre.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Oturum kapatıldı.', 'info')
    return redirect(url_for('login'))

# ─── DASHBOARD ───────────────────────────────────────────────────────────────

def get_pets():
    user_id = session['user_id']
    conn = get_db_connection()
    pets = conn.execute('SELECT * FROM pets WHERE user_id = ?', (user_id,)).fetchall()
    conn.close()
    return pets

def get_items():
    user_id = session['user_id']
    conn = get_db_connection()
    items = conn.execute('''
        SELECT ir.*, p.name as pet_name, p.daily_food_gram
        FROM inventory_and_routines ir
        JOIN pets p ON ir.pet_id = p.id
        WHERE p.user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()

    processed_items = []
    for item in items:
        item_data = dict(item)
        if item_data['item_type'] == 'Mama' and item_data['total_amount'] is not None:
            result = calculate_food_remaining(
                item_data['total_amount'],
                item_data['daily_food_gram'],
                item_data['last_action_date']
            )
            item_data['calculated_remaining_amount'] = result['calculated_remaining_amount']
            item_data['food_remaining_days'] = result['food_remaining_days']
            item_data['days_left'] = None
        elif item_data['next_due_date']:
            item_data['days_left'] = calculate_days_left(item_data['next_due_date'])
        processed_items.append(item_data)

    return processed_items

@app.route('/dashboard')
@login_required
def dashboard():
    pets = get_pets()
    username = session['username']
    processed_items = get_items()
    return render_template('dashboard.html', username=username, pets=pets, items=processed_items)

# ─── PETS ────────────────────────────────────────────────────────────────────

@app.route('/pets', methods=['GET', 'POST'])
@login_required
def pets():
    user_id = session['user_id']

    if request.method == 'GET':
        conn = get_db_connection()
        rows = conn.execute('SELECT * FROM pets WHERE user_id = ?', (user_id,)).fetchall()
        conn.close()
        return render_template('pets.html', pets=rows)

    name = request.form.get('name', '').strip()
    species = request.form.get('species', '').strip()

    try:
        dailyfoodgram = int(request.form.get('daily_food_gram', 0))
    except ValueError:
        flash('Lütfen geçerli bir sayı girin!', 'danger')
        return redirect(url_for('pets'))

    if dailyfoodgram <= 0:
        flash('Günlük mama miktarı 0\'dan büyük olmalıdır!', 'danger')
        return redirect(url_for('pets'))

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO pets (user_id, name, species, daily_food_gram) VALUES (?,?,?,?)',
                     (user_id, name, species, dailyfoodgram))
        conn.commit()
        flash('Evcil hayvan başarıyla eklendi!', 'success')
    except Exception:
        flash('Kayıt sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('pets'))

@app.route('/pets/<int:pet_id>/edit', methods=['POST'])
@login_required
def edit_pet(pet_id):
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    species = request.form.get('species', '').strip()

    try:
        dailyfoodgram = int(request.form.get('daily_food_gram', 0))
    except ValueError:
        flash('Lütfen geçerli bir sayı girin!', 'danger')
        return redirect(url_for('pets'))

    if dailyfoodgram <= 0:
        flash('Günlük mama miktarı 0\'dan büyük olmalıdır!', 'danger')
        return redirect(url_for('pets'))

    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            UPDATE pets SET name = ?, species = ?, daily_food_gram = ?
            WHERE id = ? AND user_id = ?
        ''', (name, species, dailyfoodgram, pet_id, user_id))

        if cursor.rowcount == 0:
            flash('Kayıt bulunamadı veya yetkiniz yok!', 'danger')
        else:
            conn.commit()
            flash('Evcil hayvan başarıyla güncellendi!', 'success')
    except Exception:
        flash('Güncelleme sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('pets'))

@app.route('/pets/<int:pet_id>/delete', methods=['POST'])
@login_required
def delete_pet(pet_id):
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        conn.execute('''
            DELETE FROM inventory_and_routines WHERE pet_id = ?
            AND pet_id IN (SELECT id FROM pets WHERE user_id = ?)
        ''', (pet_id, user_id))

        cursor = conn.execute('DELETE FROM pets WHERE id = ? AND user_id = ?',
                              (pet_id, user_id))
        if cursor.rowcount == 0:
            flash('Kayıt bulunamadı veya yetkiniz yok!', 'danger')
        else:
            conn.commit()
            flash('Evcil hayvan başarıyla silindi!', 'success')
    except Exception:
        flash('Silme işlemi sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('pets'))

# ─── ROUTINES / INVENTORY ────────────────────────────────────────────────────

@app.route('/routines/<int:pet_id>', methods=['GET'])
@login_required
def get_routines(pet_id):
    user_id = session['user_id']
    conn = get_db_connection()
    try:
        pet = conn.execute(
            'SELECT * FROM pets WHERE id = ? AND user_id = ?',
            (pet_id, user_id)
        ).fetchone()

        if not pet:
            flash('Bu evcil hayvana erişim yetkiniz yok!', 'danger')
            return redirect(url_for('pets'))

        routines = conn.execute('''
            SELECT ir.* FROM inventory_and_routines ir
            JOIN pets p ON ir.pet_id = p.id
            WHERE ir.pet_id = ? AND p.user_id = ?
        ''', (pet_id, user_id)).fetchall()

        processed = []
        for r in routines:
            rd = dict(r)
            rd['days_left'] = calculate_days_left(rd['next_due_date'])
            processed.append(rd)

        return render_template('routines.html', pet=pet, routines=processed)
    finally:
        conn.close()

@app.route('/routines', methods=['POST'])
@login_required
def add_routine():
    user_id = session['user_id']
    pet_id = request.form.get('pet_id')
    item_type = request.form.get('item_type', '').strip()
    total_amount = request.form.get('total_amount') or None
    interval_days = request.form.get('interval_days') or None
    last_action_date = request.form.get('last_action_date') or None

    if not pet_id or not item_type:
        flash('Tür alanı zorunludur!', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    next_due_date = calculate_next_due_date(last_action_date, interval_days)

    if interval_days:
        interval_days = int(interval_days)

    if last_action_date is None:
        last_action_date = date.today().strftime('%Y-%m-%d')

    conn = get_db_connection()
    try:
        pet_check = conn.execute(
            'SELECT id FROM pets WHERE id = ? AND user_id = ?',
            (pet_id, user_id)
        ).fetchone()

        if not pet_check:
            flash('Bu evcil hayvan size ait değil veya bulunamadı!', 'danger')
            return redirect(url_for('dashboard'))

        conn.execute('''
            INSERT INTO inventory_and_routines
                (pet_id, item_type, total_amount, interval_days, next_due_date, last_action_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pet_id, item_type, total_amount, interval_days, next_due_date, last_action_date))
        conn.commit()
        flash('Kayıt başarıyla eklendi!', 'success')
    except Exception as e:
        flash('Kayıt sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('get_routines', pet_id=pet_id))

@app.route('/routines/<int:r_id>/edit', methods=['POST'])
@login_required
def edit_routine(r_id):
    user_id = session['user_id']
    pet_id  = request.form.get('pet_id')
    is_fed  = request.form.get('is_fed')
    is_done = request.form.get('is_done')

    if not pet_id:
        flash('pet_id bulunamadı!', 'danger')
        return redirect(url_for('dashboard'))

    pet_id = int(pet_id)

    conn = get_db_connection()
    try:
        routine = conn.execute('''
            SELECT ir.* FROM inventory_and_routines ir
            JOIN pets p ON ir.pet_id = p.id
            WHERE ir.id = ? AND p.user_id = ?
        ''', (r_id, user_id)).fetchone()

        if not routine:
            flash('Kayıt bulunamadı veya yetkiniz yok!', 'danger')
            return redirect(url_for('get_routines', pet_id=pet_id))

        if is_fed:
            pet_row = conn.execute(
                'SELECT daily_food_gram FROM pets WHERE id = ?',
                (routine['pet_id'],)
            ).fetchone()
            daily_gram = pet_row['daily_food_gram'] if pet_row else 0

            item_type        = routine['item_type']
            interval_days    = routine['interval_days']
            total_amount     = calculate_fed(routine['total_amount'], daily_gram)
            today            = date.today()
            last_action_date = today.strftime('%Y-%m-%d')
            next_due_date    = calculate_next_due_date(last_action_date, interval_days)

        elif is_done:
            today            = date.today()
            item_type        = routine['item_type']
            interval_days    = routine['interval_days']
            total_amount     = routine['total_amount']
            last_action_date = today.strftime('%Y-%m-%d')
            next_due_date    = calculate_next_due_date(last_action_date, interval_days)

        else:
            item_type        = request.form.get('item_type', '').strip()
            total_amount     = request.form.get('total_amount') or None
            interval_days    = request.form.get('interval_days') or None
            last_action_date = request.form.get('last_action_date') or None
            next_due_date    = calculate_next_due_date(last_action_date, interval_days)

            if interval_days:
                interval_days = int(interval_days)

        cursor = conn.execute('''
            UPDATE inventory_and_routines
            SET item_type = ?, total_amount = ?, interval_days = ?,
                next_due_date = ?, last_action_date = ?
            WHERE id = ? AND pet_id IN (SELECT id FROM pets WHERE user_id = ?)
        ''', (item_type, total_amount, interval_days, next_due_date, last_action_date, r_id, user_id))

        if cursor.rowcount == 0:
            flash('Kayıt bulunamadı veya yetkiniz yok!', 'danger')
        else:
            conn.commit()
            flash('Mama verildi! Stok güncellendi.' if is_fed else 'Kayıt başarıyla güncellendi!', 'success')

    except Exception as e:
        flash(f'Güncelleme sırasında bir hata oluştu: {e}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('get_routines', pet_id=pet_id))

@app.route('/routines/<int:r_id>/delete', methods=['POST'])
@login_required
def delete_routine(r_id):
    user_id = session['user_id']
    pet_id = request.form.get('pet_id')

    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            DELETE FROM inventory_and_routines
            WHERE id = ? AND pet_id IN (SELECT id FROM pets WHERE user_id = ?)
        ''', (r_id, user_id))

        if cursor.rowcount == 0:
            flash('Silinecek kayıt bulunamadı veya yetkiniz yok!', 'danger')
        else:
            conn.commit()
            flash('Kayıt başarıyla silindi!', 'success')
    except Exception:
        flash('Silme işlemi sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('get_routines', pet_id=pet_id) if pet_id else url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)