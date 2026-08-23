-- ============================================
-- Projeto de Análise de Vendas com SQL
-- ============================================

CREATE TABLE clientes (
    id_cliente INTEGER PRIMARY KEY,
    nome VARCHAR(100),
    cidade VARCHAR(100),
    estado VARCHAR(2)
);

CREATE TABLE produtos (
    id_produto INTEGER PRIMARY KEY,
    produto VARCHAR(100),
    categoria VARCHAR(50),
    preco DECIMAL(10,2)
);

CREATE TABLE vendas (
    id_venda INTEGER PRIMARY KEY,
    id_cliente INTEGER,
    id_produto INTEGER,
    quantidade INTEGER,
    data_venda DATE,
    
    FOREIGN KEY (id_cliente)
        REFERENCES clientes(id_cliente),

    FOREIGN KEY (id_produto)
        REFERENCES produtos(id_produto)
);

-- Quantidade total de vendas

SELECT COUNT(*) AS total_vendas
FROM vendas;

-- Vendas por cidade

SELECT
    c.cidade,
    COUNT(v.id_venda) AS quantidade_vendas
FROM vendas v
INNER JOIN clientes c
    ON v.id_cliente = c.id_cliente
GROUP BY c.cidade
ORDER BY quantidade_vendas DESC;

-- Faturamento por produto

SELECT
    p.produto,
    SUM(v.quantidade * p.preco) AS faturamento
FROM vendas v
INNER JOIN produtos p
    ON v.id_produto = p.id_produto
GROUP BY p.produto
ORDER BY faturamento DESC;

-- Faturamento por categoria

SELECT
    p.categoria,
    SUM(v.quantidade * p.preco) AS faturamento
FROM vendas v
INNER JOIN produtos p
    ON v.id_produto = p.id_produto
GROUP BY p.categoria
ORDER BY faturamento DESC;

-- Ticket médio

SELECT
    AVG(v.quantidade * p.preco) AS ticket_medio
FROM vendas v
INNER JOIN produtos p
    ON v.id_produto = p.id_produto;

-- Clientes com maior volume de compras

SELECT
    c.nome,
    COUNT(v.id_venda) AS numero_compras,
    SUM(v.quantidade * p.preco) AS valor_total
FROM clientes c
INNER JOIN vendas v
    ON c.id_cliente = v.id_cliente
INNER JOIN produtos p
    ON v.id_produto = p.id_produto
GROUP BY c.id_cliente, c.nome
ORDER BY valor_total DESC;

-- Faturamento mensal

SELECT
    EXTRACT(YEAR FROM data_venda) AS ano,
    EXTRACT(MONTH FROM data_venda) AS mes,
    SUM(v.quantidade * p.preco) AS faturamento
FROM vendas v
INNER JOIN produtos p
    ON v.id_produto = p.id_produto
GROUP BY
    EXTRACT(YEAR FROM data_venda),
    EXTRACT(MONTH FROM data_venda)
ORDER BY ano, mes;
