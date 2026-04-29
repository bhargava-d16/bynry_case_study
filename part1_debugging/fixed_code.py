from flask import request, jsonify
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation

@app.route('/api/products', methods=['POST'])
def create_product():
    # First, make sure we actually got JSON
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    required_fields = ['name', 'sku', 'price', 'warehouse_id', 'initial_quantity']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    # Validate price is actually a number
    try:
        price = Decimal(str(data['price']))
        if price < 0:
            return jsonify({"error": "Price cannot be negative"}), 400
    except InvalidOperation:
        return jsonify({"error": "Price must be a valid number"}), 400

    # Validate initial_quantity
    if not isinstance(data['initial_quantity'], int) or data['initial_quantity'] < 0:
        return jsonify({"error": "initial_quantity must be a non-negative integer"}), 400

    # Check SKU uniqueness before doing anything
    existing = Product.query.filter_by(sku=data['sku']).first()
    if existing:
        return jsonify({"error": f"SKU '{data['sku']}' already exists"}), 409

    # Check that the warehouse actually exists
    warehouse = Warehouse.query.get(data['warehouse_id'])
    if not warehouse:
        return jsonify({"error": "Warehouse not found"}), 404

    try:
        # Create the product — note: no warehouse_id here
        # because a product can exist in multiple warehouses.
        # That relationship lives in the Inventory table.
        product = Product(
            name=data['name'],
            sku=data['sku'],
            price=price,
            description=data.get('description')  # optional field
        )
        db.session.add(product)
        db.session.flush()  # gets us product.id without committing yet

        # Now create the inventory record linking product <-> warehouse
        inventory = Inventory(
            product_id=product.id,
            warehouse_id=data['warehouse_id'],
            quantity=data['initial_quantity']
        )
        db.session.add(inventory)

        # Single commit — both succeed or both fail together
        db.session.commit()

        return jsonify({
            "message": "Product created successfully",
            "product_id": product.id
        }), 201  # 201 Created, not 200

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Database error — possible duplicate SKU"}), 409

    except Exception as e:
        db.session.rollback()
        # In production you'd log this properly, not expose the raw error
        app.logger.error(f"Error creating product: {str(e)}")
        return jsonify({"error": "Something went wrong, please try again"}), 500