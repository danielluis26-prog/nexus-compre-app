import streamlit as st
import pandas as pd
import google.generativeai as genai
import time

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE CONEXÃO ROBUSTA (A Chave Mestra) ---
def tentar_conectar_ia(prompt, api_key):
    # Lista de modelos para tentar (do mais rápido/novo para o mais antigo/seguro)
    modelos_para_tentar = [
        "gemini-1.5-flash",          # O ideal (Rápido e Barato)
        "gemini-1.5-flash-latest",   # Variação do ideal
        "gemini-1.5-pro",            # Mais inteligente
        "gemini-pro",                # O clássico (Estável)
        "gemini-1.0-pro"             # Legado
    ]

    genai.configure(api_key=api_key)
    log_erros = []

    for modelo_nome in modelos_para_tentar:
        try:
            model = genai.GenerativeModel(modelo_nome)
            # Tenta gerar
            response = model.generate_content(prompt)
            return response.text, modelo_nome # Sucesso! Retorna o texto e qual modelo funcionou
        except Exception as e:
            # Se der erro (404, 429, etc), guarda o erro e tenta o próximo da lista
            log_erros.append(f"{modelo_nome}: {str(e)}")
            continue
    
    # Se chegou aqui, nenhum funcionou
    return None, log_erros

# --- 3. FUNÇÃO DE LEITURA E LIMPEZA ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # VENDAS
        try:
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao_Venda', 
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        cols_vendas = [c for c in ['Codigo', 'Descricao_Venda', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_vendas = df_vendas.dropna(subset=['Codigo'])

        # ESTOQUE
        try:
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        df_estoque = df_estoque.dropna(subset=[0])
        
        if len(df_estoque.columns) > 5:
            df_estoque = df_estoque.rename(columns={0: 'Codigo', 1: 'Descricao_Estoque', 5: 'Estoque_Atual'})
            df_estoque = df_estoque[['Codigo', 'Descricao_Estoque', 'Estoque_Atual']]
        else:
            st.error("Erro: Layout de estoque inválido.")
            return None

        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        df_estoque = df_estoque.dropna(subset=['Codigo'])

        # MERGE
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        if 'Descricao_Venda' in df_final.columns and 'Descricao_Estoque' in df_final.columns:
            df_final['Descricao'] = df_final['Descricao_Venda'].fillna(df_final['Descricao_Estoque']).fillna("Item s/ Descrição")
            df_final = df_final.drop(columns=['Descricao_Venda', 'Descricao_Estoque'])
        elif 'Descricao_Venda' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Venda'].fillna("Item s/ Descrição")
        elif 'Descricao_Estoque' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Estoque'].fillna("Item s/ Descrição")
        
        for col in ['Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)
            else:
                df_final[col] = 0

        cols_finais = ['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        return df_final[[c for c in cols_finais if c in df_final.columns]]

    except Exception as e:
        st.error(f"Erro leitura: {e}")
        return None

# --- 4. LÓGICA DE NEGÓCIO ---
def processar_nexus(df):
    if 'Faturamento' not in df.columns: df['Faturamento'] = 0
    if 'Estoque_Atual' not in df.columns: df['Estoque_Atual'] = 0
    if 'Qtd_Venda_30d' not in df.columns: df['Qtd_Venda_30d'] = 0

    df = df.sort_values(by='Faturamento', ascending=False)
    total = df['Faturamento'].sum()
    df['Fat_Acum'] = df['Faturamento'].cumsum()
    df['Perc'] = df['Fat_Acum'] / total if total > 0 else 0

    def definir_classe(p):
        if p <= 0.50: return 'A'
        elif p <= 0.80: return 'B'
        elif p <= 0.95: return 'C'
        else: return 'D'
    
    df['Curva'] = df['Perc'].apply(definir_classe)
    df['Alerta_Fantasma'] = (df['Estoque_Atual'] > 5) & (df['Qtd_Venda_30d'] == 0)
    return df

# --- 5. INTERFACE ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("**Versão Final** | Auto-Seleção de Modelo IA")

col_up1, col_up2 = st.columns(2)
arq_vendas = col_up1.file_uploader("VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col_up2.file_uploader("ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.divider()
    df_bruto = carregar_e_limpar_dados(arq_vendas, arq_estoque)
    
    if df_bruto is not None:
        df_nexus = processar_nexus(df_bruto)
        
        col1, col2, col3 = st.columns(3)
        fantasmas = df_nexus[df_nexus['Alerta_Fantasma'] == True]
        ruptura_a = df_nexus[(df_nexus['Curva'] == 'A') & (df_nexus['Estoque_Atual'] == 0)]
        
        col1.metric("Itens", len(df_nexus))
        col2.metric("Fantasma", f"{len(fantasmas)}", delta="-Ação")
        col3.metric("Ruptura A", f"{len(ruptura_a)}", delta_color="inverse")
        
        tab1, tab2, tab3 = st.tabs(["👻 Fantasmas", "📉 Ruptura", "📋 Geral"])
        with tab1: st.dataframe(fantasmas, use_container_width=True)
        with tab2: st.dataframe(ruptura_a, use_container_width=True)
        with tab3: st.dataframe(df_nexus, use_container_width=True)
        
        st.divider()
        if st.button("🤖 Pedir Análise (Auto-Diagnóstico)", type="primary"):
            if "GEMINI_API_KEY" in st.secrets:
                
                resumo = f"FANTASMAS (Top 10):\n{fantasmas.head(10).to_string()}\nRUPTURA A (Top 10):\n{ruptura_a.head(10).to_string()}"
                prompt = f"Analise estes dados de varejo e sugira ações práticas (Você é o Comprador Nexus):\n{resumo}"
                
                with st.spinner("O Nexus está procurando o melhor cérebro disponível..."):
                    resposta, modelo_usado = tentar_conectar_ia(prompt, st.secrets["GEMINI_API_KEY"])
                    
                    if resposta:
                        st.success(f"✅ Análise gerada usando: **{modelo_usado}**")
                        st.write(resposta)
                    else:
                        st.error("❌ Falha total. Nenhum modelo do Google respondeu.")
                        st.json(modelo_usado) # Mostra o log de erros técnicos se tudo falhar
            else:
                st.warning("Configure a API Key!")