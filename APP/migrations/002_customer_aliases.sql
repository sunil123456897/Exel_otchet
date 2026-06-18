-- Migration 002: Customer aliases table for reconciliation matching
--
-- Бухгалтеры вручную указывают соответствия между заказчиками со стороны
-- кураторов (master) и заказчиками со стороны РСЧ. Это позволяет сверке
-- автоматически сопоставлять строки, где названия отличаются (сокращения,
-- разные формы юр. лиц и т.д.).
--
-- Когда alias существует, сверка считает customer match успешным и
-- строка получает статус "сверено" (если amount и executor тоже совпадают).

CREATE TABLE IF NOT EXISTS customer_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_customer TEXT NOT NULL,
    rsch_customer TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(master_customer, rsch_customer)
);

CREATE INDEX IF NOT EXISTS idx_aliases_master ON customer_aliases(master_customer);
CREATE INDEX IF NOT EXISTS idx_aliases_rsch ON customer_aliases(rsch_customer);
