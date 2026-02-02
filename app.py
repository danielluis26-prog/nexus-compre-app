import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. CONEXÃO FORÇA BRUTA (REST API) ---
def conectar_forca_bruta(prompt, api_key):
    # Lista de modelos para testar
    modelos_urls = [
        ("gemini-1.5-flash", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"),
        ("gemini-1.5-flash-latest", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"),
        ("gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"),
        ("gemini-1.5-pro", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"),
    ]
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    log_erros = []

    for nome_modelo, url_base in modelos_urls:
        url_final = f"{url_base}?key={api_key}"
        try:
            response = requests.post(url_final, headers=headers, data=json.dumps(payload), timeout=10)
            
            if response.status_code == 200:
                resultado = response.json()
                try:
                    texto = resultado['candidates'][0]['content']['parts'][0]['text']
                    return texto, f"Sucesso via {nome_modelo}"
                except:
                    log_erros.append(f"{nome_modelo}: Resposta vazia")
            elif response.status_code == 429:
                log_erros.append(f"{nome_modelo}: 429 (Limite de Cota)")
            else:
                log_erros.append(f"{nome_modelo}: {response.status_code}")
        
        except Exception as e:
            log_erros.append(f"{nome_modelo}: Erro técnico {str(e)}")
            
    return None, log_erros

# --- 3. LEITURA DE DADOS (Blindada) ---
def carregar_dados(arq_vendas, arq_estoque):
    try:
        # --- PROCESSAR VENDAS ---
        try: 
            df_v = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python')
        except: 
            arq_vendas.seek(0)
            df_v = pd.read_excel(arq_vendas)
            
        df_v = df_v.rename(columns={
            'Item de Estoque: