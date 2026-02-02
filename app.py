import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE LEITURA E LIMPEZA DE DADOS ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # --- PROCESSAR VENDAS ---
        try:
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        # Renomear colunas (Layout do seu ERP)
        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao_Venda', 
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        # Limpar
        cols_vendas = [c for c in ['Codigo', 'Descricao_Venda', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_vendas = df_vendas.dropna(subset=['Codigo'])

        # --- PROCESSAR ESTOQUE ---
        try:
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        df_estoque = df_estoque.dropna(subset=[0])
        
        # Renomear Estoque
        if len(df_estoque.columns) > 5:
            df_estoque = df_estoque.rename(columns={0: 'Codigo', 1: 'Descricao_Estoque', 5: 'Estoque_Atual'})
            df_estoque = df_estoque[['Codigo', 'Descricao_Estoque', 'Estoque_Atual']]
        else:
            st.error("Erro: Layout do arquivo de estoque inválido.")
            return None

        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        df_estoque = df_estoque.dropna(subset=['Codigo'])

        # --- MERGE ---
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        # Consolidar Descrição
        if 'Descricao_Venda' in df_final.columns and 'Descricao_Estoque' in df_final.columns:
            df_final['Descricao'] = df_final['Descricao_Venda'].fillna(df_final['Descricao_Estoque']).fillna("Item s/ Descrição")
            df_final = df_final.drop(columns=['Descricao_Venda', 'Descricao_Estoque'])
        elif 'Descricao_Venda' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Venda'].fillna("Item s/ Descrição")
        elif 'Descricao_Estoque' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Estoque'].fillna("Item s/ Descrição")
        
        # Zerar nulos
        for col in ['Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)
            else:
                df_final[col] = 0

        # Colunas Finais
        cols_finais = ['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        df_final = df_final[[c for c in cols_finais if c in df_final.columns]]
        
        return df_final

    except Exception as e:
        st.error(f"Erro ao ler arquivos: {e}")
        return None

# --- 3. LÓGICA DE NEGÓCIO (NEXUS) ---
def processar_nexus(df):
    if 'Faturamento' not in df.columns: df['Faturamento'] = 0
    if 'Estoque_Atual' not in df.columns: df['Estoque_Atual'] = 0
    if 'Qtd_Venda_30d' not in df.columns: df['Qtd_Venda_30d'] = 0

    # Curva ABCD (50/80/95)
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
    
    # Fantasma: Estoque > 5 e Venda = 0
    df['Alerta_Fantasma'] = (df['Estoque_Atual'] > 5) & (df['Qtd_Venda_30d'] == 0)
    
    return df

# --- 4. INTERFACE DO APLICATIVO ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("**Status:** Online | **IA:** Auto-Detect")

col_up1, col_up2 = st.columns(2)
arq_vendas = col_up1.file_uploader("Relatório de VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col_up2.file_uploader("Relatório de ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.divider()
    df_bruto = carregar_e_limpar_dados(arq_vendas, arq_estoque)
    
    if df_bruto is not None:
        df_nexus = processar_nexus(df_bruto)
        
        # Métricas
        col1, col2, col3 = st.columns(3)
        fantasmas = df_nexus[df_nexus['Alerta_Fantasma'] == True]
        ruptura_a = df_nexus[(df_nexus['Curva'] == 'A') & (df_nexus['Estoque_Atual'] == 0)]
        
        col1.metric("Itens", len(df_nexus))
        col2.metric("Estoque Fantasma", f"{len(fantasmas)}", delta="-Ação")
        col3.metric("Ruptura Curva A", f"{len(ruptura_a)}", delta_color="inverse")
        
        # Abas
        tab1, tab2, tab3 = st.tabs(["👻 Fantasmas", "📉 Ruptura A", "📋 Geral"])
        with tab1: st.dataframe(fantasmas, use_container_width=True)
        with tab2: st.dataframe(ruptura_a, use_container_width=True)
        with tab3: st.dataframe(df_nexus, use_container_width=True)
        
        # --- CÉREBRO DA IA (Com Redundância) ---
        st.divider()
        if st.button("🤖 Pedir Análise ao Agente", type="primary"):
            if "GEMINI_API_KEY" in st.secrets:
                
                resumo = f"""
                FANTASMAS (Top 5):
                {fantasmas.head(5).to_string() if not fantasmas.empty else "Zero."}
                
                RUPTURA A (Top 5):
                {ruptura_a.head(5).to_string() if not ruptura_a.empty else "Zero."}
                """
                
                prompt = f"Como Comprador Sênior, analise esses dados e me dê 3 ações práticas hoje:\n{resumo}"
                
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                
                with st.spinner("Conectando ao Cérebro Nexus..."):
                    try:
                        # TENTATIVA 1: Modelo Novo (Rápido)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        res = model.generate_content(prompt)
                        st.success("Análise feita com Gemini 1.5 Flash")
                        st.write(res.text)
                    except Exception as e_flash:
                        try:
                            # TENTATIVA 2: Modelo Clássico (Se o novo falhar)
                            model = genai.GenerativeModel('gemini-pro')
                            res = model.generate_content(prompt)
                            st.warning("Usando Gemini Pro (Backup)")
                            st.write(res.text)
                        except Exception as e_final:
                            st.error(f"Erro fatal na IA: {e_final}")
            else:
                st.warning("⚠️ Configure a API Key!")