from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import date
from db_connection import get_db_connection
from business_logic import calculate_days_left, calculate_fed, calculate_food_remaining, calculate_next_due_date 

routes_bp = Blueprint('routes', __name__)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen önce giriş yapın.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

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

@routes_bp.route('/dashboard')
@login_required
def dashboard():
    pets = get_pets()
    username = session['username']
    processed_items = get_items()
    return render_template('dashboard.html', username=username, pets=pets, items=processed_items)

# ─── PETS ────────────────────────────────────────────────────────────────────

@routes_bp.route('/pets', methods=['GET', 'POST'])
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
        return redirect(url_for('routes.pets'))

    if dailyfoodgram <= 0:
        flash('Günlük mama miktarı 0\'dan büyük olmalıdır!', 'danger')
        return redirect(url_for('routes.pets'))

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

    return redirect(url_for('routes.pets'))

@routes_bp.route('/pets/<int:pet_id>/edit', methods=['POST'])
@login_required
def edit_pet(pet_id):
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    species = request.form.get('species', '').strip()

    try:
        dailyfoodgram = int(request.form.get('daily_food_gram', 0))
    except ValueError:
        flash('Lütfen geçerli bir sayı girin!', 'danger')
        return redirect(url_for('routes.pets'))

    if dailyfoodgram <= 0:
        flash('Günlük mama miktarı 0\'dan büyük olmalıdır!', 'danger')
        return redirect(url_for('routes.pets'))

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

    return redirect(url_for('routes.pets'))

@routes_bp.route('/pets/<int:pet_id>/delete', methods=['POST'])
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

    return redirect(url_for('routes.pets'))

# ─── ROUTINES ────────────────────────────────────────────────────────────────

@routes_bp.route('/routines/<int:pet_id>', methods=['GET'])
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

@routes_bp.route('/routines', methods=['POST'])
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
        return redirect(request.referrer or url_for('routes.dashboard'))

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
            return redirect(url_for('routes.dashboard'))

        conn.execute('''
            INSERT INTO inventory_and_routines
                (pet_id, item_type, total_amount, interval_days, next_due_date, last_action_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pet_id, item_type, total_amount, interval_days, next_due_date, last_action_date))
        conn.commit()
        flash('Kayıt başarıyla eklendi!', 'success')
    except Exception:
        flash('Kayıt sırasında bir hata oluştu!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('routes.get_routines', pet_id=pet_id))

@routes_bp.route('/routines/<int:r_id>/edit', methods=['POST'])
@login_required
def edit_routine(r_id):
    user_id = session['user_id']
    pet_id  = request.form.get('pet_id')
    is_fed  = request.form.get('is_fed')
    is_done = request.form.get('is_done')

    if not pet_id:
        flash('pet_id bulunamadı!', 'danger')
        return redirect(url_for('routes.dashboard'))

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
            return redirect(url_for('routes.get_routines', pet_id=pet_id))

        if is_fed:
            pet_row = conn.execute(
                'SELECT daily_food_gram FROM pets WHERE id = ?',
                (routine['pet_id'],)
            ).fetchone()
            daily_gram       = pet_row['daily_food_gram'] if pet_row else 0
            item_type        = routine['item_type']
            interval_days    = routine['interval_days']
            total_amount     = calculate_fed(routine['total_amount'], daily_gram)
            last_action_date = date.today().strftime('%Y-%m-%d')
            next_due_date    = calculate_next_due_date(last_action_date, interval_days)

        elif is_done:
            item_type        = routine['item_type']
            interval_days    = routine['interval_days']
            total_amount     = routine['total_amount']
            last_action_date = date.today().strftime('%Y-%m-%d')
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

    return redirect(url_for('routes.get_routines', pet_id=pet_id))

@routes_bp.route('/routines/<int:r_id>/delete', methods=['POST'])
@login_required
def delete_routine(r_id):
    user_id = session['user_id']
    pet_id  = request.form.get('pet_id')

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

    return redirect(url_for('routes.get_routines', pet_id=pet_id) if pet_id else url_for('routes.dashboard'))