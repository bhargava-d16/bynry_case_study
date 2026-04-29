# Bynry Backend Engineering Intern — Case Study Solution

## Overview
This is my solution to the StockFlow Inventory Management System case study. The platform helps small businesses track products across multiple warehouses and manage supplier relationships.

---

## Part 1: Code Review & Debugging

### My First Thought
Honestly, when I first read this code, it looks fine at a glance — it creates a product, commits, then creates an inventory record. But once I think about what can actually go wrong in production with real users sending real data, several issues are there.

### Issues I Found

**Issue 1: No input validation**
The code directly accesses data['name'], data['sku'] etc. with no checks. If any field is missing or the body isn't JSON, it'll throw a KeyError and crash with a 500 error — which can also leak internal stack trace details.
Impact: Any slightly malformed request breaks the endpoint entirely.

**Issue 2: No SKU uniqueness check**
There's no check before inserting whether the SKU already exists. It'll either silently create a duplicate or throw an unhandled DB error.
Impact: Two products with the same SKU breaks order tracking and anything else that uses SKU to identify a product.

**Issue 3: Two separate commits**
Product is committed first, then Inventory. If anything fails in between, you get a product with no inventory record attached to it.
Impact: Orphaned products showing up in listings with no stock info, causing errors downstream.

**Issue 4: warehouse_id on the Product model**
Since products can exist in multiple warehouses, putting warehouse_id directly on Product makes no sense — that relationship belongs in the Inventory table only.
Impact: Adding the same product to a second warehouse would either overwrite or conflict with the existing value.

**Issue 5: No price validation**
No check that price is actually a number. "price": "free" would pass right through.
Impact: Financial data corruption — null or string values stored where a decimal should be.

**Issue 6: Wrong status code**
Returns 200 OK by default, but creating a resource should return 201 Created.
Impact: Minor, but API clients that rely on status codes will behave incorrectly.

**Issue 7: No auth check**
No verification of who's making the request or whether they own that warehouse.
Impact: Any user could add products to any warehouse if they know the warehouse_id.

---

## Part 2: Database Design

### My Thought Process
Before jumping into tables, I tried to map out the real-world entities first: Companies own Warehouses, Warehouses store Products, Suppliers supply Products, and some Products are made of other Products (bundles). Once I had that mental picture, the schema mostly wrote itself — except for a few spots where the requirements left gaps.

### Design Decisions Explained

**inventory as a separate table (not columns on product):**
Since the same product can be in multiple warehouses with different quantities, you need a row per product-warehouse pair. That's the only clean way to model it.

**inventory_logs as an append-only table:**
Instead of updating a quantity_history column, I keep a separate log table. This way you never lose history and can always reconstruct what happened — useful for audits.

**NUMERIC(10,2) for price:**
Using FLOAT for money is a classic mistake — floating point errors mean 0.1 + 0.2 != 0.3. NUMERIC stores exact decimals.

**bundle_items self-referencing products:**
Rather than a separate bundles table, I reuse products and just flag product_type = 'bundle'. The components are stored in bundle_items. Cleaner than duplicating product fields.

**CHECK (bundle_id != component_id):**
Just a small guard so nobody accidentally adds a product as a component of itself.

Note: I didn't index everything — over-indexing slows down writes, and most of the other columns won't be heavily queried.

### Gaps I Found — Questions I'd Ask the Product Team

**1. How does SKU uniqueness work across companies?**
Right now I've made SKU globally unique. But should Company A and Company B be allowed to use the same SKU WID-001 for different products? Probably yes in a real B2B platform. I'd need to know if SKU should be unique per-company or globally.

**2. Can a bundle contain other bundles?**
My current schema allows it technically, but that creates recursive complexity. Do we need to handle nested bundles, or is it always just "flat" — one level deep?

**3. What triggers an inventory log entry?**
Is it only manual adjustments, or do sales/orders also write to this table? If orders come from another system, how does that integration work?

**4. Can a product be supplied by multiple suppliers?**
I assumed yes (hence supplier_products as a join table). But maybe a company has one preferred supplier per product — in that case we'd just add a preferred flag.

**5. What happens to inventory when a warehouse is deleted?**
I used ON DELETE CASCADE for now which would wipe inventory records. That's probably wrong for a real business — you'd want soft deletes or at least a warning. Worth clarifying.

**6. Is price per-warehouse or global?**
I put price on the product, but in some systems price varies by warehouse (regional pricing). No requirement mentioned this, but worth confirming.

---

## Part 3: API Implementation

### My Assumptions

- "Recent sales activity" = at least one sale in the last 30 days. Without this definition the query is meaningless. I'd confirm this with the product team.
- days_until_stockout = current_stock / avg_daily_sales. Calculating avg daily sales from the last 30 days. If there are no sales, I return null — not 0, because 0 would imply "out of stock today" which isn't accurate.
- Low stock threshold is stored per product in the inventory table. Default is 10 if not set.
- A product shows up in alerts once per warehouse — so if Widget A is low in Warehouse 1 but fine in Warehouse 2, only Warehouse 1 triggers an alert.
- Picking the first listed supplier if a product has multiple. In reality you'd want a "preferred supplier" flag.

### Edge Cases I Handled

**No supplier linked to a product:**
Used LEFT JOIN so the product still shows up in alerts. Supplier field returns null instead of crashing. A product with no supplier and low stock is actually more urgent — the buyer needs to go find one.

**Division by zero in days_until_stockout:**
Used NULLIF in SQL and a Python check before dividing. If avg sales is 0, we return null rather than throwing an error or returning infinity.

**Company doesn't exist:**
Early return with 404 before running any DB queries. No point hitting the DB for a ghost company.

**Product in multiple warehouses:**
The query groups by product_id + warehouse_id, so the same product in 3 warehouses can generate up to 3 separate alerts if all 3 are low.

**Product has multiple suppliers:**
Query will return duplicate rows if multiple suppliers exist. Quick fix would be adding DISTINCT ON or a preferred flag on supplier_products.

### What I'd Improve With More Time

- Add pagination — returning 500 alerts at once is a bad idea
- Add a ?warehouse_id= query param to filter by specific warehouse
- Cache this response for a few minutes — the query is heavy and doesn't need to be real-time
- The "30 days" window should be configurable per company

