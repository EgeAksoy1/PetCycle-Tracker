from flask import Flask, redirect, url_for, session
from datetime import datetime
from db_connection import init_db
from auth import auth_bp
from routes import routes_bp

app = Flask(__name__)
app.secret_key = 'petcycle-super-secret-key'

init_db()

app.register_blueprint(auth_bp)
app.register_blueprint(routes_bp)

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('routes.dashboard'))
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(debug=True)