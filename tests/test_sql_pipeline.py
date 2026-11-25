"""Testes de integridade do pipeline SQL da Olist."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_pipeline import DB_PATH, PROCESSED_DIR, RAW_DIR, SQL_DIR, execute_sql_pipeline, load_csvs_to_sqlite


@pytest.fixture(scope="module")
def sql_results() -> dict[str, pd.DataFrame]:
    """Garante que o banco SQLite está populado e retorna os resultados das queries."""
    if RAW_DIR.exists() and (RAW_DIR / "olist_orders_dataset.csv").exists():
        with sqlite3.connect(":memory:") as conn:
            load_csvs_to_sqlite(conn)
            return execute_sql_pipeline(conn)

    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            return execute_sql_pipeline(conn)

    # Fallback para ambiente CI sem CSVs brutos: lê os artefatos processados
    return {
        p.stem: pd.read_csv(p)
        for p in PROCESSED_DIR.glob("*.csv")
    }


def test_sql_files_use_ctes_and_window_functions() -> None:
    """Confirma que os scripts analíticos usam CTEs e Window Functions."""
    for sql_name in [
        "02_coorte_retencao_recompra.sql",
        "03_pareto_categorias_sellers.sql",
        "04_sla_entrega_vs_avaliacao.sql",
    ]:
        text = (SQL_DIR / sql_name).read_text(encoding="utf-8").upper()
        assert "WITH " in text, f"{sql_name} deve conter CTE (WITH)"
        assert "OVER (" in text or "OVER(" in text, f"{sql_name} deve conter Window Function (OVER)"


def test_carga_acima_de_95k_pedidos_entregues(sql_results: dict[str, pd.DataFrame]) -> None:
    """Verifica que há mais de 95.000 pedidos entregues avaliados na análise de SLA."""
    df_sla = sql_results["sla_faixas_avaliacao"]
    total_pedidos = int(df_sla["qtd_pedidos"].sum())
    assert total_pedidos > 95_000


def test_ordenacao_monotonica_faixas_sla(sql_results: dict[str, pd.DataFrame]) -> None:
    """Confirma queda monotônica da nota média e aumento de detratores conforme o atraso cresce."""
    df_sla = sql_results["sla_faixas_avaliacao"].sort_values("ordem_faixa_sla")
    notas = df_sla["nota_media"].tolist()
    detratores = df_sla["pct_detratores_nota_1_2"].tolist()
    assert notas == sorted(notas, reverse=True), f"Nota média não é monotonicamente decrescente: {notas}"
    assert detratores == sorted(detratores), f"% de detratores não é monotonicamente crescente: {detratores}"


def test_pareto_soma_ate_100_por_cento(sql_results: dict[str, pd.DataFrame]) -> None:
    """Confirma que a curva de Pareto fecha em ~100% da receita e que sellers está consistente."""
    df_cat = sql_results["pareto_categorias"].sort_values("ranking_receita")
    assert df_cat["pct_receita"].sum() == pytest.approx(100.0, abs=0.5)
    assert float(df_cat["pct_receita_acumulada"].iloc[-1]) == pytest.approx(100.0, abs=0.05)

    df_sellers = sql_results["pareto_sellers_resumo"].iloc[0]
    assert int(df_sellers["sellers_ate_80pct_receita"]) < int(df_sellers["total_sellers_ativos"])
    assert 0 < float(df_sellers["pct_sellers_concentram_80pct"]) < 50


def test_consistencia_coortes_customer_unique_id(sql_results: dict[str, pd.DataFrame]) -> None:
    """Verifica que a retenção em M0 é 100% e que clientes únicos batem com o resumo."""
    df_resumo = sql_results["resumo_recompra_clientes"].iloc[0]
    unicos = int(df_resumo["clientes_unicos"])
    unica = int(df_resumo["clientes_compra_unica"])
    recompra = int(df_resumo["clientes_recompra"])
    assert unicos == unica + recompra
    assert unicos > 90_000

    df_coorte = sql_results["coorte_mensal_retencao"]
    m0 = df_coorte[df_coorte["mes_indice"] == 0]
    assert (m0["pct_retencao"] == 100.0).all()
    assert (df_coorte["clientes_ativos"] <= df_coorte["tamanho_coorte"]).all()
