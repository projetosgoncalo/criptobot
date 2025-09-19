import requests
import pandas as pd
import ta
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os  # para ler variáveis de ambiente

# ==============================
# CONFIGURAÇÕES
# ==============================
COINS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "hyperliquid": "HYPER",
    "ondo-finance": "ONDO",
    "render-token": "RNDR",
    "bittensor": "TAO",
}
VS_CURRENCY = "usd"
TOP_N = 5   # número de maiores altas/quedas para mostrar

# Email – usando GitHub Actions Secrets
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER = os.environ["EMAIL_RECEIVER"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# ==============================
# FUNÇÕES
# ==============================

def fetch_market_data():
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": VS_CURRENCY,
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": False
        }
        return requests.get(url, params=params).json()
    except Exception as e:
        print(f"[ERRO] Não foi possível obter dados do mercado: {e}")
        return []

def fetch_historical_data(coin_id, days=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": VS_CURRENCY, "days": days}
        response = requests.get(url, params=params)
        data = response.json()
        if "prices" not in data:
            print(f"[ERRO] Dados não encontrados para {coin_id}: {data}")
            return pd.DataFrame(columns=["timestamp", "price"])
        prices = data["prices"]
        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"[ERRO] Falha ao buscar dados históricos de {coin_id}: {e}")
        return pd.DataFrame(columns=["timestamp", "price"])

def analyze_coin(coin_id, symbol):
    df = fetch_historical_data(coin_id, days=30)
    if df.empty:
        return {
            "symbol": symbol,
            "price": 0,
            "RSI": 0,
            "SMA20": 0,
            "interpretation": "Dados indisponíveis",
            "color": "#000000",
            "arrow": ""
        }

    closes = df["price"]

    try:
        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi()
        sma20 = closes.rolling(window=20).mean()
        last_rsi = rsi.iloc[-1]
        last_sma = sma20.iloc[-1]
        last_close = closes.iloc[-1]
        last_change = ((last_close - closes.iloc[-2]) / closes.iloc[-2]) * 100

        interpretation = "Manter"
        color = "#000000"
        if last_rsi < 30 and last_close < last_sma:
            interpretation = "Comprar (sobrevendida + abaixo da média)"
            color = "#008000"
        elif last_rsi < 30:
            interpretation = "Comprar (sobrevendida)"
            color = "#008000"
        elif last_rsi > 70 and last_close > last_sma:
            interpretation = "Vender (sobrecomprada + acima da média)"
            color = "#FF0000"
        elif last_rsi > 70:
            interpretation = "Vender (sobrecomprada)"
            color = "#FF0000"

        arrow = "⬆️" if last_change >= 0 else "⬇️"

        return {
            "symbol": symbol,
            "price": last_close,
            "RSI": last_rsi,
            "SMA20": last_sma,
            "interpretation": interpretation,
            "color": color,
            "arrow": arrow
        }
    except Exception as e:
        print(f"[ERRO] Falha ao analisar {symbol}: {e}")
        return {
            "symbol": symbol,
            "price": 0,
            "RSI": 0,
            "SMA20": 0,
            "interpretation": "Erro na análise",
            "color": "#000000",
            "arrow": ""
        }

def build_report_html():
    market_data = fetch_market_data()
    btc = next((c for c in market_data if c["id"] == "bitcoin"), None)
    eth = next((c for c in market_data if c["id"] == "ethereum"), None)

    recommendations_buy = []
    recommendations_sell = []

    html = f"""<html>
<head>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Roboto&display=swap" rel="stylesheet">
<style>
    p {{ font-size: 1.5rem; }}
</style>
</head>
<body style="font-family:'Roboto',sans-serif;">
<h1>📅 Relatório Cripto – {datetime.now().strftime('%d/%m/%Y')}</h1>
"""

    # Resumo de mercado
    html += "<h2>Resumo de Mercado</h2><ul>"
    if btc:
        html += f"<li>Bitcoin (BTC): ${btc['current_price']:.2f} ({btc['price_change_percentage_24h']:.2f}% 24h)</li>"
    if eth:
        html += f"<li>Ethereum (ETH): ${eth['current_price']:.2f} ({eth['price_change_percentage_24h']:.2f}% 24h)</li>"
    if market_data:
        html += f"<li>Capitalização total estimada: ${sum(c.get('market_cap',0) for c in market_data)/1e12:.2f}T</li>"
    html += "</ul>"

    # Projetos em foco – tabela
    html += """
<h2>Projetos em Foco</h2>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;width:100%;">
<tr style="background-color:#f2f2f2;">
<th>Moeda</th>
<th>Preço (USD)</th>
<th>RSI</th>
<th>SMA20</th>
<th>Interpretação</th>
</tr>
"""
    for i, (coin_id, symbol) in enumerate(COINS.items()):
        if coin_id in ["bitcoin", "ethereum"]:
            continue
        analysis = analyze_coin(coin_id, symbol)
        row_color = "#ffffff" if i % 2 == 0 else "#e6f7ff"
        html += f"""
<tr style="background-color:{row_color};">
<td><b>{symbol}</b></td>
<td>${analysis['price']:.2f} {analysis['arrow']}</td>
<td>{analysis['RSI']:.2f}</td>
<td>{analysis['SMA20']:.2f}</td>
<td style="color:{analysis['color']};">{analysis['interpretation']}</td>
</tr>
"""
        if "Comprar" in analysis["interpretation"]:
            recommendations_buy.append(symbol)
        if "Vender" in analysis["interpretation"]:
            recommendations_sell.append(symbol)
    html += "</table>"

    # Top ganhadores/perdedores
    sorted_market = sorted(market_data, key=lambda x: x.get("price_change_percentage_24h",0) or 0, reverse=True)
    top_gainers = sorted_market[:TOP_N]
    top_losers = sorted_market[-TOP_N:]

    html += "<h2>Top Ganhadores 24h</h2><ul>"
    for coin in top_gainers:
        html += f"<li>{coin['symbol'].upper()} {coin.get('price_change_percentage_24h',0):.2f}%</li>"
    html += "</ul>"

    html += "<h2>Top Perdedores 24h</h2><ul>"
    for coin in top_losers:
        html += f"<li>{coin['symbol'].upper()} {coin.get('price_change_percentage_24h',0):.2f}%</li>"
    html += "</ul>"

    # Recomendações
    html += "<h2>Recomendações</h2>"
    if recommendations_buy:
        html += "<b>Deves reforçar a tua posição em:</b><ul>"
        for coin in recommendations_buy:
            html += f"<li>{coin}</li>"
        html += "</ul>"
    if recommendations_sell:
        html += "<b>Se quiseres tirar alguns lucros, tira de:</b><ul>"
        for coin in recommendations_sell:
            html += f"<li>{coin}</li>"
        html += "</ul>"

    html += "</body></html>"
    return html

def send_email_html(html_content):
    msg = MIMEText(html_content, "html")
    msg["Subject"] = f"Relatório Cripto {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    html_report = build_report_html()
    print("📧 Enviando relatório HTML...")
    send_email_html(html_report)
    print("✅ Relatório enviado com sucesso!")
