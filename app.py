from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    username = session['username']

    conn = get_db_connection()
    pets = conn.execute('SELECT * FROM pets WHERE user_id = ?', (user_id,)).fetchall()

    items = conn.execute('''
        SELECT ir.*, p.name as pet_name, p.daily_food_gram
        FROM inventory_and_routines ir
        JOIN pets p ON ir.pet_id = p.id
        WHERE p.user_id = ?
    ''', (user_id,)).fetchall()

    conn.close()

    today = date.today()
    processed_items = []

    for item in items:
        item_data = dict(item)

        if item_data['item_type'] == 'Mama' and item_data['total_amount'] is not None:
            action_date_str = item_data['last_action_date'][:10]
            action_date = datetime.strptime(action_date_str, '%Y-%m-%d').date()

            days_passed = max((today - action_date).days, 0)
            consumed_amount = days_passed * item_data['daily_food_gram']
            remaining_amount = max(item_data['total_amount'] - consumed_amount, 0)

            daily = item_data['daily_food_gram']
            remaining_days = remaining_amount // daily if daily > 0 else 0

            item_data['calculated_remaining_amount'] = remaining_amount
            item_data['food_remaining_days'] = remaining_days
            item_data['days_left'] = None

        elif item_data['next_due_date']:
            target_date = datetime.strptime(item_data['next_due_date'], '%Y-%m-%d').date()
            item_data['days_left'] = (target_date - today).days

        processed_items.append(item_data)

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
    """PUT yerine POST + gizli _method alanı kullanılır."""
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

        today = date.today()
        processed = []
        for r in routines:
            rd = dict(r)
            if rd['next_due_date']:
                target = datetime.strptime(rd['next_due_date'], '%Y-%m-%d').date()
                rd['days_left'] = (target - today).days
            else:
                rd['days_left'] = None
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

    if total_amount is None or interval_days is None:
        flash('hata')
        return redirect(url_for('pets'))
    
    last_action_date = request.form.get('last_action_date') or None  

    if not pet_id or not item_type:
        flash('Tür alanı zorunludur!', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    next_due_date = None
    if interval_days:
        try:
            interval_days = int(interval_days)
            if last_action_date:
                base_date = datetime.strptime(last_action_date, '%Y-%m-%d').date()
            else:
                base_date = date.today()  # DB default ile aynı mantık
            next_due_date = (base_date + __import__('datetime').timedelta(days=interval_days)).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            flash('Geçersiz aralık değeri!', 'danger')
            return redirect(url_for('get_routines', pet_id=pet_id))

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
            item_type     = routine['item_type']
            interval_days = routine['interval_days']

            pet_row = conn.execute(
                'SELECT daily_food_gram FROM pets WHERE id = ?',
                (routine['pet_id'],)
            ).fetchone()
            daily_gram = pet_row['daily_food_gram'] if pet_row else 0

            old_total        = routine['total_amount'] or 0
            new_total        = max(old_total - daily_gram, 0)
            total_amount     = new_total
            last_action_date = routine['last_action_date']
            next_due_date    = routine['next_due_date']

        else:
            item_type        = request.form.get('item_type', '').strip()
            total_amount     = request.form.get('total_amount') or None
            interval_days    = request.form.get('interval_days') or None
            last_action_date = request.form.get('last_action_date') or None

            next_due_date = None
            if interval_days:
                try:
                    interval_days = int(interval_days)
                    base_date = (
                        datetime.strptime(last_action_date, '%Y-%m-%d').date()
                        if last_action_date else date.today()
                    )
                    next_due_date = (base_date + timedelta(days=interval_days)).strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    flash('Geçersiz aralık değeri!', 'danger')
                    return redirect(url_for('get_routines', pet_id=pet_id))

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