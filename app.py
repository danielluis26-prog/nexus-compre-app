import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Nexus-Compre", page_icon="🛒", layout="wide")

# --- 2. FUNÇÃO DE AUTO-DESCOBERTA DE MODELOS ---
def descobrir_e_conectar(prompt, api_key):
    # PASSO 1: Perguntar ao Google quais modelos existem para esta conta
    url_listar = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response_list = requests.get(url_listar)
        if response_list.status_code != 200:
            return None, f"Erro ao listar modelos: {response_list.status_code}"
            
        dados = response_list.json()
        
        # Filtrar apenas modelos que geram texto ('generateContent') e são da família Gemini
        modelos_disponiveis = []
        if 'models' in dados:
            for m in dados['models']:
                if 'generateContent' in m['supportedGenerationMethods'] and 'gemini' in m['name']:
                    modelos_disponiveis.append(m['name'])
        
        # Ordenar para tentar os 'Flash' primeiro (são mais rápidos e baratos)
        # A lista fica tipo: ['models/gemini-1.5-flash', 'models/gemini-pro', ...]
        modelos_prioritarios = sorted(modelos_disponiveis, key=lambda x: 'flash' not in x)
        
        if not modelos_prioritarios:
            return None, "Nenhum modelo Gemini encontrado na sua conta."

    except Exception as e:
        return None, f"Erro de conexão na listagem: {str(e)}"

    # PASSO 2: Tentar gerar o texto usando a lista real que o Google devolveu
    log_tentativas = []
    
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for modelo_nome in modelos_prioritarios:
        # A URL precisa ser montada com o nome exato que o Google mandou
        # modelo_nome já vem como 'models/gemini-xyz'
        url_gerar = f"https://generativelanguage.googleapis.com/v1beta/{modelo_nome}:generateContent?key={api_key}"
        
        try:
            response = requests.post(url_gerar, headers=headers, data=json.dumps(payload), timeout=20)
            
            if response.status_code == 200:
                resultado = response.json()
                try:
                    texto = resultado['candidates'][0]['content']['parts'][0]['text']
                    return texto, f"Sucesso usando: **{modelo_nome}**"
                except:
                    log_tentativas.append(f"{modelo_nome}: Resposta vazia")
            
            elif response.status_code == 429:
                log_tentativas.append(f"{modelo_nome}: Sem cota (429)")
                # Não espera muito aqui, já pula para o próximo modelo da lista
                continue 
            else:
                log_tentativas.append(f"{modelo_nome}: Erro {response.status_code}")
        
        except Exception as e:
            log_tentativas.append(f"{modelo_nome}: Erro técnico")
    
    # Se chegou aqui, falhou em todos
    return None, log_tentativas

# --- 3. LEITURA DE DADOS ---
def carregar_dados(arq_vendas, arq_estoque):
    try:
        # Vendas
        try: df_v = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python')
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
        
        # Estoque
        try: df_e = pd.read_csv(arq_estoque, header=None, encoding='latin-1', sep=None, engine='python')
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
            
        # Merge
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
                
                with st.spinner("🕵️ O Agente está procurando o melhor modelo disponível na sua conta..."):
                    txt, info = descobrir_e_conectar(prompt, st.secrets["GEMINI_API_KEY"])
                    if txt:
                        st.success(f"✅ {info}")
                        st.markdown(txt)
                    else:
                        st.error("❌ Falha Total. Tentamos todos os modelos da sua conta e nenhum respondeu.")
                        st.write("Relatório de erros:")
                        st.json(info)
else:
    st.info("👆 Por favor, faça o upload dos DOIS arquivos acima para começar.")
