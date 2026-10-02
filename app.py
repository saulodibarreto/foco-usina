import streamlit as st
import pandas as pd
import os
import re
import io
import psycopg2
from datetime import date

# Configuração inicial
st.set_page_config(page_title="Foco Usina - Gestão", layout="wide")

# --- FUNÇÕES ÚTEIS ---
def safe_str(val):
    if pd.isna(val) or str(val).strip().upper() == 'NAN': return ""
    texto = str(val).strip()
    if texto.endswith('.0'): texto = texto[:-2]
    return texto

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

def executar_sql(query, params=None):
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    cur.close()

# --- MOTOR DE ESTADO E LOGIN ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario'] = None
    st.session_state['perfil'] = None
    st.session_state['nome_prof'] = None

if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
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

st.sidebar.title("🎭 Foco Usina")
st.sidebar.markdown(f"👤 **Logado como:** {st.session_state['usuario'].title()} ({st.session_state['perfil']})")
if st.sidebar.button("Sair / Logout"):
    st.session_state['logado'] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Bloco de Trabalho")
projeto_atual = st.sidebar.radio("Selecione o Projeto:", ["Curso Extra", "Projeto de Teatro Sartre", "Turno Integral Sartre"])
st.sidebar.markdown("---")

opcoes_menu = ["Dashboard", "Caderneta / Presença", "Meu Perfil / Senha"]
if st.session_state['perfil'] == 'admin':
    opcoes_menu = ["Dashboard", "Caderneta / Presença", "Ver Alunos", "Meu Perfil / Senha"]

menu = st.sidebar.radio("Navegação", opcoes_menu)

df_escolas_db = ler_sql("SELECT nome_escola FROM escolas WHERE projeto=%s ORDER BY nome_escola", params=(projeto_atual,))
lista_escolas_limpa = [safe_str(x) for x in df_escolas_db['nome_escola'].tolist() if safe_str(x) != ""]

# --- ECRÃS DO SISTEMA ---
if menu == "Dashboard":
    st.title("Visão Geral")
    st.write(f"Bem-vindo ao sistema da Foco Usina de Artes, **{st.session_state['usuario'].title()}**.")
    st.info(f"📌 Você está no ambiente: **{projeto_atual}**.")
    
    # Mostrar estatísticas rápidas
    total_alunos = ler_sql("SELECT COUNT(DISTINCT a.id) as total FROM alunos a JOIN matriculas m ON a.id = m.aluno_id WHERE m.projeto=%s", (projeto_atual,))['total'][0]
    st.metric("Total de Alunos neste Projeto", total_alunos)

elif menu == "Meu Perfil / Senha":
    st.title("👤 Meu Perfil")
    with st.form("form_senha"):
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
        if st.form_submit_button("Atualizar Senha", type="primary"):
            if nova_senha and nova_senha == confirma_senha:
                executar_sql("UPDATE usuarios SET senha=%s WHERE login=%s", (nova_senha, st.session_state['usuario']))
                st.success("✅ Senha alterada com sucesso!")
            else:
                st.error("⚠️ As senhas não coincidem.")

elif menu == "Ver Alunos":
    st.title(f"👥 Alunos: {projeto_atual}")
    df_resumo = ler_sql('''
        SELECT m.escola as ESCOLA, m.turma as TURMA, a.nome_aluno as ALUNO, m.espetaculo as ESPETÁCULO, m.cena as CENA, m.observacoes as OBSERVAÇÕES
        FROM alunos a JOIN matriculas m ON a.id = m.aluno_id 
        WHERE m.projeto=%s ORDER BY m.escola, m.turma, a.nome_aluno
    ''', params=(projeto_atual,))
    st.dataframe(df_resumo, use_container_width=True, hide_index=True)

elif menu == "Caderneta / Presença":
    st.title(f"📝 Caderneta Digital: {projeto_atual}")
    
    datas_db = ['25/07', '01/08', '12/09', '18/09', '22/09', '26/09', 'ENSAIO DE PALCO', '17/10', 'APRESENT.']
    datas_ui = ['25/07', '01/08', '12/09', '18/09', '22/09', '26/09', 'ENSAIO\nPALCO', '17/10', 'APRESENT.']
        
    colA, colB, colC = st.columns(3)
    if st.session_state['perfil'] == 'professor':
        prof_logado = st.session_state['nome_prof']
        st.info(f"👨‍🏫 Turmas do professor(a): **{prof_logado}**")
        escolas_do_prof = ler_sql("SELECT DISTINCT escola FROM turmas WHERE professor=%s AND projeto=%s", params=(prof_logado, projeto_atual))
        escolas_lista = escolas_do_prof['escola'].tolist() if not escolas_do_prof.empty else []
    else:
        escolas_lista = lista_escolas_limpa
        prof_logado = None
    
    with colA: esc_chamada = st.selectbox("1. Escola", ["Selecione..."] + escolas_lista)
    if esc_chamada != "Selecione...":
        if prof_logado: t_c = ler_sql("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s AND professor=%s", params=(esc_chamada, projeto_atual, prof_logado))
        else: t_c = ler_sql("SELECT nome_turma, professor FROM turmas WHERE escola=%s AND projeto=%s", params=(esc_chamada, projeto_atual))
        
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
                for _, row in edited_df.iterrows():
                    a_id, m_id = row['aluno_id'], row['matricula_id']
                    executar_sql("UPDATE matriculas SET espetaculo=%s, cena=%s, nota_qualitativa=%s WHERE id=%s", (safe_str(row.get('Espetáculo','')), safe_str(row.get('Cena','')), float(row.get('Qualitativo',0.0)), m_id))
                    for i in range(len(datas_db)):
                        val = row[datas_ui[i]]
                        p_val = 1 if val == "🟢 P" else (0 if val == "🔴 F" else -1)
                        executar_sql("INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (%s, %s, %s) ON CONFLICT (aluno_id, data_aula) DO UPDATE SET presente = EXCLUDED.presente", (a_id, datas_db[i], p_val))
                st.toast("✅ Salvo automaticamente!", icon="💾")

            st.markdown("---")
            with st.expander("🔒 Cofre de Observações Privadas (Invisível aos Alunos)"):
                aluno_obs_nome = st.selectbox("Selecione o Aluno para anotações:", ["Selecione..."] + df_alunos.index.tolist())
                if aluno_obs_nome != "Selecione...":
                    row_obs = df_alunos.loc[aluno_obs_nome]
                    nova_obs = st.text_area(f"Anotações para {aluno_obs_nome}:", value=row_obs['Observações'], height=120)
                    if st.button("💾 Guardar Anotação no Cofre", type="primary"):
                        executar_sql("UPDATE matriculas SET observacoes=%s WHERE id=%s", (nova_obs, row_obs['matricula_id']))
                        st.success("Anotação guardada com segurança!"); st.rerun()
