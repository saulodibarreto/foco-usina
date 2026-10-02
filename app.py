import streamlit as st
import sqlite3
import pandas as pd
import os
import re
import calendar
import io
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

def formatar_data(texto):
    texto_limpo = safe_str(texto)
    if not texto_limpo: return ""
    num = re.sub(r'\D', '', texto_limpo)
    if len(num) == 8: return f"{num[:2]}/{num[2:4]}/{num[4:]}"
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

# --- BASE DE DADOS (SUPABASE / LOCAL) ---
try:
    # Tenta usar a ligação segura da nuvem (Streamlit Secrets)
    db_url = st.secrets["DATABASE_URL"]
    import psycopg2
    conn = psycopg2.connect(db_url, sslmode='require')
    # Nota: para manter compatibilidade máxima, criamos os comandos adaptados
    is_postgres = True
except:
    # Fallback para SQLite local se rodar no computador
    conn = sqlite3.connect('banco.db', check_same_thread=False)
    is_postgres = False

c = conn.cursor()

# CRIAR TABELAS
if not is_postgres:
    c.execute('''CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome_aluno TEXT, cpf_responsavel TEXT DEFAULT '', responsavel TEXT DEFAULT '', telefone TEXT DEFAULT '', responsavel2 TEXT DEFAULT '', telefone2 TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS matriculas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, ano_letivo INTEGER DEFAULT 2026, escola TEXT DEFAULT '', turma TEXT DEFAULT '', serie_aluno TEXT DEFAULT '', mes_entrada TEXT DEFAULT 'MARÇO', valor_mensalidade REAL DEFAULT 280.0, projeto TEXT DEFAULT 'Curso Extra', espetaculo TEXT DEFAULT '', cena TEXT DEFAULT '', nota_qualitativa REAL DEFAULT 0.0, observacoes TEXT DEFAULT '', FOREIGN KEY(aluno_id) REFERENCES alunos(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS turmas (id INTEGER PRIMARY KEY AUTOINCREMENT, escola TEXT, nome_turma TEXT, professor TEXT DEFAULT '', projeto TEXT DEFAULT 'Curso Extra')''')
    c.execute('''CREATE TABLE IF NOT EXISTS frequencia (aluno_id INTEGER, data_aula TEXT, presente INTEGER, PRIMARY KEY (aluno_id, data_aula))''')
    c.execute('''CREATE TABLE IF NOT EXISTS escolas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome_escola TEXT, projeto TEXT DEFAULT 'Curso Extra')''')
    c.execute('''CREATE TABLE IF NOT EXISTS professores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome_professor TEXT, telefone TEXT, projeto TEXT DEFAULT 'Curso Extra')''')
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE, senha TEXT, perfil TEXT, nome_professor TEXT)''')
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios (login, senha, perfil, nome_professor) VALUES ('admin', '1234', 'admin', '')")
    conn.commit()

# --- MOTOR DE ESTADO E LOGIN ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = None
    st.session_state['perfil'] = None
    st.session_state['nome_prof'] = None

for key in ['key_escola', 'key_turma', 'key_matricula', 'key_prof', 'key_user']:
    if key not in st.session_state: st.session_state[key] = 0

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if os.path.exists("FOCO USINA DE ARTES.png"): st.image("FOCO USINA DE ARTES.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center;'>Acesso ao Sistema</h2>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                if is_postgres:
                    cur = conn.cursor()
                    cur.execute("SELECT login, perfil, nome_professor FROM usuarios WHERE login=%s AND senha=%s", (usuario_input, senha_input))
                    resultado = cur.fetchone()
                else:
                    c.execute("SELECT login, perfil, nome_professor FROM usuarios WHERE login=? AND senha=?", (usuario_input, senha_input))
                    resultado = c.fetchone()
                
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

# Funções auxiliares de leitura de dados seguras para Postgres/SQLite
def ler_sql(query, params=None):
    if is_postgres:
        return pd.read_sql_query(query, conn, params=params)
    else:
        return pd.read_sql_query(query, conn, params=params)

df_escolas_db = ler_sql("SELECT nome_escola FROM escolas WHERE projeto=%s ORDER BY nome_escola" if is_postgres else "SELECT nome_escola FROM escolas WHERE projeto=? ORDER BY nome_escola", params=(projeto_atual,))
lista_escolas_limpa = [safe_str(x) for x in df_escolas_db['nome_escola'].tolist() if safe_str(x) != ""]
df_prof_db = ler_sql("SELECT nome_professor FROM professores WHERE projeto=%s ORDER BY nome_professor" if is_postgres else "SELECT nome_professor FROM professores WHERE projeto=? ORDER BY nome_professor", params=(projeto_atual,))
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
                if is_postgres:
                    cur = conn.cursor()
                    cur.execute("UPDATE usuarios SET senha=%s WHERE login=%s", (nova_senha, st.session_state['usuario']))
                    conn.commit()
                else:
                    c.execute("UPDATE usuarios SET senha=? WHERE login=?", (nova_senha, st.session_state['usuario']))
                    conn.commit()
                st.success("✅ A sua senha foi alterada com sucesso!")
            else:
                st.error("⚠️ As senhas não coincidem ou estão vazias.")

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
                escolas_do_prof = ler_sql("SELECT DISTINCT escola FROM turmas WHERE professor=%s AND projeto=%s" if is_postgres else "SELECT DISTINCT escola FROM turmas WHERE professor=? AND projeto=?", params=(prof_logado, projeto_atual))
                escolas_lista = escolas_do_prof['escola'].tolist() if not escolas_do_prof.empty else []
            else:
                escolas_lista = lista_escolas_limpa
                prof_logado = None
            
            with colA: esc_chamada = st.selectbox("1. Escola", ["Selecione..."] + escolas_lista)
            if esc_chamada != "Selecione...":
                if prof_logado: t_c = ler_sql("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s AND professor=%s" if is_postgres else "SELECT nome_turma, professor FROM turmas WHERE escola=? AND projeto=? AND professor=?", params=(esc_chamada, projeto_atual, prof_logado))
                else: t_c = ler_sql("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s" if is_postgres else "SELECT nome_turma, professor FROM turmas WHERE escola=? AND projeto=?", params=(esc_chamada, projeto_atual))
                
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
                df_alunos = ler_sql('''
                    SELECT a.id as aluno_id, m.id as matricula_id, a.nome_aluno as Aluno, 
                           m.espetaculo as Espetáculo, m.cena as Cena, m.nota_qualitativa as Qualitativo, m.observacoes as Observações
                    FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                    WHERE m.escola=%s AND m.turma=%s AND m.projeto=%s ORDER BY a.nome_aluno
                ''' if is_postgres else '''
                    SELECT a.id as aluno_id, m.id as matricula_id, a.nome_aluno as Aluno, 
                           m.espetaculo as Espetáculo, m.cena as Cena, m.nota_qualitativa as Qualitativo, m.observacoes as Observações
                    FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                    WHERE m.escola=? AND m.turma=? AND m.projeto=? ORDER BY a.nome_aluno
                ''', params=(esc_chamada, turma_chamada, projeto_atual))
                
                if df_alunos.empty: st.error("Não há alunos nesta turma.")
                else:
                    df_freq = ler_sql("SELECT aluno_id, data_aula, presente FROM frequencia")
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
                        q_val = row['Qualitativo'] if pd.notna(row['Qualitativo']) else 0.0
                        notas_list.append(10.0 - (f_count * 0.5) + float(q_val))
                    df_alunos['Faltas'] = faltas_list
                    df_alunos['Nota'] = notas_list
                    cols_order = ['aluno_id', 'matricula_id', 'Aluno', 'Espetáculo', 'Cena'] + datas_ui + ['Faltas', 'Qualitativo', 'Nota', 'Observações']
                    df_alunos = df_alunos[cols_order]
                    df_alunos_copy = df_alunos.copy()
                    df_alunos = df_alunos.set_index('Aluno')
                    
                    edited_df = st.data_editor(df_alunos, column_config=col_cfg, use_container_width=True)
                    if edited_df.reset_index().to_json() != df_alunos_copy.to_json():
                        cur = conn.cursor()
                        for _, row in edited_df.iterrows():
                            a_id, m_id = row['aluno_id'], row['matricula_id']
                            if is_postgres:
                                cur.execute("UPDATE matriculas SET espetaculo=%s, cena=%s, nota_qualitativa=%s WHERE id=%s", (safe_str(row.get('Espetáculo','')), safe_str(row.get('Cena','')), float(row.get('Qualitativo',0.0)), m_id))
                            else:
                                cur.execute("UPDATE matriculas SET espetaculo=?, cena=?, nota_qualitativa=? WHERE id=?", (safe_str(row.get('Espetáculo','')), safe_str(row.get('Cena','')), float(row.get('Qualitativo',0.0)), m_id))
                            for i in range(len(datas_db)):
                                val = row[datas_ui[i]]
                                p_val = 1 if val == "🟢 P" else (0 if val == "🔴 F" else -1)
                                if is_postgres:
                                    cur.execute("INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (%s, %s, %s) ON CONFLICT (aluno_id, data_aula) DO UPDATE SET presente = EXCLUDED.presente", (a_id, datas_db[i], p_val))
                                else:
                                    cur.execute("INSERT OR REPLACE INTO frequencia (aluno_id, data_aula, presente) VALUES (?, ?, ?)", (a_id, datas_db[i], p_val))
                        conn.commit(); st.toast("✅ Salvo automaticamente!", icon="💾")

                    st.markdown("---")
                    with st.expander("🔒 Cofre de Observações Privadas (Invisível aos Alunos)"):
                        aluno_obs_nome = st.selectbox("Selecione o Aluno para anotações:", ["Selecione..."] + df_alunos.index.tolist())
                        if aluno_obs_nome != "Selecione...":
                            row_obs = df_alunos.loc[aluno_obs_nome]
                            nova_obs = st.text_area(f"Anotações para {aluno_obs_nome}:", value=row_obs['Observações'], height=120)
                            if st.button("💾 Guardar Anotação no Cofre", type="primary"):
                                cur = conn.cursor()
                                if is_postgres:
                                    cur.execute("UPDATE matriculas SET observacoes=%s WHERE id=%s", (nova_obs, row_obs['matricula_id']))
                                else:
                                    cur.execute("UPDATE matriculas SET observacoes=? WHERE id=?", (nova_obs, row_obs['matricula_id']))
                                conn.commit(); st.success("Anotação guardada com segurança!"); st.rerun()

        with aba_resumo:
            st.subheader("📊 Resumo Geral do Projeto")
            df_resumo = ler_sql('''
                SELECT m.escola as ESCOLA, m.turma as TURMA, m.espetaculo as ESPETÁCULO, m.cena as CENA, 
                       a.nome_aluno as ALUNO, m.nota_qualitativa as QUALIT, a.id as aluno_id, m.observacoes as OBSERVAÇÕES
                FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                WHERE m.projeto=%s ORDER BY m.escola, m.turma, a.nome_aluno
            ''' if is_postgres else '''
                SELECT m.escola as ESCOLA, m.turma as TURMA, m.espetaculo as ESPETÁCULO, m.cena as CENA, 
                       a.nome_aluno as ALUNO, m.nota_qualitativa as QUALIT, a.id as aluno_id, m.observacoes as OBSERVAÇÕES
                FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
                WHERE m.projeto=? ORDER BY m.escola, m.turma, a.nome_aluno
            ''', params=(projeto_atual,))
            
            if not df_resumo.empty:
                df_freq = ler_sql("SELECT aluno_id, data_aula, presente FROM frequencia")
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
                    q_val = row['QUALIT'] if pd.notna(row['QUALIT']) else 0.0
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
        st.info("Caderneta de acompanhamento ativa.")
