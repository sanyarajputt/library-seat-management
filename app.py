from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from dotenv import load_dotenv
from datetime import datetime, timedelta
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

if __name__ == '__main__':
    app.run(debug=True)