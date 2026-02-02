import streamlit as st
import pandas as pd
import google.generativeai as genai
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE CONEXÃO (Tenta TUDO) ---
def tentar_conectar_ia(prompt, api_key):
    # Tenta modelos variados para garantir resposta
    modelos = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    
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
                    time.sleep(5)
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
        
        # Garante colunas mínimas
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
st.caption("Versão Corrigida: Foco 100% Varejo")

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
        
        # Lógica Fantasma: Estoque > 5 e Venda Zerada
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
                # --- AQUI ESTÁ A CORREÇÃO DO PROMPT ---
                prompt = f"""
                ATUE COMO UM GERENTE DE COMPRAS DE SUPERMERCADO SÊNIOR.
                Contexto: Estamos analisando dados reais de Varejo Alimentar.
                
                NÃO DÊ CONSELHOS PSICOLÓGICOS OU DE AUTO-AJUDA.
                SEJA TÉCNICO, FRIO E FOCADO EM LUCRO.

                DEFINIÇÕES TÉCNICAS:
                1. "FANTASMAS" = "Estoque Virtual" ou "Item Sem Giro". Significa produto parado na prateleira ou erro de sistema (tem saldo mas não vende). Dinheiro parado.
                2. "RUPTURA" = Produto que vende muito (Curva A) mas o estoque está zero. Perda de venda.

                DADOS DO RELATÓRIO ATUAL:
                - Itens Fantasmas (Top 10):
                {fantasmas[['Codigo', 'Descricao', 'Estoque']].head(10).to_string(index=False)}

                - Ruptura Curva A (Top 10):
                {ruptura[['Codigo', 'Descricao', 'Venda']].head(10).to_string(index=False)}

                MISSÃO:
                Escreva um plano de ação curto (3 tópicos) para a equipe da loja resolver isso HOJE.
                Sugira ações como: Auditoria, Promoção, Transferência, Compra Urgente.
                """
                
                with st.spinner("Analisando estoque com IA..."):
                    txt, modelo = tentar_conectar_ia(prompt, st.secrets["GEMINI_API_KEY"])
                    if txt:
                        st.success(f"Analise gerada por: {modelo}")
                        st.markdown(txt)
                    else:
                        st.error("Erro na conexão.")
                        st.json(modelo)