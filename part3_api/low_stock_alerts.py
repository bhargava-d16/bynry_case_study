from flask import jsonify
from sqlalchemy import text
from datetime import datetime, timedelta

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):

    # First check the company actually exists
    # No point running heavy queries if company_id is invalid
    company = Company.query.get(company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404

    # "Recent" = last 30 days. I'm hardcoding this for now,
    # but ideally this would be a config value or query param
    recent_cutoff = datetime.utcnow() - timedelta(days=30)

    # This is the main query — joining several tables together
    # Breaking it down:
    # 1. Get all inventory rows for this company's warehouses
    # 2. Only keep rows where current stock is below threshold
    # 3. Only keep products that had at least one sale in last 30 days
    # 4. Pull in supplier info for reordering
    # 5. Calculate avg daily sales to estimate days until stockout

    query = text("""
        SELECT
            p.id                    AS product_id,
            p.name                  AS product_name,
            p.sku                   AS sku,
            w.id                    AS warehouse_id,
            w.name                  AS warehouse_name,
            i.quantity              AS current_stock,
            i.low_stock_threshold   AS threshold,
            
            -- avg daily sales over last 30 days
            -- NULLIF prevents division by zero
            COALESCE(
                ROUND(
                    SUM(CASE 
                        WHEN il.change_type = 'sale' 
                        AND il.created_at >= :cutoff
                        THEN ABS(il.quantity_before - il.quantity_after)
                        ELSE 0 
                    END) / NULLIF(30.0, 0)
                , 2),
                0
            )                       AS avg_daily_sales,

            s.id                    AS supplier_id,
            s.name                  AS supplier_name,
            s.contact_email         AS supplier_email

        FROM inventory i
        JOIN products p         ON p.id = i.product_id
        JOIN warehouses w       ON w.id = i.warehouse_id
        
        -- Only warehouses belonging to this company
        JOIN companies c        ON c.id = w.company_id
        
        -- Get supplier (taking first one if multiple exist)
        LEFT JOIN supplier_products sp  ON sp.product_id = p.id
        LEFT JOIN suppliers s           ON s.id = sp.supplier_id

        -- Inventory logs to check recent sales activity
        LEFT JOIN inventory_logs il     ON il.inventory_id = i.id

        WHERE
            c.id = :company_id
            AND p.is_active = TRUE
            AND i.quantity < i.low_stock_threshold

        GROUP BY
            p.id, p.name, p.sku,
            w.id, w.name,
            i.quantity, i.low_stock_threshold,
            s.id, s.name, s.contact_email

        -- The "recent sales activity" filter:
        -- Only include products that had at least 1 sale in last 30 days
        HAVING SUM(
            CASE 
                WHEN il.change_type = 'sale' 
                AND il.created_at >= :cutoff 
                THEN 1 ELSE 0 
            END
        ) > 0

        ORDER BY i.quantity ASC  -- most critical (lowest stock) first
    """)

    try:
        results = db.session.execute(query, {
            "company_id": company_id,
            "cutoff": recent_cutoff
        }).fetchall()

    except Exception as e:
        app.logger.error(f"Low stock query failed for company {company_id}: {str(e)}")
        return jsonify({"error": "Failed to fetch alerts"}), 500

    # Build the response
    alerts = []
    for row in results:

        # Calculate days until stockout
        # If avg_daily_sales is 0 or null, we can't estimate — return null
        if row.avg_daily_sales and row.avg_daily_sales > 0:
            days_until_stockout = round(row.current_stock / row.avg_daily_sales)
        else:
            days_until_stockout = None  # can't estimate with no sales data

        alert = {
            "product_id":   row.product_id,
            "product_name": row.product_name,
            "sku":          row.sku,
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "current_stock": row.current_stock,
            "threshold":    row.threshold,
            "days_until_stockout": days_until_stockout,
            "supplier": {
                "id":            row.supplier_id,
                "name":          row.supplier_name,
                "contact_email": row.supplier_email
            } if row.supplier_id else None  # some products may have no supplier
        }
        alerts.append(alert)

    return jsonify({
        "alerts": alerts,
        "total_alerts": len(alerts)
    }), 200