CREATE TABLE vendas (
    id INTEGER PRIMARY KEY,
    cidade VARCHAR(100),
    valor DECIMAL(10,2)
);

SELECT
    cidade,
    COUNT(*) AS quantidade,
    AVG(valor) AS valor_medio
FROM vendas
GROUP BY cidade
ORDER BY valor_medio DESC;
