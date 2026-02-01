import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- FUNÇÃO ESPECIAL DE LEITURA BLINDADA ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # Tenta ler com encoding 'latin-1' (padrão Brasil/Windows antigo)
        # engine='python' ajuda a detectar separadores automaticamente
        
        # 1. Carregar Vendas
        try:
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            # Se falhar, tenta ler como Excel direto (caso seja .xls real)
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        # Renomear as colunas chatas
        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao', 
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        # Selecionar só o que importa
        # Garante que as colunas existem antes de filtrar
        cols_vendas = [c for c in ['Codigo', 'Descricao', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        
        # 2. Carregar Estoque
        try:
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        # Limpar linhas vazias
        df_estoque = df_estoque.dropna(subset=[0])
        
        # Pegar as colunas certas (Col 0: Código, Col 5: Estoque Atual)
        # Verifica se a coluna 5 existe (para não dar erro de índice)
        if 5 in df_estoque.columns:
            df_estoque = df_estoque[[0, 5]]
            df_estoque.columns = ['Codigo', 'Estoque_Atual']
        else:
            st.error("Erro: O arquivo de estoque não tem a coluna 5 (Estoque). Verifique o layout.")
            return None
        
        # 3. Tratamento de Tipos
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        
        df_estoque['Estoque_Atual'] = pd.to_numeric(df_estoque['Estoque_Atual'], errors='coerce').fillna(0)
        
        # Se 'Faturamento' existir, converte. Se não, cria zerado.
        if 'Faturamento' in df_vendas.columns:
            df_vendas['Faturamento'] = pd.to_numeric(df_vendas['Faturamento'], errors='coerce').fillna(0)
        
        # Remover códigos inválidos
        df_vendas = df_vendas.dropna(subset=['Codigo'])
        df_estoque = df_estoque.dropna(subset=['Codigo'])
        
        # 4. Juntar tudo
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        # Preencher vazios
        if 'Descricao' in df_final.columns:
            df_final['Descricao'] = df_final['Descricao'].fillna("Item sem Descrição")
        
        df_final = df_final.fillna(0)
        
        return df_final

    except Exception as e:
        st.error(f"Erro técnico ao processar: {e}")
        return None

# --- LÓGICA DE NEGÓCIO NEXUS ---
def processar_nexus(df):
    # Garante que as colunas existam
    if 'Faturamento' not in df.columns: df['Faturamento'] = 0
    if 'Estoque_Atual' not in df.columns: df['Estoque_Atual'] = 0
    if 'Qtd_Venda_30d' not in df.columns: df['Qtd_Venda_30d'] = 0

    # 1. Curva ABCD
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
    
    # 2. Detector de Fantasma
    df['Alerta_Fantasma'] = (df['Estoque_Atual'] > 5) & (df['Qtd_Venda_30d'] == 0)
    
    return df

# --- INTERFACE DO APP ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("Versão adaptada (Correção Latin-1)")

col_up1, col_up2 = st.columns(2)
arq_vendas = col_up1.file_uploader("Solte o Relatório de VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col_up2.file_uploader("Solte o Relatório de ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.divider()
    df_bruto = carregar_e_limpar_dados(arq_vendas, arq_estoque)
    
    if df_bruto is not None:
        df_nexus = processar_nexus(df_bruto)
        
        col1, col2, col3 = st.columns(3)
        fantasmas = df_nexus[df_nexus['Alerta_Fantasma'] == True]
        
        col1.metric("Itens Analisados", len(df_nexus))
        col2.metric("Estoque Fantasma", f"{len(fantasmas)} itens", delta="-Ação Necessária")
        col3.metric("Faturamento Total", f"R$ {df_nexus['Faturamento'].sum():,.2f}")
        
        if not fantasmas.empty:
            st.error(f"🚨 ATENÇÃO: Encontramos {len(fantasmas)} produtos com suspeita de estoque virtual!")
            st.dataframe(fantasmas[['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d']], use_container_width=True)
        
        st.divider()
        if st.button("🤖 Pedir Análise ao Agente", type="primary"):
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                dados_csv = fantasmas.head(10).to_string()
                prompt = f"""
                Sou o Nexus-Compre. Analise estes itens com 'Estoque Fantasma' (Alto estoque, Venda Zero).
                Dê 3 sugestões práticas do que fazer com eles.
                DADOS:
                {dados_csv}
                """
                model = genai.GenerativeModel('gemini-pro')
                res = model.generate_content(prompt)
                st.write(res.text)
            else:
                st.warning("Configure a API Key no .streamlit/secrets.toml")