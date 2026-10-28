-- ============================================================
-- Kidney food database: example queries
-- Database: data/food.db (SQLite), built by 04_build_food_db.py
-- Each query notes the T-SQL (MS SQL Server) spelling where it differs.
-- ============================================================


-- Query 1: Search foods by name
-- Filtering with LIKE; the % wildcard matches any text.
-- T-SQL: SELECT TOP 20 ... (no LIMIT at the end)
SELECT fdc_id, description, dataset, potassium_mg, sodium_mg, phosphorus_mg
FROM food_kidney
WHERE description LIKE '%potato%baked%'
ORDER BY description
LIMIT 20;


-- Query 2: Potassium in each household portion of one food
-- Joining two tables on fdc_id, then scaling the per-100 g value to the portion.
SELECT f.description            AS food,
       p.description            AS portion,
       p.gram_weight,
       ROUND(fk.potassium_mg * p.gram_weight / 100.0) AS potassium_mg_in_portion
FROM portions p
JOIN foods f        ON f.fdc_id  = p.fdc_id
JOIN food_kidney fk ON fk.fdc_id = p.fdc_id
WHERE f.description = 'Bananas, raw'
ORDER BY p.gram_weight;


-- Query 3: Highest-potassium foods per 100 g, by category
-- Grouping and aggregating: how many foods each category has, and its average potassium.
SELECT category,
       COUNT(*)                     AS foods,
       ROUND(AVG(potassium_mg))     AS avg_potassium_mg_per_100g,
       MAX(potassium_mg)            AS max_potassium_mg_per_100g
FROM food_kidney
WHERE dataset = 'sr_legacy' AND potassium_mg IS NOT NULL
GROUP BY category
ORDER BY avg_potassium_mg_per_100g DESC;


-- Query 4: Lower-potassium options within the same category
-- Window function: rank foods inside each category without collapsing rows.
-- Same syntax in T-SQL (RANK() OVER (PARTITION BY ... ORDER BY ...)).
WITH ranked AS (
    SELECT category, description, potassium_mg,
           RANK() OVER (PARTITION BY category ORDER BY potassium_mg) AS k_rank
    FROM food_kidney
    WHERE dataset = 'sr_legacy' AND potassium_mg IS NOT NULL
      AND category = 'Fruits and Fruit Juices'
)
SELECT category, description, potassium_mg
FROM ranked
WHERE k_rank <= 10
ORDER BY potassium_mg;


-- Query 5: Totals for one day's food log
-- A CTE (WITH ...) stands in for the app's food-log table:
-- each row is a food and the grams eaten.
-- T-SQL: same idea, but write the rows as
--   SELECT * FROM (VALUES (173944, 118), ...) AS v(fdc_id, grams)
WITH food_log (fdc_id, grams) AS (
    VALUES (173944, 118),   -- Bananas, raw: 1 medium
           (170093, 173),   -- Potatoes, baked, flesh and skin: 1 medium
           (171477, 140)    -- Chicken breast, roasted: 1 cup chopped
)
SELECT ROUND(SUM(fk.potassium_mg  * l.grams / 100.0)) AS potassium_mg,
       ROUND(SUM(fk.sodium_mg     * l.grams / 100.0)) AS sodium_mg,
       ROUND(SUM(fk.phosphorus_mg * l.grams / 100.0)) AS phosphorus_mg,
       ROUND(SUM(fk.protein_g     * l.grams / 100.0), 1) AS protein_g
FROM food_log l
JOIN food_kidney fk ON fk.fdc_id = l.fdc_id;


-- Query 6: Food search ranked by how commonly people eat the food
-- LEFT JOIN keeps foods nobody reported (popularity is NULL for them);
-- COALESCE turns that NULL into 0 so they sort last.
-- Built by 05_link_nhanes_foods.py from NHANES 2021-2023 recalls.
-- T-SQL: SELECT TOP 10 ... (no LIMIT at the end)
SELECT fk.description,
       COALESCE(fp.nhanes_people, 0) AS people_reporting,
       fp.median_grams,
       fk.potassium_mg               AS potassium_mg_per_100g
FROM food_kidney fk
LEFT JOIN food_popularity fp ON fp.fdc_id = fk.fdc_id
WHERE fk.dataset = 'fndds' AND fk.description LIKE '%potato%'
ORDER BY people_reporting DESC
LIMIT 10;
