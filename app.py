from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from functools import wraps

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
            total_amount INTEGER NOT NULL,
            action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    conn.close()

    pets_list = [dict(pet) for pet in pets]
    return jsonify({"username": username, "pets": pets_list}), 200

@app.route('/pets', methods=['GET', 'POST'])
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

if __name__ == '__main__':
    app.run(debug=True)