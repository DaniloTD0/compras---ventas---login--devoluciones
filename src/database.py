import mysql.connector

db = mysql.connector.connect(
    host='localhost',
    database='tienda',
    user='mercatododb',
    password='',
    port='3306'
)

def get_db_cursor():
    return db.cursor(dictionary=True)
