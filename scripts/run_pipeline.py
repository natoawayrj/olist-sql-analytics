"""Pipeline SQL + Python para o projeto Olist SQL Analytics.

Carrega os CSVs oficiais da Olist em SQLite, cria views analíticas sem fan-out,
executa as consultas com CTEs e Window Functions em sql/*.sql, exporta os resultados
para data/processed/ e gera visualizações em tema escuro.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
SQL_DIR = BASE_DIR / "sql"
IMG_DIR = BASE_DIR / "img"
DB_PATH = BASE_DIR / "data" / "olist.db"
PORTFOLIO_IMG_DIR = BASE_DIR.parent / "natoawayrj.github.io" / "img"

CSV_TABLES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

BG_FIG = "#0d1526"
BG_AX = "#111827"
BORDER_COLOR = "#1f2d45"
TEXT_MAIN = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
ACCENT_CYAN = "#00c8ff"
ACCENT_GREEN = "#10b981"
ACCENT_AMBER = "#f59e0b"
ACCENT_CORAL = "#ef4444"


def load_csvs_to_sqlite(conn: sqlite3.Connection) -> dict[str, int]:
    """Carrega os CSVs da pasta data/raw para o banco SQLite e cria índices."""
    row_counts: dict[str, int] = {}
    for table_name, filename in CSV_TABLES.items():
        csv_path = RAW_DIR / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV obrigatório não encontrado: {csv_path}")
        df = pd.read_csv(csv_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        row_counts[table_name] = len(df)

    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);",
        "CREATE INDEX IF NOT EXISTS idx_items_order_id ON order_items(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_items_seller_id ON order_items(seller_id);",
        "CREATE INDEX IF NOT EXISTS idx_items_product_id ON order_items(product_id);",
        "CREATE INDEX IF NOT EXISTS idx_payments_order_id ON order_payments(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_reviews_order_id ON order_reviews(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_customers_id ON customers(customer_id);",
        "CREATE INDEX IF NOT EXISTS idx_customers_unique ON customers(customer_unique_id);",
    ]
    for stmt in index_statements:
        conn.execute(stmt)
    conn.commit()
    return row_counts


def parse_named_queries(sql_path: Path) -> list[tuple[str, str]]:
    """Extrai pares (nome_query, sql) delimitados por `-- @query: <nome>`."""
    text = sql_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^--\s*@query:\s*([a-zA-Z0-9_]+)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    queries: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sql_block = text[start:end].strip()
        if sql_block:
            queries.append((match.group(1), sql_block))
    return queries


def execute_sql_pipeline(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Cria as views analíticas e executa todas as queries SQL exportando CSVs."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    views_sql = (SQL_DIR / "01_views_camada_analitica.sql").read_text(encoding="utf-8")
    conn.executescript(views_sql)

    results: dict[str, pd.DataFrame] = {}
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        if sql_file.name.startswith("01_"):
            continue
        for name, query_sql in parse_named_queries(sql_file):
            df = pd.read_sql_query(query_sql, conn)
            df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False, encoding="utf-8")
            results[name] = df

    return results


def _configure_dark_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": BG_FIG,
            "axes.facecolor": BG_AX,
            "axes.edgecolor": BORDER_COLOR,
            "axes.labelcolor": TEXT_MAIN,
            "text.color": TEXT_MAIN,
            "xtick.color": TEXT_MUTED,
            "ytick.color": TEXT_MUTED,
            "grid.color": "#1e293b",
            "grid.alpha": 0.6,
            "font.family": "DejaVu Sans",
        }
    )


def _fmt_br(value: float, decimals: int = 1) -> str:
    """Formata número com separador de milhar '.' e decimal ','."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_int_br(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _save_chart(fig: plt.Figure, filename_stem: str, portfolio_name: str) -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    png_path = IMG_DIR / f"{filename_stem}.png"
    fig.savefig(png_path, dpi=180, bbox_inches="tight", facecolor=BG_FIG)
    plt.close(fig)

    if PORTFOLIO_IMG_DIR.exists():
        webp_path = PORTFOLIO_IMG_DIR / portfolio_name
        with Image.open(png_path) as img:
            img.convert("RGB").save(webp_path, format="WEBP", quality=90, method=6)


def generate_sla_chart(df_faixas: pd.DataFrame, df_uf: pd.DataFrame) -> None:
    """Gráfico 1: Impacto do atraso na nota média / detratores e Top UFs críticas."""
    _configure_dark_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.8), gridspec_kw={"width_ratios": [1.18, 1.0]})
    fig.subplots_adjust(wspace=0.30, top=0.81)

    faixas = df_faixas["faixa_sla"].tolist()
    notas = df_faixas["nota_media"].tolist()
    detratores = df_faixas["pct_detratores_nota_1_2"].tolist()
    pedidos = df_faixas["qtd_pedidos"].tolist()

    x = np.arange(len(faixas))
    bar_colors = [ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER, "#fb7185", ACCENT_CORAL]
    bars = ax1.bar(x, notas, width=0.56, color=bar_colors, edgecolor="none", zorder=2, label="Nota média (eixo esq.)")
    ax1.set_ylim(0, 5.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [f"{f}\n(n={_fmt_int_br(n)})" for f, n in zip(faixas, pedidos)],
        fontsize=8.3,
    )
    ax1.set_ylabel("Nota média (1 a 5)", fontsize=10, fontweight="bold")
    ax1.set_title("Nota média despenca conforme aumenta o atraso", fontsize=11.5, fontweight="bold", pad=12, loc="left")
    ax1.grid(axis="y", zorder=0)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    ax1_twin = ax1.twinx()
    ax1_twin.plot(
        x,
        detratores,
        color="#f8fafc",
        marker="o",
        linewidth=2.3,
        markersize=6.5,
        markeredgecolor="#080d1a",
        markeredgewidth=1.0,
        zorder=5,
        label="% Notas 1–2 (eixo dir.)",
    )
    ax1_twin.set_ylim(0, 98)
    ax1_twin.set_ylabel("% Avaliações 1–2 estrelas (linha branca)", fontsize=9.2, color="#cbd5e1")
    ax1_twin.tick_params(axis="y", colors="#cbd5e1")
    ax1_twin.spines["top"].set_visible(False)
    ax1_twin.spines["left"].set_visible(False)
    ax1_twin.spines["right"].set_color(BORDER_COLOR)

    for idx_b, (bar, nota, det) in enumerate(zip(bars, notas, detratores)):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            nota + 0.12,
            f"{_fmt_br(nota, 2)} ★",
            ha="center",
            va="bottom",
            fontsize=9.3,
            fontweight="bold",
            color=TEXT_MAIN,
        )
        # Posiciona rótulo % detratores próximo à linha branca sem colisão
        det_y_ax1 = (det / 98.0) * 5.4
        offset = 0.34 if idx_b < 3 else -0.44
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            max(0.28, min(det_y_ax1 + offset, 4.95)),
            f"{_fmt_br(det, 1)}% notas 1–2",
            ha="center",
            va="center",
            fontsize=7.6,
            fontweight="bold",
            color="#f8fafc",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#080d1a", edgecolor="#334155", alpha=0.88),
            zorder=6,
        )

    df_top_uf = df_uf[df_uf["qtd_pedidos"] >= 300].sort_values("pct_atraso", ascending=False).head(8).iloc[::-1]
    y = np.arange(len(df_top_uf))
    uf_colors = [ACCENT_CORAL if v >= 15 else ACCENT_AMBER for v in df_top_uf["pct_atraso"]]
    ax2.barh(y, df_top_uf["pct_atraso"], height=0.58, color=uf_colors, zorder=3)
    media_nac = float(df_uf["media_nacional_atraso"].iloc[0])
    ax2.axvline(media_nac, color=ACCENT_CYAN, linestyle="--", linewidth=1.6, zorder=4)
    ax2.set_ylim(-0.6, len(df_top_uf) - 0.15)
    ax2.text(
        media_nac + 0.35,
        len(df_top_uf) - 0.45,
        f"Média Brasil: {_fmt_br(media_nac, 1)}%",
        color=ACCENT_CYAN,
        fontsize=8.6,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#080d1a", edgecolor=ACCENT_CYAN, linewidth=0.8),
    )
    ax2.set_yticks(y)
    ax2.set_yticklabels(
        [f"{row.uf} ({_fmt_int_br(int(row.qtd_pedidos))})" for row in df_top_uf.itertuples()],
        fontsize=9,
    )
    ax2.set_xlim(0, df_top_uf["pct_atraso"].max() * 1.28)
    ax2.set_xlabel("% de pedidos entregues após o prazo estimado", fontsize=9.5, fontweight="bold")
    ax2.set_title("UFs com maior taxa de atraso (mín. 300 pedidos)", fontsize=11.5, fontweight="bold", pad=12, loc="left")
    ax2.grid(axis="x", zorder=0)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    for idx, row in enumerate(df_top_uf.itertuples()):
        ax2.text(
            row.pct_atraso + 0.35,
            idx,
            f"{_fmt_br(row.pct_atraso, 1)}%  |  {_fmt_br(row.nota_media, 2)} ★",
            va="center",
            fontsize=8.5,
            color=TEXT_MAIN,
        )

    fig.suptitle(
        "Olist E-commerce · Atraso logístico é o principal gatilho de avaliações negativas",
        fontsize=14,
        fontweight="bold",
        color=TEXT_MAIN,
        y=0.96,
    )
    fig.text(
        0.5,
        0.895,
        "Base: 95.824 pedidos entregues com avaliação registrada (SQLite · CTEs + Window Functions)",
        ha="center",
        fontsize=9.5,
        color=TEXT_MUTED,
    )
    _save_chart(fig, "olist_1_sla_avaliacao", "olist-1.webp")


def generate_cohort_chart(df_coorte: pd.DataFrame, df_resumo: pd.DataFrame) -> None:
    """Gráfico 2: Matriz de retenção mensal (coortes M0–M6) e resumo de recompra."""
    _configure_dark_style()
    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(13.5, 5.8), gridspec_kw={"width_ratios": [1.55, 0.92]}
    )
    fig.subplots_adjust(wspace=0.24, top=0.81)

    safras_foco = sorted(df_coorte["safra_inicial"].unique())
    safras_foco = [s for s in safras_foco if "2017-01" <= s <= "2018-02"]
    sub = df_coorte[(df_coorte["safra_inicial"].isin(safras_foco)) & (df_coorte["mes_indice"].between(1, 6))]
    piv = sub.pivot(index="safra_inicial", columns="mes_indice", values="pct_retencao")
    piv = piv.reindex(index=safras_foco, columns=[1, 2, 3, 4, 5, 6])

    tamanhos = (
        df_coorte[df_coorte["mes_indice"] == 0]
        .set_index("safra_inicial")["tamanho_coorte"]
        .reindex(safras_foco)
    )

    data = piv.to_numpy(dtype=float)
    masked = np.ma.masked_invalid(data)
    cmap = plt.cm.YlGnBu.copy()
    cmap.set_bad(color="#0b1220")
    vmax = max(0.85, float(np.nanmax(data)))
    im = ax_left.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)

    ax_left.set_xticks(range(6))
    ax_left.set_xticklabels([f"Mês +{m}" for m in range(1, 7)], fontsize=9)
    ax_left.set_yticks(range(len(safras_foco)))
    ax_left.set_yticklabels(
        [f"{s} (n={_fmt_int_br(int(tamanhos.loc[s]))})" for s in safras_foco],
        fontsize=8.5,
    )
    ax_left.set_title("Retenção mensal pós-1ª compra (M+1 a M+6, % da safra)", fontsize=11.5, fontweight="bold", pad=10, loc="left")

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            if not np.isnan(val):
                # Em YlGnBu, valores baixos sao claros (texto escuro) e valores altos sao escuros (texto claro)
                txt_color = "#080d1a" if val < vmax * 0.56 else "#f8fafc"
                ax_left.text(
                    j,
                    i,
                    f"{_fmt_br(val, 2)}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                    fontweight="bold",
                    color=txt_color,
                )

    cbar = fig.colorbar(im, ax=ax_left, fraction=0.035, pad=0.02)
    cbar.ax.tick_params(labelsize=8, colors=TEXT_MUTED)
    cbar.set_label("% retido", fontsize=8.5, color=TEXT_MUTED)

    row = df_resumo.iloc[0]
    unicos = int(row["clientes_unicos"])
    unica = int(row["clientes_compra_unica"])
    recompra = int(row["clientes_recompra"])
    recompra_dist = int(row["clientes_recompra_dias_distintos"])
    pct_unica = unica * 100.0 / unicos
    pct_rec = float(row["pct_recompra"])
    pct_rec_dist = float(row["pct_recompra_dias_distintos"])
    media_dias = float(row["media_dias_ate_2a_compra"])

    cats = ["Compra única\n(1 pedido)", "Recompra total\n(2+ pedidos)", "Recompra em dias\ndistintos (>= 1 dia)"]
    vals = [pct_unica, pct_rec, pct_rec_dist]
    counts = [unica, recompra, recompra_dist]
    colors = ["#475569", ACCENT_CYAN, ACCENT_GREEN]

    bx = np.arange(len(cats))
    bars = ax_right.bar(bx, vals, width=0.52, color=colors, zorder=3)
    ax_right.set_ylim(0, 115)
    ax_right.set_xticks(bx)
    ax_right.set_xticklabels(cats, fontsize=8.4)
    ax_right.set_ylabel("% dos clientes únicos", fontsize=9.5, fontweight="bold")
    ax_right.set_title("Perfil de recompra (customer_unique_id)", fontsize=11.5, fontweight="bold", pad=10, loc="left")
    ax_right.grid(axis="y", zorder=0)
    ax_right.spines["top"].set_visible(False)
    ax_right.spines["right"].set_visible(False)

    for bar, val, cnt in zip(bars, vals, counts):
        ax_right.text(
            bar.get_x() + bar.get_width() / 2,
            val + 2.5,
            f"{_fmt_br(val, 1)}%\n({_fmt_int_br(cnt)})",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
            color=TEXT_MAIN,
        )

    ax_right.text(
        0.56,
        0.72,
        f"Base total: {_fmt_int_br(unicos)} clientes únicos\nIntervalo médio até 2ª compra:\n{_fmt_br(media_dias, 1)} dias",
        transform=ax_right.transAxes,
        ha="center",
        va="center",
        fontsize=8.6,
        color=TEXT_MAIN,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#080d1a", edgecolor=ACCENT_CYAN, linewidth=1.1),
    )

    fig.suptitle(
        "Olist E-commerce · Apenas 3,0% dos clientes recompram no marketplace",
        fontsize=14,
        fontweight="bold",
        color=TEXT_MAIN,
        y=0.96,
    )
    fig.text(
        0.5,
        0.895,
        "Análise de coorte mensal (ROW_NUMBER + FIRST_VALUE + LAG em customer_unique_id)",
        ha="center",
        fontsize=9.5,
        color=TEXT_MUTED,
    )
    _save_chart(fig, "olist_2_coorte_retencao", "olist-2.webp")


def generate_pareto_chart(df_cat: pd.DataFrame, df_sellers: pd.DataFrame) -> None:
    """Gráfico 3: Curva de Pareto (80/20) de receita por categoria + resumo de sellers."""
    _configure_dark_style()
    fig, ax = plt.subplots(figsize=(13.2, 5.8))
    fig.subplots_adjust(top=0.81, bottom=0.22)

    top_n = df_cat.head(20).copy()
    pretty_names = {
        "beleza_saude": "Beleza e Saúde",
        "relogios_presentes": "Relógios e Presentes",
        "cama_mesa_banho": "Cama, Mesa e Banho",
        "esporte_lazer": "Esporte e Lazer",
        "informatica_acessorios": "Informática e Acess.",
        "moveis_decoracao": "Móveis e Decoração",
        "utilidades_domesticas": "Util. Domésticas",
        "cool_stuff": "Cool Stuff",
        "automotivo": "Automotivo",
        "brinquedos": "Brinquedos",
        "ferramentas_jardim": "Ferram. e Jardim",
        "bebes": "Bebês",
        "perfumaria": "Perfumaria",
        "telefonia": "Telefonia",
        "moveis_escritorio": "Móveis Escritório",
        "papelaria": "Papelaria",
        "pcs": "PCs",
        "pet_shop": "Pet Shop",
        "instrumentos_musicais": "Instr. Musicais",
        "eletroportateis": "Eletroportáteis",
    }
    labels = [pretty_names.get(c, c.replace("_", " ").title()) for c in top_n["categoria_raw"]]
    receitas_mi = top_n["receita_total"] / 1_000_000.0
    acum = top_n["pct_receita_acumulada"]

    x = np.arange(len(labels))
    bar_colors = [ACCENT_CYAN if a <= 81.5 else "#475569" for a in acum]
    bars = ax.bar(x, receitas_mi, width=0.62, color=bar_colors, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=32, ha="right", fontsize=8.2)
    ax.set_ylabel("Receita de itens (R$ milhões)", fontsize=10, fontweight="bold")
    ax.set_ylim(0, receitas_mi.max() * 1.24)
    ax.grid(axis="y", zorder=0)
    ax.spines["top"].set_visible(False)

    ax2 = ax.twinx()
    ax2.plot(x, acum, color=ACCENT_AMBER, marker="o", linewidth=2.2, markersize=5, zorder=5)
    ax2.axhline(80.0, color=ACCENT_CORAL, linestyle="--", linewidth=1.4, zorder=4)
    ax2.text(
        4.2,
        82.5,
        "Corte Pareto 80% (atingido na 18ª categoria)",
        color=ACCENT_CORAL,
        fontsize=8.6,
        ha="left",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#080d1a", edgecolor=ACCENT_CORAL, alpha=0.85, linewidth=0.7),
    )
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("% Acumulado da receita total", fontsize=9.5, color=ACCENT_AMBER)
    ax2.tick_params(axis="y", colors=ACCENT_AMBER)
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(BORDER_COLOR)

    for bar, rec_m in zip(bars, receitas_mi):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            rec_m + 0.025,
            f"{_fmt_br(rec_m, 2)}M",
            ha="center",
            va="bottom",
            fontsize=7.3,
            color=TEXT_MAIN,
        )

    s_row = df_sellers.iloc[0]
    n_cat_80 = int((df_cat["pct_receita_acumulada"] <= 80.0).sum()) + 1
    total_cats = len(df_cat)
    total_sellers_fmt = _fmt_int_br(int(s_row["total_sellers_ativos"]))
    sellers_80_fmt = _fmt_int_br(int(s_row["sellers_ate_80pct_receita"]))
    pct_sellers_80_fmt = _fmt_br(float(s_row["pct_sellers_concentram_80pct"]), 1)
    pct_top20_fmt = _fmt_br(float(s_row["pct_receita_nos_top_20pct_sellers"]), 1)
    ax.text(
        0.54,
        0.44,
        (
            f"Concentração (Regra 80/20)\n"
            f"• {n_cat_80} de {total_cats} categorias = 81,3% do GMV\n"
            f"• {sellers_80_fmt} de {total_sellers_fmt} sellers "
            f"({pct_sellers_80_fmt}%) concentram 80% da receita\n"
            f"• Top 20% dos sellers geram {pct_top20_fmt}% do faturamento"
        ),
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=8.6,
        color=TEXT_MAIN,
        bbox=dict(boxstyle="round,pad=0.65", facecolor="#080d1a", edgecolor=ACCENT_CYAN, linewidth=1.1),
    )

    fig.suptitle(
        "Olist E-commerce · Curva de Pareto (80/20) de receita por categoria e sellers",
        fontsize=14,
        fontweight="bold",
        color=TEXT_MAIN,
        y=0.96,
    )
    fig.text(
        0.5,
        0.895,
        "Top 20 categorias por faturamento entregue (SQLite · SUM OVER + DENSE_RANK)",
        ha="center",
        fontsize=9.5,
        color=TEXT_MUTED,
    )
    _save_chart(fig, "olist_3_pareto_receita", "olist-3.webp")


def export_dashboard_json(results: dict[str, pd.DataFrame]) -> None:
    """Exporta JSON e JS consolidados consumidos pelo painel estático docs/index.html."""
    docs_dir = BASE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "resumo_recompra": results["resumo_recompra_clientes"].to_dict(orient="records")[0],
        "pareto_sellers": results["pareto_sellers_resumo"].to_dict(orient="records")[0],
        "sla_faixas": results["sla_faixas_avaliacao"].to_dict(orient="records"),
        "sla_por_uf": results["sla_por_uf"].to_dict(orient="records"),
        "serie_mensal_sla": results["serie_mensal_sla"].to_dict(orient="records"),
        "pareto_categorias": results["pareto_categorias"].head(20).to_dict(orient="records"),
        "coorte_mensal": results["coorte_mensal_retencao"].to_dict(orient="records"),
    }
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    (docs_dir / "data_summary.json").write_text(json_str, encoding="utf-8")
    (docs_dir / "data_summary.js").write_text(
        f"window.OLIST_DATA = {json_str};\n", encoding="utf-8"
    )


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        counts = load_csvs_to_sqlite(conn)
        results = execute_sql_pipeline(conn)

    generate_sla_chart(results["sla_faixas_avaliacao"], results["sla_por_uf"])
    generate_cohort_chart(results["coorte_mensal_retencao"], results["resumo_recompra_clientes"])
    generate_pareto_chart(results["pareto_categorias"], results["pareto_sellers_resumo"])
    export_dashboard_json(results)

    print("=== CARGA SQLITE ===")
    for k, v in counts.items():
        print(f"  {k}: {v:,}")
    print("\n=== RESUMO RECOMPRA ===")
    print(results["resumo_recompra_clientes"].to_string(index=False))
    print("\n=== SLA vs AVALIACAO ===")
    print(results["sla_faixas_avaliacao"].to_string(index=False))
    print("\n=== TOP 10 UFS ATRASO ===")
    print(results["sla_por_uf"].head(10).to_string(index=False))
    print("\n=== PARETO SELLERS ===")
    print(results["pareto_sellers_resumo"].to_string(index=False))
    print("\n=== TOP 15 CATEGORIAS ===")
    print(results["pareto_categorias"].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
