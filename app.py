# --- FUNÇÃO ESPECIAL DE LEITURA BLINDADA E INTELIGENTE ---
def carregar_e_limpar_dados(arquivo_vendas, arquivo_estoque):
    try:
        # --- 1. PROCESSAR VENDAS ---
        try:
            df_vendas = pd.read_csv(arquivo_vendas, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_vendas.seek(0)
            df_vendas = pd.read_excel(arquivo_vendas)

        # Mapeamento explícito das colunas do relatório de Vendas
        df_vendas = df_vendas.rename(columns={
            'Item de Estoque:': 'Codigo',
            'Qtde\r\nCupom': 'Descricao_Venda', # Nome provisório
            'Qtde. Venda': 'Qtd_Venda_30d',
            'Valor Venda': 'Faturamento'
        })
        
        # Manter apenas colunas úteis e limpar Codigo
        cols_vendas = [c for c in ['Codigo', 'Descricao_Venda', 'Qtd_Venda_30d', 'Faturamento'] if c in df_vendas.columns]
        df_vendas = df_vendas[cols_vendas]
        df_vendas['Codigo'] = pd.to_numeric(df_vendas['Codigo'], errors='coerce')
        df_vendas = df_vendas.dropna(subset=['Codigo'])

        # --- 2. PROCESSAR ESTOQUE ---
        try:
            df_estoque = pd.read_csv(arquivo_estoque, header=None, encoding='latin-1', sep=None, engine='python')
        except:
            arquivo_estoque.seek(0)
            df_estoque = pd.read_excel(arquivo_estoque, header=None)
        
        # Limpar linhas vazias
        df_estoque = df_estoque.dropna(subset=[0])
        
        # Mapeamento explícito das colunas do relatório de Estoque
        # Col 0 = Código, Col 1 = Descrição, Col 5 = Estoque
        df_estoque = df_estoque.rename(columns={0: 'Codigo', 1: 'Descricao_Estoque', 5: 'Estoque_Atual'})
        
        # Manter apenas colunas úteis
        df_estoque = df_estoque[['Codigo', 'Descricao_Estoque', 'Estoque_Atual']]
        df_estoque['Codigo'] = pd.to_numeric(df_estoque['Codigo'], errors='coerce')
        df_estoque = df_estoque.dropna(subset=['Codigo'])

        # --- 3. UNIFICAR (MERGE INTELIGENTE) ---
        # Unir tudo pelo Código
        df_final = pd.merge(df_estoque, df_vendas, on='Codigo', how='outer')
        
        # TRUQUE DO MESTRE: Consolidar a Descrição
        # Se tem na Venda, usa da Venda. Se não, usa do Estoque. Se não, avisa.
        df_final['Descricao'] = df_final['Descricao_Venda'].fillna(df_final['Descricao_Estoque']).fillna("Item sem Descrição")
        
        # Limpar as colunas auxiliares antigas
        df_final = df_final.drop(columns=['Descricao_Venda', 'Descricao_Estoque'])
        
        # Preencher números vazios com 0
        cols_num = ['Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']
        for col in cols_num:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)
            else:
                df_final[col] = 0

        # Reordenar para ficar bonito na tela
        df_final = df_final[['Codigo', 'Descricao', 'Estoque_Atual', 'Qtd_Venda_30d', 'Faturamento']]
        
        return df_final

    except Exception as e:
        st.error(f"Erro técnico ao processar: {e}")
        return None