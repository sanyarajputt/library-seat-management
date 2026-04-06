from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from dotenv import load_dotenv
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import os

load_dotenv()

app = Flask(__name__)

app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.secret_key = os.getenv('SECRET_KEY')

mysql = MySQL(app)

@app.route('/')
def home():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM seats")
    count = cursor.fetchone()
    return f'Database connected! Total seats: {count[0]}'

@app.route('/allocate', methods=['POST'])
def allocate():
    data = request.get_json()
    seat_number = data.get('seat_number')
    student_roll = data.get('student_roll')

    cursor = mysql.connection.cursor()

    cursor.execute("SELECT is_blocked, blocked_until FROM penalties WHERE student_roll = %s", (student_roll,))
    penalty = cursor.fetchone()
    if penalty and penalty[0] and penalty[1] > datetime.now():
        return jsonify({'success': False, 'message': 'You are blocked from booking seats for 24 hours due to ghost-seat reports!'})

    cursor.execute("SELECT * FROM seats WHERE seat_number = %s", (seat_number,))
    seat = cursor.fetchone()

    if seat[2]:
        return jsonify({'success': False, 'message': 'Seat already occupied!'})

    allocated_at = datetime.now()
    expires_at = allocated_at + timedelta(hours=2)

    cursor.execute("""
        UPDATE seats 
        SET is_occupied=TRUE, student_roll=%s, allocated_at=%s, expires_at=%s 
        WHERE seat_number=%s
    """, (student_roll, allocated_at, expires_at, seat_number))
    mysql.connection.commit()

    return jsonify({'success': True, 'message': f'Seat {seat_number} allocated to {student_roll} for 2 hours!'})

@app.route('/release', methods=['POST'])
def release():
    data = request.get_json()
    seat_number = data.get('seat_number')

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE seats 
        SET is_occupied=FALSE, student_roll=NULL, allocated_at=NULL, expires_at=NULL 
        WHERE seat_number=%s
    """, (seat_number,))
    mysql.connection.commit()

    return jsonify({'success': True, 'message': f'Seat {seat_number} released!'})

@app.route('/seats', methods=['GET'])
def get_seats():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT seat_number, is_occupied, student_roll, expires_at FROM seats")
    rows = cursor.fetchall()

    seats = []
    for row in rows:
        seats.append({
            'seat_number': row[0],
            'is_occupied': bool(row[1]),
            'student_roll': row[2],
            'expires_at': str(row[3]) if row[3] else None
        })

    return jsonify(seats)

@app.route('/report', methods=['POST'])
def report():
    data = request.get_json()
    seat_number = data.get('seat_number')

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT student_roll FROM seats WHERE seat_number = %s", (seat_number,))
    seat = cursor.fetchone()

    if not seat or not seat[0]:
        return jsonify({'success': False, 'message': 'Seat is not occupied!'})

    student_roll = seat[0]

    cursor.execute("SELECT * FROM penalties WHERE student_roll = %s", (student_roll,))
    penalty = cursor.fetchone()

    if not penalty:
        cursor.execute("""
            INSERT INTO penalties (student_roll, report_count, is_blocked, last_reported) 
            VALUES (%s, 1, FALSE, NOW())
        """, (student_roll,))
    else:
        new_count = penalty[2] + 1
        is_blocked = new_count >= 2
        blocked_until = datetime.now() + timedelta(hours=24) if is_blocked else None
        cursor.execute("""
            UPDATE penalties 
            SET report_count=%s, is_blocked=%s, blocked_until=%s, last_reported=NOW()
            WHERE student_roll=%s
        """, (new_count, is_blocked, blocked_until, student_roll))

    mysql.connection.commit()

    if penalty and penalty[2] + 1 >= 2:
        return jsonify({'success': True, 'message': f'{student_roll} has been blocked for 24 hours!'})
    return jsonify({'success': True, 'message': f'Warning issued to {student_roll}!'})

@app.route('/penalties', methods=['GET'])
def get_penalties():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT student_roll, report_count, is_blocked, blocked_until FROM penalties")
    rows = cursor.fetchall()

    penalties = []
    for row in rows:
        penalties.append({
            'student_roll': row[0],
            'report_count': row[1],
            'is_blocked': bool(row[2]),
            'blocked_until': str(row[3]) if row[3] else None
        })

    return jsonify(penalties)

def auto_expire_seats():
    with app.app_context():
        cursor = mysql.connection.cursor()
        cursor.execute("""
            UPDATE seats 
            SET is_occupied=FALSE, student_roll=NULL, allocated_at=NULL, expires_at=NULL 
            WHERE is_occupied=TRUE AND expires_at < NOW()
        """)
        mysql.connection.commit()
        cursor.close()

scheduler = BackgroundScheduler()
scheduler.add_job(func=auto_expire_seats, trigger='interval', minutes=1)
scheduler.start()

if __name__ == '__main__':
    app.run(debug=True)