import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- FUNÇÕES DE LÓGICA DE NEGÓCIO ---
def classificar_abcd(df):
    # Lógica do Usuário: A(50%), B(80%), C(95%), D(Resto) baseada em Faturamento
    df['Faturamento'] = df['Venda'] * df['Preco_Venda']
    df = df.sort_values(by='Faturamento', ascending=False)
    df['Faturamento_Acumulado'] = df['Faturamento'].cumsum()
    df['Total_Fat'] = df['Faturamento'].sum()
    df['Perc_Acumulado'] = df['Faturamento_Acumulado'] / df['Total_Fat']
    
    def definir_classe(p):
        if p <= 0.50: return 'A'
        elif p <= 0.80: return 'B'
        elif p <= 0.95: return 'C'
        else: return 'D'
    
    df['Curva'] = df['Perc_Acumulado'].apply(definir_classe)
    return df

def detectar_fantasma(df):
    # Lógica: Estoque alto + Venda Zero Recentemente
    # Critério: Estoque > 10 E Venda 7 dias == 0
    df['Alerta_Fantasma'] = (df['Estoque'] > 10) & (df['Venda_7dias'] == 0)
    return df

# --- INTERFACE VISUAL (FRONT-END) ---
st.title("🛒 Nexus-Compre: Agente Inteligente")
st.markdown("**Versão Mobile/PC** | Foco: Bomboniere & Geral")

# 1. Configurar API Key (Segredo)
api_key = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=api_key)

# 2. Upload de Arquivo
uploaded_file = st.file_uploader("📂 Solte sua planilha Excel aqui", type=["xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        
        # Validar colunas mínimas
        colunas_necessarias = ['Descricao', 'Estoque', 'Venda', 'Venda_7dias', 'Preco_Venda']
        if not all(col in df.columns for col in colunas_necessarias):
            st.error(f"Erro: A planilha precisa ter as colunas: {colunas_necessarias}")
        else:
            # Processar Dados
            df_processado = classificar_abcd(df)
            df_processado = detectar_fantasma(df_processado)
            
            # --- VISÃO RESUMIDA (DASHBOARD) ---
            st.subheader("📊 Diagnóstico Rápido")
            col1, col2, col3 = st.columns(3)
            
            total_ruptura = len(df_processado[df_processado['Estoque'] == 0])
            total_fantasma = len(df_processado[df_processado['Alerta_Fantasma'] == True])
            top_a = df_processado[df_processado['Curva'] == 'A']['Descricao'].head(1).values[0] if not df_processado.empty else "N/A"

            col1.metric("Ruptura Total", f"{total_ruptura} itens", delta_color="inverse")
            col2.metric("Estoque Fantasma", f"{total_fantasma} itens", delta="-Perigo")
            col3.metric("Líder Curva A", top_a)

            # --- BOTÃO PARA CHAMAR A IA ---
            st.divider()
            if st.button("🤖 Gerar Análise de Compras (IA)", type="primary", use_container_width=True):
                with st.spinner("O Nexus está pensando..."):
                    # Preparar resumo para a IA (Não enviar a planilha toda para economizar tokens)
                    resumo_csv = df_processado[df_processado['Curva'].isin(['A', 'B']) | (df_processado['Alerta_Fantasma'] == True)].to_string()
                    
                    prompt = f"""
                    Atue como o Nexus-Compre, comprador sênior.
                    Analise os dados abaixo (Curva A/B e Fantasmas).
                    1. Identifique o maior risco de ruptura.
                    2. Sugira ação para os Estoques Fantasmas.
                    3. Se houver itens Curva A com estoque baixo, sugira compra urgente (Cenário Matinal).
                    
                    DADOS:
                    {resumo_csv}
                    """
                    
                    model = genai.GenerativeModel('gemini-pro')
                    response = model.generate_content(prompt)
                    
                    st.success("Análise Concluída!")
                    st.write(response.text)
            
            # Mostrar Tabela Filtrável
            st.subheader("🔎 Detalhe dos Dados")
            st.dataframe(df_processado, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
else:
    st.info("👆 Faça upload da planilha com as colunas: Descricao, Estoque, Venda, Venda_7dias, Preco_Venda")