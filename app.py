import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. CONEXÃO FORÇA BRUTA (REST API) ---
def conectar_forca_bruta(prompt, api_key):
    # Lista de modelos para testar via URL direta
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
        # Vendas
        try: df_v = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python')
        except: 
            arq_vendas.seek(0)
            df_v = pd.read_excel(arq_vendas)
            
        df_v = df_v.rename(columns={'Item de Estoque:': 'Codigo', 'Qtde\r\nCupom': 'Descricao', 'Qtde. Venda': 'Venda', 'Valor Venda': 'Fat'})
        
        cols_v = ['Codigo', 'Descricao', 'Venda', 'Fat']
        df_v = df_v[[c for c in cols_v if c in df_v.columns]]
        df_v['Codigo'] = pd.to_numeric(df_v['Codigo'], errors='coerce')
        df_v = df_v.dropna(subset=['Codigo'])
        
        # Estoque
        try: df_e = pd.read_csv(arq_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except: 
            arq_estoque.seek(0)
            df_e = pd.read_excel(arq_estoque, header=None)
            
        df_e = df_e.dropna(subset=[0])
        if len(df_e.columns) > 5:
            df_e = df_e.rename(columns={0: 'Codigo', 1: 'Desc_E', 5: 'Estoque'})
            df_e = df_e[['Codigo', 'Desc_E', 'Estoque']]
            df_e['Codigo'] = pd.to_numeric(df_e['Codigo'], errors='coerce')
            df_e = df_e.dropna(subset=['Codigo'])
        else:
            return None
            
        # Merge
        df = pd.merge(df_e, df_v, on='Codigo', how='outer')
        if 'Descricao' in df.columns and 'Desc_E' in df.columns:
            df['Descricao'] = df['Descricao'].fillna(df['Desc_E']).fillna("Item s/ Nome")
        elif 'Desc_E' in df.columns:
            df['Descricao'] = df['Desc_E'].fillna("Item s/ Nome")
        
        cols = ['Codigo', 'Descricao', 'Estoque', 'Venda', 'Fat']
        for c in cols: 
            if c not in df.columns: df[c] = 0
            if c != 'Descricao': df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
        return df[cols]
    except:
        return None

# --- 4. INTERFACE ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.caption("Modo API: Varredura Multi-Modelo")

up1, up2 = st.columns(2)
f1 = up1.file_uploader("Vendas")
f2 = up2