import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. CONEXÃO FORÇA BRUTA (REST API - VARREDURA TOTAL) ---
def conectar_forca_bruta(prompt, api_key):
    # Lista expandida com versões específicas e antigas
    modelos_urls = [
        # TENTATIVA 1: O Clássico (Geralmente funciona quando os novos falham)
        ("gemini-pro", "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"),
        
        # TENTATIVA 2: Versões específicas do Flash (às vezes o nome curto falha)
        ("gemini-1.5-flash-001", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-001:generateContent"),
        ("gemini-1.5-flash-002", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-002:generateContent"),
        
        # TENTATIVA 3: Nomes curtos
        ("gemini-1.5-flash", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"),
        ("gemini-1.5-flash-latest", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"),
        
        # TENTATIVA 4: Experimental (Pode dar limite de cota)
        ("gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"),
        ("gemini-2.0-flash-exp", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"),
    ]
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    log_erros = []

    for nome_modelo, url_base in modelos_urls:
        url_final = f"{url_base}?key={api_key}"
        try:
            # Tenta conectar
            response = requests.post(url_final, headers=headers, data=json.dumps(payload), timeout=15)
            
            if response.status_code == 200:
                # SUCESSO!
                resultado = response.json()
                try:
                    texto = resultado['candidates'][0]['content']['parts'][0]['text']
                    return texto, f"Sucesso via {nome_modelo}"
                except:
                    log_erros.append(f"{nome_modelo}: Resposta 200 mas vazia")
            
            elif response.status_code == 429:
                # Se for limite de cota, espera 2 segundinhos e tenta o próximo
                log_erros.append(f"{nome_modelo}: Limite de Cota (429)")
                time.sleep(2) 
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
            
        mapa_colunas = {
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao',
            'Qtde. Venda': 'Venda',
            'Valor Venda': 'Fat'
        }
        df_v = df_v.rename(columns=mapa_colunas)
        
        cols_v = ['Codigo', 'Descricao', 'Venda', 'Fat']
        df_v = df_v[[c for c in cols_v if c in df_v.columns]]
        
        df_v['Codigo'] = pd.to_numeric(df_v['Codigo'], errors='coerce')
        df_v = df_v.dropna(subset=['Codigo'])
        
        # --- PROCESSAR ESTOQUE ---
        try: 
            df_e = pd.read_csv(arq_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except: 
            arq_estoque.seek(0)
            df_e = pd.read_excel(arq_estoque, header=None)
            
        df_e = df_e.dropna(subset=[0])
        
        if len(df_e.columns) > 5:
            df_e = df_e.rename(columns={0: 'Codigo', 1: 'Desc_E', 5: 'Estoque'})
            
            colunas_estoque = ['Codigo', 'Desc_E', 'Estoque']
            df_e = df_e[colunas_estoque]
            
            df_e['Codigo'] = pd.to_numeric(df_e['Codigo'], errors='coerce')
            df_e = df_e.dropna(subset=['Codigo'])
        else:
            return None
            
        # --- MERGE ---
        df = pd.merge(df_e, df_v, on='Codigo', how='outer')
        
        if 'Descricao' in df.columns and 'Desc_E' in df.columns:
            df['Descricao'] = df['Descricao'].fillna(df['Desc_E']).fillna("Item s/ Nome")
        elif 'Desc_E' in df.columns:
            df['Descricao'] = df['Desc_E'].fillna("Item s/ Nome")
        
        cols_finais = ['Codigo', 'Descricao', 'Estoque', 'Venda', 'Fat']
        for c in cols_finais: 
            if c not in df.columns: df[c] = 0
            if c != 'Descricao': df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
        return df[cols_finais]
    except:
        return None

# --- 4. INTERFACE ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("---")

col1, col2 = st.columns(2)
arq_vendas = col1.file_uploader("📂 1. Solte o arquivo de VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col2.file_uploader("📦 2. Solte o arquivo de ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.success("✅ Arquivos Recebidos! Processando...")
    df = carregar_dados(arq_vendas, arq_estoque)
    
    if df is not None:
        # Lógica Nexus
        df = df.sort_values('Fat', ascending=False)
        total = df['Fat'].sum()
        df['Fat_Acum'] = df['Fat'].cumsum()
        df['Perc'] = df['Fat_Acum'] / total if total > 0 else 0
        
        def def_curva(x): return 'A' if x<=0.5 else ('B' if x<=0.8 else 'C')
        df['Curva'] = df['Perc'].apply(def_curva)
        
        df['Fantasma'] = (df['Estoque'] > 5) & (df['Venda'] == 0)
        
        fantasmas = df[df['Fantasma']]
        ruptura = df[(df['Curva']=='A') & (df['Estoque']==0)]
        
        # Métricas
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens Totais", len(df))
        c2.metric("Estoque Fantasma", len(fantasmas), delta="-Atenção")
        c3.metric("Ruptura Curva A", len(ruptura), delta_color="inverse")
        
        st.subheader("📋 Top Itens Fantasmas (Dinheiro Parado)")
        st.dataframe(fantasmas[['Codigo', 'Descricao', 'Estoque', 'Venda']].head(10), use_container_width=True)
        
        st.markdown("---")
        if st.button("🤖 Gerar Plano de Ação (IA)", type="primary"):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("⚠️ Configure a API Key nos 'Secrets' do Streamlit!")
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
                
                with st.spinner("O Agente está tentando 8 satélites diferentes..."):
                    txt, info = conectar_forca_bruta(prompt, st.secrets["GEMINI_API_KEY"])
                    if txt:
                        st.success(f"✅ Análise feita via: {info}")
                        st.markdown(txt)
                    else:
                        st.error("❌ Falha Total. Relatório:")
                        st.json(info)
else:
    st.info("👆 Por favor, faça o upload dos DOIS arquivos acima para começar.")
