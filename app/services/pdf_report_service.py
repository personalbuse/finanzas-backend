import logging
from datetime import datetime
from typing import Any

from fpdf import FPDF

logger = logging.getLogger(__name__)


class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(16, 185, 129)
        self.cell(0, 10, 'Simulador de Inversiones', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, 'Reporte de Portafolio', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Generado por Simulador de Inversiones - Finanzas Internacionales | {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')


def generate_portfolio_pdf(
    user_data: dict[str, Any],
    portfolio: list[dict[str, Any]],
    exchange_rate: float
) -> bytes:
    pdf = PDFReport()
    pdf.add_page()

    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 10, f'Usuario: {user_data.get("username", "N/A")}', 0, 1)
    pdf.cell(0, 10, f'Fecha: {datetime.now().strftime("%d de %B de %Y")}', 0, 1)
    pdf.ln(5)

    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(0, 10, 'Resumen de Cuenta', 0, 1)
    pdf.ln(3)

    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(50, 50, 50)

    initial_balance = float(user_data.get('initial_balance', 0))
    current_balance = float(user_data.get('current_balance', 0))
    portfolio_value = sum(stock.get('stock_value', 0) for stock in portfolio)
    total_value = current_balance + portfolio_value
    total_cost = sum(stock.get('stock_cost', 0) for stock in portfolio)
    total_profit = portfolio_value - total_cost

    profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
    total_profit_percent = ((total_value - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0

    pdf.set_fill_color(240, 240, 240)
    pdf.cell(90, 10, 'Saldo Disponible (USD)', 1, 0, 'L', 1)
    pdf.cell(90, 10, f'${current_balance:,.2f}', 1, 1, 'R', 1)

    pdf.cell(90, 10, 'Valor Portafolio (USD)', 1, 0, 'L', 1)
    pdf.cell(90, 10, f'${portfolio_value:,.2f}', 1, 1, 'R', 1)

    pdf.cell(90, 10, 'Total Activos (USD)', 1, 0, 'L', 1)
    pdf.cell(90, 10, f'${total_value:,.2f}', 1, 1, 'R', 1)

    pdf.cell(90, 10, 'Ganancia/Perdida (USD)', 1, 0, 'L', 1)
    profit_color = (16, 185, 129) if total_profit >= 0 else (220, 38, 38)
    pdf.set_text_color(*profit_color)
    pdf.cell(90, 10, f'{"+" if total_profit >= 0 else ""}${total_profit:,.2f} ({total_profit_percent:+.2f}%)', 1, 1, 'R', 1)

    pdf.set_text_color(50, 50, 50)
    pdf.ln(10)

    cop_value = total_value * exchange_rate
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Equivalent in COP', 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 10, f'${cop_value:,.0f} COP (1 USD = {exchange_rate:,.0f} COP)', 0, 1)

    pdf.ln(10)
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(0, 10, 'Detalle del Portafolio', 0, 1)
    pdf.ln(3)

    col_widths = [25, 40, 30, 30, 35, 30]
    headers = ['Simbolo', 'Cantidad', 'Costo Prom.', 'Precio Actual', 'Valor', 'Ganancia']
    header_color = (16, 185, 129)

    pdf.set_fill_color(*header_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 9)

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', 1)
    pdf.ln()

    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(50, 50, 50)

    for stock in portfolio:
        symbol = stock.get('symbol', '')
        quantity = float(stock.get('quantity', 0))
        avg_cost = float(stock.get('average_cost', 0))
        current_price = float(stock.get('current_price', 0))
        stock_value = float(stock.get('stock_value', 0))
        stock_profit = float(stock.get('stock_profit', 0))

        pdf.cell(col_widths[0], 7, symbol, 1, 0, 'C')
        pdf.cell(col_widths[1], 7, f'{quantity:.2f}', 1, 0, 'R')
        pdf.cell(col_widths[2], 7, f'${avg_cost:.2f}', 1, 0, 'R')
        pdf.cell(col_widths[3], 7, f'${current_price:.2f}', 1, 0, 'R')
        pdf.cell(col_widths[4], 7, f'${stock_value:,.2f}', 1, 0, 'R')

        profit_color = (16, 185, 129) if stock_profit >= 0 else (220, 38, 38)
        pdf.set_text_color(*profit_color)
        pdf.cell(col_widths[5], 7, f'{"+" if stock_profit >= 0 else ""}${stock_profit:,.2f}', 1, 1, 'R')
        pdf.set_text_color(50, 50, 50)

    pdf.ln(10)
    pdf.set_font('Arial', 'I', 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, 'Este reporte es generado con fines educativos para la materia de Finanzas Internacionales.', 0, 1, 'C')

    return pdf.output(dest='S').encode('latin-1')


async def generate_report(db, user_id: int):
    import asyncio

    from sqlalchemy import select

    from app.models.base import Portfolio, User
    from app.services.finnhub_service import FinnhubService

    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    portfolio_stmt = select(Portfolio).where(Portfolio.user_id == user_id)
    portfolio_result = await db.execute(portfolio_stmt)
    portfolios = portfolio_result.scalars().all()

    price_results = []
    if portfolios:
        async with FinnhubService() as service:
            async def fetch_price(p):
                current_price_data = await service.get_stock_price(p.symbol, db)
                current_price = current_price_data.get('price', 0)
                return p, current_price

            price_results = await asyncio.gather(
                *[fetch_price(p) for p in portfolios],
                return_exceptions=True
            )

    portfolio_list = []
    for r in price_results:
        if isinstance(r, Exception):
            continue
        p, current_price = r
        stock_value = float(p.quantity) * current_price
        stock_cost = float(p.quantity) * float(p.average_cost)
        portfolio_list.append({
            'symbol': p.symbol,
            'quantity': float(p.quantity),
            'average_cost': float(p.average_cost),
            'current_price': current_price,
            'stock_value': stock_value,
            'stock_cost': stock_cost,
            'stock_profit': stock_value - stock_cost
        })

    from app.services.exchange_rate_service import ExchangeRateService
    exchange_rate = 3850
    try:
        async with ExchangeRateService() as rate_service:
            rate = await rate_service.get_exchange_rate("USD", "COP", db)
            exchange_rate = rate.get('rate', 3850)
    except:
        pass

    user_data = {
        'username': user.username,
        'initial_balance': float(user.initial_balance),
        'current_balance': float(user.current_balance)
    }

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None, generate_portfolio_pdf, user_data, portfolio_list, exchange_rate
    )
    return pdf_bytes
