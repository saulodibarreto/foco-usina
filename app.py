
import streamlit as st
import pandas as pd
import os
import re
import calendar
import io
import psycopg2
from datetime import date

# Configuração inicial
st.set_page_config(page_title="Foco Usina - Gestão", layout="wide")

# --- FUNÇÕES ---
def safe_str(val):
    if pd.isna(val) or str(val).strip().upper() == 'NAN': return ""
    texto = str(val).strip()
    if texto.endswith('.0'): texto = texto[:-2]
    return texto

def formatar_cpf(texto):
    texto_limpo = safe_str(texto)
    if not texto_limpo: return ""
    num = re.sub(r'\D', '', texto_limpo)
    if len(num) == 11: return f"{num[:3]}.{num[3:6]}.{num[6:9]}-{num[9:]}"
    return texto_limpo

def formatar_telefone(texto):
    texto_limpo = safe_str(texto)
    if not texto_limpo: return ""
    num = re.sub(r'\D', '', texto_limpo)
    if len(num) == 11: return f"({num[:2]}) {num[2:7]}-{num[7:]}"
    elif len(num) == 10: return f"({num[:2]}) {num[2:6]}-{num[6:]}"
    return texto_limpo

def extrair_serie(nome_turma):
    match = re.search(r'(\d+)º', str(nome_turma))
    return f"{match.group(1)}º Ano" if match else "Outras"

def ordenar_turmas(lista_turmas):
    def chave_ordem(nome):
        dias_map = {'SEG':1, 'TER':2, 'QUA':3, 'QUI':4, 'SEX':5, 'SAB':6, 'DOM':7}
        dia_val = 8
        for sigla, num in dias_map.items():
            if sigla in str(nome).upper():
                dia_val = num
                break
        match = re.search(r'(\d{1,2})[hH:]', str(nome))
        hora_val = int(match.group(1)) if match else 24
        match_sartre = re.search(r'(\d+)º\s*(\d+)', str(nome))
        if match_sartre: return (0, int(match_sartre.group(1)), int(match_sartre.group(2)), str(nome))
        return (dia_val, hora_val, str(nome))
    return sorted(list(set([str(t) for t in lista_turmas if pd.notna(t) and safe_str(t) != ""])), key=chave_ordem)

# --- BASE DE DADOS (SUPABASE POSTGRES) ---
@st.cache_resource
def init_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"], sslmode='require')

conn = init_connection()

def ler_sql(query, params=None):
    return pd.read_sql_query(query, conn, params=params)

@st.cache_data(ttl=120)
def ler_sql_cached(query, params=None):
    return pd.read_sql_query(query, conn, params=params)

def executar_sql(query, params=None):
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()
    st.cache_data.clear()

def executar_lote_sql(comandos):
    cur = conn.cursor()
    for query, params in comandos:
        cur.execute(query, params)
    conn.commit()
    cur.close()
    st.cache_data.clear()

# --- MOTOR DE ESTADO E LOGIN ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = None
    st.session_state['perfil'] = None
    st.session_state['nome_prof'] = None

for key in ['key_escola', 'key_turma', 'key_matricula', 'key_prof', 'key_user', 'key_novo_aluno']:
    if key not in st.session_state: st.session_state[key] = 0

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("FOCO USINA DE ARTES.png"): st.image("FOCO USINA DE ARTES.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center;'>🎭 Foco Usina - Acesso</h2>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                cur = conn.cursor()
                cur.execute("SELECT login, perfil, nome_professor FROM usuarios WHERE login=%s AND senha=%s", (usuario_input, senha_input))
                resultado = cur.fetchone()
                cur.close()
                if resultado:
                    st.session_state['logado'] = True
                    st.session_state['usuario'] = resultado[0]
                    st.session_state['perfil'] = resultado[1]
                    st.session_state['nome_prof'] = resultado[2]
                    st.rerun()
                else:
                    st.error("⚠️ Usuário ou senha incorretos.")
    st.stop()

if os.path.exists("FOCO USINA DE ARTES.png"): st.sidebar.image("FOCO USINA DE ARTES.png", use_container_width=True)
else: st.sidebar.title("🎭 Foco Usina")

st.sidebar.markdown(f"👤 **Logado como:** {st.session_state['usuario'].title()} ({st.session_state['perfil']})")
if st.sidebar.button("Sair / Logout"):
    st.session_state['logado'] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Bloco de Trabalho")
projeto_atual = st.sidebar.radio("Selecione o Projeto:", ["Curso Extra", "Projeto de Teatro Sartre", "Turno Integral Sartre"])
st.sidebar.markdown("---")

if st.session_state['perfil'] == 'admin':
    opcoes_menu = ["Dashboard", "Escolas, Turmas, Profs e Acessos", "Cadastrar Aluno / Matrícula", "Ver / Editar Alunos", "Caderneta / Presença"]
    if projeto_atual == "Curso Extra": opcoes_menu.append("Financeiro / Extrato")
    opcoes_menu.append("Meu Perfil / Senha")
else:
    opcoes_menu = ["Dashboard", "Caderneta / Presença", "Meu Perfil / Senha"]

menu = st.sidebar.radio("Navegação", opcoes_menu)

df_escolas_db = ler_sql_cached("SELECT nome_escola FROM escolas WHERE projeto=%s ORDER BY nome_escola", params=(projeto_atual,))
lista_escolas_limpa = [safe_str(x) for x in df_escolas_db['nome_escola'].tolist() if safe_str(x) != ""]
df_prof_db = ler_sql_cached("SELECT nome_professor FROM professores WHERE projeto=%s ORDER BY nome_professor", params=(projeto_atual,))
lista_profs = [safe_str(x) for x in df_prof_db['nome_professor'].tolist() if safe_str(x) != ""]

# --- ECRÃS DO SISTEMA ---

if menu == "Dashboard":
    st.title("Visão Geral")
    st.write(f"Bem-vindo ao sistema da Foco Usina de Artes, **{st.session_state['usuario'].title()}**.")
    st.info(f"📌 Você está no ambiente: **{projeto_atual}**.")

elif menu == "Meu Perfil / Senha":
    st.title("👤 Meu Perfil")
    st.write("Altere a sua senha de acesso ao sistema.")
    with st.form("form_senha"):
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
        if st.form_submit_button("Atualizar Senha", type="primary"):
            if nova_senha and nova_senha == confirma_senha:
                executar_sql("UPDATE usuarios SET senha=%s WHERE login=%s", (nova_senha, st.session_state['usuario']))
                st.success("✅ A sua senha foi alterada com sucesso!")
            else:
                st.error("⚠️ As senhas não coincidem ou estão vazias.")

elif menu == "Escolas, Turmas, Profs e Acessos" and st.session_state['perfil'] == 'admin':
    st.title(f"🏫 Gestão Base: {projeto_atual}")
    aba_escolas, aba_profs, aba_turmas, aba_importar, aba_acessos = st.tabs(["🏢 Escolas", "👨‍🏫 Professores", "⏰ Turmas", "📥 Importar Planilha Mágica", "🔐 Acessos (Logins)"])
    
    with aba_escolas:
        colE1, colE2 = st.columns(2)
        with colE1:
            st.subheader("Nova Escola")
            with st.form(f"form_escola_{st.session_state.key_escola}"):
                nova_escola = st.text_input("Nome da Escola / Local")
                if st.form_submit_button("Adicionar Escola"):
                    if nova_escola.strip():
                        if ler_sql("SELECT id FROM escolas WHERE nome_escola=%s AND projeto=%s", (nova_escola.strip().upper(), projeto_atual)).empty:
                            executar_sql("INSERT INTO escolas (nome_escola, projeto) VALUES (%s, %s)", (nova_escola.strip().upper(), projeto_atual))
                            st.rerun()
        with colE2:
            st.subheader("Escolas deste Projeto")
            df_esc = ler_sql('''SELECT id, nome_escola as "Escola" FROM escolas WHERE projeto=%s''', params=(projeto_atual,))
            if not df_esc.empty:
                with st.form("form_edicao_escolas"):
                    df_esc['Excluir'] = False
                    edited_escolas = st.data_editor(df_esc, hide_index=True, column_config={"id": None, "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", default=False)}, use_container_width=True)
                    conf_esc = st.checkbox("Confirmo as exclusões")
                    if st.form_submit_button("💾 Salvar Alterações (Escolas)", type="primary"):
                        if not conf_esc and any(edited_escolas['Excluir']): st.error("Marque a confirmação antes de excluir.")
                        else:
                            lote_comandos = []
                            for _, row in edited_escolas.iterrows():
                                if row.get('Excluir', False): lote_comandos.append(("DELETE FROM escolas WHERE id=%s", (row['id'],)))
                                else: lote_comandos.append(("UPDATE escolas SET nome_escola=%s WHERE id=%s", (row['Escola'], row['id'])))
                            executar_lote_sql(lote_comandos)
                            st.success("✅ Atualizado!"); st.rerun()

    with aba_profs:
        colP1, colP2 = st.columns(2)
        with colP1:
            st.subheader("Novo Professor")
            with st.form(f"form_prof_{st.session_state.key_prof}"):
                novo_prof = st.text_input("Nome do Professor")
                if st.form_submit_button("Adicionar Professor"):
                    if novo_prof.strip():
                        if ler_sql("SELECT id FROM professores WHERE nome_professor=%s AND projeto=%s", (novo_prof.strip(), projeto_atual)).empty:
                            executar_sql("INSERT INTO professores (nome_professor, projeto) VALUES (%s, %s)", (novo_prof.strip(), projeto_atual))
                            st.rerun()
        with colP2:
            st.subheader("Professores deste Projeto")
            df_prof = ler_sql('''SELECT id, nome_professor as "Nome" FROM professores WHERE projeto=%s''', params=(projeto_atual,))
            if not df_prof.empty:
                with st.form("form_edicao_profs"):
                    df_prof['Excluir'] = False
                    edited_profs = st.data_editor(df_prof, hide_index=True, column_config={"id": None, "Excluir": st.column_config.CheckboxColumn("🗑 Excluir", default=False)}, use_container_width=True)
                    conf_prof = st.checkbox("Confirmo as exclusões")
                    if st.form_submit_button("💾 Salvar Alterações (Profs)", type="primary"):
                        if not conf_prof and any(edited_profs['Excluir']): st.error("Marque a confirmação antes de excluir.")
                        else:
                            lote_comandos = []
                            for _, row in edited_profs.iterrows():
                                if row.get('Excluir', False): lote_comandos.append(("DELETE FROM professores WHERE id=%s", (row['id'],)))
                                else: lote_comandos.append(("UPDATE professores SET nome_professor=%s WHERE id=%s", (row['Nome'], row['id'])))
                            executar_lote_sql(lote_comandos)
                            st.success("✅ Atualizado!"); st.rerun()

    with aba_turmas:
        colT1, colT2 = st.columns(2)
        with colT1:
            st.subheader("Adicionar Turma")
            with st.form(f"form_turma_{st.session_state.key_turma}"):
                escola_da_turma = st.selectbox("Escola Parceira", lista_escolas_limpa)
                prof_da_turma = st.selectbox("Professor Responsável", ["Sem professor ainda"] + lista_profs)
                nova_turma = st.text_input("Horário / Nome da Turma")
                if st.form_submit_button("Adicionar Turma"):
                    if nova_turma.strip() and escola_da_turma:
                        prof_salvar = "" if prof_da_turma == "Sem professor ainda" else prof_da_turma
                        executar_sql("INSERT INTO turmas (escola, nome_turma, professor, projeto) VALUES (%s, %s, %s, %s)", (escola_da_turma, nova_turma, prof_salvar, projeto_atual))
                        st.rerun()
        with colT2:
            st.subheader("Turmas deste Projeto")
            df_turmas = ler_sql('''SELECT id, escola as "Escola", nome_turma as "Turma", professor as "Professor" FROM turmas WHERE projeto=%s''', params=(projeto_atual,))
            if not df_turmas.empty:
                with st.form("form_edicao_turmas"):
                    turmas_lista = ordenar_turmas(df_turmas['Turma'].tolist())
                    df_turmas['Turma'] = pd.Categorical(df_turmas['Turma'], categories=turmas_lista, ordered=True)
                    df_turmas = df_turmas.sort_values(by=['Escola', 'Turma'])
                    df_turmas['Excluir'] = False
                    edited_turmas = st.data_editor(df_turmas, hide_index=True, column_config={
                        "id": None, "Escola": st.column_config.SelectboxColumn("Escola", options=lista_escolas_limpa),
                        "Professor": st.column_config.SelectboxColumn("Professor", options=lista_profs),
                        "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", default=False)
                    }, use_container_width=True)
                    
                    conf_turma = st.checkbox("Confirmo as exclusões")
                    if st.form_submit_button("💾 Salvar Alterações (Turmas)", type="primary"):
                        if not conf_turma and any(edited_turmas['Excluir']): st.error("Marque a confirmação antes de excluir.")
                        else:
                            lote_comandos = []
                            for _, row in edited_turmas.iterrows():
                                if row.get('Excluir', False): lote_comandos.append(("DELETE FROM turmas WHERE id=%s", (row['id'],)))
                                else:
                                    res = ler_sql("SELECT escola, nome_turma FROM turmas WHERE id=%s", (row['id'],))
                                    if not res.empty and (res.iloc[0]['escola'] != row['Escola'] or res.iloc[0]['nome_turma'] != row['Turma']):
                                        lote_comandos.append(("UPDATE matriculas SET escola=%s, turma=%s WHERE escola=%s AND turma=%s AND projeto=%s", (row['Escola'], row['Turma'], res.iloc[0]['escola'], res.iloc[0]['nome_turma'], projeto_atual)))
                                    lote_comandos.append(("UPDATE turmas SET escola=%s, nome_turma=%s, professor=%s WHERE id=%s", (row['Escola'], row['Turma'], row['Professor'], row['id'])))
                            executar_lote_sql(lote_comandos)
                            st.success("✅ Atualizado!"); st.rerun()

    with aba_importar:
        st.subheader(f"📥 Importação Mágica: {projeto_atual}")
        escola_importacao = st.selectbox("Para qual ESCOLA deseja importar estes alunos?", ["Selecione..."] + lista_escolas_limpa)
        arquivo_submetido = st.file_uploader("Escolha o arquivo Excel (.xlsx) ou CSV", type=["xlsx", "csv"])
        
        if arquivo_submetido is not None and escola_importacao != "Selecione...":
            try:
                is_sartre_format = False
                if arquivo_submetido.name.endswith('.xlsx'):
                    xls = pd.ExcelFile(arquivo_submetido)
                    if 'RESUMO' in xls.sheet_names: is_sartre_format = True
                        
                if is_sartre_format:
                    df_import = pd.read_excel(xls, sheet_name='RESUMO')
                    prof_map = {}
                    serie_prefix = "6º"
                    for sheet in xls.sheet_names:
                        if "-" in sheet:
                            partes = sheet.split("-")
                            if len(partes) >= 2: 
                                turma_aba = partes[1].strip()
                                prof_map[turma_aba.replace(" ", "")] = partes[0].strip().title()
                                match_serie = re.search(r'(\d+)º', turma_aba)
                                if match_serie: serie_prefix = f"{match_serie.group(1)}º"
                else:
                    if arquivo_submetido.name.endswith('.csv'): df_import = pd.read_csv(arquivo_submetido)
                    else: df_import = pd.read_excel(arquivo_submetido)
                
                df_import.columns = [str(c).strip().upper() for c in df_import.columns]
                
                if st.button("🚀 Iniciar Importação Mágica", type="primary"):
                    with st.spinner("⏳ Por favor, aguarde. Importando e organizando os dados na nuvem..."):
                        importados_contador, atualizados_contador = 0, 0
                        escola = escola_importacao
                        col_mappings = {'07-25': '25/07', '08-01': '01/08', '09-12': '12/09', '09-18': '18/09', '09-22': '22/09', '09-26': '26/09', 'ENSAIO': 'ENSAIO DE PALCO', '10-17': '17/10', 'APRESENT': 'APRESENT.'}
                        esp_col = next((c for c in df_import.columns if 'ESPET' in c), None)
                        cena_col = next((c for c in df_import.columns if 'CENA' in c), None)
                        qualit_col = next((c for c in df_import.columns if 'QUALIT' in c), None)
                        
                        lote_comandos = []
                        
                        for _, row in df_import.iterrows():
                            if is_sartre_format:
                                nome = safe_str(row.get('ALUNO', ''))
                                if not nome: continue
                                turma_raw = safe_str(row.get('TURMA', ''))
                                turma_nome = turma_raw if "º" in turma_raw else f"{serie_prefix}{turma_raw}"
                                turma_key = turma_nome.replace(" ", "")
                                prof_nome = prof_map.get(turma_key, "")
                                if prof_nome:
                                    if ler_sql("SELECT id FROM professores WHERE nome_professor=%s AND projeto=%s", (prof_nome, projeto_atual)).empty:
                                        lote_comandos.append(("INSERT INTO professores (nome_professor, projeto) VALUES (%s, %s) ON CONFLICT DO NOTHING", (prof_nome, projeto_atual)))
                            else:
                                nome = safe_str(row.get('NOME DO ALUNO', row.get('NOME', '')))
                                if not nome: continue
                                turma_nome = safe_str(row.get('TURMA DE TEATRO', row.get('TURMA', '')))
                                prof_nome = ""

                            esp_raw = safe_str(row[esp_col]) if esp_col else ""
                            cena_raw = safe_str(row[cena_col]) if cena_col else ""
                            q_val = float(row[qualit_col]) if qualit_col and pd.notna(row[qualit_col]) else 0.0

                            if ler_sql("SELECT id FROM turmas WHERE escola=%s AND nome_turma=%s AND projeto=%s", (escola, turma_nome, projeto_atual)).empty and escola and turma_nome:
                                executar_sql("INSERT INTO turmas (escola, nome_turma, professor, projeto) VALUES (%s, %s, %s, %s)", (escola, turma_nome, prof_nome, projeto_atual))
                                
                            aluno_db = ler_sql("SELECT id FROM alunos WHERE nome_aluno=%s", (nome,))
                            if aluno_db.empty:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO alunos (nome_aluno) VALUES (%s) RETURNING id", (nome,))
                                aluno_id = cur.fetchone()[0]
                                conn.commit()
                                cur.close()
                            else: aluno_id = aluno_db.iloc[0]['id']
                                
                            mat_db = ler_sql("SELECT id FROM matriculas WHERE aluno_id=%s AND ano_letivo=2026 AND projeto=%s", (int(aluno_id), projeto_atual))
                            if mat_db.empty:
                                lote_comandos.append(('''INSERT INTO matriculas (aluno_id, ano_letivo, escola, turma, projeto, espetaculo, cena, nota_qualitativa) 
                                             VALUES (%s, 2026, %s, %s, %s, %s, %s, %s)''', (int(aluno_id), escola, turma_nome, projeto_atual, esp_raw, cena_raw, q_val)))
                                importados_contador += 1
                            else:
                                lote_comandos.append(("UPDATE matriculas SET escola=%s, turma=%s, espetaculo=%s, cena=%s, nota_qualitativa=%s WHERE id=%s", (escola, turma_nome, esp_raw, cena_raw, q_val, int(mat_db.iloc[0]['id']))))
                                atualizados_contador += 1
                                
                            for col_name in df_import.columns:
                                for key, db_date in col_mappings.items():
                                    if key in col_name.upper():
                                        val = str(row.get(col_name, '')).strip().upper()
                                        if val in ['P', 'F', 'A']:
                                            p_val = 1 if val == 'P' else 0
                                            lote_comandos.append(("INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (%s, %s, %s) ON CONFLICT (aluno_id, data_aula) DO UPDATE SET presente = EXCLUDED.presente", (int(aluno_id), db_date, p_val)))
                        
                        executar_lote_sql(lote_comandos)
                    st.balloons()
                    st.success(f"🎉 SUCESSO! A importação foi concluída: {importados_contador} alunos criados e {atualizados_contador} atualizados (Série: {serie_prefix}).")

            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    with aba_acessos:
        st.subheader("🔐 Gestão de Logins")
        colA1, colA2 = st.columns(2)
        with colA1:
            with st.form(f"form_user_{st.session_state.key_user}"):
                prof_associado = st.selectbox("Vincular ao Professor:", ["Admin (Acesso Total)"] + lista_profs)
                novo_login = st.text_input("Nome de Usuário (Ex: larissa.teatro)")
                nova_senha = st.text_input("Senha Inicial", type="password")
                
                if st.form_submit_button("Criar Login"):
                    if novo_login.strip() and nova_senha.strip():
                        perfil_novo = 'admin' if prof_associado == "Admin (Acesso Total)" else 'professor'
                        prof_salvar = "" if perfil_novo == 'admin' else prof_associado
                        try:
                            executar_sql("INSERT INTO usuarios (login, senha, perfil, nome_professor) VALUES (%s, %s, %s, %s)", (novo_login.strip(), nova_senha.strip(), perfil_novo, prof_salvar))
                            st.success(f"✅ Usuário {novo_login} criado!"); st.session_state.key_user += 1; st.rerun()
                        except: st.error("⚠️ Este nome de usuário já existe.")
        with colA2:
            df_users = ler_sql('''SELECT id, login as "Usuário", perfil as "Perfil", nome_professor as "Professor" FROM usuarios''')
            if not df_users.empty:
                with st.form("form_edicao_logins"):
                    df_users['Excluir'] = False
                    edited_users = st.data_editor(df_users, hide_index=True, column_config={"id": None, "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", default=False)}, use_container_width=True)
                    conf_user = st.checkbox("Confirmo as exclusões")
                    if st.form_submit_button("💾 Salvar Alterações (Logins)", type="primary"):
                        if not conf_user and any(edited_users['Excluir']): st.error("Marque a confirmação antes de excluir.")
                        else:
                            lote_comandos = []
                            for _, row in edited_users.iterrows():
                                if row.get('Excluir', False) and row['Usuário'] != 'admin':
                                    lote_comandos.append(("DELETE FROM usuarios WHERE id=%s", (row['id'],)))
                            executar_lote_sql(lote_comandos)
                            st.success("✅ Atualizado!"); st.rerun()

elif menu == "Cadastrar Aluno / Matrícula" and st.session_state['perfil'] == 'admin':
    st.title(f"➕ Cadastro Manual: {projeto_atual}")
    st.info("Utilize a ferramenta 'Importar Planilha Mágica' no menu de Gestão Base para cadastrar em lote rapidamente.")
    
    with st.form(f"form_novo_aluno_{st.session_state.key_novo_aluno}"):
        st.subheader("Dados do Aluno")
        nome_novo = st.text_input("Nome Completo do Aluno *", placeholder="Ex: João da Silva")
        col1, col2 = st.columns(2)
        with col1:
            serie_nova = st.text_input("Série / Ano", placeholder="Ex: 6º Ano")
            escola_nova = st.selectbox("Escola *", ["Selecione..."] + lista_escolas_limpa)
        with col2:
            turmas_cadastradas = []
            if escola_nova != "Selecione...":
                df_t = ler_sql_cached("SELECT nome_turma FROM turmas WHERE escola=%s AND projeto=%s", params=(escola_nova, projeto_atual))
                turmas_cadastradas = ordenar_turmas(df_t['nome_turma'].tolist())
            turma_nova = st.selectbox("Turma *", ["Selecione..."] + turmas_cadastradas)
        
        st.markdown("---")
        st.subheader("Responsáveis e Contato")
        c1, c2, c3 = st.columns(3)
        with c1: 
            resp_novo = st.text_input("Responsável Principal")
            cpf_novo = st.text_input("CPF do Responsável", placeholder="Apenas números")
        with c2: tel_novo = st.text_input("Telefone 1", placeholder="Apenas números com DDD")
        with c3: 
            resp2_novo = st.text_input("Responsável Secundário")
            tel2_novo = st.text_input("Telefone 2", placeholder="Apenas números com DDD")
        
        st.markdown("---")
        if st.form_submit_button("✅ Salvar Cadastro", type="primary"):
            if nome_novo.strip() and escola_nova != "Selecione..." and turma_nova != "Selecione...":
                cur = conn.cursor()
                cur.execute("INSERT INTO alunos (nome_aluno, responsavel, cpf_responsavel, telefone, responsavel2, telefone2) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", 
                          (nome_novo.strip(), resp_novo.strip(), formatar_cpf(cpf_novo), formatar_telefone(tel_novo), resp2_novo.strip(), formatar_telefone(tel2_novo)))
                novo_id = cur.fetchone()[0]
                cur.execute('''INSERT INTO matriculas (aluno_id, ano_letivo, escola, turma, serie_aluno, projeto) 
                             VALUES (%s, 2026, %s, %s, %s, %s)''', (novo_id, escola_nova, turma_nova, serie_nova.strip(), projeto_atual))
                conn.commit()
                cur.close()
                st.cache_data.clear()
                st.success(f"Aluno **{nome_novo}** cadastrado com sucesso!")
                st.session_state.key_novo_aluno += 1
                st.rerun()
            else:
                st.error("Por favor, preencha o Nome, a Escola e a Turma.")

elif menu == "Ver / Editar Alunos" and st.session_state['perfil'] == 'admin':
    st.title(f"👥 Gestão de Alunos: {projeto_atual}")
    st.info("💡 Edite os alunos na tabela e clique no botão **Salvar Alterações** no final da página.")
    
    with st.expander("🗑️ Apagar Turma Inteira em Lote (Correção de Importação)"):
        st.warning("⚠️ **Atenção:** Esta ação apagará as matrículas de TODOS os alunos da turma selecionada neste projeto. Use apenas para corrigir planilhas importadas errado.")
        col_del1, col_del2 = st.columns(2)
        with col_del1:
            esc_del = st.selectbox("Selecione a Escola da Turma a apagar:", ["Selecione..."] + lista_escolas_limpa, key="del_esc")
        with col_del2:
            opc_t_del = ["Selecione..."]
            if esc_del != "Selecione...":
                t_c_del = ler_sql_cached("SELECT nome_turma FROM turmas WHERE escola=%s AND projeto=%s", params=(esc_del, projeto_atual))
                opc_t_del = ["Selecione..."] + ordenar_turmas(t_c_del['nome_turma'].tolist())
            turma_del = st.selectbox("Selecione a Turma a apagar:", opc_t_del, key="del_turma")
            
        confirmar_del = st.checkbox("Eu tenho certeza absoluta que desejo apagar estes dados permanentemente (NÃO há Ctrl+Z).")
        if st.button("🚨 Apagar Matrículas desta Turma", type="primary"):
            if esc_del != "Selecione..." and turma_del != "Selecione..." and confirmar_del:
                executar_sql("DELETE FROM matriculas WHERE escola=%s AND turma=%s AND projeto=%s", (esc_del, turma_del, projeto_atual))
                st.success(f"A turma {turma_del} da escola {esc_del} foi apagada com sucesso!")
                import time
                time.sleep(1)
                st.rerun()
            elif not confirmar_del:
                st.error("Marque a caixa de confirmação para poder apagar.")

    st.markdown("---")

    df_geral_alunos = ler_sql('''
        SELECT 
            m.id as matricula_id, a.id as aluno_id, a.nome_aluno as "Aluno",
            m.serie_aluno as "Série", a.responsavel as "Resp1", a.cpf_responsavel as "CPF", a.telefone as "Tel1", 
            a.responsavel2 as "Resp2", a.telefone2 as "Tel2", m.ano_letivo as "Ano", m.turma as "Turma", 
            m.escola as "Escola", m.espetaculo as "Espetáculo", m.cena as "Cena"
        FROM alunos a JOIN matriculas m ON a.id = m.aluno_id WHERE m.projeto = %s
    ''', params=(projeto_atual,))
    
    if df_geral_alunos.empty: st.warning(f"Nenhum aluno registado neste projeto.")
    else:
        df_geral_alunos = df_geral_alunos.fillna({'Série': '', 'Turma': '', 'Escola': '', 'Espetáculo': '', 'Cena': '', 'Ano': 2026})
        df_geral_alunos_copy = df_geral_alunos.copy()
        
        cfg_colunas = {
            "matricula_id": None, "aluno_id": None,
            "Aluno": st.column_config.TextColumn("Aluno", required=True),
            "Escola": st.column_config.SelectboxColumn("Escola", options=lista_escolas_limpa),
            "Ano": st.column_config.NumberColumn("Ano", format="%d"),
            "Espetáculo": st.column_config.TextColumn("Espetáculo"),
            "Cena": st.column_config.TextColumn("Cena"),
            "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", default=False)
        }
        
        if projeto_atual != "Curso Extra":
            cfg_colunas["CPF"] = None; cfg_colunas["Resp1"] = None; cfg_colunas["Resp2"] = None; cfg_colunas["Tel1"] = None; cfg_colunas["Tel2"] = None
        else: 
            cfg_colunas["Espetáculo"] = None; cfg_colunas["Cena"] = None
            
        with st.form("form_edicao_alunos"):
            df_geral_alunos['Excluir'] = False
            edited_alunos_df = st.data_editor(df_geral_alunos, hide_index=True, column_config=cfg_colunas, use_container_width=True)
            conf_indiv = st.checkbox("Confirmo as exclusões (Não há Ctrl+Z)", key="conf_indiv")
            
            if st.form_submit_button("💾 Salvar Todas as Alterações", type="primary"):
                if edited_alunos_df.to_json() != df_geral_alunos_copy.to_json():
                    lote_comandos = []
                    erro_exclusao = False
                    for _, row in edited_alunos_df.iterrows():
                        if row.get('Excluir', False):
                            if conf_indiv:
                                lote_comandos.append(("DELETE FROM matriculas WHERE id=%s", (int(row['matricula_id']),)))
                            else:
                                erro_exclusao = True
                        else:
                            if projeto_atual == "Curso Extra":
                                lote_comandos.append(('''UPDATE alunos SET nome_aluno=%s, cpf_responsavel=%s, responsavel=%s, telefone=%s, responsavel2=%s, telefone2=%s WHERE id=%s''', 
                                          (row['Aluno'], formatar_cpf(row.get('CPF','')), row.get('Resp1',''), formatar_telefone(row.get('Tel1','')), row.get('Resp2',''), formatar_telefone(row.get('Tel2','')), int(row['aluno_id']))))
                            else: lote_comandos.append(('''UPDATE alunos SET nome_aluno=%s WHERE id=%s''', (row['Aluno'], int(row['aluno_id']))))
                            lote_comandos.append(('''UPDATE matriculas SET ano_letivo=%s, escola=%s, turma=%s, serie_aluno=%s, espetaculo=%s, cena=%s WHERE id=%s''', 
                                      (int(row['Ano']), row['Escola'], row['Turma'], row['Série'], safe_str(row.get('Espetáculo', '')), safe_str(row.get('Cena', '')), int(row['matricula_id']))))
                    
                    if erro_exclusao:
                        st.error("Marque a caixa de confirmação se deseja excluir alunos.")
                    elif lote_comandos:
                        executar_lote_sql(lote_comandos)
                        st.success("✅ Dados atualizados com sucesso!")
                        import time
                        time.sleep(1)
                        st.rerun()

elif menu == "Caderneta / Presença":
    st.title(f"📝 Caderneta Digital: {projeto_atual}")
    
    if projeto_atual == "Projeto de Teatro Sartre":
        aba_chamada, aba_resumo = st.tabs(["📝 Fazer Chamada", "📊 Resumo Geral do Projeto"])
        datas_db = ['25/07', '01/08', '12/09', '18/09', '22/09', '26/09', 'ENSAIO DE PALCO', '17/10', 'APRESENT.']
        datas_ui = ['25/07', '01/08', '12/09', '18/09', '22/09', '26/09', 'ENSAIO\nPALCO', '17/10', 'APRESENT.']
            
        with aba_chamada:
            colA, colB, colC = st.columns(3)
            
            if st.session_state['perfil'] == 'professor':
                prof_logado = st.session_state['nome_prof']
                st.info(f"👨‍🏫 Turmas do professor(a): **{prof_logado}**")
                escolas_do_prof = ler_sql_cached("SELECT DISTINCT escola FROM turmas WHERE professor=%s AND projeto=%s", params=(prof_logado, projeto_atual))
                escolas_lista = escolas_do_prof['escola'].tolist() if not escolas_do_prof.empty else []
            else:
                escolas_lista = lista_escolas_limpa
                prof_logado = None
            
            with colA: esc_chamada = st.selectbox("1. Escola", ["Selecione..."] + escolas_lista)
            
            if esc_chamada != "Selecione...":
                if prof_logado: t_c = ler_sql_cached("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s AND professor=%s", params=(esc_chamada, projeto_atual, prof_logado))
                else: t_c = ler_sql_cached("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s", params=(esc_chamada, projeto_atual))
                
                t_c['Serie'] = t_c['nome_turma'].apply(extrair_serie)
                series_disp = sorted(list(set(t_c['Serie'].tolist())))
                with colB: serie_chamada = st.selectbox("2. Série", ["Selecione..."] + series_disp)
                
                if serie_chamada != "Selecione...":
                    t_filtradas = t_c[t_c['Serie'] == serie_chamada]['nome_turma'].tolist()
                    opc_t_chamada = ["Selecione..."] + ordenar_turmas(t_filtradas)
                else: opc_t_chamada = ["Selecione a série..."]
            else:
                with colB: serie_chamada = st.selectbox("2. Série", ["Selecione a escola..."])
                opc_t_chamada = ["Selecione a escola..."]
                
            with colC: turma_chamada = st.selectbox("3. Turma / Cena", opc_t_chamada)

            if esc_chamada != "Selecione..." and turma_chamada not in ["Selecione...", "Nenhuma turma", "Selecione a escola...", "Selecione a série..."]:
                
                prof_da_turma_db = ler_sql_cached("SELECT professor FROM turmas WHERE escola=%s AND nome_turma=%s AND projeto=%s", (esc_chamada, turma_chamada, projeto_atual))
                if not prof_da_turma_db.empty and prof_da_turma_db.iloc[0]['professor']:
                    st.markdown(f"👨‍🏫 **Professor Responsável:** {prof_da_turma_db.iloc[0]['professor']}")

                df_alunos = ler_sql('''
                    SELECT a.id as aluno_id, m.id as matricula_id, a.nome_aluno as "Aluno", 
                           m.espetaculo as "Espetáculo", m.cena as "Cena", m.nota_qualitativa as "Qualitativo", m.observacoes as "Observações"
                    FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                    WHERE m.escola=%s AND m.turma=%s AND m.projeto=%s
                    ORDER BY a.nome_aluno
                ''', params=(esc_chamada, turma_chamada, projeto_atual))
                
                if df_alunos.empty: st.error("Não há alunos nesta turma.")
                else:
                    aluno_ids_tuple = tuple(df_alunos['aluno_id'].tolist())
                    if len(aluno_ids_tuple) == 1: aluno_ids_tuple = f"({aluno_ids_tuple[0]})"
                    else: aluno_ids_tuple = str(aluno_ids_tuple)
                    
                    df_freq = ler_sql_cached(f"SELECT aluno_id, data_aula, presente FROM frequencia WHERE aluno_id IN {aluno_ids_tuple}")
                    freq_dict = {(row['aluno_id'], row['data_aula']): row['presente'] for _, row in df_freq.iterrows()}
                    
                    col_cfg = {
                        "aluno_id": None, "matricula_id": None, "Observações": None,
                        "Aluno": st.column_config.TextColumn("Aluno", disabled=True),
                        "Espetáculo": st.column_config.TextColumn("Espetác.", width=65),
                        "Cena": st.column_config.TextColumn("Cena", width=120),
                        "Faltas": st.column_config.NumberColumn("Faltas", disabled=True, width=60),
                        "Qualitativo": st.column_config.NumberColumn("Qualit.", format="%.1f", width=65),
                        "Nota": st.column_config.NumberColumn("Nota Final", disabled=True, width=70)
                    }
                    
                    faltas_list, notas_list = [], []
                    for i in range(len(datas_db)):
                        col_banco = datas_db[i]
                        col_tela = datas_ui[i]
                        presencas = []
                        for _, row in df_alunos.iterrows():
                            ip = freq_dict.get((row['aluno_id'], col_banco), -1)
                            presencas.append("🟢 P" if ip == 1 else ("🔴 F" if ip == 0 else "⚪ -"))
                        df_alunos[col_tela] = presencas
                        col_cfg[col_tela] = st.column_config.SelectboxColumn(col_tela, options=["⚪ -", "🟢 P", "🔴 F"], width=80)
                    
                    for _, row in df_alunos.iterrows():
                        f_count = sum(1 for c in datas_ui if row[c] == "🔴 F")
                        faltas_list.append(f_count)
                        q_val = row.get('Qualitativo', 0.0)
                        if pd.isna(q_val): q_val = 0.0
                        notas_list.append(10.0 - (f_count * 0.5) + float(q_val))
                        
                    df_alunos['Faltas'] = faltas_list
                    df_alunos['Nota'] = notas_list
                    
                    cols_order = ['aluno_id', 'matricula_id', 'Aluno', 'Espetáculo', 'Cena'] + datas_ui + ['Faltas', 'Qualitativo', 'Nota', 'Observações']
                    df_alunos = df_alunos[cols_order]
                    df_alunos_copy = df_alunos.copy()
                    df_alunos = df_alunos.set_index('Aluno')
                    
                    st.info("💡 Edite a tabela e clique em **Salvar Chamada e Notas**.")
                    with st.form("form_caderneta"):
                        edited_df = st.data_editor(df_alunos, column_config=col_cfg, use_container_width=True)
                        btn_salvar_chamada = st.form_submit_button("💾 Salvar Chamada e Notas", type="primary")
                        
                        if btn_salvar_chamada:
                            if edited_df.reset_index().to_json() != df_alunos_copy.to_json():
                                lote_comandos = []
                                for _, row in edited_df.iterrows():
                                    a_id, m_id = int(row['aluno_id']), int(row['matricula_id'])
                                    lote_comandos.append(("UPDATE matriculas SET espetaculo=%s, cena=%s, nota_qualitativa=%s WHERE id=%s", 
                                              (safe_str(row.get('Espetáculo','')), safe_str(row.get('Cena','')), float(row.get('Qualitativo',0.0)), m_id)))
                                    for i in range(len(datas_db)):
                                        val = row[datas_ui[i]]
                                        p_val = 1 if val == "🟢 P" else (0 if val == "🔴 F" else -1)
                                        lote_comandos.append(("INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (%s, %s, %s) ON CONFLICT (aluno_id, data_aula) DO UPDATE SET presente = EXCLUDED.presente", (a_id, datas_db[i], p_val)))
                                executar_lote_sql(lote_comandos)
                                st.success("✅ Chamada salva com sucesso!")
                                import time
                                time.sleep(1)
                                st.rerun()

                    st.markdown("---")
                    with st.expander("🔒 Cofre de Observações Privadas (Invisível aos Alunos)"):
                        aluno_obs_nome = st.selectbox("Selecione o Aluno para anotações:", ["Selecione..."] + df_alunos.index.tolist())
                        if aluno_obs_nome != "Selecione...":
                            row_obs = df_alunos.loc[aluno_obs_nome]
                            nova_obs = st.text_area(f"Anotações para {aluno_obs_nome}:", value=row_obs.get('Observações', ''), height=120)
                            if st.button("💾 Guardar Anotação no Cofre", type="primary"):
                                executar_sql("UPDATE matriculas SET observacoes=%s WHERE id=%s", (nova_obs, int(row_obs.get('matricula_id'))))
                                st.success("Anotação guardada com segurança!"); st.rerun()

        with aba_resumo:
            st.subheader("📊 Resumo Geral do Projeto")
            df_resumo = ler_sql_cached('''
                SELECT m.escola as "ESCOLA", m.turma as "TURMA", m.espetaculo as "ESPETÁCULO", m.cena as "CENA", 
                       a.nome_aluno as "ALUNO", m.nota_qualitativa as "QUALIT", a.id as aluno_id, m.observacoes as "OBSERVAÇÕES"
                FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                WHERE m.projeto=%s ORDER BY m.escola, m.turma, a.nome_aluno
            ''', params=(projeto_atual,))
            
            if not df_resumo.empty:
                df_freq = ler_sql_cached("SELECT aluno_id, data_aula, presente FROM frequencia")
                freq_dict = {(r['aluno_id'], r['data_aula']): r['presente'] for _, r in df_freq.iterrows()}
                for i in range(len(datas_db)):
                    col_banco = datas_db[i]
                    col_tela = datas_ui[i]
                    presencas = []
                    for _, row in df_resumo.iterrows():
                        ip = freq_dict.get((row['aluno_id'], col_banco), -1)
                        presencas.append("P" if ip == 1 else ("F" if ip == 0 else "-"))
                    df_resumo[col_tela] = presencas
                
                faltas_list, notas_list = [], []
                for _, row in df_resumo.iterrows():
                    f_count = sum(1 for c in datas_ui if row[c] == "F")
                    faltas_list.append(f_count)
                    q_val = row.get('QUALIT', 0.0)
                    if pd.isna(q_val): q_val = 0.0
                    notas_list.append(10.0 - (f_count * 0.5) + float(q_val))
                    
                df_resumo['FALTAS'] = faltas_list
                df_resumo['NOTA FINAL'] = notas_list
                
                df_resumo_limpo = df_resumo.drop(columns=['aluno_id'])
                cols_r = ['ESCOLA', 'TURMA', 'ESPETÁCULO', 'CENA', 'ALUNO'] + datas_ui + ['FALTAS', 'QUALIT', 'NOTA FINAL', 'OBSERVAÇÕES']
                df_resumo_limpo = df_resumo_limpo[cols_r]
                
                st.dataframe(df_resumo_limpo, use_container_width=True, hide_index=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_resumo_limpo.to_excel(writer, index=False, sheet_name='Resumo Geral')
                st.download_button(label="📥 Descarregar Resumo em Excel (.xlsx)", data=output.getvalue(), file_name=f"Resumo_Geral_{projeto_atual}_2026.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1: ano_sel = st.number_input("Ano", min_value=2024, max_value=2030, value=2026)
        with col2:
            meses_map = {"JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
            mes_sel = st.selectbox("Mês", list(meses_map.keys()))
            
        if st.session_state['perfil'] == 'professor':
            prof_logado = st.session_state['nome_prof']
            st.info(f"👨‍🏫 Turmas do professor(a): **{prof_logado}**")
            escolas_do_prof = ler_sql_cached("SELECT DISTINCT escola FROM turmas WHERE professor=%s AND projeto=%s", params=(prof_logado, projeto_atual))
            escolas_lista = escolas_do_prof['escola'].tolist() if not escolas_do_prof.empty else []
        else:
            escolas_lista = lista_escolas_limpa
            prof_logado = None
            
        with col3: esc_chamada = st.selectbox("Escola", ["Selecione..."] + escolas_lista)
            
        opc_t_chamada = ["Selecione a escola primeiro..."]
        if esc_chamada != "Selecione...":
            if prof_logado: t_c = ler_sql_cached("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s AND professor=%s", params=(esc_chamada, projeto_atual, prof_logado))
            else: t_c = ler_sql_cached("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s", params=(esc_chamada, projeto_atual))
            opc_t_chamada = ["Selecione..."] + ordenar_turmas(t_c['nome_turma'].tolist()) if not t_c.empty else ["Nenhuma turma"]
        with col4: turma_chamada = st.selectbox("Turma", opc_t_chamada)

        if esc_chamada != "Selecione..." and turma_chamada not in ["Selecione...", "Nenhuma turma", "Selecione a escola primeiro..."]:
            
            prof_da_turma_db = ler_sql_cached("SELECT professor FROM turmas WHERE escola=%s AND nome_turma=%s AND projeto=%s", (esc_chamada, turma_chamada, projeto_atual))
            if not prof_da_turma_db.empty and prof_da_turma_db.iloc[0]['professor']:
                st.markdown(f"👨‍🏫 **Professor Responsável:** {prof_da_turma_db.iloc[0]['professor']}")
                
            df_alunos_turma = ler_sql('''
                SELECT a.id as aluno_id, a.nome_aluno as "Aluno" 
                FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                WHERE m.escola=%s AND m.turma=%s AND m.ano_letivo=%s AND m.projeto=%s
                ORDER BY a.nome_aluno
            ''', params=(esc_chamada, turma_chamada, ano_sel, projeto_atual))
            
            if df_alunos_turma.empty: st.error(f"Não há alunos ativos nesta turma.")
            else:
                dias_map = {'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5, 'DOM': 6}
                datas_ui, datas_db = [], []
                m_num = meses_map[mes_sel]
                num_dias = calendar.monthrange(ano_sel, m_num)[1]
                for dia in range(1, num_dias + 1):
                    d_atual = date(ano_sel, m_num, dia)
                    for sigla, num_ds in dias_map.items():
                        if sigla in turma_chamada.upper() and d_atual.weekday() == num_ds:
                            datas_ui.append(f"{dia:02d}/{m_num:02d} {sigla}")
                            datas_db.append(d_atual.strftime("%Y-%m-%d"))

                df_alunos_turma = df_alunos_turma.set_index('Aluno')
                
                aluno_ids_tuple = tuple(df_alunos_turma['aluno_id'].tolist())
                if len(aluno_ids_tuple) == 1: aluno_ids_tuple = f"({aluno_ids_tuple[0]})"
                else: aluno_ids_tuple = str(aluno_ids_tuple)
                df_freq = ler_sql_cached(f"SELECT aluno_id, data_aula, presente FROM frequencia WHERE aluno_id IN {aluno_ids_tuple}")
                freq_dict = {(row['aluno_id'], row['data_aula']): row['presente'] for _, row in df_freq.iterrows()}
                
                col_cfg = {"aluno_id": None}
                for i, col_ui in enumerate(datas_ui):
                    col_db = datas_db[i]
                    presencas = []
                    for a_id in df_alunos_turma['aluno_id']:
                        ip = freq_dict.get((a_id, col_db), -1)
                        presencas.append("🟢 P" if ip == 1 else ("🔴 F" if ip == 0 else "⚪ -"))
                    df_alunos_turma[col_ui] = presencas
                    col_cfg[col_ui] = st.column_config.SelectboxColumn(col_ui, options=["⚪ -", "🟢 P", "🔴 F"], required=True, width=85)
                
                df_alunos_turma_copy = df_alunos_turma.copy()
                
                st.info("💡 Preencha a chamada para toda a turma e clique em **Salvar Chamada**.")
                with st.form("form_caderneta_extra"):
                    edited_df = st.data_editor(df_alunos_turma, column_config=col_cfg, use_container_width=True)
                    btn_salvar_chamada_extra = st.form_submit_button("💾 Salvar Chamada", type="primary")
                    
                    if btn_salvar_chamada_extra:
                        if edited_df.reset_index().to_json() != df_alunos_turma_copy.to_json():
                            lote_comandos = []
                            for _, row in edited_df.iterrows():
                                a_id = int(row['aluno_id'])
                                for i, cui in enumerate(datas_ui):
                                    val = row[cui]
                                    p_val = 1 if val == "🟢 P" else (0 if val == "🔴 F" else -1)
                                    lote_comandos.append(("INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (%s, %s, %s) ON CONFLICT (aluno_id, data_aula) DO UPDATE SET presente = EXCLUDED.presente", (a_id, datas_db[i], p_val)))
                            executar_lote_sql(lote_comandos)
                            st.success("✅ Chamada salva com sucesso!")
                            import time
                            time.sleep(1)
                            st.rerun()

elif menu == "Financeiro / Extrato":
    st.title("🏦 Financeiro")
    st.write("Apenas para Administradores.")
