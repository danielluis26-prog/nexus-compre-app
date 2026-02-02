import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- CONFIGURAÇÃO DA PÁGINA (Primeira Linha Obrigatória) ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- FUNÇÃO DE LEITURA BLINDADA (Lê XLS, CSV, Latin-1 e corrige colunas) ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # --- 1. PROCESSAR VENDAS ---
        try:
            # Tenta ler CSV com encoding antigo (comum em ERPs brasileiros)
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            # Se falhar, tenta ler como Excel nativo
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        # Renomear colunas baseadas no layout do seu sistema
        # 'Qtde\r\nCupom' é onde o sistema joga a descrição
        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao_Venda', 
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        # Limpar e converter Codigo
        cols_vendas = [c for c in ['Codigo', 'Descricao_Venda', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_vendas = df_vendas.dropna(subset=['Codigo'])

        # --- 2. PROCESSAR ESTOQUE ---
        try:
            # Tenta ler CSV primeiro
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            # Tenta Excel se falhar
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        # Remover linhas vazias iniciais
        df_estoque = df_estoque.dropna(subset=[0])
        
        # Renomear colunas do Estoque (Col 0=Cod, Col 1=Desc, Col 5=Estoque)
        if len(df_estoque.columns) > 5:
            df_estoque = df_estoque.rename(columns={0: 'Codigo', 1: 'Descricao_Estoque', 5: 'Estoque_Atual'})
            df_estoque = df_estoque[['Codigo', 'Descricao_Estoque', 'Estoque_Atual']]
        else:
            st.error("Erro: O arquivo de estoque não tem as colunas esperadas. Verifique o layout.")
            return None

        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        df_estoque = df_estoque.dropna(subset=['Codigo'])

        # --- 3. MERGE INTELIGENTE (Juntar tudo) ---
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        # Consolidar Descrição (Se não tem na venda, pega do estoque)
        if 'Descricao_Venda' in df_final.columns and 'Descricao_Estoque' in df_final.columns:
            df_final['Descricao'] = df_final['Descricao_Venda'].fillna(df_final['Descricao_Estoque']).fillna("Item sem Descrição")
            df_final = df_final.drop(columns=['Descricao_Venda', 'Descricao_Estoque'])
        elif 'Descricao_Venda' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Venda'].fillna("Item sem Descrição")
        elif 'Descricao_Estoque' in df_final.columns:
             df_final['Descricao'] = df_final['Descricao_Estoque'].fillna("Item sem Descrição")
        
        # Preencher números vazios com 0
        cols_num = ['Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)
            else:
                df_final[col] = 0

        # Garantir colunas finais
        colunas_finais = ['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        # Filtra apenas as que existem
        colunas_existentes = [c for c in colunas_finais if c in df_final.columns]
        df_final = df_final[colunas_existentes]
        
        return df_final

    except Exception as e:
        st.error(f"Erro técnico ao processar arquivos: {e}")
        return None

# --- LÓGICA DE NEGÓCIO NEXUS ---
def processar_nexus(df):
    # Garantir que colunas existam
    if 'Faturamento' not in df.columns: df['Faturamento'] = 0
    if 'Estoque_Atual' not in df.columns: df['Estoque_Atual'] = 0
    if 'Qtd_Venda_30d' not in df.columns: df['Qtd_Venda_30d'] = 0

    # 1. Curva ABCD (Regra: 50/80/95)
    df = df.sort_values(by='Faturamento', ascending=False)
    total_fat = df['Faturamento'].sum()
    df['Fat_Acum'] = df['Faturamento'].cumsum()
    
    if total_fat > 0:
        df['Perc'] = df['Fat_Acum'] / total_fat
    else:
        df['Perc'] = 0

    def definir_classe(p):
        if p <= 0.50: return 'A'
        elif p <= 0.80: return 'B'
        elif p <= 0.95: return 'C'
        else: return 'D'
    
    df['Curva'] = df['Perc'].apply(definir_classe)
    
    # 2. Detector de Fantasma (Estoque > 5 e Venda Zero)
    df['Alerta_Fantasma'] = (df['Estoque_Atual'] > 5) & (df['Qtd_Venda_30d'] == 0)
    
    return df

# --- INTERFACE DO APP ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("**Versão Final 2.0** | Gemini 1.5 Flash | Leitura Universal")

col_up1, col_up2 = st.columns(2)
arq_vendas = col_up1.file_uploader("Solte o Relatório de VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col_up2.file_uploader("Solte o Relatório de ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.divider()
    df_bruto = carregar_e_limpar_dados(arq_vendas, arq_estoque)
    
    if df_bruto is not None:
        df_nexus = processar_nexus(df_bruto)
        
        # Dashboard de Métricas
        col1, col2, col3 = st.columns(3)
        fantasmas = df_nexus[df_nexus['Alerta_Fantasma'] == True]
        ruptura_a = df_nexus[(df_nexus['Curva'] == 'A') & (df_nexus['Estoque_Atual'] == 0)]
        
        col1.metric("Itens Analisados", len(df_nexus))
        col2.metric("Estoque Fantasma", f"{len(fantasmas)} itens", delta="-Ação Necessária")
        col3.metric("Ruptura Curva A", f"{len(ruptura_a)} itens", delta_color="inverse")
        
        # Abas de Análise
        tab1, tab2, tab3 = st.tabs(["👻 Estoque Fantasma", "📉 Ruptura Curva A", "📋 Tabela Geral"])
        
        with tab1:
            if not fantasmas.empty:
                st.error(f"Estes {len(fantasmas)} itens têm estoque mas venda ZERO. Dinheiro parado!")
                st.dataframe(fantasmas[['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d']], use_container_width=True)
            else:
                st.success("Tudo limpo! Nenhum estoque fantasma detectado.")
                
        with tab2:
            if not ruptura_a.empty:
                st.warning(f"Estes {len(ruptura_a)} itens são VIPs (Curva A) e estão faltando!")
                st.dataframe(ruptura_a[['Codigo', 'Descricao', 'Qtd_Venda_30d', 'Faturamento']], use_container_width=True)
            else:
                st.success("Estoque da Curva A está saudável.")

        with tab3:
            st.dataframe(df_nexus, use_container_width=True)
        
        # --- CÉREBRO DA IA (Versão 1.5 Flash) ---
        st.divider()
        if st.button("🤖 Pedir Análise Estratégica ao Agente", type="primary"):
            if "GEMINI_API_KEY" in st.secrets:
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    
                    # Prepara resumo para não estourar limite de texto
                    resumo_fantasmas = fantasmas.head(10).to_string() if not fantasmas.empty else "Sem fantasmas."
                    resumo_ruptura = ruptura_a.head(10).to_string() if not ruptura_a.empty else "Sem ruptura."
                    
                    prompt = f"""
                    Atue como Nexus-Compre, comprador sênior de supermercado.
                    
                    Analise estes problemas detectados hoje:
                    
                    1. ESTOQUE FANTASMA (Itens parados no depósito):
                    {resumo_fantasmas}
                    
                    2. RUPTURA CRÍTICA (Curva A zerada):
                    {resumo_ruptura}
                    
                    ME DÊ:
                    1. Uma ação imediata para os fantasmas (Promoção? Auditoria?).
                    2. Uma estratégia de compra urgente para a Ruptura (Considerando logística).
                    Seja direto e use linguagem de varejo.
                    """
                    
                    with st.spinner("Analisando com Gemini 1.5 Flash..."):
                        # MODELO ATUALIZADO
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        res = model.generate_content(prompt)
                        st.markdown("### 🧠 Parecer do Comprador Digital:")
                        st.write(res.text)
                        
                except Exception as e:
                    st.error(f"Erro na conexão com a IA: {e}")
            else:
                st.warning("⚠️ API Key não configurada. Adicione no 'Secrets' do Streamlit.")
else:
    st.info("👆 Por favor, solte os relatórios de Vendas e Estoque acima para começar.")