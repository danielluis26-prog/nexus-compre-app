import streamlit as st
import pandas as pd
import google.generativeai as genai
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE CONEXÃO (Tenta TUDO) ---
def tentar_conectar_ia(prompt, api_key):
    # Ordem de tentativa:
    # 1. 1.5 Flash: O melhor (Rápido/Grátis). Precisa da lib nova.
    # 2. 2.0 Flash: O que apareceu na sua lista (mas tem limite baixo).
    # 3. Pro Latest: Último recurso.
    modelos = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
    
    genai.configure(api_key=api_key)
    
    log_erros = []
    
    for modelo in modelos:
        try:
            mod = genai.GenerativeModel(modelo)
            res = mod.generate_content(prompt)
            return res.text, modelo
        except Exception as e:
            erro_str = str(e)
            # Se for erro de limite (429) no modelo 2.0, espera e tenta de novo
            if "429" in erro_str and "2.0" in modelo:
                try:
                    time.sleep(5) # Espera um pouco
                    res = mod.generate_content(prompt)
                    return res.text, modelo
                except:
                    pass
            
            log_erros.append(f"{modelo}: {erro_str}")
            continue
            
    return None, log_erros

# --- 3. LEITURA DE DADOS ---
def carregar_dados(arq_vendas, arq_estoque):
    try:
        # Vendas
        try: df_v = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python')
        except: 
            arq_vendas.seek(0)
            df_v = pd.read_excel(arq_vendas)
            
        df_v = df_v.rename(columns={'Item de Estoque:': 'Codigo', 'Qtde\r\nCupom': 'Descricao', 'Qtde. Venda': 'Venda', 'Valor Venda': 'Fat'})
        df_v = df_v[['Codigo', 'Descricao', 'Venda', 'Fat']]
        df_v['Codigo'] = pd.to_numeric(df_v['Codigo'], errors='coerce')
        
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
        else:
            return None
            
        # Merge
        df = pd.merge(df_e, df_v, on='Codigo', how='outer')
        if 'Descricao' in df.columns and 'Desc_E' in df.columns:
            df['Descricao'] = df['Descricao'].fillna(df['Desc_E']).fillna("Item s/ Nome")
        
        cols = ['Codigo', 'Descricao', 'Estoque', 'Venda', 'Fat']
        for c in cols: 
            if c not in df.columns: df[c] = 0
            if c != 'Descricao': df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
        return df[cols]
    except:
        return None

# --- 4. INTERFACE ---
st.title("🛒 Nexus-Compre: Agente Integrado")

up1, up2 = st.columns(2)
f1 = up1.file_uploader("Vendas")
f2 = up2.file_uploader("Estoque")

if f1 and f2:
    df = carregar_dados(f1, f2)
    if df is not None:
        # Lógica Nexus
        df = df.sort_values('Fat', ascending=False)
        df['Fat_Acum'] = df['Fat'].cumsum()
        total = df['Fat'].sum()
        df['Perc'] = df['Fat_Acum'] / total if total > 0 else 0
        df['Curva'] = df['Perc'].apply(lambda x: 'A' if x<=0.5 else ('B' if x<=0.8 else 'C'))
        df['Fantasma'] = (df['Estoque'] > 5) & (df['Venda'] == 0)
        
        fantasmas = df[df['Fantasma']]
        ruptura = df[(df['Curva']=='A') & (df['Estoque']==0)]
        
        st.metric("Fantasmas", len(fantasmas))
        st.metric("Ruptura A", len(ruptura))
        
        st.dataframe(fantasmas.head())
        
        if st.button("🤖 Analisar"):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("Sem chave API.")
            else:
                prompt = f"Analise: Fantasmas ({len(fantasmas)} itens), Ruptura A ({len(ruptura)} itens). Dê 3 ações."
                with st.spinner("Tentando conectar..."):
                    txt, modelo = tentar_conectar_ia(prompt, st.secrets["GEMINI_API_KEY"])
                    if txt:
                        st.success(f"Conectado via: {modelo}")
                        st.write(txt)
                    else:
                        st.error("Erro fatal. Logs:")
                        st.json(modelo)