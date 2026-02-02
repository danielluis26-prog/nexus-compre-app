import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE CONEXÃO DIRETA (SEM BIBLIOTECA GOOGLE) ---
def conectar_via_api_rest(prompt, api_key):
    # Vamos tentar conectar direto na URL do Google, sem usar a biblioteca bugada
    
    # Opção A: Gemini 1.5 Flash (Rápido e Grátis)
    url_flash = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    # Opção B: Gemini 1.0 Pro (O Clássico - Backup)
    url_pro = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    # Tentativa 1: Flash
    try:
        response = requests.post(url_flash, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            resultado = response.json()
            texto = resultado['candidates'][0]['content']['parts'][0]['text']
            return texto, "Gemini 1.5 Flash (Via API REST)"
        else:
            # Se der erro (404 ou 429), vamos para o backup
            pass 
    except:
        pass

    # Tentativa 2: Pro (Clássico)
    try:
        time.sleep(1) # Respira
        response = requests.post(url_pro, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            resultado = response.json()
            texto = resultado['candidates'][0]['content']['parts'][0]['text']
            return texto, "Gemini 1.0 Pro (Backup Seguro)"
        else:
            return None, f"Erro Google: {response.text}"
    except Exception as e:
        return None, f"Erro Técnico: {str(e)}"

# --- 3. LEITURA DE DADOS ---
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
st.caption("Modo API Direta: Ignorando erros de biblioteca.")

up1, up2 = st.columns(2)
f1 = up1.file_uploader("Vendas")
f2 = up2.file_uploader("Estoque")

if f1 and f2:
    df = carregar_dados(f1, f2)
    if df is not None:
        # Lógica Nexus
        df = df.sort_values('Fat', ascending=False)
        total = df['Fat'].sum()
        df['Fat_Acum'] = df['Fat'].cumsum()
        df['Perc'] = df['Fat_Acum'] / total if total > 0 else 0
        
        def def_curva(x): return 'A' if x<=0.5 else ('B' if x<=0.8 else 'C')
        df['Curva'] = df['Perc'].apply(def_curva)
        
        # Lógica Fantasma
        df['Fantasma'] = (df['Estoque'] > 5) & (df['Venda'] == 0)
        
        fantasmas = df[df['Fantasma']]
        ruptura = df[(df['Curva']=='A') & (df['Estoque']==0)]
        
        # Métricas
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens Totais", len(df))
        c2.metric("Estoque Fantasma", len(fantasmas), delta="-Atenção")
        c3.metric("Ruptura Curva A", len(ruptura), delta_color="inverse")
        
        st.dataframe(fantasmas[['Codigo', 'Descricao', 'Estoque', 'Venda']].head(10))
        
        if st.button("🤖 Analisar (Modo Comprador)"):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("Sem chave API.")
            else:
                prompt = f"""
                ATUE COMO UM GERENTE DE COMPRAS DE SUPERMERCADO SÊNIOR.
                Contexto: Dados reais de Varejo Alimentar.
                
                NÃO SEJA UM COACH. SEJA TÉCNICO E COMERCIAL.

                DADOS:
                - Itens Fantasmas (Estoque parado, Venda Zero):
                {fantasmas[['Codigo', 'Descricao', 'Estoque']].head(10).to_string(index=False)}

                - Ruptura Curva A (Vende muito, Estoque Zero):
                {ruptura[['Codigo', 'Descricao', 'Venda']].head(10).to_string(index=False)}

                MISSÃO:
                3 Ações curtas e grossas para resolver isso hoje e liberar caixa.
                """
                
                with st.spinner("Conectando direto nos servidores do Google..."):
                    txt, modelo = conectar_via_api_rest(prompt, st.secrets["GEMINI_API_KEY"])
                    if txt:
                        st.success(f"Analise gerada por: {modelo}")
                        st.markdown(txt)
                    else:
                        st.error("Falha na API Direta. Detalhes:")
                        st.code(modelo)