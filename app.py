from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from functools import wraps
from datetime import date, datetime

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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Lütfen önce giriş yapın."}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON verisi bulunamadı"}), 400
        
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                         (username, password))
            conn.commit()
            return jsonify({"message": "Kayıt başarılı!"}), 201
        except sqlite3.IntegrityError:
            return jsonify({"error": "Bu kullanıcı adı zaten alınmış."}), 409
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON verisi bulunamadı"}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({"message": "Giriş başarılı!", "username": user['username']}), 200
        else:
            return jsonify({"error": "Hatalı kullanıcı adı veya şifre."}), 401
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({"message": "Oturum kapatıldı."}), 200

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
            action_date_str = item_data['action_date'][:10] 
            action_date = datetime.strptime(action_date_str, '%Y-%m-%d').date()

            days_passed = (today - action_date).days
            if days_passed < 0:
                days_passed = 0 

            consumed_amount = days_passed * item_data['daily_food_gram']
            remaining_amount = item_data['total_amount'] - consumed_amount

            if remaining_amount < 0:
                remaining_amount = 0

            if item_data['daily_food_gram'] > 0:
                remaining_days = remaining_amount // item_data['daily_food_gram']
            else:
                remaining_days = 0

            item_data['calculated_remaining_amount'] = remaining_amount
            item_data['food_remaining_days'] = remaining_days
            item_data['days_left'] = None 

        elif item_data['next_due_date']:
            target_date = datetime.strptime(item_data['next_due_date'], '%Y-%m-%d').date()
            item_data['days_left'] = (target_date - today).days

        processed_items.append(item_data)

    return render_template('dashboard.html', username=username, pets=pets, items=processed_items)
@app.route('/delete-pet', methods=['DELETE'])
@login_required
def delete_pet():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON verisi bulunamadı"}), 400
        
    pet_id = data.get('id')
    user_id = session['user_id'] 

    if not pet_id:
        return jsonify({"error": "Silinecek evcil hayvanın ID'si (id) gereklidir!"}), 400

    conn = get_db_connection()
    try:

        cursor = conn.execute('DELETE FROM pets WHERE id = ? AND user_id = ?', (pet_id, user_id))

        if cursor.rowcount == 0:
            return jsonify({"error": "Kayıt bulunamadı veya bu evcil hayvanı silme yetkiniz yok!"}), 404
            
        conn.commit() 
        return jsonify({"message": "Evcil hayvan başarıyla silindi!"}), 200
        
    except Exception as e:
        return jsonify({"error": "Silme işlemi sırasında sunucuda bir hata oluştu!"}), 500
    finally:
        conn.close() 


@app.route('/pets', methods=['GET', 'POST', 'PUT'])
@login_required
def pets():
    if request.method == 'GET':
        user_id = session['user_id']
        conn = get_db_connection()
        pets = conn.execute('SELECT * FROM pets WHERE user_id = ?', (user_id,)).fetchall()
        conn.close()
        return jsonify([dict(pet) for pet in pets]), 200

    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON verisi bulunamadı"}), 400
            
        user_id = session['user_id']
        name = data.get('name')
        species = data.get('species')

        try:
            dailyfoodgram = int(data.get('daily_food_gram'))
        except (ValueError, TypeError):
            return jsonify({"error": "Lütfen geçerli bir sayı girin!"}), 400

        if dailyfoodgram <= 0:
            return jsonify({"error": "Günlük mama miktarı 0'dan büyük olmalıdır!"}), 400
            
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO pets (user_id, name, species, daily_food_gram) VALUES (?,?,?,?)', 
                         (user_id, name, species, dailyfoodgram))
            conn.commit()
            return jsonify({"message": "Evcil hayvan başarıyla eklendi!"}), 201
        except:
            return jsonify({"error": "Kayıt sırasında bir hata oluştu!"}), 500
        finally:
            conn.close()
    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON verisi bulunamadı"}), 400
            
        user_id = session['user_id']
        pet_id = data.get('id') 
        name = data.get('name')
        species = data.get('species')

        if not pet_id:
            return jsonify({"error": "Güncellenecek evcil hayvanın ID'si (id) gereklidir!"}), 400

        try:
            dailyfoodgram = int(data.get('daily_food_gram'))
        except (ValueError, TypeError):
            return jsonify({"error": "Lütfen geçerli bir sayı girin!"}), 400

        if dailyfoodgram <= 0:
            return jsonify({"error": "Günlük mama miktarı 0'dan büyük olmalıdır!"}), 400
            
        conn = get_db_connection()
        try:
            cursor = conn.execute('''
                UPDATE pets 
                SET name = ?, species = ?, daily_food_gram = ?
                WHERE id = ? AND user_id = ?
            ''', (name, species, dailyfoodgram, pet_id, user_id))

            if cursor.rowcount == 0:
                return jsonify({"error": "Kayıt bulunamadı veya bu evcil hayvanı güncelleme yetkiniz yok!"}), 404

            conn.commit()
            return jsonify({"message": "Evcil hayvan başarıyla güncellendi!"}), 200 
        except Exception as e:
            return jsonify({"error": "Güncelleme sırasında bir hata oluştu!"}), 500
        finally:
            conn.close()

@app.route('/routines/<int:pet_id>', methods=['GET'])
@login_required
def get_routines(pet_id):
  
    user_id = session['user_id']
    
    conn = get_db_connection()
    try:
        routines = conn.execute('''
            SELECT ir.* FROM inventory_and_routines ir
            JOIN pets p ON ir.pet_id = p.id
            WHERE ir.pet_id = ? AND p.user_id = ?
        ''', (pet_id, user_id)).fetchall()
        
        return jsonify([dict(routine) for routine in routines]), 200
        
    except Exception as e:
        return jsonify({"error": "Kayıtlar getirilirken bir hata oluştu!"}), 500
    finally:
        conn.close()

@app.route('/routines', methods=['POST', 'PUT'])
@login_required
def routines():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON verisi bulunamadı"}), 400
        
    user_id = session['user_id']
    conn = get_db_connection()

    if request.method == 'POST':
        pet_id = data.get('pet_id')
        item_type = data.get('item_type')
        total_amount = data.get('total_amount') 
        action_date = data.get('action_date')
        routine_date = data.get('routine_date')

        if not pet_id or not item_type:
            return jsonify({"error": "pet_id ve item_type alanları zorunludur!"}), 400

        try:
            pet_check = conn.execute('SELECT id FROM pets WHERE id = ? AND user_id = ?', (pet_id, user_id)).fetchone()
            
            if not pet_check:
                return jsonify({"error": "Bu evcil hayvan size ait değil veya bulunamadı!"}), 403

            conn.execute('''
                INSERT INTO inventory_and_routines (pet_id, item_type, total_amount, action_date, routine_date) 
                VALUES (?,?,?,?,?)
            ''', (pet_id, item_type, total_amount, action_date, routine_date))
            
            conn.commit()
            return jsonify({"message": "Kayıt başarıyla eklendi!"}), 201
            
        except Exception as e:
            return jsonify({"error": "Kayıt sırasında bir hata oluştu!"}), 500
        finally:
            conn.close()

    if request.method == 'PUT':
        routine_id = data.get('id') 
        item_type = data.get('item_type')
        total_amount = data.get('total_amount')
        action_date = data.get('action_date')
        routine_date = data.get('routine_date')

        if not routine_id:
            return jsonify({"error": "Güncellenecek kaydın ID'si (id) gereklidir!"}), 400

        try:
            cursor = conn.execute('''
                UPDATE inventory_and_routines 
                SET item_type = ?, total_amount = ?, action_date = ?, routine_date = ?
                WHERE id = ? AND pet_id IN (SELECT id FROM pets WHERE user_id = ?)
            ''', (item_type, total_amount, action_date, routine_date, routine_id, user_id))

            if cursor.rowcount == 0:
                return jsonify({"error": "Kayıt bulunamadı veya bu kaydı güncelleme yetkiniz yok!"}), 404

            conn.commit()
            return jsonify({"message": "Kayıt başarıyla güncellendi!"}), 200
            
        except Exception as e:
            return jsonify({"error": "Güncelleme sırasında bir hata oluştu!"}), 500
        finally:
            conn.close()

@app.route('/routines/delete/<int:r_id>', methods=['DELETE'])
@login_required
def delete_routines(r_id):
    user_id = session['user_id']
    conn = get_db_connection()
    
    try:
        cursor = conn.execute('''
            DELETE FROM inventory_and_routines 
            WHERE id = ? AND pet_id IN (SELECT id FROM pets WHERE user_id = ?)
        ''', (r_id, user_id))

        if cursor.rowcount == 0:
            return jsonify({"error": "Silinecek kayıt bulunamadı veya bu kaydı silme yetkiniz yok!"}), 404
            
        conn.commit() 
        return jsonify({"message": "Rutin/Stok kaydı başarıyla silindi!"}), 200
        
    except Exception as e:
        return jsonify({"error": "Silme işlemi sırasında sunucuda bir hata oluştu!"}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)