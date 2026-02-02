import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- CONFIGURAÇÃO DA PÁGINA (Deve ser o primeiro comando) ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- FUNÇÃO ESPECIAL DE LEITURA BLINDADA E INTELIGENTE ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # --- 1. PROCESSAR VENDAS ---
        try:
            # Tenta ler CSV com encoding antigo
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            # Se der erro, volta o arquivo pro começo e tenta ler como Excel
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        # Mapeamento explícito das colunas do relatório de Vendas
        # Ajuste baseado nos seus arquivos: 'Qtde\r\nCupom' é onde está a descrição
        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao_Venda', 
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        # Manter apenas colunas úteis e limpar Codigo
        cols_vendas = [c for c in ['Codigo', 'Descricao_Venda', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        
        # Converter código para número
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_vendas = df_vendas.dropna(subset=['Codigo'])

        # --- 2. PROCESSAR ESTOQUE ---
        try:
            # Tenta ler CSV (muitos .xls exportados são na verdade CSVs disfarçados)
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            # Se falhar, tenta ler como Excel real
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        # Limpar linhas vazias iniciais
        df_estoque = df_estoque.dropna(subset=[0])
        
        # Mapeamento explícito das colunas do relatório de Estoque
        # Col 0 = Código, Col 1 = Descrição, Col 5 = Estoque
        # Verificamos se as colunas existem antes de renomear
        if len(df_estoque.columns) > 5:
            df_estoque = df_estoque.rename(columns={0: 'Codigo', 1: 'Descricao_Estoque', 5: 'Estoque_Atual'})
            df_estoque = df_estoque[['Codigo', 'Descricao_Estoque', 'Estoque_Atual']]
        else:
            st.error("Erro: O arquivo de estoque não tem colunas suficientes. Verifique se é o modelo correto.")
            return None

        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        df_estoque = df_estoque.dropna(subset=['Codigo'])

        # --- 3. UNIFICAR (MERGE INTELIGENTE) ---
        # Unir tudo pelo Código
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        # TRUQUE DO MESTRE: Consolidar a Descrição
        # Se tem na Venda, usa da Venda. Se não, usa do Estoque.
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

        # Garantir que as colunas finais existam
        colunas_finais = ['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        df_final = df_final[colunas_finais]
        
        return df_final

    except Exception as e:
        st.error(f"Erro técnico ao processar: {e}")
        return None

# --- LÓGICA DE NEGÓCIO NEXUS ---
def processar_nexus(df):
    # 1. Curva ABCD (Sua regra: 50/80/95)
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
    # Regra: Estoque > 5 unidades E Venda Zero nos 30 dias
    df['Alerta_Fantasma'] = (df['Estoque_Atual'] > 5) & (df['Qtd_Venda_30d'] == 0)
    
    return df

# --- INTERFACE DO APP (O QUE APARECE NA TELA) ---
st.title("🛒 Nexus-Compre: Agente Integrado")
st.markdown("Versão Final: Correção de Descrição + Leitura .XLS")

col_up1, col_up2 = st.columns(2)
arq_vendas = col_up1.file_uploader("Solte o Relatório de VENDAS", type=["csv", "xls", "xlsx"])
arq_estoque = col_up2.file_uploader("Solte o Relatório de ESTOQUE", type=["csv", "xls", "xlsx"])

if arq_vendas and arq_estoque:
    st.divider()
    df_bruto = carregar_e_limpar_dados(arq_vendas, arq_estoque)
    
    if df_bruto is not None:
        df_nexus = processar_nexus(df_bruto)
        
        # Dashboard
        col1, col2, col3 = st.columns(3)
        fantasmas = df_nexus[df_nexus['Alerta_Fantasma'] == True]
        ruptura_a = df_nexus[(df_nexus['Curva'] == 'A') & (df_nexus['Estoque_Atual'] == 0)]
        
        col1.metric("Itens Analisados", len(df_nexus))
        col2.metric("Estoque Fantasma", f"{len(fantasmas)} itens", delta="-Ação Necessária")
        col3.metric("Ruptura Curva A", f"{len(ruptura_a)} itens", delta_color="inverse")
        
        # Tabelas
        tab1, tab2, tab3 = st.tabs(["👻 Estoque Fantasma", "📉 Curva A (Ruptura)", "📋 Geral"])
        
        with tab1:
            if not fantasmas.empty:
                st.error(f"Estes {len(fantasmas)} itens constam no estoque mas NÃO vendem.")
                st.dataframe(fantasmas[['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d']], use_container_width=True)
            else:
                st.success("Nenhum estoque fantasma detectado!")
                
        with tab2:
            if not ruptura_a.empty:
                st.warning(f"Estes {len(ruptura_a)} itens são seus Campeões de Venda e estão ZERADOS!")
                st.dataframe(ruptura_a[['Codigo', 'Descricao', 'Qtd_Venda_30d', 'Faturamento']], use_container_width=True)
            else:
                st.success("Sua Curva A está abastecida!")

        with tab3:
            st.dataframe(df_nexus, use_container_width=True)
        
        # Botão IA
        st.divider()
        if st.button("🤖 Pedir Análise ao Agente", type="primary"):
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                
                # Resumo Inteligente para a IA
                resumo_fantasmas = fantasmas.head(5).to_string() if not fantasmas.empty else "Sem fantasmas."
                resumo_ruptura = ruptura_a.head(5).to_string() if not ruptura_a.empty else "Sem ruptura na Curva A."
                
                prompt = f"""
                Atue como Nexus-Compre (Comprador Sênior).
                Analise os dados extraídos dos relatórios:
                
                1. ITENS FANTASMA (Estoque alto, Venda zero):
                {resumo_fantasmas}
                
                2. RUPTURA CURVA A (Mais importantes faltando):
                {resumo_ruptura}
                
                AÇÃO: Me dê um plano de ação curto e grosso para resolver esses B.O.s hoje.
                """
                
                with st.spinner("Analisando cenários..."):
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content(prompt)
                    st.write(res.text)
            else:
                st.warning("⚠️ API Key não configurada. Adicione no 'Secrets' do Streamlit.")
else:

    st.info("👆 Aguardando arquivos... Solte os dois relatórios acima.")
