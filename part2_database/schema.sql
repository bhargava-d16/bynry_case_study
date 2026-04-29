-- Core company entity
CREATE TABLE companies (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) UNIQUE,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Each company can have multiple warehouses
CREATE TABLE warehouses (
    id            SERIAL PRIMARY KEY,
    company_id    INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name          VARCHAR(255) NOT NULL,
    location      TEXT,  -- address or city, kept simple for now
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Products belong to a company (not a warehouse directly)
CREATE TABLE products (
    id            SERIAL PRIMARY KEY,
    company_id    INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name          VARCHAR(255) NOT NULL,
    sku           VARCHAR(100) NOT NULL UNIQUE,  -- unique across platform
    price         NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    product_type  VARCHAR(50) DEFAULT 'standard', -- 'standard' or 'bundle'
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- This is the core join table: which product is in which warehouse, and how many
CREATE TABLE inventory (
    id            SERIAL PRIMARY KEY,
    product_id    INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id  INT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    quantity      INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    low_stock_threshold  INT DEFAULT 10,  -- per product per warehouse
    updated_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (product_id, warehouse_id)  -- one row per product-warehouse combo
);

-- Every time inventory changes, we log it here
-- This is how we track history without polluting the inventory table
CREATE TABLE inventory_logs (
    id              SERIAL PRIMARY KEY,
    inventory_id    INT NOT NULL REFERENCES inventory(id),
    changed_by      INT REFERENCES users(id),  -- who made the change
    change_type     VARCHAR(50) NOT NULL,  -- 'restock', 'sale', 'adjustment', 'transfer'
    quantity_before INT NOT NULL,
    quantity_after  INT NOT NULL,
    note            TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Suppliers are external to the company, but tied to them
CREATE TABLE suppliers (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    phone         VARCHAR(50),
    created_at    TIMESTAMP DEFAULT NOW()
);

-- A supplier can supply multiple companies, a company can have multiple suppliers
-- This also stores which products a supplier provides
CREATE TABLE company_suppliers (
    id            SERIAL PRIMARY KEY,
    company_id    INT NOT NULL REFERENCES companies(id),
    supplier_id   INT NOT NULL REFERENCES suppliers(id),
    UNIQUE (company_id, supplier_id)
);

CREATE TABLE supplier_products (
    id            SERIAL PRIMARY KEY,
    supplier_id   INT NOT NULL REFERENCES suppliers(id),
    product_id    INT NOT NULL REFERENCES products(id),
    supplier_sku  VARCHAR(100),  -- supplier's own code for this product
    unit_cost     NUMERIC(10, 2),
    lead_time_days INT,  -- how many days to restock, useful for stockout alerts
    UNIQUE (supplier_id, product_id)
);

-- For bundle products: which products make up this bundle and how many of each
CREATE TABLE bundle_items (
    id              SERIAL PRIMARY KEY,
    bundle_id       INT NOT NULL REFERENCES products(id),
    component_id    INT NOT NULL REFERENCES products(id),
    quantity        INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    UNIQUE (bundle_id, component_id),
    CHECK (bundle_id != component_id)  -- a product can't bundle itself
);

-- Basic users table (needed for inventory_logs and auth)
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    company_id    INT NOT NULL REFERENCES companies(id),
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    role          VARCHAR(50) DEFAULT 'staff',  -- 'admin', 'staff', etc.
    created_at    TIMESTAMP DEFAULT NOW()
);
