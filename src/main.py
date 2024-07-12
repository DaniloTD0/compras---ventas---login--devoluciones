from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db  # Aquí importamos la conexión como 'db'
import mysql.connector
from datetime import date

app = Flask(__name__)
app.secret_key = 'supersecretkey'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rol = request.form['rol']

        cursor = db.db.cursor(dictionary=True)  # Utilizamos db.db para obtener la conexión

        if rol == 'empleado':
            cursor.execute('SELECT * FROM usuarios WHERE Nombre = %s AND cedula = %s', (username, password))
        else:
            cursor.execute('SELECT * FROM admin WHERE nombre = %s AND cc = %s', (username, password))

        user = cursor.fetchone()

        if user:
            session['id_usuario'] = user['ID_usuario'] if rol == 'empleado' else user['cc']
            if rol == 'empleado':
                return redirect(url_for('ventas'))
            else:
                return redirect(url_for('compras'))

        flash('Invalid username or password')
        return redirect(url_for('index'))

@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    cursor = db.db.cursor(dictionary=True)

    categorias = []
    productos = []
    selected_categoria_id = request.form.get('categoria_id', None)
    search_query = request.form.get('search_query', '')

    venta_id = session.get('venta_id')

    if request.method == 'POST':
        if 'id_producto' in request.form and 'cantidad' in request.form:
            id_producto = request.form['id_producto']
            cantidad = int(request.form['cantidad'])

            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto and producto['stock'] >= cantidad:
                try:
                    if not venta_id:
                        # Crear una nueva venta
                        cursor.execute('INSERT INTO ventas (fecha_venta, ID_usuario) VALUES (NOW(), %s)', (session['id_usuario'],))
                        db.db.commit()
                        venta_id = cursor.lastrowid
                        session['venta_id'] = venta_id

                    # Insertar detalle de venta
                    cursor.execute('INSERT INTO detalle_ventas (ID_venta, ID_producto, cantidad, valor_venta_producto) VALUES (%s, %s, %s, %s)', 
                                   (venta_id, id_producto, cantidad, producto['valor_producto']))
                    db.db.commit()

                    # Actualizar total de la venta
                    cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
                    total_venta = cursor.fetchone()['total'] or 0
                    cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, venta_id))
                    db.db.commit()

                    # Actualizar stock del producto
                    new_stock = producto['stock'] - cantidad
                    cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (new_stock, id_producto))
                    db.db.commit()

                    flash('Producto agregado a la venta')
                except mysql.connector.Error as err:
                    flash(f"Error al agregar producto a la venta: {err}")
            else:
                flash('No hay suficiente stock')
        else:
            flash('error')

    # Obtener categorías y productos para mostrar en la página
    cursor.execute('SELECT * FROM categoria_producto')
    categorias = cursor.fetchall()

    query = 'SELECT * FROM producto'
    if selected_categoria_id:
        query += ' WHERE ID_categoria_producto = %s'
        cursor.execute(query, (selected_categoria_id,))
    elif search_query:
        query += ' WHERE nombre_producto LIKE %s'
        cursor.execute(query, ('%' + search_query + '%',))
    else:
        cursor.execute(query)

    productos = cursor.fetchall()

    # Obtener detalles de la venta actual
    detalles_venta = []
    total_venta = 0
    if venta_id:
        cursor.execute('SELECT dv.ID_detalle_venta, dv.ID_venta, p.nombre_producto, dv.cantidad, dv.valor_venta_producto '
                       'FROM detalle_ventas dv '
                       'JOIN producto p ON dv.ID_producto = p.ID_producto '
                       'WHERE dv.ID_venta = %s', (venta_id,))
        detalles_venta = cursor.fetchall()

        cursor.execute('SELECT total FROM ventas WHERE ID_venta = %s', (venta_id,))
        total_venta = cursor.fetchone()['total'] or 0

    cursor.close()

    return render_template('ventas.html', categorias=categorias, productos=productos, detalles_venta=detalles_venta, selected_categoria_id=selected_categoria_id, search_query=search_query, total_venta=total_venta)

@app.route('/ventas/editar/<int:id>', methods=['POST'])
def editar_producto(id):
    if request.method == 'POST':
        nueva_cantidad = int(request.form['cantidad'])

        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
        detalle_venta = cursor.fetchone()

        if detalle_venta:
            id_producto = detalle_venta['ID_producto']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                diferencia = nueva_cantidad - detalle_venta['cantidad']
                nuevo_stock = producto['stock'] - diferencia
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

                cursor.execute('UPDATE detalle_ventas SET cantidad = %s WHERE ID_detalle_venta = %s', (nueva_cantidad, id))
                db.db.commit()

                # Actualizar total de la venta
                cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (detalle_venta['ID_venta'],))
                total_venta = cursor.fetchone()['total'] or 0
                cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, detalle_venta['ID_venta']))
                db.db.commit()

                flash('Producto editado correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/eliminar/<int:id>', methods=['POST'])
def eliminar_producto(id):
    cursor = db.db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
    detalle_venta = cursor.fetchone()

    if detalle_venta:
        id_producto = detalle_venta['ID_producto']
        cantidad = detalle_venta['cantidad']
        cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
        producto = cursor.fetchone()

        if producto:
            nuevo_stock = producto['stock'] + cantidad
            cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
            db.db.commit()

            cursor.execute('DELETE FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
            db.db.commit()

            # Actualizar total de la venta
            cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (detalle_venta['ID_venta'],))
            total_venta = cursor.fetchone()['total'] or 0
            cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, detalle_venta['ID_venta']))
            db.db.commit()

            flash('Producto eliminado correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/cancelar', methods=['POST'])
def cancelar_venta():
    venta_id = session.get('venta_id', None)

    if venta_id:
        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        detalles_venta = cursor.fetchall()

        for detalle in detalles_venta:
            id_producto = detalle['ID_producto']
            cantidad = detalle['cantidad']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                nuevo_stock = producto['stock'] + cantidad
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

        cursor.execute('DELETE FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        cursor.execute('DELETE FROM ventas WHERE ID_venta = %s', (venta_id,))
        db.db.commit()

        session.pop('venta_id', None)

        flash('Venta cancelada correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/finalizar', methods=['POST'])
def finalizar_venta():
    venta_id = session.get('venta_id', None)

    if venta_id:
        cursor = db.db.cursor(dictionary=True)
        
        # Asegurarse de que el total se ha calculado y actualizado correctamente
        cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        total_venta = cursor.fetchone()['total'] or 0
        cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, venta_id))
        db.db.commit()

        session.pop('venta_id', None)

        flash('Venta finalizada correctamente')

    return redirect(url_for('ventas'))

#compras

# Función para obtener la lista de proveedores
def obtener_proveedores():
    try:
        connection = db.db
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM proveedores"
        cursor.execute(query)
        proveedores = cursor.fetchall()
        return proveedores
    except Exception as e:
        print(f"Error al obtener proveedores: {str(e)}")
        return []

# Función para obtener la lista de productos filtrados por proveedor
def obtener_productos_filtrados(proveedor_id):
    try:
        connection = db.db
        cursor = connection.cursor(dictionary=True)
        if proveedor_id:
            query = "SELECT * FROM producto WHERE ID_proveedor = %s ORDER BY nombre_producto ASC"
            cursor.execute(query, (proveedor_id,))
        else:
            query = "SELECT * FROM producto ORDER BY nombre_producto ASC"
            cursor.execute(query)
        productos = cursor.fetchall()
        return productos
    except Exception as e:
        print(f"Error al obtener productos filtrados: {str(e)}")
        return []

# Función para buscar productos por nombre
def buscar_productos(nombre_producto):
    try:
        connection = db.db
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM producto WHERE nombre_producto LIKE %s ORDER BY nombre_producto ASC"
        cursor.execute(query, ('%' + nombre_producto + '%',))
        productos = cursor.fetchall()
        return productos
    except Exception as e:
        print(f"Error al buscar productos: {str(e)}")
        return []

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    if request.method == 'POST':
        if 'proveedor_id' in request.form:
            proveedor_id = request.form['proveedor_id']
            productos = obtener_productos_filtrados(proveedor_id)
        elif 'buscar' in request.form:
            nombre_producto = request.form['buscar']
            productos = buscar_productos(nombre_producto)
        else:
            flash('Acción no válida.', 'danger')
            return redirect(url_for('compras'))
    else:
        productos = obtener_productos_filtrados(None)  # Obtener todos los productos al cargar la página
    
    proveedores = obtener_proveedores()
    total_compra = calcular_total_compra(session.get('carrito', []))
    
    return render_template('compras.html', proveedores=proveedores, productos=productos, total_compra=total_compra, carrito=session.get('carrito', []))

# Función para agregar al carrito
@app.route('/agregar_al_carrito/<int:producto_id>', methods=['POST'])
def agregar_al_carrito(producto_id):
    cantidad = int(request.form['cantidad'])
    try:
        connection = db.db
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM producto WHERE ID_producto = %s"
        cursor.execute(query, (producto_id,))
        producto = cursor.fetchone()
        
        if producto:
            precio_total = producto['valor_producto'] * cantidad
            producto_carrito = {
                'ID_producto': producto['ID_producto'],
                'nombre_producto': producto['nombre_producto'],
                'cantidad': cantidad,
                'precio_total': precio_total
            }
            carrito = session.get('carrito', [])
            carrito.append(producto_carrito)
            session['carrito'] = carrito
            flash('Producto añadido al carrito.', 'success')
        else:
            flash('Producto no encontrado.', 'danger')
    except Exception as e:
        flash(f'Error al agregar producto al carrito: {str(e)}', 'danger')
    
    return redirect(url_for('compras'))


# Función para eliminar un producto del carrito de compras
@app.route('/eliminar_del_carrito/<int:index>', methods=['POST'])
def eliminar_del_carrito(index):
    carrito = session.get('carrito', [])
    if 0 <= index < len(carrito):
        del carrito[index]
        session['carrito'] = carrito
        flash('Producto eliminado del carrito.', 'success')
    else:
        flash('Índice de carrito no válido.', 'danger')
    
    return redirect(url_for('compras'))

# Función para calcular el total de la compra
def calcular_total_compra(carrito):
    total = 0
    for producto in carrito:
        total += float(producto['precio_total'])  # Asegúrate de que producto['precio_total'] sea numérico
    return total

# Función para cancelar la compra (vaciar carrito)
@app.route('/cancelar_compra', methods=['POST'])
def cancelar_compra():
    session.pop('carrito', None)
    flash('Compra cancelada.', 'info')
    return redirect(url_for('compras'))


@app.route('/finalizar_compra', methods=['POST'])
def finalizar_compra():
    carrito = session.get('carrito', [])
    if carrito:
        try:
            connection = db.db
            cursor = db.get_db_cursor()

            fecha_actual = date.today()
            insert_compra_query = "INSERT INTO compras (fecha_compra, valor_compra) VALUES (%s, %s)"
            cursor.execute(insert_compra_query, (fecha_actual, calcular_total_compra(carrito)))
            connection.commit()

            id_compra = cursor.lastrowid
            for item in carrito:
                producto_id = item.get('ID_producto')
                if producto_id is None:
                    flash(f'El producto en el carrito no tiene un ID válido.', 'danger')
                    continue

                cantidad = item['cantidad']
                precio_total = item['precio_total']

                obtener_proveedor_query = "SELECT ID_proveedor FROM producto WHERE ID_producto = %s"
                cursor.execute(obtener_proveedor_query, (producto_id,))
                proveedor_id_result = cursor.fetchone()

                if proveedor_id_result is None:
                    flash(f'No se encontró proveedor para el producto con ID {producto_id}.', 'warning')
                    continue
                
                proveedor_id = proveedor_id_result['ID_proveedor']
                valor_compra_producto = float(precio_total) * cantidad

                insert_detalle_query = "INSERT INTO detalle_compra (ID_compra, ID_producto, cantidad, ID_proveedor, valor_compra_producto) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(insert_detalle_query, (id_compra, producto_id, cantidad, proveedor_id, valor_compra_producto))
                connection.commit()

                # Actualizar el stock
                actualizar_stock_query = "UPDATE producto SET stock = stock + %s WHERE ID_producto = %s"
                cursor.execute(actualizar_stock_query, (cantidad, producto_id))
                connection.commit()

            session.pop('carrito', None)
            flash('Compra finalizada correctamente.', 'success')
        
        except Exception as e:
            flash(f'Error al finalizar compra: {str(e)}', 'danger')
            connection.rollback()
            return redirect(url_for('compras'))
        
        finally:
            cursor.close()

    else:
        flash('No hay productos en el carrito para finalizar la compra.', 'warning')

    return redirect(url_for('compras'))




if __name__ == '__main__':
    app.run(debug=True)